"""Routing trace inspection commands.

Usage:
    vibe trace list                  List recent routing traces
    vibe trace show <trace_id>       Show full trace detail
    vibe trace clean [--keep N]      Remove old traces (legacy .vibe/traces/*.json)
    vibe trace replay [--trace-id ID] [--span-file PATH]
                                     Replay agent-internal spans
                                     (.vibe/observability/spans.jsonl)
                                     grouped by trace_id, showing the
                                     task → llm → tool_call tree.
    vibe trace metrics <skill_id>    Aggregate metrics for a skill from
                                     spans.jsonl (closes GAP-3 by
                                     consuming SpanAggregator).
    vibe trace prune [--days N]      Prune old spans from spans.jsonl by age.
                                     Writes atomically (temp + rename) so a
                                     crash mid-prune cannot corrupt the file.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.routing.tracer import RoutingTracer

app = typer.Typer(name="trace", help="Inspect routing traces", no_args_is_help=True)
console = Console()


@app.callback(invoke_without_command=True)
def _trace_overview(ctx: typer.Context) -> None:  # pyright: ignore[reportUnusedFunction]
    """Show trace overview."""
    if ctx.invoked_subcommand is not None:
        return
    list_traces(limit=10)


@app.command()
def list_traces(
    limit: int = typer.Option(20, "--limit", "-n", help="Max traces to show"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """List recent routing traces from .vibe/traces/."""
    tracer = RoutingTracer(traces_dir=Path.cwd() / ".vibe" / "traces")
    traces = tracer.list_traces(limit=limit)

    if not traces:
        console.print()
        console.print(
            Panel(
                "[dim]No routing traces yet.[/dim]\n\n"
                "Use [cyan]vibe route --trace <query>[/cyan] to generate one.",
                title="Routing Traces",
                border_style="dim",
            )
        )
        console.print()
        return

    if json_output:
        console.print(json.dumps(traces, indent=2, ensure_ascii=False, default=str))
        return

    table = Table(title="Routing Traces", show_header=True)
    table.add_column("Trace ID", style="cyan")
    table.add_column("Time", style="dim")
    table.add_column("Query", max_width=50)
    table.add_column("Result", style="bold")
    table.add_column("Conf", justify="right")
    table.add_column("Layers", justify="center")

    for t in traces:
        ts = t.get("timestamp", "")
        time_str = ts[11:19] if len(ts) > 19 else ts[:8]
        confidence = t.get("confidence", 0)
        conf_style = "green" if confidence >= 0.7 else "yellow" if confidence >= 0.4 else "red"

        table.add_row(
            t.get("trace_id", "")[:12],
            time_str,
            t.get("query", "")[:50],
            t.get("final_skill", "-") or "-",
            f"[{conf_style}]{confidence:.0%}[/{conf_style}]",
            str(t.get("layer_count", 0)),
        )

    console.print()
    console.print(table)
    console.print()
    console.print(
        f"[dim]{len(traces)} traces shown. View details:[/dim] [cyan]vibe trace show <id>[/cyan]"
    )
    console.print()


@app.command()
def show(
    trace_id: str = typer.Argument(..., help="Trace ID or prefix"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show full detail of a routing trace."""
    traces_dir = Path.cwd() / ".vibe" / "traces"

    # Support partial ID matching
    if not trace_id.endswith(".json"):
        matches = list(traces_dir.glob(f"{trace_id}*.json"))
        if not matches:
            console.print(f"[red]No trace found with ID: {trace_id}[/red]")
            raise typer.Exit(1)
        trace_file = matches[0]
    else:
        trace_file = traces_dir / trace_id

    if not trace_file.exists():
        console.print(f"[red]Trace file not found: {trace_file}[/red]")
        raise typer.Exit(1)

    data = json.loads(trace_file.read_text(encoding="utf-8"))

    if json_output:
        console.print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    console.rule(f"[bold cyan]Routing Trace: {data.get('trace_id', '')}[/bold cyan]")
    console.print()

    console.print(f"  [bold]Query:[/bold] {data.get('query', '')}")
    console.print(f"  [bold]Time:[/bold] {data.get('timestamp', '')}")
    console.print(f"  [bold]Duration:[/bold] {data.get('total_duration_ms', 0):.1f}ms")
    console.print(f"  [bold]Mode:[/bold] {data.get('mode', 'single')}")

    final = data.get("final", {})
    if final.get("skill_id"):
        final_style = (
            "green"
            if final.get("confidence", 0) >= 0.7
            else "yellow"
            if final.get("confidence", 0) >= 0.4
            else "red"
        )
        console.print(
            f"  [bold]Result:[/bold] [{final_style}]{final['skill_id']} "
            f"({final.get('confidence', 0):.0%})[/{final_style}] "
            f"via [dim]{final.get('layer', '-')}[/dim]"
        )
    else:
        console.print("  [bold]Result:[/bold] [red]No match[/red]")

    console.print()
    console.print("[bold]Layer Decision Tree:[/bold]")
    console.print()

    layers = data.get("layers", [])
    layer_table = Table(show_header=True, box=None)
    layer_table.add_column("Layer", justify="right", style="dim")
    layer_table.add_column("Stage", style="bold")
    layer_table.add_column("Matched?", justify="center")
    layer_table.add_column("Skill", style="cyan")
    layer_table.add_column("Conf", justify="right")
    layer_table.add_column("Ms", justify="right", style="dim")
    layer_table.add_column("Rejected", justify="center")

    for lt in layers:
        matched = "✓" if lt.get("matched") else "✗"
        matched_style = "green" if lt.get("matched") else "red"
        skill = lt.get("matched_skill") or "-"
        conf = lt.get("confidence", 0)
        dms = lt.get("duration_ms", 0)
        n_rej = len(lt.get("rejected", []))

        layer_table.add_row(
            f"#{lt.get('layer_number', '?')}",
            lt.get("layer", ""),
            f"[{matched_style}]{matched}[/{matched_style}]",
            skill[:30],
            f"{conf:.0%}" if lt.get("matched") else "-",
            f"{dms:.1f}",
            f"[dim]{n_rej}[/dim]" if n_rej > 0 else "-",
        )

    console.print(layer_table)

    # Show rejected candidates with reasons
    all_rejected = []
    for lt in layers:
        for r in lt.get("rejected", []):
            r["_from_layer"] = lt.get("layer", "")
            all_rejected.append(r)

    if all_rejected:
        console.print()
        console.print("[bold]Rejected Candidates:[/bold]")
        rej_table = Table(show_header=True, box=None)
        rej_table.add_column("Skill", style="yellow")
        rej_table.add_column("Conf", justify="right")
        rej_table.add_column("Layer", style="dim")
        rej_table.add_column("Reason", max_width=50)

        for r in all_rejected[:15]:
            rej_table.add_row(
                r.get("skill_id", "")[:30],
                f"{r.get('confidence', 0):.0%}",
                r.get("_from_layer", ""),
                r.get("reason", "")[:50],
            )

        console.print(rej_table)

    console.print()
    console.print(
        "[dim]Tip: use [cyan]vibe route --trace <query>[/cyan] for future traces. "
        "Inspired by SkillTree's routing trace mode.[/dim]"
    )
    console.print()


@app.command()
def clean(
    keep: int = typer.Option(10, "--keep", "-k", help="Number of recent traces to keep"),
) -> None:
    """Remove old routing traces, keeping the most recent ones."""
    traces_dir = Path.cwd() / ".vibe" / "traces"

    if not traces_dir.exists():
        console.print("[dim]No traces directory found.[/dim]")
        return

    files = sorted(
        traces_dir.glob("*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    if len(files) <= keep:
        console.print(f"[dim]Only {len(files)} traces — nothing to clean.[/dim]")
        return

    removed = 0
    for f in files[keep:]:
        f.unlink()
        removed += 1

    console.print(
        f"[green]Removed {removed} old trace(s).[/green] [dim]{keep} most recent kept.[/dim]"
    )


def _decode_span_field(record: dict, key: str) -> dict:
    """SpanWriter persists metadata / input_data / output_data as JSON strings.
    Decode back to dict when present."""
    val = record.get(key)
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return val if isinstance(val, dict) else {}


def _load_spans(span_file: Path) -> list[dict]:
    if not span_file.exists():
        return []
    spans: list[dict] = []
    with span_file.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            record["metadata"] = _decode_span_field(record, "metadata")
            spans.append(record)
    return spans


def _group_by_trace(spans: list[dict]) -> dict[str, list[dict]]:
    """Group spans by trace_id. Returns trace_id → sorted list of spans.

    Spans with empty/missing trace_id (true orphans, e.g. llm-spans emitted
    with no active trace context) are skipped — they cannot be grouped
    meaningfully and would otherwise merge into a single bogus "" trace.
    """
    traces: dict[str, list[dict]] = {}
    orphan_count = 0
    for s in spans:
        tid = s.get("trace_id", "")
        if not tid:
            orphan_count += 1
            continue
        traces.setdefault(tid, []).append(s)
    for _tid, tlist in traces.items():
        tlist.sort(key=lambda s: (s.get("started_at", ""), s.get("id", "")))
    if orphan_count:
        console.print(f"[yellow]Skipped {orphan_count} span(s) with no trace_id (cannot group).[/]")
    return traces


def _format_cost(cost_usd: float | None) -> str:
    if cost_usd is None:
        return "-"
    if cost_usd == 0:
        return "$0.00"
    if cost_usd < 0.01:
        return f"${cost_usd:.4f}"
    return f"${cost_usd:.2f}"


def _render_trace_tree(trace_id: str, spans: list[dict]) -> None:
    """Print a single trace's spans as an indented tree based on parent_span_id.

    Handles three span categories:
    * Roots (``parent_span_id`` empty/None) — rendered at depth 0
    * Mid-tree spans whose parent exists — rendered nested under parent
    * Orphans whose ``parent_span_id`` points to a missing span — rendered at
      depth 0 with a [yellow]ORPHAN[/] marker so users see data wasn't dropped
    """
    console.print()
    console.rule(f"[bold cyan]Trace {trace_id}[/bold cyan]")

    by_id = {s.get("id", ""): s for s in spans if s.get("id")}
    ids_present = set(by_id.keys())

    # Build children index O(n) — replaces O(n²) repeated filter
    children_by_parent: dict[str, list[dict]] = {}
    roots: list[dict] = []
    orphans: list[dict] = []  # parent_span_id set, but parent not in this trace
    for s in spans:
        parent = s.get("parent_span_id")
        if not parent:
            roots.append(s)
        elif parent in ids_present:
            children_by_parent.setdefault(parent, []).append(s)
        else:
            orphans.append(s)

    if not roots and not orphans:
        # No roots but spans exist — shouldn't happen, but defensive
        roots = spans

    kind_icons = {
        "task": "T",
        "llm": "L",
        "tool_call": "X",
        "file_edit": "F",
        "workflow_node": "W",
    }

    def render(span: dict, depth: int, is_orphan: bool = False) -> None:
        indent = "  " * depth
        icon = kind_icons.get(span.get("span_kind", ""), "?")
        name = (span.get("name", "") or "?")[:60]
        status = span.get("status", "?")
        status_color = "green" if status == "ok" else "red" if status == "error" else "yellow"
        dur = span.get("duration_ms")
        # Treat None as unknown; 0 is a valid sub-millisecond duration
        dur_str = f"{dur}ms" if dur is not None else "-"
        tokens_in = span.get("tokens_input", 0)
        tokens_out = span.get("tokens_output", 0)
        token_str = f" [{tokens_in}+{tokens_out} tok]" if (tokens_in or tokens_out) else ""
        cost = _format_cost(span.get("cost_usd"))
        meta = span.get("metadata") or {}
        skill = meta.get("skill_id") if isinstance(meta, dict) else None
        skill_str = f" [dim]skill={skill}[/dim]" if skill else ""
        orphan_marker = " [yellow]ORPHAN[/] " if is_orphan else " "

        console.print(
            f"  {indent}[bold]{icon}[/bold] [{status_color}]{status}[/{status_color}]"
            f"{orphan_marker}[cyan]{name}[/cyan] "
            f"[dim]{dur_str}{token_str} {cost}[/dim]{skill_str}"
        )

        # Children — O(1) via prebuilt index
        for child in children_by_parent.get(span.get("id", ""), []):
            render(child, depth + 1)

    for root in roots:
        render(root, 0)
    for orphan in orphans:
        render(orphan, 0, is_orphan=True)

    # Summary
    llm_count = sum(1 for s in spans if s.get("span_kind") == "llm")
    tool_count = sum(1 for s in spans if s.get("span_kind") == "tool_call")
    total_cost = sum((s.get("cost_usd") or 0) for s in spans)
    total_tokens = sum(s.get("tokens_input", 0) + s.get("tokens_output", 0) for s in spans)

    console.print()
    summary_parts = [
        f"Spans: {len(spans)} (LLM: {llm_count}, Tool: {tool_count})",
        f"Tokens: {total_tokens}",
        f"Cost: {_format_cost(total_cost)}",
    ]
    if orphans:
        summary_parts.append(f"[yellow]Orphans: {len(orphans)}[/]")
    console.print(f"  [dim]{' | '.join(summary_parts)}[/dim]")


@app.command()
def replay(
    trace_id: str = typer.Option(
        None, "--trace-id", "-t", help="Show only this trace ID (or prefix)"
    ),
    span_file: Path = typer.Option(
        None,
        "--span-file",
        "-f",
        help="Span JSONL file (default: .vibe/observability/spans.jsonl)",
    ),
    limit: int = typer.Option(10, "--limit", "-n", help="Max traces to display"),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output as JSON (one object per trace)"
    ),
) -> None:
    """Replay agent-internal spans grouped by trace_id.

    Reads `.vibe/observability/spans.jsonl` (written by SpanWriter +
    SpanWrappedProvider) and renders each trace as a tree showing the
    task → llm → tool_call hierarchy with status, duration, tokens, and cost.
    """
    span_path = span_file or (Path.cwd() / ".vibe" / "observability" / "spans.jsonl")
    if not span_path.exists():
        console.print(
            Panel(
                f"[dim]Span file not found:[/dim] [cyan]{span_path}[/cyan]\n\n"
                "Spans are emitted automatically once v8.2 GAP-1 wraps the LLM\n"
                "provider factory. Run [cyan]vibe route <query>[/cyan] in a hook-enabled\n"
                "session to generate spans.",
                title="No Span Data",
                border_style="dim",
            )
        )
        return

    spans = _load_spans(span_path)
    if not spans:
        console.print(f"[dim]No spans found in {span_path}[/dim]")
        return

    traces = _group_by_trace(spans)

    # Filter by trace_id prefix if provided
    if trace_id:
        traces = {tid: tlist for tid, tlist in traces.items() if tid.startswith(trace_id)}
        if not traces:
            console.print(f"[red]No trace found matching: {trace_id}[/red]")
            raise typer.Exit(1)

    # Limit to most recent N traces (sort by first span's started_at)
    sorted_traces = sorted(
        traces.items(),
        key=lambda kv: kv[1][0].get("started_at", "") if kv[1] else "",
        reverse=True,
    )
    sorted_traces = sorted_traces[:limit]

    if json_output:
        out = [{"trace_id": tid, "spans": tlist} for tid, tlist in sorted_traces]
        console.print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return

    console.print()
    console.print(
        f"[bold]Replay: {len(sorted_traces)} trace(s)[/bold] "
        f"[dim]from {span_path} ({len(spans)} spans total)[/dim]"
    )

    for tid, tlist in sorted_traces:
        _render_trace_tree(tid, tlist)

    console.print()


@app.command()
def metrics(
    skill_id: str = typer.Argument(..., help="Skill ID to aggregate metrics for"),
    window_hours: int = typer.Option(24, "--window", "-w", help="Lookback window in hours"),
    span_file: Path = typer.Option(
        None,
        "--span-file",
        "-f",
        help="Span JSONL file (default: .vibe/observability/spans.jsonl)",
    ),
    project_id: str = typer.Option(
        None, "--project-id", help="Filter spans by project_id (default: any)"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show aggregated metrics for a skill from agent-internal spans.

    Closes the v8.2 GAP-3 by consuming SpanAggregator — makes the
    ``get_skill_metrics`` API reachable from the CLI (not just importable).
    """
    from vibesop.core.observability.aggregator import SpanAggregator

    span_path = span_file or (Path.cwd() / ".vibe" / "observability" / "spans.jsonl")
    if not span_path.exists():
        console.print(
            Panel(
                f"[dim]Span file not found:[/dim] [cyan]{span_path}[/cyan]\n\n"
                "Generate spans by running [cyan]vibe route <query>[/cyan] in a\n"
                "hook-enabled session.",
                title="No Span Data",
                border_style="dim",
            )
        )
        return

    agg = SpanAggregator(spans_path=span_path)
    m = agg.get_skill_metrics(
        skill_id,
        window_hours=window_hours,
        use_analytics_fallback=False,
        project_id=project_id,
    )

    if json_output:
        console.print(
            json.dumps(
                {
                    "skill_id": m.skill_id,
                    "source": m.source,
                    "window_hours": m.window_hours,
                    "total_executions": m.total_executions,
                    "success_count": m.success_count,
                    "success_rate": m.success_rate,
                    "avg_duration_ms": m.avg_duration_ms,
                    "avg_tokens": m.avg_tokens,
                    "llm_call_count": m.llm_call_count,
                    "llm_success_rate": m.llm_success_rate,
                    "total_cost_usd": m.total_cost_usd,
                    "avg_cost_usd": m.avg_cost_usd,
                    "cost_usd_per_execution": m.cost_usd_per_execution,
                    "tool_call_distribution": m.tool_call_distribution,
                    "top_errors": m.top_errors,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if m.source == "none":
        console.print(
            f"[yellow]No span data for skill '{skill_id}' in last {window_hours}h.[/yellow]\n"
            f"[dim]Looked in: {span_path}[/dim]"
        )
        return

    console.print()
    console.rule(f"[bold cyan]Metrics: {skill_id}[/bold cyan]")
    console.print(f"  [bold]Source:[/bold] {m.source} | [bold]Window:[/bold] {m.window_hours}h")
    console.print(
        f"  [bold]Executions:[/bold] {m.total_executions} (success: {m.success_count}, rate: {m.success_rate:.0%})"
    )
    console.print(f"  [bold]Avg duration:[/bold] {m.avg_duration_ms:.0f}ms")
    console.print(
        f"  [bold]LLM calls:[/bold] {m.llm_call_count} (success rate: {m.llm_success_rate:.0%})"
    )
    console.print(f"  [bold]Avg tokens:[/bold] {m.avg_tokens}")
    console.print(
        f"  [bold]Cost:[/bold] total ${m.total_cost_usd:.4f} | avg/exec ${m.avg_cost_usd:.4f}"
    )

    if m.tool_call_distribution:
        console.print()
        console.print("[bold]Tool call distribution:[/bold]")
        for tool, count in sorted(m.tool_call_distribution.items(), key=lambda x: -x[1]):
            console.print(f"  [dim]•[/dim] {tool}: {count}")

    if m.top_errors:
        console.print()
        console.print("[bold red]Top errors:[/bold red]")
        for err in m.top_errors:
            console.print(f"  [dim]•[/dim] {err}")

    console.print()


@app.command()
def prune(
    days: int = typer.Option(
        30,
        "--days",
        "-d",
        help="Remove spans whose started_at is older than N days (default: 30).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be pruned without writing."
    ),
    span_file: Path = typer.Option(
        Path(".vibe/observability/spans.jsonl"),
        "--span-file",
        help="Span JSONL file to prune (default: .vibe/observability/spans.jsonl).",
    ),
) -> None:
    """Prune old spans from spans.jsonl by age (closes v8.2 P2 §24.5 #5).

    Reads the span file, filters out spans older than ``--days``, writes
    the surviving spans back atomically (temp file + rename). Use
    ``--dry-run`` to preview without modifying.

    Spans without a parseable ``started_at`` are kept (defensive — never
    silently drop data we can't reason about).
    """
    from datetime import UTC, datetime, timedelta

    if not span_file.exists():
        console.print(f"[dim]Span file not found: {span_file}[/dim]")
        return

    cutoff = datetime.now(UTC) - timedelta(days=days)

    kept: list[str] = []
    pruned = 0
    unparseable = 0
    total = 0

    with span_file.open("r", encoding="utf-8") as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue
            total += 1
            try:
                record = json.loads(stripped)
                started_at = record.get("started_at")
                if not started_at:
                    unparseable += 1
                    kept.append(stripped)
                    continue
                # Tolerate both ISO-with-tz and ISO-without-tz.
                # SpanWriter always writes timezone-aware ISO, but be defensive.
                ts = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                if ts < cutoff:
                    pruned += 1
                    continue
                kept.append(stripped)
            except (json.JSONDecodeError, ValueError, TypeError):
                unparseable += 1
                kept.append(stripped)

    console.print(
        f"[dim]Total: {total} spans | would prune: {pruned} | "
        f"keep: {len(kept)} (incl. {unparseable} unparseable)[/dim]"
    )

    if dry_run:
        console.print("[yellow]Dry-run mode — no changes written.[/yellow]")
        return

    if pruned == 0:
        console.print("[dim]Nothing to prune.[/dim]")
        return

    # Atomic write: temp file + rename. A crash mid-write leaves the
    # original spans.jsonl intact and the .tmp file orphaned (recoverable).
    # Use mkstemp (not a fixed ``<file>.tmp`` name) so two concurrent prune
    # runs — manual + cron, or two terminals — don't interleave writes into
    # the same temp file (which would corrupt the output as the UNION of
    # both survivors). Reviewer flag (kimi §5, pi §5a).
    import tempfile

    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=span_file.name + ".", suffix=".tmp", dir=span_file.parent
    )
    tmp_file = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            for line in kept:
                f.write(line + "\n")
        tmp_file.replace(span_file)
    except Exception as e:
        # Best-effort cleanup of orphaned temp file
        with contextlib.suppress(Exception):
            tmp_file.unlink(missing_ok=True)
        console.print(f"[red]Failed to prune: {e}[/red]")
        raise typer.Exit(1) from e

    console.print(
        f"[green]Pruned {pruned} span(s) older than {days} day(s).[/green] "
        f"[dim]Kept {len(kept)} in {span_file}.[/dim]"
    )
