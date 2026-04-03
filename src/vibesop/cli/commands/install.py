"""VibeSOP install command - Install skill pack integrations.

This command installs skill pack integrations like Superpowers and gstack.

Usage:
    vibe install <NAME>
    vibe install --auto
    vibe install --list

Examples:
    # Install gstack skill pack
    vibe install gstack

    # Install superpowers skill pack
    vibe install superpowers

    # Auto-install recommended integrations
    vibe install --auto

    # List available integrations
    vibe install --list
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from vibesop.installer import GstackInstaller, SuperpowersInstaller
from vibesop.integrations import IntegrationManager, IntegrationStatus

console = Console()

# Valid integrations
VALID_INTEGRATIONS = ["gstack", "superpowers"]


def install(
    name: Optional[str] = typer.Argument(
        None,
        help="Integration name (gstack, superpowers)",
    ),
    auto: bool = typer.Option(
        False,
        "--auto",
        "-a",
        help="Auto-install recommended integrations",
    ),
    list_available: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="List available integrations",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force reinstall even if already installed",
    ),
    skip_verify: bool = typer.Option(
        False,
        "--skip-verify",
        help="Skip verification after installation",
    ),
) -> None:
    """Install skill pack integrations.

    This command installs external skill pack integrations
    like gstack and Superpowers from their GitHub repositories.

    \b
    Examples:
        # Install gstack skill pack
        vibe install gstack

        # Install superpowers skill pack
        vibe install superpowers

        # Auto-install recommended integrations
        vibe install --auto

        # List available integrations
        vibe install --list

        # Force reinstall
        vibe install gstack --force
    """
    # List mode
    if list_available:
        _list_available()
        return

    # Auto mode
    if auto:
        _auto_install(force, skip_verify)
        return

    # Manual mode - require name
    if not name:
        console.print(
            "[red]✗ No integration specified[/red]\n"
            "[dim]Specify an integration:[/dim]\n"
            "  [cyan]vibe install gstack[/cyan]\n"
            "  [cyan]vibe install superpowers[/cyan]\n"
            "\n"
            "[dim]Or use:[/dim]\n"
            "  [cyan]vibe install --auto[/cyan] [dim]to install recommended integrations[/dim]\n"
            "  [cyan]vibe install --list[/cyan] [dim]to see available integrations[/dim]\n"
        )
        raise typer.Exit(1)

    # Validate name
    if name not in VALID_INTEGRATIONS:
        console.print(
            f"[red]✗ Unknown integration: {name}[/red]\n"
            f"[dim]Valid integrations: {', '.join(VALID_INTEGRATIONS)}[/dim]"
        )
        raise typer.Exit(1)

    # Check if already installed
    manager = IntegrationManager()
    integration = manager.get_integration(name)

    if integration and integration.status == IntegrationStatus.INSTALLED and not force:
        console.print(
            f"[yellow]⚠ {name} is already installed[/yellow]\n"
            f"[dim]Path: {integration.path}[/dim]\n"
            "[dim]Use --force to reinstall[/dim]"
        )
        return

    # Install
    _install_integration(name, force, skip_verify)


def _list_available() -> None:
    """List available integrations."""
    console.print(
        f"\n[bold cyan]📦 Available Integrations[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    t = Table()
    t.add_column("Integration", style="cyan")
    t.add_column("Description")
    t.add_column("Skills")
    t.add_column("Status", style="bold")

    manager = IntegrationManager()

    for name in VALID_INTEGRATIONS:
        integration = manager.get_integration(name)

        if integration:
            if integration.status == IntegrationStatus.INSTALLED:
                status = "[green]✓ Installed[/green]"
            else:
                status = "[dim]⊘ Not installed[/dim]"
            skills = ", ".join(integration.skills[:3])
            if len(integration.skills) > 3:
                skills += f" [+{len(integration.skills) - 3}]"
        else:
            status = "[dim]⊘ Not installed[/dim]"
            skills = "-"

        # Get description
        if name == "gstack":
            description = "Virtual engineering team skills"
            skill_count = "9 skills"
        elif name == "superpowers":
            description = "General-purpose productivity skills"
            skill_count = "7 skills"
        else:
            description = "-"
            skill_count = "-"

        t.add_row(name, description, skill_count, status)

    console.print(t)

    console.print(
        "\n[dim]To install an integration:[/dim]\n"
        "  [cyan]vibe install <name>[/cyan]\n"
        "  [cyan]vibe install --auto[/cyan] [dim]to install all recommended[/dim]\n"
    )


def _auto_install(force: bool, skip_verify: bool) -> None:
    """Auto-install recommended integrations.

    Args:
        force: Force reinstall
        skip_verify: Skip verification
    """
    console.print(
        f"\n[bold cyan]🚀 Auto-Installing Recommended Integrations[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    manager = IntegrationManager()
    results = {}

    for name in VALID_INTEGRATIONS:
        integration = manager.get_integration(name)

        if integration and integration.status == IntegrationStatus.INSTALLED and not force:
            console.print(f"[dim]⊘ {name}: already installed, skipping[/dim]")
            results[name] = "skipped"
            continue

        console.print(f"[dim]Installing {name}...[/dim]")
        result = _install_integration(name, force, skip_verify, quiet=True)
        results[name] = result

    # Summary
    console.print(f"\n[bold]Summary[/bold]\n")

    for name, result in results.items():
        if result == "success":
            console.print(f"  [green]✓ {name}[/green]")
        elif result == "skipped":
            console.print(f"  [dim]⊘ {name} (already installed)[/dim]")
        else:
            console.print(f"  [red]✗ {name}[/red]")

    console.print()


def _install_integration(
    name: str,
    force: bool,
    skip_verify: bool,
    quiet: bool = False,
) -> str:
    """Install a specific integration.

    Args:
        name: Integration name
        force: Force reinstall
        skip_verify: Skip verification
        quiet: Suppress progress output

    Returns:
        "success", "failed", or "skipped"
    """
    if not quiet:
        console.print(
            f"\n[bold cyan]📦 Installing {name}[/bold cyan]"
            f"\n{'=' * 40}\n"
        )

    # Get appropriate installer
    if name == "gstack":
        installer = GstackInstaller()
    elif name == "superpowers":
        installer = SuperpowersInstaller()
    else:
        console.print(f"[red]✗ Unknown integration: {name}[/red]")
        return "failed"

    # Install with progress
    if quiet:
        # Simple install without progress
        result = installer.install(platform=None, force=force)
    else:
        # Install with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Installing {name}...", total=100)

            # Create progress tracker
            from vibesop.cli import ProgressTracker

            progress_tracker = ProgressTracker(
                f"Installing {name}",
            )
            progress_tracker._started = False  # Prevent auto-start

            result = installer.install(platform=None, force=force, progress=progress_tracker)

            progress.update(task, completed=100)

    # Check result
    if result.get("success"):
        if not quiet:
            console.print(
                f"\n[green]✓ {name} installed successfully![/green]\n"
                f"[dim]Path: {result.get('installed_path', 'N/A')}[/dim]\n"
            )

            # Show symlinks if any
            symlinks = result.get("symlinks_created", [])
            if symlinks:
                console.print("[bold]Symlinks created:[/bold]")
                for symlink in symlinks:
                    console.print(f"  📎 {symlink}")
                console.print()

            # Verify
            if not skip_verify:
                if not quiet:
                    console.print("[dim]Verifying installation...[/dim]")

                verify_result = installer.verify()
                if verify_result.get("installed"):
                    console.print("[green]✓ Installation verified[/green]\n")
                else:
                    console.print("[yellow]⚠ Verification failed[/yellow]\n")

        return "success"
    else:
        if not quiet:
            errors = result.get("errors", [])
            console.print(
                f"\n[red]✗ Failed to install {name}[/red]\n"
            )
            for error in errors:
                console.print(f"  [dim]{error}[/dim]")
            console.print()

        return "failed"
