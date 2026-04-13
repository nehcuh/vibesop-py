"""VibeSOP build command - Build platform configuration from manifest.

This command generates platform-specific configuration files
from the manifest and source files.

Usage:
    vibe build [TARGET] [--profile PROFILE] [--output DIR] [--overlay FILE]
    vibe build --help

Examples:
    # Build for Claude Code (outputs to .vibe/dist/claude-code)
    vibe build claude-code

    # Build and deploy directly to Claude Code config
    vibe build claude-code --output ~/.claude

    # Build with specific profile
    vibe build claude-code --profile minimal

    # Build with overlay customization
    vibe build claude-code --overlay .vibe/overlay.yaml

    # Build using configured platform (from config.yaml)
    vibe build
"""

import logging
from pathlib import Path
from typing import Any, cast

import typer
from rich.console import Console
from rich.panel import Panel
from ruamel.yaml import YAML

from vibesop.adapters.models import Manifest
from vibesop.builder.manifest import ManifestBuilder
from vibesop.builder.renderer import ConfigRenderer

console = Console()
logger = logging.getLogger(__name__)

VALID_TARGETS = ["claude-code", "opencode", "superpowers", "cursor"]

PROFILES: dict[str, str] = {
    "default": "Full configuration with all skills",
    "minimal": "Minimal configuration with core skills only",
    "development": "Development-friendly configuration",
}


def execute_build(
    target: str,
    profile: str,
    output: Path | None,
    overlay: Path | None,
    verify: bool,
) -> None:
    """Execute build logic (reusable by other commands)."""
    if profile not in PROFILES:
        console.print(
            f"[red]✗ Invalid profile: {profile}[/red]\n"
            f"[dim]Valid profiles: {', '.join(PROFILES.keys())}[/dim]"
        )
        raise typer.Exit(1)

    if output is None:
        output = Path(f".vibe/dist/{target}")

    console.print(f"\n[bold cyan]🔨 Building {target}[/bold cyan]\n{'=' * 40}\n")

    try:
        console.print(f"[dim]Loading manifest for {target}...[/dim]")
        builder = ManifestBuilder(project_root=Path())

        if overlay:
            console.print(f"[dim]Applying overlay: {overlay}[/dim]")
            manifest = builder.build(overlay_path=overlay, platform=target)
        else:
            manifest = builder.build_from_registry(platform=target)

        console.print(
            f"[green]✓[/green] Loaded {len(manifest.skills)} skills, "
            f"{len(manifest.policies.behavior or {})} policy rules\n"
        )

        if False:
            console.print("[bold]Manifest generated (manifest-only mode)[/bold]")
            _display_manifest_summary(manifest)
            return

        if verify:
            _verify_build(target, manifest)
            return

        console.print(f"[dim]Rendering configuration for {target}...[/dim]")
        renderer = ConfigRenderer()

        output_dir = Path(output).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        result = renderer.render(
            manifest=manifest,
            output_dir=output_dir,
        )

        console.print(f"\n[green]✓ Build complete![/green]\n[bold]Output:[/bold] {output_dir}\n")

        if result.files_created:
            console.print("[bold]Files created:[/bold]")
            for file_path in result.files_created:
                # Handle paths outside current directory (e.g., ~/.claude)
                try:
                    rel_path = Path(file_path).relative_to(Path.cwd())
                    console.print(f"  📄 {rel_path}")
                except ValueError:
                    # Path is outside current directory, show absolute path
                    console.print(f"  📄 {file_path}")

        # Suggest deployment based on output location
        if str(output_dir) == str(Path.home() / ".claude"):
            console.print(
                "\n[dim]✓ Deployed to Claude Code config directory[/dim]\n"
                "[dim]Restart Claude Code to apply changes.[/dim]\n"
            )
        else:
            console.print(
                f"\n[dim]Next steps:[/dim]\n"
                f"  1. Review generated files in [cyan]{output_dir}[/cyan]\n"
                f"  2. For deployment, use: [cyan]vibe build {target} --output ~/.claude[/cyan]\n"
            )

        return

    except FileNotFoundError as e:
        console.print(f"[red]✗ File not found: {e}[/red]")
        raise typer.Exit(1) from None
    except ValueError as e:
        console.print(f"[red]✗ Configuration error: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]✗ Build failed: {e}[/red]")
        raise typer.Exit(1) from None


def _get_configured_platform() -> str | None:
    """Get platform from .vibe/config.yaml."""
    config_path = Path(".vibe/config.yaml")
    if not config_path.exists():
        return None

    try:
        yaml_parser = YAML()
        with config_path.open() as f:
            config = cast("dict[str, Any]", yaml_parser.load(f))  # type: ignore[reportUnknownMemberType,reportUnknownVariableType]
            return config.get("platform") if config else None
    except Exception as e:
        logger.debug(f"Failed to read config.yaml: {e}")
        return None


def build(
    target: str | None = typer.Argument(
        None,
        help="Target platform (claude-code, opencode, superpowers, cursor). "
        "Defaults to platform from config.yaml or claude-code",
    ),
    profile: str = typer.Option(
        "default",
        "--profile",
        "-p",
        help=f"Build profile: {', '.join(PROFILES.keys())}",
    ),
    output: Path | None = typer.Option(  # noqa: B008
        None,
        "--output",
        "-o",
        help="Output directory (default: .vibe/dist/<target>). Use ~/.claude to deploy directly.",
        exists=False,
    ),
    overlay: Path | None = typer.Option(  # noqa: B008
        None,
        "--overlay",
        help="Path to overlay YAML file for customization",
        exists=True,
    ),
    _manifest_only: bool = typer.Option(
        False,
        "--manifest-only",
        help="Only generate manifest, skip rendering",
    ),
    verify: bool = typer.Option(
        False,
        "--verify",
        help="Verify build output without writing files",
    ),
) -> None:
    """Build platform configuration from manifest."""
    if target is None:
        target = _get_configured_platform()
        if target is None:
            target = "claude-code"
            console.print(f"[dim]No platform specified, using default: {target}[/dim]\n")
        else:
            console.print(f"[dim]Using configured platform: {target}[/dim]\n")

    if target not in VALID_TARGETS:
        console.print(
            f"[red]✗ Invalid target: {target}[/red]\n"
            f"[dim]Valid targets: {', '.join(VALID_TARGETS)}[/dim]"
        )
        raise typer.Exit(1)

    execute_build(
        target=target,
        profile=profile,
        output=output,
        overlay=overlay,
        verify=verify,
    )


def _display_manifest_summary(manifest: Manifest) -> None:
    """Display manifest summary."""
    console.print("\n[bold]Manifest Summary[/bold]\n")
    console.print(f"  Platform: {manifest.metadata.platform}")
    console.print(f"  Version: {manifest.metadata.version}")
    console.print(f"  Skills: {len(manifest.skills)}")
    console.print(f"  Policy rules: {len(manifest.policies.behavior or {})}")


def _verify_build(target: str, manifest: Manifest) -> None:
    """Verify build without writing files."""
    console.print(
        Panel(
            f"[bold cyan]🔍 Verification Mode[/bold cyan]\n\n"
            f"[bold]Target:[/bold] {target}\n"
            f"[bold]Platform:[/bold] {manifest.metadata.platform}\n"
            f"[bold]Version:[/bold] {manifest.metadata.version}\n"
            f"[bold]Skills:[/bold] {len(manifest.skills)}\n\n"
            f"[dim]No files were written. Remove --verify to actually build.[/dim]",
            title="[bold]Build Verification[/bold]",
            border_style="cyan",
        )
    )
