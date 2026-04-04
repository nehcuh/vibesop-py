"""VibeSOP targets command - List available platform targets.

This command shows all available platform targets and their
status.

Usage:
    vibe targets
    vibe targets --help

Examples:
    # List all targets
    vibe targets

    # Show detailed information
    vibe targets --verbose

    # Show only installed targets
    vibe targets --installed
"""

from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from vibesop.installer.installer import VibeSOPInstaller

console = Console()

# Platform information
PLATFORM_INFO = {
    "claude-code": {
        "name": "Claude Code",
        "description": "Anthropic's Claude Code CLI and desktop app",
        "config_dir": "~/.claude",
        "status": "stable",
    },
    "opencode": {
        "name": "OpenCode",
        "description": "OpenCode AI coding assistant",
        "config_dir": "~/.config/opencode",
        "status": "beta",
    },
    "superpowers": {
        "name": "Superpowers",
        "description": "Superpowers skill pack for Claude Code",
        "config_dir": "~/.config/superpowers",
        "status": "stable",
    },
    "cursor": {
        "name": "Cursor",
        "description": "Cursor AI code editor",
        "config_dir": "~/.config/cursor",
        "status": "experimental",
    },
}


def targets(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed information",
    ),
    installed: bool = typer.Option(
        False,
        "--installed",
        "-i",
        help="Show only installed targets",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output as JSON",
    ),
) -> None:
    """List available platform targets.

    This command shows all available platform targets and their
    installation status.

    \b
    Examples:
        # List all targets
        vibe targets

        # Show detailed information
        vibe targets --verbose

        # Show only installed targets
        vibe targets --installed

        # Output as JSON
        vibe targets --json
    """
    try:
        installer = VibeSOPInstaller()
        platforms = installer.list_platforms()

        # Filter by installed if requested
        if installed:
            platforms = [p for p in platforms if installer.verify(p["name"])["installed"]]

        # JSON output
        if json_output:
            _output_json(platforms, verbose)
            return

        # Table output
        _output_table(platforms, verbose, installed)

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        raise typer.Exit(1)


def _output_table(platforms: list[dict[str, str]], verbose: bool, installed_only: bool) -> None:
    """Output platforms as a table.

    Args:
        platforms: List of platform dictionaries
        verbose: Show detailed information
        installed_only: Whether filtering by installed
    """
    console.print(f"\n[bold cyan]🎯 Available Targets[/bold cyan]\n{'=' * 40}\n")

    if not platforms:
        if installed_only:
            console.print("[dim]No targets installed[/dim]")
        else:
            console.print("[dim]No targets available[/dim]")
        return

    # Create table
    table = Table()
    table.add_column("Target", style="cyan")
    table.add_column("Name")
    table.add_column("Status")

    if verbose:
        table.add_column("Config Dir")
        table.add_column("Description")

    for platform_info in platforms:
        platform_id = platform_info["name"]
        info = PLATFORM_INFO.get(platform_id, {})
        name = info.get("name", platform_id.title())
        config_dir = info.get("config_dir", "N/A")
        description = info.get("description", "")

        installer = VibeSOPInstaller()
        verify_result = installer.verify(platform_id)
        installed_status = "✓" if verify_result["installed"] else "✗"
        status_color = "green" if verify_result["installed"] else "dim"

        row: list[str] = [platform_id, name, f"[{status_color}]{installed_status}[/]"]

        if verbose:
            row.append(config_dir)
            row.append(description)

        table.add_row(*row)

    console.print(table)

    # Show summary
    installed_count = sum(1 for p in platforms if VibeSOPInstaller().verify(p["name"])["installed"])
    console.print(f"\n[dim]Showing {len(platforms)} targets ({installed_count} installed)[/dim]\n")


def _output_json(platforms: list[dict[str, str]], verbose: bool) -> None:
    """Output platforms as JSON.

    Args:
        platforms: List of platform dictionaries
        verbose: Include detailed information
    """
    import json

    output: list[dict[str, Any]] = []

    for platform_info in platforms:
        platform_id = platform_info["name"]
        info = PLATFORM_INFO.get(platform_id, {})

        # Check installation status
        installer = VibeSOPInstaller()
        verify_result = installer.verify(platform_id)

        data = {
            "id": platform_id,
            "name": info.get("name", platform_id.title()),
            "installed": verify_result["installed"],
            "status": info.get("status", "unknown"),
        }

        if verbose:
            data["config_dir"] = info.get("config_dir", "")
            data["description"] = info.get("description", "")

        output.append(data)

    console.print_json(json.dumps(output, indent=2))
