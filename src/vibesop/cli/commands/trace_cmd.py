"""Routing trace inspection commands.

Usage:
    vibe trace list                  List recent routing traces
    vibe trace show <trace_id>       Show full trace detail
    vibe trace clean [--keep N]      Remove old traces
"""

from __future__ import annotations

import json
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

    data = json.loads(trace_file.read_text())

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
