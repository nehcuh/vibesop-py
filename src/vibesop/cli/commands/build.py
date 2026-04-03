"""VibeSOP build command - Build platform configuration from manifest.

This command generates platform-specific configuration files
from the manifest and source files.

Usage:
    vibe build [TARGET] [--profile PROFILE] [--output DIR] [--overlay FILE]
    vibe build --help

Examples:
    # Build for Claude Code
    vibe build claude-code

    # Build with specific profile
    vibe build claude-code --profile minimal

    # Build with overlay
    vibe build claude-code --overlay .vibe/overlay.yaml

    # Build to custom output
    vibe build claude-code --output ./dist

    # Build using configured platform (from config.yaml)
    vibe build
"""

import yaml
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from vibesop.builder.manifest import ManifestBuilder, QuickBuilder
from vibesop.builder.renderer import ConfigRenderer

console = Console()

# Valid targets
VALID_TARGETS = ["claude-code", "opencode", "superpowers", "cursor"]

# Default profiles
PROFILES = {
    "default": "Full configuration with all skills",
    "minimal": "Minimal configuration with core skills only",
    "development": "Development-friendly configuration",
}


def _get_configured_platform() -> Optional[str]:
    """Get platform from .vibe/config.yaml.

    Returns:
        Platform string if configured, None otherwise
    """
    config_path = Path(".vibe/config.yaml")
    if not config_path.exists():
        return None

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
            return config.get("platform") if config else None
    except Exception:
        return None


def build(
    target: str = typer.Argument(
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
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory (default: .vibe/dist/<target>)",
        exists=False,
    ),
    overlay: Optional[Path] = typer.Option(
        None,
        "--overlay",
        help="Path to overlay YAML file for customization",
        exists=True,
    ),
    manifest_only: bool = typer.Option(
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
    """Build platform configuration from manifest.

    This command generates platform-specific configuration files
    from the manifest and source files.

    \b
    Examples:
        # Build for Claude Code (default)
        vibe build

        # Build with specific profile
        vibe build claude-code --profile minimal

        # Build with overlay customization
        vibe build claude-code --overlay .vibe/overlay.yaml

        # Build to custom output directory
        vibe build claude-code --output ./dist

        # Only generate manifest
        vibe build claude-code --manifest-only
    """
    # Determine target platform
    if target is None:
        target = _get_configured_platform()
        if target is None:
            target = "claude-code"
            console.print(f"[dim]No platform specified, using default: {target}[/dim]\n")
        else:
            console.print(f"[dim]Using configured platform: {target}[/dim]\n")

    # Validate target
    if target not in VALID_TARGETS:
        console.print(
            f"[red]✗ Invalid target: {target}[/red]\n"
            f"[dim]Valid targets: {', '.join(VALID_TARGETS)}[/dim]"
        )
        raise typer.Exit(1)

    # Validate profile
    if profile not in PROFILES:
        console.print(
            f"[red]✗ Invalid profile: {profile}[/red]\n"
            f"[dim]Valid profiles: {', '.join(PROFILES.keys())}[/dim]"
        )
        raise typer.Exit(1)

    # Set default output directory
    if output is None:
        output = Path(f".vibe/dist/{target}")

    console.print(
        f"\n[bold cyan]🔨 Building {target}[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    try:
        # Build manifest
        console.print(f"[dim]Loading manifest for {target}...[/dim]")
        builder = ManifestBuilder(project_root=Path("."))

        if overlay:
            console.print(f"[dim]Applying overlay: {overlay}[/dim]")
            manifest = builder.build(overlay_path=overlay, platform=target)
        else:
            manifest = builder.build_from_registry(platform=target)

        console.print(
            f"[green]✓[/green] Loaded {len(manifest.skills)} skills, "
            f"{len(manifest.policies.behavior or {})} policy rules\n"
        )

        # Exit if manifest-only
        if manifest_only:
            console.print("[bold]Manifest generated (manifest-only mode)[/bold]")
            _display_manifest_summary(manifest)
            return

        # Verify mode
        if verify:
            _verify_build(target, manifest)
            return

        # Render configuration
        console.print(f"[dim]Rendering configuration for {target}...[/dim]")
        renderer = ConfigRenderer()

        # Get output directory
        output_dir = Path(output).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        # Render
        result = renderer.render(
            manifest=manifest,
            output_dir=output_dir,
        )

        # Show results
        console.print(
            f"\n[green]✓ Build complete![/green]\n"
            f"[bold]Output:[/bold] {output_dir}\n"
        )

        # Show created files
        if result.files_created:
            console.print("[bold]Files created:[/bold]")
            for file_path in result.files_created:
                rel_path = Path(file_path).relative_to(Path.cwd())
                console.print(f"  📄 {rel_path}")

        console.print(
            f"\n[dim]Next steps:[/dim]\n"
            f"  1. Review generated files in [cyan]{output_dir}[/cyan]\n"
            f"  2. Run [cyan]vibe deploy {target}[/cyan] to install\n"
        )

        return

    except FileNotFoundError as e:
        console.print(f"[red]✗ File not found: {e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]✗ Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]✗ Build failed: {e}[/red]")
        raise typer.Exit(1)


def _display_manifest_summary(manifest) -> None:
    """Display manifest summary.

    Args:
        manifest: Manifest to display
    """
    console.print(f"\n[bold]Manifest Summary[/bold]\n")
    console.print(f"  Platform: {manifest.metadata.platform}")
    console.print(f"  Version: {manifest.metadata.version}")
    console.print(f"  Skills: {len(manifest.skills)}")
    console.print(f"  Policy rules: {len(manifest.policies.behavior or {})}")


def _verify_build(target: str, manifest) -> None:
    """Verify build without writing files.

    Args:
        target: Target platform
        manifest: Built manifest
    """
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
