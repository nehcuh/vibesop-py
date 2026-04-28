"""Single-skill routing result renderers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.panel import Panel

if TYPE_CHECKING:
    from rich.console import Console


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
    """Render improved no-match panel with actionable suggestions."""
    query = getattr(result, "original_query", getattr(result, "query", "your query"))

    suggestions = [
        "Try being more specific with your intent",
        "Use [cyan]vibe skills list[/cyan] to see available skills",
        "Use [cyan]vibe skill discover[/cyan] to find community skills",
        "Check [cyan]vibe status[/cyan] for ecosystem health",
    ]

    if hasattr(result, "alternatives") and result.alternatives:
        best_alt = result.alternatives[0]
        suggestions.insert(
            0,
            f"[cyan]{best_alt.skill_id}[/cyan] was close "
            f"([dim]{best_alt.confidence:.0%}[/dim]) — try rephrasing",
        )

    suggestion_text = "\n".join(f"  • {s}" for s in suggestions[:4])

    console.print(
        Panel(
            f"[yellow]No matching skill found for:[/yellow] {query}\n\n"
            f"[bold]Suggestions:[/bold]\n{suggestion_text}",
            title="[bold]Routing Result[/bold]",
            border_style="yellow",
        )
    )
