"""VibeSOP inspect command - Inspect current configuration.

This command shows information about the current platform
configuration and installation status.

Usage:
    vibe inspect
    vibe inspect --help

Examples:
    # Show current configuration
    vibe inspect

    # Show detailed information
    vibe inspect --verbose

    # Show only skills
    vibe inspect --skills-only
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.config import ConfigLoader
from vibesop.installer.init_support import InitSupport
from vibesop.installer.installer import VibeSOPInstaller

console = Console()


def inspect_cmd(
    project_path: Path = typer.Option(
        Path("."),
        "--path",
        "-p",
        help="Project path to inspect",
        show_default=False,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed information",
    ),
    skills_only: bool = typer.Option(
        False,
        "--skills",
        "-s",
        help="Show only installed skills",
    ),
    config_only: bool = typer.Option(
        False,
        "--config",
        "-c",
        help="Show only configuration",
    ),
) -> None:
    """Inspect current VibeSOP configuration.

    This command displays information about the current platform
    configuration, installed skills, and installation status.

    \b
    Examples:
        # Show all information
        vibe inspect

        # Show detailed information
        vibe inspect --verbose

        # Show only skills
        vibe inspect --skills

        # Show only configuration
        vibe inspect --config
    """
    project_path = project_path.expanduser().resolve()

    if skills_only:
        _show_skills(project_path, verbose)
        raise typer.Exit(0)

    if config_only:
        _show_config(project_path, verbose)
        raise typer.Exit(0)

    # Show all information
    console.print(
        Panel(
            "[bold cyan]VibeSOP Configuration Inspector[/bold cyan]",
            border_style="cyan",
        )
    )

    # Show initialization status
    _show_init_status(project_path)

    # Show configuration
    _show_config(project_path, verbose)

    # Show skills
    _show_skills(project_path, verbose)

    # Show installation status
    _show_installation_status()


def _show_init_status(project_path: Path) -> None:
    """Show initialization status.

    Args:
        project_path: Project path
    """
    init_support = InitSupport()
    result = init_support.verify_init(project_path)

    console.print("\n[bold]📁 Initialization Status[/bold]\n")

    table = Table(show_header=False, box=None)
    table.add_column("Item", style="cyan")
    table.add_column("Status")

    status_icon = "✅" if result["vibe_dir_exists"] else "❌"
    table.add_row(".vibe directory", status_icon)

    status_icon = "✅" if result["config_exists"] else "❌"
    table.add_row("config.yaml", status_icon)

    status_icon = "✅" if result["skills_dir_exists"] else "❌"
    table.add_row("skills/ directory", status_icon)

    console.print(table)


def _show_config(project_path: Path, verbose: bool) -> None:
    """Show configuration.

    Args:
        project_path: Project path
        verbose: Show detailed information
    """
    console.print("\n[bold]⚙️  Configuration[/bold]\n")

    try:
        loader = ConfigLoader(project_path)
        config = loader.load_config()

        console.print(f"  Platform: [cyan]{config.get('platform', 'not set')}[/cyan]")

        if verbose:
            routing = config.get("routing", {})
            console.print(f"  Semantic threshold: {routing.get('semantic_threshold', 'N/A')}")
            console.print(f"  Enable fuzzy: {routing.get('enable_fuzzy', 'N/A')}")

            security = config.get("security", {})
            console.print(f"  Threat level: {security.get('threat_level', 'N/A')}")

    except Exception as e:
        console.print(f"  [dim]Error loading config: {e}[/dim]")


def _show_skills(project_path: Path, verbose: bool) -> None:
    """Show installed skills.

    Args:
        project_path: Project path
        verbose: Show detailed information
    """
    console.print("\n[bold]📚 Skills[/bold]\n")

    try:
        loader = ConfigLoader(project_path)
        skills = loader.get_all_skills()

        console.print(f"  Total: [cyan]{len(skills)}[/cyan] skills")

        if verbose and skills:
            console.print()
            for skill in skills[:10]:  # Show first 10
                skill_id = skill.get("id", "unknown")
                name = skill.get("name", skill_id)
                console.print(f"    • [cyan]{skill_id}[/cyan] - {name}")

            if len(skills) > 10:
                console.print(f"    [dim]... and {len(skills) - 10} more[/dim]")

    except Exception as e:
        console.print(f"  [dim]Error loading skills: {e}[/dim]")


def _show_installation_status() -> None:
    """Show platform installation status."""
    console.print("\n[bold]🚀 Installation Status[/bold]\n")

    try:
        installer = VibeSOPInstaller()
        platforms = installer.list_platforms()

        for platform_info in platforms:
            platform_name = platform_info["name"]
            verify_result = installer.verify(platform_name)

            if verify_result["installed"]:
                console.print(f"  [cyan]{platform_name}[/cyan]: [green]✓ Installed[/green]")
            else:
                console.print(f"  [cyan]{platform_name}[/cyan]: [dim]✗ Not installed[/dim]")

    except Exception as e:
        console.print(f"  [dim]Error checking installation: {e}[/dim]")


def _show_skills(project_path: Path, verbose: bool) -> None:
    """Show only skills.

    Args:
        project_path: Project path
        verbose: Show detailed information
    """
    console.print("[bold]📚 Installed Skills[/bold]\n")

    try:
        loader = ConfigLoader(project_path)
        skills = loader.get_all_skills()

        if not skills:
            console.print("[dim]No skills found[/dim]")
            return

        console.print(f"Total: [cyan]{len(skills)}[/cyan] skills\n")

        for skill in skills:
            skill_id = skill.get("id", "unknown")
            name = skill.get("name", skill_id)
            description = skill.get("description", "")
            console.print(f"  [cyan]{skill_id}[/cyan] - {name}")
            if verbose and description:
                console.print(f"    [dim]{description}[/dim]")

    except Exception as e:
        console.print(f"[red]✗ Error loading skills: {e}[/red]")


def _show_config(project_path: Path, verbose: bool) -> None:
    """Show only configuration.

    Args:
        project_path: Project path
        verbose: Show detailed information
    """
    console.print("[bold]⚙️  Configuration[/bold]\n")

    try:
        loader = ConfigLoader(project_path)
        config = loader.load_config()

        # Create table
        table = Table(show_header=False)
        table.add_column("Setting", style="cyan")
        table.add_column("Value")

        table.add_row("Platform", config.get("platform", "not set"))

        routing = config.get("routing", {})
        table.add_row("Semantic threshold", str(routing.get("semantic_threshold", "N/A")))
        table.add_row("Enable fuzzy", str(routing.get("enable_fuzzy", "N/A")))

        security = config.get("security", {})
        table.add_row("Threat level", security.get("threat_level", "N/A"))

        console.print(table)

        if verbose:
            console.print("\n[bold]Full Configuration:[/bold]\n")
            import json
            console.print_json(json.dumps(config, indent=2))

    except Exception as e:
        console.print(f"[red]✗ Error loading config: {e}[/red]")
