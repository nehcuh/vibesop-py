# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false, reportUnknownParameterType=false
"""VibeSOP quickstart command - Interactive setup wizard.

This command guides users through the initial setup process
with interactive questions.

Usage:
    vibe quickstart
    vibe quickstart --force

Examples:
    # Run interactive setup
    vibe quickstart

    # Run without confirmation
    vibe quickstart --force
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from vibesop.installer.quickstart_runner import QuickstartRunner

console = Console()


def quickstart(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmations and use defaults",
    ),
    platform: str = typer.Option(
        "claude-code",
        "--platform",
        "-p",
        help="Target platform (claude-code, opencode)",
    ),
    _global_install: bool = typer.Option(
        False,
        "--global",
        "-g",
        help="Install to global configuration directory",
    ),
) -> None:
    """Run interactive setup wizard.

    This command guides you through the initial VibeSOP setup
    with an interactive wizard.

    \b
    Examples:
        # Run interactive setup
        vibe quickstart

        # Run with specific platform
        vibe quickstart --platform claude-code

        # Run without confirmations
        vibe quickstart --force

        # Install to global config
        vibe quickstart --global
    """
    console.print(f"\n[bold cyan]🚀 VibeSOP Quickstart Wizard[/bold cyan]\n{'=' * 40}\n")

    runner = QuickstartRunner()

    if force:
        # Non-interactive mode
        result = runner.run(
            project_path=Path(),
        )

        if result.get("success"):
            console.print("[green]✓ Quickstart complete[/green]")
            for step in result.get("steps_completed", []):
                console.print(f"  • {step}")
        else:
            console.print("[red]✗ Quickstart failed[/red]")
            for error in result.get("errors", []):
                console.print(f"  • {error}")
            raise typer.Exit(1)
    else:
        # Interactive mode
        console.print(
            Panel(
                "[bold]Welcome to VibeSOP![/bold]\n\n"
                "This wizard will guide you through setup.\n"
                "Press Ctrl+C to cancel at any time.\n\n"
                "[dim]Platform: " + platform + "[/dim]",
                title="[bold]Quickstart[/bold]",
                border_style="cyan",
            )
        )

        result = runner.run(
            project_path=Path(),
        )

        if result.get("success"):
            console.print(
                "\n[green]✓ Setup complete![/green]\n"
                "[dim]Next steps:[/dim]\n"
                "  1. Review .vibe/ directory\n"
                "  2. Run [cyan]vibe build[/cyan] to generate config\n"
                "  3. Run [cyan]vibe deploy[/cyan] to install\n"
            )
        else:
            console.print("\n[red]✗ Setup failed[/red]")
            raise typer.Exit(1)
