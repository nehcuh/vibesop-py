"""VibeSOP onboard command - New user onboarding.

This command provides a guided 5-step onboarding process
for new users.

Usage:
    vibe onboard
    vibe onboard --skip-deploy

Examples:
    # Run full onboarding
    vibe onboard

    # Skip deployment step
    vibe onboard --skip-deploy
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()


def onboard(
    skip_deploy: bool = typer.Option(
        False,
        "--skip-deploy",
        help="Skip deployment step (config already installed)",
    ),
    _skip_hooks: bool = typer.Option(
        False,
        "--skip-hooks",
        help="Skip hooks installation",
    ),
    skip_integrations: bool = typer.Option(
        False,
        "--skip-integrations",
        help="Skip integrations installation",
    ),
) -> None:
    """Run new user onboarding.

    This command provides a guided 5-step onboarding process
    for new users to get started with VibeSOP.

    \b
    Examples:
        # Run full onboarding
        vibe onboard

        # Skip deployment step
        vibe onboard --skip-deploy

        # Minimal onboarding (no deploy, hooks, integrations)
        vibe onboard --skip-deploy --skip-hooks --skip-integrations
    """
    console.print(f"\n[bold cyan]👋 Welcome to VibeSOP![/bold cyan]\n{'=' * 40}\n")

    console.print(
        Panel(
            "[bold]5-Step Onboarding[/bold]\n\n"
            "1. [cyan]Initialize[/cyan] - Set up project structure\n"
            "2. [cyan]Build[/cyan] - Generate platform configuration\n"
            "3. [cyan]Deploy[/cyan] - Install configuration\n"
            "4. [cyan]Integrations[/cyan] - Set up external integrations\n"
            "5. [cyan]Verify[/cyan] - Verify everything works\n",
            title="[bold]Onboarding Steps[/bold]",
            border_style="cyan",
        )
    )

    # Step 1: Initialize
    console.print("\n[bold]Step 1: Initialize[/bold]\n")
    console.print("[dim]Creating .vibe directory structure...[/dim]")

    from vibesop.installer.init_support import InitSupport

    init_support = InitSupport()
    result = init_support.init_project(Path(), platform="claude-code")

    if result.get("success"):
        console.print("[green]✓[/green] Initialized\n")
    else:
        console.print("[red]✗[/red] Initialization failed\n")
        raise typer.Exit(1)

    # Step 2: Build
    console.print("[bold]Step 2: Build[/bold]\n")
    console.print("[dim]Generating configuration...[/dim]")
    console.print("[dim]Run 'vibe build' to generate platform config[/dim]\n")

    # Step 3: Deploy
    if not skip_deploy:
        console.print("[bold]Step 3: Deploy[/bold]\n")
        console.print("[dim]To deploy configuration, run:[/dim]")
        console.print("  [cyan]vibe deploy claude-code[/cyan]\n")
    else:
        console.print("[bold]Step 3: Deploy[/bold] [dim](skipped)[/dim]\n")

    # Step 4: Integrations
    if not skip_integrations:
        console.print("[bold]Step 4: Integrations[/bold]\n")
        console.print("[dim]Available integrations:[/dim]")
        console.print("  • gstack - Virtual engineering team")
        console.print("  • superpowers - Productivity skills\n")
    else:
        console.print("[bold]Step 4: Integrations[/bold] [dim](skipped)[/dim]\n")

    # Step 5: Verify
    console.print("[bold]Step 5: Verify[/bold]\n")
    console.print("[dim]Run 'vibe doctor' to verify your setup[/dim]\n")

    console.print(
        Panel(
            "[bold green]✓ Onboarding complete![/bold green]\n\n"
            "[dim]Next steps:[/dim]\n"
            "  • Run [cyan]vibe build[/cyan] to generate config\n"
            "  • Run [cyan]vibe deploy[/cyan] to install\n"
            "  • Run [cyan]vibe doctor[/cyan] to verify\n"
            '  • Run [cyan]vibe route "help"[/cyan] to find skills',
            border_style="green",
        )
    )
