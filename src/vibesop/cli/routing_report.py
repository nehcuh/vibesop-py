"""Rich decision tree renderer for routing transparency.

Renders a human-readable routing decision report from RoutingResult.layer_details.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from vibesop.core.models import RoutingLayer, RoutingResult


def render_routing_report(
    result: RoutingResult,
    console: Console | None = None,
    context: Any | None = None,
) -> None:
    """Render a full routing decision report to the console."""
    if console is None:
        console = Console()

    # Header panel
    query_text = getattr(result, "query", None) or getattr(result, "original_query", "")
    header_text = f"[bold]Query:[/bold] {query_text}\n"
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

    # Context-awareness panel
    if context is not None:
        _render_context_panel(context, console)

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
        console.print(
            "[dim]These candidates were close but didn't meet the confidence threshold.[/dim]"
        )

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


def _render_context_panel(context: Any, console: Console) -> None:
    """Render context-awareness information."""
    lines: list[str] = []

    if getattr(context, "conversation_id", None):
        lines.append(f"[dim]Conversation:[/dim] {context.conversation_id}")

    if getattr(context, "current_skill", None):
        lines.append(f"[dim]Current skill:[/dim] {context.current_skill}")

    if getattr(context, "recent_queries", None):
        recent = context.recent_queries
        if recent:
            lines.append(f"[dim]Recent queries:[/dim] {len(recent)} turn(s)")
            for q in recent[-2:]:
                lines.append(f"  [dim]•[/dim] {q[:50]}{'...' if len(q) > 50 else ''}")

    if getattr(context, "habit_boosts", None):
        boosts = context.habit_boosts
        if boosts:
            lines.append("[dim]Habit boosts:[/dim]")
            for skill_id, boost in boosts.items():
                lines.append(f"  [dim]•[/dim] {skill_id}: +{boost:.0%}")

    if getattr(context, "project_type", None):
        lines.append(f"[dim]Project type:[/dim] {context.project_type}")

    if lines:
        console.print(
            Panel(
                "\n".join(lines),
                title="[bold blue]🧠 Context Awareness[/bold blue]",
                border_style="blue",
                box=box.ROUNDED,
            )
        )


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


def render_compact_summary(
    result: RoutingResult,
    console: Console | None = None,
    mode: str = "single",
    steps_count: int | None = None,
    strategy: str | None = None,
) -> None:
    """Render a compact routing decision summary using Rich Table.

    This is the default CLI output — shows the routing decision without
    the full decision tree. Displayed before confirmation prompts.
    """
    if console is None:
        console = Console()

    table = Table(
        title="[bold cyan]🔍 Routing Summary[/bold cyan]",
        box=box.SIMPLE,
        show_header=False,
        padding=(0, 1),
    )
    table.add_column("Field", style="dim", justify="right")
    table.add_column("Value", style="bold")

    if result.primary:
        if result.primary.layer == RoutingLayer.FALLBACK_LLM:
            table.add_row("Selected", f"[yellow]{result.primary.skill_id}[/yellow]")
            table.add_row("Status", "[yellow]Fallback (no skill matched)[/yellow]")
        else:
            table.add_row("Selected", f"[green]{result.primary.skill_id}[/green]")
            table.add_row("Confidence", f"{result.primary.confidence:.0%}")
            table.add_row("Layer", result.primary.layer.value)
    else:
        table.add_row("Selected", "[yellow]No match[/yellow]")

    table.add_row("Duration", f"{result.duration_ms:.1f}ms")

    # Show top 3 alternatives
    if result.alternatives:
        alt_lines = []
        for alt in result.alternatives[:3]:
            alt_lines.append(f"  • {alt.skill_id} ({alt.confidence:.0%} via {alt.layer.value})")
        table.add_row("Alternatives", "\n".join(alt_lines))

    # Orchestration info
    if mode == "orchestrated":
        table.add_row("Mode", "[cyan]Orchestrated[/cyan]")
        if steps_count is not None:
            table.add_row("Steps", str(steps_count))
        if strategy:
            table.add_row("Strategy", strategy)

    console.print(table)
    console.print()

    from vibesop.cli.render.tips import render_ecosystem_tips

    render_ecosystem_tips(
        project_root=Path.cwd(),
        console=console,
        query=getattr(result, "query", ""),
        routed_skill_id=result.primary.skill_id if result.primary else "",
    )
