"""``vibe recall`` — task-memory recall CLI.

Recalls similar past traces by embedding cosine similarity. Searches
``.vibe/observability/spans.jsonl`` for spans within a configurable
look-back window, groups by ``task_id``, and returns the top-k matches
above an absolute cosine threshold.

Usage::

    vibe recall "<query>"                # default top-3, threshold 0.70, 30d
    vibe recall "<query>" -k 5           # top-5 matches
    vibe recall "<query>" -t 0.80        # stricter threshold
    vibe recall "<query>" --json         # JSON output for programmatic use
    vibe recall "<query>" --days 7       # restrict to last 7 days

Registered as a direct ``@app.command()`` on the main Typer app rather
than a nested sub-Typer — the nested form interpreted ``--json`` and
other options as subcommand names. Direct registration gives us a flat
``vibe recall [opts] <query>`` CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.observability.recall import recall_similar
from vibesop.core.observability.span_writer import SpanWriter

console = Console()


def recall_command(
    query: str = typer.Argument(..., help="Query to find similar past tasks for"),
    top_k: int = typer.Option(3, "--top-k", "-k", help="Max matches to return"),
    threshold: float = typer.Option(
        0.70, "--threshold", "-t", help="Min cosine similarity (default 0.70)"
    ),
    days: int = typer.Option(30, "--days", "-d", help="Look-back window in days"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
    span_file: Path | None = typer.Option(
        None, "--span-file", help="Override span file location"
    ),
    limit: int = typer.Option(
        5000, "--limit", help="Max spans to scan (newest first)"
    ),
) -> None:
    """Find past traces similar to ``query`` by embedding cosine similarity."""
    writer = SpanWriter(storage_path=span_file) if span_file else SpanWriter()
    spans = writer.query_recent(limit=limit)

    if not spans:
        _print_empty(query, json_output)
        return

    results = recall_similar(
        query=query,
        spans=spans,
        top_k=top_k,
        threshold=threshold,
        days=days,
    )

    if not results:
        _print_no_matches(query, threshold, json_output)
        return

    if json_output:
        payload = {
            "query": query,
            "threshold": threshold,
            "days": days,
            "total": len(results),
            "matches": [
                {
                    "task_id": r.task_id,
                    "similarity": round(r.similarity, 4),
                    "representative_query": r.representative_query,
                    "span_count": r.span_count,
                    "step_sequence": r.step_sequence,
                    "last_seen": r.last_seen,
                    "is_gold": r.is_gold,
                }
                for r in results
            ],
        }
        # Use print() not console.print() so ANSI codes never leak into JSON
        # output when stdout is a TTY (matches main.py route JSON pattern).
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    _render_results(query, results)


def register(app: typer.Typer) -> None:
    """Register the recall command on the given Typer app."""
    app.command(name="recall")(recall_command)


def _print_empty(query: str, json_output: bool) -> None:
    if json_output:
        print(json.dumps({"query": query, "total": 0, "matches": []}, ensure_ascii=False))
        return
    console.print()
    console.print(
        Panel(
            "[dim]No spans recorded yet.[/dim]\n\n"
            "Use [cyan]vibe route <query>[/cyan] to generate traces first.",
            title=f"Recall — {query[:60]}",
            border_style="dim",
        )
    )
    console.print()


def _print_no_matches(query: str, threshold: float, json_output: bool) -> None:
    if json_output:
        print(
            json.dumps(
                {"query": query, "threshold": threshold, "total": 0, "matches": []},
                ensure_ascii=False,
            )
        )
        return
    console.print()
    console.print(
        Panel(
            f"[dim]No matches above cosine {threshold:.2f}.[/dim]\n\n"
            "Try lowering threshold with [cyan]-t 0.60[/cyan] or "
            "expanding the window with [cyan]-d 90[/cyan].",
            title=f"Recall — {query[:60]}",
            border_style="yellow",
        )
    )
    console.print()


def _render_results(query: str, results: list) -> None:
    console.print()
    console.print(
        Panel(
            f"[bold]{len(results)}[/bold] match(es) for [cyan]{query[:80]}[/cyan]",
            title="Recall",
            border_style="cyan",
        )
    )

    # Hide Gold column when no result populates it (recall itself never sets
    # is_gold — it's a W3+ concern). Avoids a dead column confusing users.
    any_gold = any(r.is_gold for r in results)

    table = Table(show_header=True, header_style="bold")
    table.add_column("Sim", style="green", justify="right")
    table.add_column("Task ID", style="cyan")
    table.add_column("Query", max_width=40)
    table.add_column("Spans", justify="right")
    table.add_column("Last Seen", style="dim")
    if any_gold:
        table.add_column("Gold", justify="center")

    for r in results:
        sim_color = "green" if r.similarity >= 0.85 else "yellow" if r.similarity >= 0.75 else "red"
        row = [
            f"[{sim_color}]{r.similarity:.3f}[/{sim_color}]",
            r.task_id[:12],
            r.representative_query[:40],
            str(r.span_count),
            (r.last_seen or "-")[:10],
        ]
        if any_gold:
            row.append("★" if r.is_gold else "")
        table.add_row(*row)

    console.print(table)

    console.print()
    for i, r in enumerate(results, 1):
        console.print(
            f"[bold cyan]#{i}[/bold cyan] [dim]{r.task_id}[/dim] "
            f"[green]{r.similarity:.3f}[/green] "
            f"({'★ gold, ' if r.is_gold else ''}{r.span_count} spans)"
        )
        if r.step_sequence:
            preview = " → ".join(r.step_sequence[:6])
            suffix = (
                f" (+{len(r.step_sequence) - 6} more)"
                if len(r.step_sequence) > 6
                else ""
            )
            console.print(f"  [dim]steps:[/dim] {preview}{suffix}")
    console.print()
