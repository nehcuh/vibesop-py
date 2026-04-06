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
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.config import ConfigManager
from vibesop.installer.init_support import InitSupport
from vibesop.installer.installer import VibeSOPInstaller

console = Console()


def inspect_cmd(
    project_path: Path = typer.Option(  # noqa: B008
        Path(),
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
    project_path = project_path.expanduser().resolve()

    if skills_only:
        _show_skills(project_path, verbose)
        raise typer.Exit(0)

    if config_only:
        _show_config(project_path, verbose)
        raise typer.Exit(0)

    console.print(
        Panel(
            "[bold cyan]VibeSOP Configuration Inspector[/bold cyan]",
            border_style="cyan",
        )
    )

    _show_init_status(project_path)

    _show_config(project_path, verbose)

    _show_skills(project_path, verbose)

    _show_installation_status()


def _show_init_status(project_path: Path) -> None:
    init_support = InitSupport()
    result = init_support.verify_init(project_path)

    console.print("\n[bold]📁 Initialization Status[/bold]\n")

    table = Table(show_header=False, box=None)
    table.add_column("Item", style="cyan")
    table.add_column("Status")

    status_icon = "✅" if result.get("vibe_dir_exists", False) else "❌"
    table.add_row(".vibe directory", status_icon)

    status_icon = "✅" if result.get("config_exists", False) else "❌"
    table.add_row("config.yaml", status_icon)

    status_icon = "✅" if result.get("skills_dir_exists", False) else "❌"
    table.add_row("skills/ directory", status_icon)

    console.print(table)


def _show_config(project_path: Path, verbose: bool) -> None:
    console.print("\n[bold]⚙️  Configuration[/bold]\n")

    try:
        loader = ConfigManager(project_path)
        config: dict[str, Any] = loader.load_registry()

        console.print(f"  Platform: [cyan]{config.get('platform', 'not set')}[/cyan]")

        if verbose:
            routing: dict[str, Any] = config.get("routing", {})
            console.print(f"  Semantic threshold: {routing.get('semantic_threshold', 'N/A')}")
            console.print(f"  Enable fuzzy: {routing.get('enable_fuzzy', 'N/A')}")

            security: dict[str, Any] = config.get("security", {})
            console.print(f"  Threat level: {security.get('threat_level', 'N/A')}")

    except Exception as e:
        console.print(f"  [dim]Error loading config: {e}[/dim]")


def _show_skills(project_path: Path, verbose: bool) -> None:
    console.print("\n[bold]📚 Skills[/bold]\n")

    try:
        loader = ConfigManager(project_path)
        skills: list[dict[str, Any]] = loader.get_all_skills()

        console.print(f"  Total: [cyan]{len(skills)}[/cyan] skills")

        if verbose and skills:
            console.print()
            for skill in skills[:10]:
                skill_id = skill.get("id", "unknown")
                name = skill.get("name", skill_id)
                console.print(f"    • [cyan]{skill_id}[/cyan] - {name}")

            if len(skills) > 10:
                console.print(f"    [dim]... and {len(skills) - 10} more[/dim]")

    except Exception as e:
        console.print(f"  [dim]Error loading skills: {e}[/dim]")


def _show_installation_status() -> None:
    console.print("\n[bold]🚀 Installation Status[/bold]\n")

    try:
        installer = VibeSOPInstaller()
        platforms = installer.list_platforms()

        for platform_info in platforms:
            platform_name = platform_info["name"]
            verify_result: dict[str, Any] = installer.verify(platform_name)

            if verify_result.get("installed", False):
                console.print(f"  [cyan]{platform_name}[/cyan]: [green]✓ Installed[/green]")
            else:
                console.print(f"  [cyan]{platform_name}[/cyan]: [dim]✗ Not installed[/dim]")

    except Exception as e:
        console.print(f"  [dim]Error checking installation: {e}[/dim]")
