"""VibeSOP switch command - Switch platform configuration.

This command switches between different platform configurations
or profiles.

Usage:
    vibe switch [PLATFORM]
    vibe switch --help

Examples:
    # Switch to Claude Code configuration
    vibe switch claude-code

    # Switch with specific profile
    vibe switch claude-code --profile minimal

    # Switch without rebuilding
    vibe switch claude-code --no-build

    # Switch to configured platform (from config.yaml)
    vibe switch
"""

import logging
from pathlib import Path

import typer
from rich.console import Console
from ruamel.yaml import YAML

console = Console()
logger = logging.getLogger(__name__)

# Valid targets
VALID_TARGETS = ["claude-code", "opencode", "superpowers", "cursor"]


def _get_configured_platform() -> str | None:
    """Get platform from .vibe/config.yaml.

    Returns:
        Platform string if configured, None otherwise
    """
    config_path = Path(".vibe/config.yaml")
    if not config_path.exists():
        return None

    try:
        yaml_parser = YAML()
        with config_path.open() as f:
            config = yaml_parser.load(f)
            return config.get("platform") if config else None
    except Exception as e:
        logger.debug(f"Failed to read config.yaml: {e}")
        return None


def switch(
    platform: str | None = typer.Argument(
        None,
        help="Target platform (claude-code, opencode, superpowers, cursor). "
        "Defaults to platform from config.yaml",
    ),
    profile: str = typer.Option(
        "default",
        "--profile",
        "-p",
        help="Build profile to use",
    ),
    overlay: Path | None = typer.Option(  # noqa: B008
        None,
        "--overlay",
        help="Overlay file to apply",
        exists=True,
    ),
    destination: Path | None = typer.Option(  # noqa: B008
        None,
        "--destination",
        "-d",
        help="Custom destination directory",
    ),
    build: bool = typer.Option(
        True,
        "--build/--no-build",
        help="Build before deploying",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force overwrite existing files",
    ),
) -> None:
    """Switch platform configuration.

    This command combines build and deploy to switch between
    different platform configurations or profiles.

    \b
    Examples:
        # Switch to Claude Code configuration
        vibe switch claude-code

        # Switch with specific profile
        vibe switch claude-code --profile minimal

        # Switch with overlay
        vibe switch claude-code --overlay .vibe/overlay.yaml

        # Switch without rebuilding
        vibe switch claude-code --no-build
    """
    # Determine target platform
    if platform is None:
        platform = _get_configured_platform()
        if platform is None:
            console.print(
                "[red]✗ No platform specified and no configured platform found[/red]\n"
                "[dim]Either:[/dim]\n"
                "  1. Run [cyan]vibe init --platform <PLATFORM>[/cyan] first\n"
                "  2. Specify platform: [cyan]vibe switch <PLATFORM>[/cyan]\n"
            )
            raise typer.Exit(1)
        console.print(f"[dim]Using configured platform: {platform}[/dim]\n")

    # Validate platform
    if platform not in VALID_TARGETS:
        console.print(
            f"[red]✗ Invalid platform: {platform}[/red]\n"
            f"[dim]Valid platforms: {', '.join(VALID_TARGETS)}[/dim]"
        )
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]🔄 Switching to {platform}[/bold cyan]\n{'=' * 40}\n")

    # Build phase
    if build:
        console.print("[bold]Phase 1: Build[/bold]\n")

        # Import build logic
        from vibesop.cli.commands import build as build_module

        # Call build logic (will raise typer.Exit on failure)
        build_module.execute_build(
            target=platform,
            profile=profile,
            output=None,  # Use default output
            overlay=overlay,
            verify=False,
        )
    else:
        console.print("[dim]Skipping build (--no-build)[/dim]\n")

    # Deploy phase
    console.print("[bold]Phase 2: Deploy[/bold]\n")

    # Deploy logic - actually call the deploy command
    source = Path(f".vibe/dist/{platform}")

    if not source.exists():
        console.print(
            f"[red]✗ Build output not found: {source}[/red]\n"
            f"[dim]Run [cyan]vibe build {platform}[/cyan] first[/dim]"
        )
        raise typer.Exit(1)

    console.print(f"[dim]Source: {source}[/dim]")
    console.print(f"[dim]Destination: {destination or 'platform default'}[/dim]\n")

    # Import and call the actual deploy function
    from vibesop.cli.commands.deploy import _execute_deploy

    _execute_deploy(
        target=platform,
        destination=destination,
        source=source,
        force=force,  # Use the force flag from switch
        backup=True,
        dry_run=False,
    )

    console.print(
        f"[green]✓ Switched to {platform}[/green]\n"
        f"[dim]Restart the platform to apply changes.[/dim]"
    )
