"""Project pool CLI — manage trusted projects for cross-project recall.

W5.1 Task 3.1: lets users register multiple project paths so
``recall --cross-project`` and ``scan-candidates`` can aggregate spans
across them.

Storage: ``~/.vibe/pool.yaml`` (user-home, NOT per-project). User-home
because cross-project operations are by definition invoked from one
project directory but need to know about all the others.

Privacy: paths stay local. Never synced, never uploaded. One-time
notice printed on first ``vibe pool add``. The notice is versioned
(``.pool-privacy-ack.v1``) so a future W5.2 sync feature can bump the
version to force re-acknowledgement instead of silently grandfathering
existing users past new consent requirements.

YAML schema::

    projects:
      - path: /Users/me/Projects/vibesop-py
        alias: vibesop
        added_at: 2026-07-30T12:00:00+00:00
      - path: /Users/me/Projects/cmspark
        alias: cmspark
        added_at: 2026-07-30T12:01:00+00:00

Concurrency: ``add`` / ``remove`` take a cross-process lock during the
read-modify-write cycle (mirrors ``preference.py`` / ``reflection.py``).
Two shells running ``vibe pool add`` concurrently will not silently drop
each other's entries.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from ruamel.yaml import YAML

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="pool",
    help="Manage trusted projects for cross-project recall",
    no_args_is_help=False,
)
console = Console()

_DEFAULT_POOL_PATH = Path.home() / ".vibe" / "pool.yaml"
_PRIVACY_ACK_VERSION = "v1"


def _pool_path() -> Path:
    return _DEFAULT_POOL_PATH


def load_pool(path: Path | None = None) -> dict[str, Any]:
    """Load pool.yaml; return empty schema if missing or malformed.

    Public API — ``recall_cmd`` imports this to read pool entries for
    ``recall --cross-project``. The non-underscored name signals that
    cross-module callers are expected.
    """
    p = path or _pool_path()
    if not p.exists():
        return {"projects": []}
    try:
        yaml_parser = YAML()
        data = yaml_parser.load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:  # ruamel.yaml raises exotic subclasses; broaden
        logger.debug("Failed to read %s: %s", p, e)
        return {"projects": []}
    if not isinstance(data, dict):
        return {"projects": []}
    projects = data.get("projects") or []
    if not isinstance(projects, list):
        return {"projects": []}
    return {"projects": projects}


# Backwards-compat alias. New code should call ``load_pool``.
_load_pool = load_pool


def collect_pool_spans(
    *,
    limit: int,
    pool_path: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Union spans from every pool member's spans.jsonl (W5.2).

    For each pool entry, read ``<project_path>/.vibe/observability/spans.jsonl``
    via ``SpanWriter.query_recent`` and append to a flat list. Each span
    already carries its own ``project_id`` (set by tracer), so we don't
    tag here — callers that need alias mapping resolve it at render time
    via ``load_pool``.

    Returns ``(spans, aliases_with_data)``. The second value lets callers
    report how many pool members actually contributed (vs. missing files).

    Missing spans.jsonl or read errors are silently skipped (mirrors
    ``recall_cmd._run_cross_project`` behavior).

    Empty pool → returns ``([], [])``. The caller decides whether that's
    an error (cross-project scan: yes) or a no-op.
    """
    from vibesop.core.observability.span_writer import SpanWriter

    pool_data = load_pool(pool_path)
    projects = pool_data.get("projects") or []

    spans: list[dict[str, Any]] = []
    aliases_with_data: list[str] = []
    for entry in projects:
        alias = entry.get("alias", "?")
        project_path = Path(entry.get("path", ""))
        spans_file = project_path / ".vibe" / "observability" / "spans.jsonl"
        if not spans_file.exists():
            continue
        try:
            writer = SpanWriter(storage_path=spans_file)
            member_spans = writer.query_recent(limit=limit)
        except (OSError, ValueError) as e:
            logger.debug("Failed to read %s: %s", spans_file, e)
            continue
        if not member_spans:
            continue
        spans.extend(member_spans)
        aliases_with_data.append(alias)

    return spans, aliases_with_data


def _save_pool_locked(
    path: Path,
    mutator: Callable[[dict[str, Any]], None],
) -> None:
    """Acquire cross-process lock, re-read pool, apply mutator, write atomically.

    The mutator receives the latest data (read inside the lock) and mutates
    it in place. The result is written via ``atomic_writer.write_text``
    (temp + rename) so concurrent readers never see a half-written file.

    Mirrors the pattern in ``core/preference.py:_save_storage`` (P0-3 fix).
    """
    from vibesop.utils.atomic_writer import write_text
    from vibesop.utils.file_lock import cross_process_lock

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with cross_process_lock(lock_path):
        # Re-read under lock so we don't clobber a concurrent writer.
        data = load_pool(path)
        mutator(data)
        yaml_parser = YAML()
        yaml_parser.default_flow_style = False
        import io

        buf = io.StringIO()
        yaml_parser.dump(data, buf)
        write_text(path, buf.getvalue())


def _resolve_path(path_arg: str) -> Path:
    """Resolve user-provided path argument to absolute, resolved form.

    Matches SpanWriter._path and process_identity canonical form (symlinks
    resolved) so Phase 3 cross-project recall can match project_id against
    pool entries without canonical-disagreement false negatives.
    """
    return Path(path_arg).expanduser().resolve()


def _maybe_print_privacy_notice(pool_path: Path) -> None:
    """First-add notice that pool paths stay local. Idempotent across runs.

    The marker is versioned (``.pool-privacy-ack.v1``) so a future W5.2
    feature that changes the privacy posture (e.g., adds remote sync) can
    bump to ``.v2`` and force users to re-acknowledge instead of being
    silently grandfathered past the new consent gate.
    """
    notice_marker = pool_path.parent / f".pool-privacy-ack.{_PRIVACY_ACK_VERSION}"
    if notice_marker.exists():
        return
    console.print(
        "[dim]Privacy: project paths are stored locally at "
        f"{pool_path} and never synced.[/dim]"
    )
    try:
        notice_marker.parent.mkdir(parents=True, exist_ok=True)
        notice_marker.touch()
    except OSError:
        pass


def _find_entry(
    data: dict[str, Any], alias_or_path: str
) -> tuple[int, dict[str, Any]] | None:
    """Find pool entry by alias OR path; return (index, entry) or None."""
    projects = data.get("projects") or []
    # Skip path resolution for pure-alias inputs (typical case) to avoid
    # wasting a syscall and creating misleading cwd-relative Paths.
    target_path: Path | None = None
    for i, entry in enumerate(projects):
        if not isinstance(entry, dict):
            continue
        if entry.get("alias") == alias_or_path:
            return i, entry
        entry_path = entry.get("path")
        if entry_path:
            if target_path is None:
                try:
                    target_path = _resolve_path(alias_or_path)
                except (OSError, ValueError):
                    return None
            try:
                if Path(entry_path).resolve() == target_path:
                    return i, entry
            except (OSError, ValueError):
                continue
    return None


@app.callback(invoke_without_command=True)
def _pool_overview(ctx: typer.Context) -> None:  # pyright: ignore[reportUnusedFunction]
    if ctx.invoked_subcommand is not None:
        return

    data = load_pool()
    projects = data.get("projects") or []

    console.rule("[bold cyan]Project Pool[/bold cyan]")
    console.print()
    console.print(f"  [bold]{len(projects)}[/bold] project(s) registered")
    console.print()
    console.print("[dim]Quick actions:[/dim]")
    console.print("  [cyan]vibe pool add <path>[/cyan]     [dim]— register a project[/dim]")
    console.print("  [cyan]vibe pool list[/cyan]           [dim]— show table[/dim]")
    console.print("  [cyan]vibe pool remove <alias>[/cyan] [dim]— unregister[/dim]")
    console.print("  [cyan]vibe pool status[/cyan]         [dim]— summary[/dim]")
    console.print()


@app.command()
def add(
    path: str = typer.Argument(..., help="Project path (absolute or relative)"),
    alias: str | None = typer.Option(
        None, "--alias", "-a", help="Short name for the project (defaults to dir name)"
    ),
) -> None:
    """Register a project in the pool. Idempotent on path."""
    pool_path = _pool_path()
    resolved = _resolve_path(path)

    if not resolved.exists():
        console.print(f"[red]✗ Path does not exist: {resolved}[/red]")
        raise typer.Exit(1)
    if not resolved.is_dir():
        console.print(f"[red]✗ Path is not a directory: {resolved}[/red]")
        raise typer.Exit(1)

    chosen_alias = alias or resolved.name

    # Print privacy notice OUTSIDE the lock (console I/O shouldn't block
    # other writers). Idempotent — only fires once per install.
    _maybe_print_privacy_notice(pool_path)

    # Outcome is captured by the mutator so the caller can print the right
    # message. Boxed in a list so the closure can reassign.
    outcome: list[str] = []

    def _mutate(data: dict[str, Any]) -> None:
        existing = _find_entry(data, str(resolved))
        if existing is not None:
            idx, entry = existing
            if entry.get("alias") == chosen_alias:
                outcome.append("idempotent")
                return
            # Alias update: verify no collision.
            for j, other in enumerate(data["projects"]):
                if j != idx and other.get("alias") == chosen_alias:
                    raise _AliasCollision(chosen_alias, other.get("path", ""))
            entry["alias"] = chosen_alias
            outcome.append("updated")
            return
        # New entry: verify alias unique.
        for other in data["projects"]:
            if other.get("alias") == chosen_alias:
                raise _AliasCollision(chosen_alias, other.get("path", ""))
        data["projects"].append(
            {
                "path": str(resolved),
                "alias": chosen_alias,
                "added_at": datetime.now(UTC).isoformat(),
            }
        )
        outcome.append("added")

    try:
        _save_pool_locked(pool_path, _mutate)
    except _AliasCollision as exc:
        console.print(
            f"[red]✗ Alias '{exc.alias}' already in use by {exc.existing_path}[/red]"
        )
        raise typer.Exit(1) from exc

    if not outcome:
        # Shouldn't happen — mutator always appends. Defensive default.
        outcome.append("added")
    kind = outcome[0]
    if kind == "idempotent":
        console.print(
            f"[dim]Already registered: {resolved} (alias: {chosen_alias})[/dim]"
        )
    elif kind == "updated":
        console.print(f"[green]✓ Updated alias:[/green] {chosen_alias} → {resolved}")
    else:
        console.print(f"[green]✓ Added:[/green] {chosen_alias} → {resolved}")


class _AliasCollision(Exception):
    """Internal control-flow signal — raised inside lock, caught outside."""

    def __init__(self, alias: str, existing_path: str) -> None:
        super().__init__(alias)
        self.alias = alias
        self.existing_path = existing_path


@app.command()
def remove(
    alias_or_path: str = typer.Argument(..., help="Alias or path to remove"),
) -> None:
    """Remove a project from the pool. Silent if absent."""
    pool_path = _pool_path()

    removed: list[dict[str, Any]] = []

    def _mutate(data: dict[str, Any]) -> None:
        found = _find_entry(data, alias_or_path)
        if found is None:
            return
        idx, _entry = found
        removed.append(data["projects"].pop(idx))

    _save_pool_locked(pool_path, _mutate)

    if not removed:
        console.print(f"[dim]Not in pool: {alias_or_path}[/dim]")
        return
    entry = removed[0]
    console.print(f"[green]✓ Removed:[/green] {entry.get('alias')} ({entry.get('path')})")


@app.command(name="list")
def list_cmd() -> None:
    """Show pool as a table."""
    data = load_pool()
    projects = data.get("projects") or []
    if not projects:
        console.print("[dim]Pool is empty. Add with: vibe pool add <path>[/dim]")
        return

    table = Table(title="Project Pool")
    table.add_column("Alias", style="cyan", no_wrap=True)
    table.add_column("Path", style="white")
    table.add_column("Spans", justify="right", style="yellow")
    table.add_column("Added", style="dim")

    for entry in projects:
        path = Path(entry.get("path", ""))
        span_count = _count_spans(path)
        added = entry.get("added_at", "")
        if added:
            with contextlib.suppress(ValueError):
                added = datetime.fromisoformat(added).strftime("%Y-%m-%d")
        table.add_row(entry.get("alias", ""), str(path), str(span_count), added)

    console.print(table)


def _count_spans(project_path: Path) -> int:
    """Best-effort count of spans for a project. Returns 0 on any error."""
    spans_file = project_path / ".vibe" / "observability" / "spans.jsonl"
    if not spans_file.exists():
        return 0
    try:
        with spans_file.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


@app.command()
def status() -> None:
    """Summary: count + last modification."""
    pool_path = _pool_path()
    if not pool_path.exists():
        console.print("[dim]No pool file yet. Add with: vibe pool add <path>[/dim]")
        return

    data = load_pool(pool_path)
    projects = data.get("projects") or []

    console.rule("[bold cyan]Pool Status[/bold cyan]")
    console.print(f"  Pool file: [dim]{pool_path}[/dim]")
    console.print(f"  Projects:  [bold]{len(projects)}[/bold]")

    if projects:
        total_spans = sum(_count_spans(Path(p.get("path", ""))) for p in projects)
        console.print(f"  Total spans across pool: [bold]{total_spans}[/bold]")

    try:
        mtime = datetime.fromtimestamp(pool_path.stat().st_mtime, tz=UTC)
        console.print(f"  Last modified: [dim]{mtime.isoformat()}[/dim]")
    except OSError:
        pass
    console.print()
