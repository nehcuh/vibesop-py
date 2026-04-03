"""VibeSOP detect command - Detect available skill pack integrations.

This command checks for available skill pack integrations
like Superpowers and gstack.

Usage:
    vibe detect
    vibe detect --all
    vibe detect --verbose

Examples:
    # Detect all integrations
    vibe detect

    # Show detailed information
    vibe detect --verbose
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from vibesop.integrations import IntegrationManager, IntegrationDetector, IntegrationStatus

console = Console()


def detect(
    all_: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show all integrations including not installed",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed information including skills",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output as JSON",
    ),
) -> None:
    """Detect available skill pack integrations.

    This command checks for installed and available skill pack
    integrations like Superpowers and gstack.

    \b
    Examples:
        # Show detected integrations
        vibe detect

        # Show all integrations
        vibe detect --all

        # Show detailed information
        vibe detect --verbose

        # Output as JSON
        vibe detect --json
    """
    console.print(
        f"\n[bold cyan]🔍 Detecting Integrations[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    # Create detector and manager
    detector = IntegrationDetector()
    manager = IntegrationManager()

    # Check skills base path
    skills_path = detector.skills_base_path
    if skills_path:
        console.print(f"[dim]Skills path: {skills_path}[/dim]\n")
    else:
        console.print(
            "[yellow]⚠ No skills path found[/yellow]\n"
            "[dim]Expected locations:[/dim]"
        )
        for path in IntegrationDetector.SKILLS_BASE_PATHS:
            console.print(f"  [dim]  {path}[/dim]")
        console.print()

    # Detect all integrations
    all_integrations = manager.list_integrations(refresh=True)

    # Filter by installed status unless --all
    if not all_:
        integrations = [i for i in all_integrations if i.status == IntegrationStatus.INSTALLED]
        if not integrations:
            console.print(
                "[yellow]No integrations installed[/yellow]\n"
                "[dim]Use --all to see available integrations[/dim]\n"
            )
            console.print(
                "[dim]To install integrations, run:[/dim]\n"
                "  [cyan]vibe install gstack[/cyan]\n"
                "  [cyan]vibe install superpowers[/cyan]\n"
            )
            return
    else:
        integrations = all_integrations

    # JSON output
    if json_output:
        import json
        data = [info.to_dict() for info in integrations]
        console.print_json(json.dumps(data, indent=2))
        return

    # Table output
    table = Table(title="Skill Pack Integrations")
    table.add_column("Integration", style="cyan")
    table.add_column("Status")
    table.add_column("Description")
    table.add_column("Version", style="dim")
    table.add_column("Path", style="dim")

    for info in integrations:
        # Status icon
        if info.status == IntegrationStatus.INSTALLED:
            status = "[green]✓ Installed[/green]"
        elif info.status == IntegrationStatus.NOT_INSTALLED:
            status = "[dim]⊘ Not installed[/dim]"
        elif info.status == IntegrationStatus.INCOMPATIBLE:
            status = "[yellow]⚠ Incompatible[/yellow]"
        else:
            status = "[dim]? Unknown[/dim]"

        # Version
        version = info.version or "[dim]-[/dim]"

        # Path
        path_str = str(info.path) if info.path else "[dim]-[/dim]"
        if len(path_str) > 30:
            path_str = "..." + path_str[-27:]

        table.add_row(
            info.name,
            status,
            info.description,
            version,
            path_str,
        )

        # Show skills if verbose
        if verbose and info.skills:
            for skill in info.skills:
                table.add_row(
                    "",
                    "",
                    f"  [dim]→ {skill}[/dim]",
                    "",
                    "",
                )

    console.print(table)

    # Show summary
    installed_count = sum(
        1 for i in all_integrations if i.status == IntegrationStatus.INSTALLED
    )
    total_count = len(all_integrations)

    console.print(
        f"\n[dim]Installed: {installed_count}/{total_count} integrations[/dim]"
    )

    # Show install suggestions if not all installed
    if installed_count < total_count:
        not_installed = [
            i.name for i in all_integrations
            if i.status != IntegrationStatus.INSTALLED
        ]
        if not_installed:
            console.print(
                f"\n[dim]Available to install: {', '.join(not_installed)}[/dim]\n"
                "[dim]Run: [cyan]vibe install <name>[/cyan] to install[/dim]"
            )
