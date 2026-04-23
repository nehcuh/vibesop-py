"""Rich decision tree renderer for routing transparency.

Renders a human-readable routing decision report from RoutingResult.layer_details.
"""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from typing import Any

from vibesop.core.models import RoutingLayer, RoutingResult


def render_routing_report(result: RoutingResult, console: Console | None = None) -> None:
    """Render a full routing decision report to the console."""
    if console is None:
        console = Console()

    # Header panel
    header_text = f"[bold]Query:[/bold] {result.query}\n"
    if result.primary:
        if result.primary.layer == RoutingLayer.FALLBACK_LLM:
            header_text += (
                f"[bold yellow]🤖 Fallback Mode:[/bold yellow] {result.primary.skill_id} "
                f"(no skill matched)\n"
            )
        else:
            header_text += (
                f"[bold green]Selected:[/bold green] {result.primary.skill_id} "
                f"(confidence: {result.primary.confidence:.0%})\n"
            )
    else:
        header_text += "[yellow]No match found[/yellow]\n"

    header_text += f"[dim]Total duration:[/dim] {result.duration_ms:.1f}ms"

    console.print(
        Panel(
            header_text,
            title="[bold cyan]🔍 Routing Decision Report[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    if not result.layer_details:
        console.print("[dim]No layer details available.[/dim]")
        return

    # Layer details tree
    tree = Tree("[bold]Layer Execution[/bold]")
    for detail in result.layer_details:
        icon = "✅" if detail.matched else "❌"
        layer_label = f"{icon} {detail.layer.value.upper()}"
        if detail.duration_ms > 0:
            layer_label += f" [dim]({detail.duration_ms:.1f}ms)[/dim]"

        node = tree.add(f"[bold]{layer_label}[/bold]")
        if detail.reason:
            node.add(f"[dim]{detail.reason}[/dim]")

        # Show diagnostics if any
        if detail.diagnostics:
            for key, value in detail.diagnostics.items():
                if key in ("cleaned_query", "scenario", "model"):
                    node.add(f"[dim]  • {key}:[/dim] {value}")

    console.print(tree)

    # Rejected candidates (near-misses) per layer
    rejected_by_layer: dict[str, list[Any]] = {}
    for detail in result.layer_details:
        if detail.rejected_candidates:
            rejected_by_layer[detail.layer.value] = detail.rejected_candidates

    if rejected_by_layer:
        console.print()
        rej_table = Table(title="Near-Miss Candidates (Rejected)", box=box.SIMPLE)
        rej_table.add_column("Layer", style="dim")
        rej_table.add_column("Skill ID", style="bold")
        rej_table.add_column("Confidence", justify="right")
        rej_table.add_column("Reason", style="dim")

        for layer_val, cands in rejected_by_layer.items():
            for c in cands[:3]:
                rej_table.add_row(
                    layer_val.upper(),
                    c.skill_id,
                    f"{c.confidence:.0%}",
                    c.reason or "—",
                )
        console.print(rej_table)
        console.print("[dim]These candidates were close but didn't meet the confidence threshold.[/dim]")

    # Alternatives table
    if result.alternatives:
        alt_table = Table(title="Alternative Skills", box=box.SIMPLE)
        alt_table.add_column("Rank", style="dim", justify="right")
        alt_table.add_column("Skill ID", style="bold")
        alt_table.add_column("Description", style="dim")
        alt_table.add_column("Confidence", justify="right")
        alt_table.add_column("Layer", style="dim")

        for i, alt in enumerate(result.alternatives[:5], 1):
            desc = (alt.description[:45] + "...") if len(alt.description) > 45 else alt.description
            alt_table.add_row(
                str(i),
                alt.skill_id,
                desc or "—",
                f"{alt.confidence:.0%}",
                alt.layer.value,
            )
        console.print()
        console.print(alt_table)


def render_compact_report(result: RoutingResult, console: Console | None = None) -> None:
    """Render a compact single-line routing summary."""
    if console is None:
        console = Console()

    if result.primary:
        if result.primary.layer == RoutingLayer.FALLBACK_LLM:
            console.print(
                f"[bold yellow]→ {result.primary.skill_id}[/bold yellow] "
                f"(fallback — no skill matched)"
            )
        else:
            console.print(
                f"[bold green]→ {result.primary.skill_id}[/bold green] "
                f"({result.primary.confidence:.0%} via {result.primary.layer.value})"
            )
    else:
        console.print("[yellow]→ No match[/yellow]")
