"""Single-skill routing result renderers."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel


def render_match_panel(result: Any, console: Console) -> None:
    """Render normal skill match panel with quality indicators."""
    primary = result.primary
    quality_str = ""
    grade = primary.metadata.get("grade")
    if grade:
        grade_colors = {"A": "green", "B": "green", "C": "yellow", "D": "yellow", "F": "red"}
        color = grade_colors.get(grade, "dim")
        quality_str = f"\n[dim]Quality:[/dim] [{color}]{grade}[/{color}]"
    habit_boost = primary.metadata.get("habit_boost")
    if habit_boost:
        quality_str += " [dim](habit)[/dim]"
        console.print("[dim]💡 Habit boost applied[/dim]")

    deprecated = primary.metadata.get("deprecated_warnings", [])
    if deprecated:
        console.print(
            f"\n[yellow]⚠️  Deprecated skills in ecosystem:[/yellow] {', '.join(deprecated)}"
        )

    console.print(
        Panel(
            f"[bold green]✅ Matched:[/bold green] {primary.skill_id}\n"
            f"[dim]Confidence:[/dim] {primary.confidence:.0%}\n"
            f"[dim]Layer:[/dim] {primary.layer.value}\n"
            f"[dim]Source:[/dim] {primary.source}{quality_str}\n"
            f"[dim]Duration:[/dim] {result.duration_ms:.1f}ms",
            title="[bold]Routing Result[/bold]",
            border_style="blue",
        )
    )
    if result.alternatives:
        console.print("\n[bold]💡 Alternatives:[/bold]")
        for alt in result.alternatives[:3]:
            desc = f" — {alt.description[:50]}" if alt.description else ""
            console.print(f"  • {alt.skill_id} ({alt.confidence:.0%}){desc}")


def render_no_match(result: Any, console: Console) -> None:
    """Render no-match panel."""
    console.print(
        Panel(
            f"[yellow]❓ No suitable match found[/yellow]\n\n"
            f"[dim]Query:[/dim] {result.original_query}\n"
            f"[dim]Routing path:[/dim] {' → '.join([layer.value for layer in result.routing_path])}\n\n"
            f"[dim]Try:[/dim]\n"
            f"  • Using more specific keywords\n"
            f"  • Lowering the threshold\n"
            f"  • Listing available skills",
            title="[bold]Routing Result[/bold]",
            border_style="yellow",
        )
    )
