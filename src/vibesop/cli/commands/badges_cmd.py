"""CLI commands for badge management.

Usage:
    vibe badges list
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.badges import BadgeTracker, get_badge_display

app = typer.Typer(
    name="badges",
    help="View earned badges and achievements",
)
console = Console()


@app.command("list")
def list_badges() -> None:
    """List all earned badges."""
    tracker = BadgeTracker()
    badges = tracker.list_badges()

    if not badges:
        console.print(
            Panel(
                "No badges yet!\n\n"
                "Earn badges by:\n"
                "  • Giving feedback on skills (vibe skills feedback)\n"
                "  • Using skills repeatedly\n"
                "  • Maintaining high-quality skills",
                title="🎖️ Badges",
                border_style="dim",
            )
        )
        return

    table = Table(title="🎖️ Earned Badges", show_header=True, header_style="bold")
    table.add_column("Icon", justify="center", width=4)
    table.add_column("Badge", style="bold")
    table.add_column("Description", style="dim")
    table.add_column("Awarded", justify="right", style="dim")

    for badge in badges:
        meta = get_badge_display(badge.type)
        awarded = badge.awarded_at[:10] if badge.awarded_at else "Unknown"
        table.add_row(
            meta.get("icon", "🏅"),
            meta.get("title", badge.type.value),
            meta.get("description", ""),
            awarded,
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(badges)} badge(s)[/dim]")
