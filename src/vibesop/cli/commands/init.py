# pyright: reportMissingTypeArgument=false
"""VibeSOP init command - Initialize project with VibeSOP configuration.

This command sets up the .vibe directory structure and creates
default configuration files for a project.

Usage:
    vibe init [--platform PLATFORM] [--force] [--dry-run]
    vibe init --help

Examples:
    # Initialize for Claude Code platform
    vibe init

    # Initialize for specific platform
    vibe init --platform opencode

    # Force re-initialization
    vibe init --force

    # Preview what would be created
    vibe init --dry-run
"""

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.installer.init_support import InitSupport
from vibesop.integrations import IntegrationManager, IntegrationStatus

console = Console()

# Platform labels for display
PLATFORM_LABELS = {
    "claude-code": "Claude Code",
    "kimi-cli": "Kimi Code CLI",
    "opencode": "OpenCode",
    "superpowers": "Superpowers",
    "cursor": "Cursor",
}

# Valid platforms
VALID_PLATFORMS = list(PLATFORM_LABELS.keys())


def init(
    project_path: Path = typer.Argument(
        Path(),
        help="Project path (default: current directory)",
        show_default=False,
    ),
    platform: str = typer.Option(
        "claude-code",
        "--platform",
        "-p",
        help="Target platform for configuration",
        show_default=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-initialization if already initialized",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be created without making changes",
    ),
    verify_only: bool = typer.Option(
        False,
        "--verify",
        help="Only verify initialization without creating anything",
    ),
    skip_index: bool = typer.Option(
        False,
        "--skip-index",
        help="Skip building the skill semantic index after initialization",
    ),
) -> None:
    """Initialize a project with VibeSOP configuration.

    This command creates the .vibe directory structure and
    default configuration files for your project.

    \b
    Examples:
        # Initialize for Claude Code (default)
        vibe init

        # Initialize for specific platform
        vibe init --platform opencode

        # Force re-initialization
        vibe init --force

        # Preview what would be created
        vibe init --dry-run

        # Verify existing initialization
        vibe init --verify
    """
    # Validate platform
    if platform not in VALID_PLATFORMS:
        console.print(
            f"[red]✗ Invalid platform: {platform}[/red]\n"
            f"[dim]Valid platforms: {', '.join(VALID_PLATFORMS)}[/dim]"
        )
        raise typer.Exit(1)

    platform_label = PLATFORM_LABELS.get(platform, platform)

    # Handle verify mode
    if verify_only:
        _verify_init(project_path, platform_label)
        return

    # Handle dry-run mode
    if dry_run:
        _preview_init(project_path, platform, platform_label)
        return

    # Perform initialization
    _do_init(project_path, platform, platform_label, force, skip_index)


def _verify_init(project_path: Path, platform_label: str) -> None:
    """Verify project initialization status.

    Args:
        project_path: Path to verify
        platform_label: Platform name for display
    """
    init_support = InitSupport()
    result = init_support.verify_init(project_path)

    console.print("[bold]🔍 VibeSOP Initialization Status[/bold]\n")

    # Create status table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Item", style="cyan")
    table.add_column("Status")

    status_icon = "✅" if result["vibe_dir_exists"] else "❌"
    table.add_row(".vibe directory", status_icon)

    status_icon = "✅" if result["config_exists"] else "❌"
    table.add_row("config.toml", status_icon)

    status_icon = "✅" if result["skills_dir_exists"] else "❌"
    table.add_row("skills/ directory", status_icon)

    console.print(table)

    if result["initialized"]:
        console.print(f"\n[green]✓ Project is properly initialized for {platform_label}[/green]")
        raise typer.Exit(0)
    else:
        console.print("\n[yellow]⚠ Project is not fully initialized[/yellow]")
        console.print("  Run: [cyan]vibe init[/cyan] to initialize")
        raise typer.Exit(1)


def _preview_init(project_path: Path, _platform: str, platform_label: str) -> None:
    """Preview what would be created during initialization.

    Args:
        project_path: Project path
        platform: Platform identifier
        platform_label: Platform name for display
    """
    project_path = project_path.expanduser().resolve()
    vibe_dir = project_path / ".vibe"

    console.print(
        Panel(
            "[bold cyan]🔍 DRY RUN[/bold cyan]\n\n"
            "This is a preview of what would be created.\n"
            "No changes will be made.\n\n"
            "[dim]Run again without --dry-run to actually initialize.[/dim]",
            title="[bold]Preview Mode[/bold]",
            border_style="cyan",
        )
    )

    console.print(f"\n[bold]Target:[/bold] {project_path}")
    console.print(f"[bold]Platform:[/bold] {platform_label}\n")

    # Check if already initialized
    if vibe_dir.exists():
        console.print(
            "[yellow]⚠ .vibe directory already exists[/yellow]\n"
            "[dim]Use --force to overwrite[/dim]\n"
        )

    console.print("[bold]Files that would be created:[/bold]\n")
    console.print("  📁 .vibe/")
    console.print("  ├─ 📄 config.toml")
    console.print("  ├─ 📁 skills/")
    console.print("  ├─ 📁 core/")
    console.print("  ├─ 📁 memory/")
    console.print("  └─ 📄 README.md")
    console.print("  📁 .skills/")
    console.print("  📄 .gitignore (updated)\n")

    console.print(
        "[dim]To actually install, run:[/dim]\n"
        "  [cyan]vibe init[/cyan] [dim](or 'vibe init --force' to overwrite)[/dim]\n"
    )


def _do_init(
    project_path: Path, platform: str, platform_label: str, force: bool, skip_index: bool = False
) -> None:
    """Perform the actual initialization.

    Args:
        project_path: Project path
        platform: Platform identifier
        platform_label: Platform name for display
        force: Whether to force re-initialization
        skip_index: Whether to skip building the skill semantic index
    """
    console.print(f"\n[bold cyan]🚀 {platform_label} Initialization[/bold cyan]\n{'=' * 40}\n")

    init_support = InitSupport()
    result = init_support.init_project(
        project_path=project_path,
        platform=platform,
        force=force,
    )

    # Handle warnings
    for warning in result.get("warnings", []):
        console.print(f"[yellow]⚠ {warning}[/yellow]")

    # Handle errors
    if result.get("errors"):
        for error in result["errors"]:
            console.print(f"[red]✗ {error}[/red]")
        raise typer.Exit(1)

    # Show success message
    if result.get("success"):
        console.print("[green]✓ Initialization complete![/green]\n")

        # Show created directories
        if result.get("created_dirs"):
            console.print("[bold]Directories created:[/bold]")
            for dir_path in result["created_dirs"]:
                rel_path = Path(dir_path).relative_to(Path.cwd())
                console.print(f"  📁 {rel_path}")
            console.print()

        # Show created files
        if result.get("created_files"):
            console.print("[bold]Files created:[/bold]")
            for file_path in result["created_files"]:
                rel_path = Path(file_path).relative_to(Path.cwd())
                console.print(f"  📄 {rel_path}")
            console.print()

        console.print(
            "[dim]Next steps:[/dim]\n"
            "  1. Review .vibe/config.toml\n"
            f"  2. Run [cyan]vibe switch {platform}[/cyan] to build and deploy configuration\n"
        )

        # Build skill semantic index (layered: global first, then project)
        if not skip_index:
            from vibesop.core.llm_config import LLMConfigResolver
            from vibesop.core.skills.indexer import SkillIndexer
            from vibesop.llm.factory import create_provider

            def _llm_factory() -> Any:
                # Honor ~/.vibe/config.toml first (S5 P1-A priority order);
                # fall back to env-based detection if config is absent.
                resolver = LLMConfigResolver()
                cfg = resolver.get_llm_for_understanding()
                if cfg and cfg.provider and cfg.model:
                    return create_provider(
                        provider=cfg.provider,
                        api_key=cfg.api_key,
                        base_url=cfg.api_base,
                    )
                return create_provider()

            indexer = SkillIndexer(project_root=project_path, llm_factory=_llm_factory)

            # Ensure global index exists (built once, shared across projects)
            if not indexer.global_index_path.exists():
                console.print("\n[bold cyan]🔍 Building global skill index...[/bold cyan]")
                indexer.build_index(scope="global", show_progress=True)

            # Build project-local index (only project-specific skills)
            console.print("\n[bold cyan]🔍 Building project skill index...[/bold cyan]")
            indexer.build_index(scope="project", show_progress=True)
        else:
            console.print("\n[dim]⊘ Skill index build skipped (--skip-index)[/dim]")

        # Auto-detect integrations
        console.print(f"\n[bold cyan]🔍 Detecting Integrations[/bold cyan]\n{'=' * 40}\n")
        _detect_and_show_integrations()

        raise typer.Exit(0)
    else:
        console.print("[red]✗ Initialization failed[/red]")
        raise typer.Exit(1)


def _detect_and_show_integrations() -> None:
    """Detect and display integration status.

    Shows which skill pack integrations (superpowers, omx, mattpocock) are
    installed and provides install suggestions for missing ones.
    gstack is an optional recommended pack — install it explicitly via
    `vibe install gstack` if needed.
    """
    manager = IntegrationManager()
    all_integrations = manager.list_integrations(refresh=True)

    # Create status table
    table = Table(show_header=True)
    table.add_column("Integration", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Description")

    installed_count = 0

    for info in all_integrations:
        if info.status == IntegrationStatus.INSTALLED:
            status = "[green]✓ Installed[/green]"
            installed_count += 1
        elif info.status == IntegrationStatus.NOT_INSTALLED:
            status = "[dim]⊘ Not installed[/dim]"
        elif info.status == IntegrationStatus.INCOMPATIBLE:
            status = "[yellow]⚠ Incompatible[/yellow]"
        else:
            status = "[dim]? Unknown[/dim]"

        table.add_row(
            info.name,
            status,
            info.description,
        )

    console.print(table)

    # Show summary
    total_count = len(all_integrations)
    console.print(f"\n[dim]Installed: {installed_count}/{total_count} integrations[/dim]")

    # Show install suggestions if not all installed
    if installed_count < total_count:
        not_installed = [
            i.name for i in all_integrations if i.status != IntegrationStatus.INSTALLED
        ]
        if not_installed:
            console.print(
                f"\n[yellow]⚠ Missing recommended integrations: {', '.join(not_installed)}[/yellow]"
            )
            console.print(
                "[dim]Run to install:[/dim]\n"
                "  [cyan]vibe install --auto[/cyan] [dim](install all recommended)[/dim]\n"
                "  [cyan]vibe install <name>[/cyan] [dim](install specific)[/dim]"
            )
    else:
        console.print("\n[green]✓ All recommended integrations installed![/green]")
