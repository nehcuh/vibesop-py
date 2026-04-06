"""VibeSOP config command - Configuration management."""

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()


def config(
    semantic: bool = typer.Option(
        False,
        "--semantic",
        "-s",
        help="Show semantic matching configuration (deprecated)",
    ),
) -> None:
    """Manage VibeSOP configuration.

    \\b
    Examples:
        # Show general configuration
        vibe config
    """
    if semantic:
        console.print(
            Panel(
                "[bold yellow]⚠️ Semantic module has been removed in v4.0.[/bold yellow]\n\n"
                "Semantic matching is now handled by core/matching/ module.\n"
                "The dedicated semantic CLI has been deprecated.",
                title="[bold]Deprecated[/bold]",
                border_style="yellow",
            )
        )
        return

    _show_general_config()


def _show_general_config() -> None:
    """Show general VibeSOP configuration."""
    from vibesop import __version__

    console.print(
        Panel(
            f"[bold]VibeSOP[/bold] Configuration\n\n"
            f"Version: {__version__}\n"
            f"Python: 3.12+\n\n"
            f"[bold]Matching:[/bold]\n"
            f"  Keyword, TF-IDF, Fuzzy (built-in)\n\n"
            f"[bold]For skill management, use:[/bold]\n"
            f"  vibe skills list\n"
            f"  vibe skills health",
            title="[bold]Configuration[/bold]",
            border_style="blue",
        )
    )
