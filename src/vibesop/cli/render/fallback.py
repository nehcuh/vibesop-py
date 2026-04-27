"""Fallback routing result renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.panel import Panel

if TYPE_CHECKING:
    from rich.console import Console


def render_fallback_panel(result: Any, console: Console) -> None:
    """Render fallback-llm routing result panel."""
    alt_text = ""
    if result.alternatives:
        alt_text = "\n[bold]💡 Nearest installed skills:[/bold]\n"
        for alt in result.alternatives[:3]:
            desc = f" — {alt.description[:50]}" if alt.description else ""
            alt_text += f"  • {alt.skill_id} ({alt.confidence:.0%}){desc}\n"

    stale_text = _render_stale_suggestions()

    console.print(
        Panel(
            f"[bold yellow]🤖 Fallback Mode[/bold yellow]\n\n"
            f"No installed skill confidently matched your query.\n"
            f"[dim]Query:[/dim] {result.original_query}\n"
            f"[dim]Routing path:[/dim] {' → '.join([layer.value for layer in result.routing_path])}\n"
            f"{alt_text}\n"
            f"[dim]VibeSOP is a routing engine, not an executor.[/dim]\n"
            f"[dim]Your AI Agent can still process this request using raw LLM.[/dim]\n\n"
            f"[dim]Try:[/dim]\n"
            f"  • Using more specific keywords\n"
            f"  • Browsing available skills: [bold]vibe skills list[/bold]\n"
            f"  • Installing a relevant skill pack\n"
            f"{stale_text}",
            title="[bold]Routing Result[/bold]",
            border_style="yellow",
        )
    )


def _render_stale_suggestions() -> str:
    """Check for stale/unused skills and return suggestion text."""
    try:
        from vibesop.core.skills.feedback_loop import FeedbackLoop

        loop = FeedbackLoop()
        suggestions = loop.analyze_all()

        deprecated = [s for s in suggestions if s.action == "deprecate"]
        warned = [s for s in suggestions if s.action == "warn"]

        if not deprecated and not warned:
            return ""

        lines = ["\n[bold yellow]⚡ Skill Health:[/bold yellow]"]
        if deprecated:
            skill_names = ", ".join(s.skill_id for s in deprecated[:3])
            lines.append(
                f"  • [red]{len(deprecated)} skill(s) may need attention:[/red] "
                f"[dim]{skill_names}[/dim]"
            )
        if warned:
            skill_names = ", ".join(s.skill_id for s in warned[:3])
            lines.append(
                f"  • [yellow]{len(warned)} skill(s) could be reviewed:[/yellow] "
                f"[dim]{skill_names}[/dim]"
            )
        lines.append("  • Run [bold]vibe skill stale[/bold] for details and cleanup options")
        return "\n".join(lines)
    except Exception:
        return ""
