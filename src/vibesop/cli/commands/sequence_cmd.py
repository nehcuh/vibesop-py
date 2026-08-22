"""``vibe sequence`` — tool-sequence capture & assembly (P3: distillation data source).

- ``vibe sequence record-tool``: called by the host agent's PostToolUse hook
  (Claude Code / Kimi CLI via ``vibesop-tool-seq.sh``; Grok Build via
  ``vibesop-tool-seq.json``, gate33); reads the hook event JSON from stdin —
  snake_case AND camelCase envelopes — and appends a minimal entry (tool name
  + timestamp + session id, never tool_input) to ``.vibe/tool_sequences.jsonl``.
- ``vibe sequence assemble``: fold new capture entries into instinct sequence
  patterns (application-only telemetry, success=False).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Tool-sequence capture for skill distillation (P3).",
    no_args_is_help=True,
)
console = Console()


def _sequences_enabled(project_root: Path) -> bool:
    """Read the ``sequences.enabled`` switch (default true).

    Same reading pattern as ``suggestions.enabled`` (env vars arrive as raw
    strings). Fail-open: a broken config must not silently disable capture.
    """
    try:
        from vibesop.core.config.manager import ConfigManager

        enabled = ConfigManager(project_root).get("sequences.enabled", True)
        if isinstance(enabled, str):  # env vars are returned as raw strings
            enabled = enabled.strip().lower() in ("true", "1", "yes", "on")
        return bool(enabled)
    except Exception:
        logger.debug("sequences.enabled lookup failed, defaulting to enabled", exc_info=True)
        return True


@app.command("record-tool")
def record_tool(
    project_root: Path | None = typer.Option(
        None, "--project-root", help="Project root (where .vibe/ lives). Defaults to cwd."
    ),
) -> None:
    """Record one host-agent PostToolUse hook event, read as JSON from stdin.

    Only the tool name, a local timestamp, and the session id are persisted —
    ``tool_input`` (paths, secrets) is NEVER written. Malformed input is
    dropped silently and the command always exits 0: a hook must never block
    the host agent.

    Project-root resolution when ``--project-root`` is absent (gate33 pi
    MAJOR-3): ``$GROK_WORKSPACE_ROOT`` / ``$CLAUDE_PROJECT_DIR`` env (both
    injected by the respective hosts around hook commands) → the payload's
    ``workspaceRoot``/``cwd`` (grok's envelope carries both) → process cwd.
    Without this, a hook fired from a non-project cwd would scatter captures
    into the wrong ``.vibe/`` (the gate15 lesson).
    """
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        try:
            root = _resolve_hook_project_root(project_root, payload)
            if _sequences_enabled(root):
                from vibesop.core.instinct.tool_sequences import record_tool_event

                record_tool_event(payload, root)
        except Exception:  # capture must never block the host agent
            logger.debug("tool-sequence record failed", exc_info=True)
    raise typer.Exit(0)


def _resolve_hook_project_root(flag: Path | None, payload: dict) -> Path:
    """Resolve where the capture lands: explicit flag → host env → payload → cwd."""
    import os

    if flag is not None:
        return flag
    for env_var in ("GROK_WORKSPACE_ROOT", "CLAUDE_PROJECT_DIR"):
        value = os.environ.get(env_var)
        if value and value.strip():
            return Path(value.strip())
    for key in ("workspaceRoot", "workspace_root", "cwd"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value.strip())
    return Path()


@app.command("assemble")
def assemble(
    project_root: Path = typer.Option(
        Path(), "--project-root", help="Project root (where .vibe/ lives). Defaults to cwd."
    ),
) -> None:
    """Fold captured tool sequences into instinct sequence patterns.

    Groups new entries (since the last assembly watermark) by session id —
    session-less entries fall back to 30-minute time windows — and records
    every group of ≥3 tool calls as application-only telemetry
    (``record_sequence(..., success=False)``).
    """
    from vibesop.core.instinct.tool_sequences import assemble_tool_sequences

    try:
        fed = assemble_tool_sequences(project_root)
    except Exception as e:
        console.print(f"[red]✗[/red] Assembly failed: {e}")
        raise typer.Exit(1) from None
    console.print(f"[green]✓[/green] Fed {fed} tool sequence(s) into instinct learning.")


@app.command("status")
def status(
    project_root: Path = typer.Option(
        Path(), "--project-root", help="Project root (where .vibe/ lives). Defaults to cwd."
    ),
) -> None:
    """Report capture liveness: last-capture age, file sizes, rotation state.

    The last-capture heartbeat (``.vibe/tool_sequences.last``, one
    epoch-seconds line) is written on every captured event — by the hook
    template (Claude Code / Kimi) or by ``record_tool_event`` itself on the
    Grok JSON-hook path (gate33); when it is missing we cannot distinguish
    "never captured" from "installed hook predates the liveness fix" — both
    are reported.
    """
    from vibesop.core.instinct.tool_sequences import (
        cursor_path,
        last_capture_path,
        rotated_path,
        sequences_path,
    )

    data = sequences_path(project_root)
    rotated = rotated_path(project_root)
    cursor = cursor_path(project_root)
    heartbeat = last_capture_path(project_root)

    # --- liveness heartbeat ---
    last_ts = _read_last_capture(heartbeat)
    if last_ts is None:
        console.print(
            f"[yellow]last-capture:[/yellow] 从未捕获或 hook 未更新（无 {heartbeat.name}）"
        )
    else:
        age = datetime.now(UTC) - last_ts
        style = "green" if age.days < 7 else "red"
        console.print(
            f"[{style}]last-capture:[/{style}] {last_ts.isoformat()} （{_format_age(age)}前）"
        )

    # --- capture log ---
    if data.exists():
        size = data.stat().st_size
        console.print(f"capture: {data} — {_format_bytes(size)}")
    else:
        size = 0
        console.print(f"capture: {data} — [dim]不存在[/dim]")

    # --- rotation ---
    if rotated.exists():
        console.print(f"rotation: {rotated} — {_format_bytes(rotated.stat().st_size)}")
    else:
        console.print("rotation: [dim]无（未发生轮转）[/dim]")

    # --- assembly watermark ---
    if cursor.exists():
        try:
            data_raw = json.loads(cursor.read_text(encoding="utf-8"))
            raw_offset = data_raw.get("offset", 0) if isinstance(data_raw, dict) else None
            # Non-dict JSON or wrong-typed offset = corrupt (gate16b claude
            # N2); mirror core._read_cursor's guards but keep the corrupt
            # warning distinct from "never assembled".
            offset = raw_offset if isinstance(raw_offset, int) else -1
        except (OSError, json.JSONDecodeError):
            offset = -1
        if offset < 0:
            console.print("assembly: [red]cursor 损坏[/red]")
        elif not data.exists():
            console.print(f"assembly: cursor offset={offset}（capture 文件不存在）")
        else:
            pending = max(size - offset, 0)
            state = "已装配到最新" if pending == 0 else f"待装配 {_format_bytes(pending)}"
            console.print(f"assembly: offset={offset}/{size} — {state}")
    else:
        console.print("assembly: [dim]无 cursor（从未装配）[/dim]")


def _read_last_capture(path: Path) -> datetime | None:
    """Parse the one-line epoch-seconds heartbeat; None when absent/broken."""
    try:
        raw = path.read_text(encoding="utf-8").splitlines()[0].strip()
        return datetime.fromtimestamp(float(raw), tz=UTC)
    except (OSError, IndexError, ValueError, OverflowError):
        return None


def _format_age(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 120:
        return f"{seconds} 秒"
    minutes = seconds // 60
    if minutes < 120:
        return f"{minutes} 分钟"
    hours = minutes // 60
    if hours < 72:
        return f"{hours} 小时"
    return f"{hours // 24} 天"


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


if __name__ == "__main__":
    app()
