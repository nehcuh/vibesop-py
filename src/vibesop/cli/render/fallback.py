"""Fallback routing result renderer."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel


def render_fallback_panel(result: Any, console: Console) -> None:
    """Render fallback-llm routing result panel."""
    alt_text = ""
    if result.alternatives:
        alt_text = "\n[bold]💡 Nearest installed skills:[/bold]\n"
        for alt in result.alternatives[:3]:
            desc = f" — {alt.description[:50]}" if alt.description else ""
            alt_text += f"  • {alt.skill_id} ({alt.confidence:.0%}){desc}\n"
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
            f"  • Installing a relevant skill pack",
            title="[bold]Routing Result[/bold]",
            border_style="yellow",
        )
    )
