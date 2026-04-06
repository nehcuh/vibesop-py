"""VibeSOP deploy command - Deploy configuration to platform.

This command installs generated configuration to the target platform.

Usage:
    vibe deploy TARGET [DESTINATION]
    vibe deploy --help

Examples:
    # Deploy to Claude Code default location
    vibe deploy claude-code

    # Deploy to custom location
    vibe deploy claude-code ./config

    # Force overwrite
    vibe deploy claude-code --force
"""

import shutil
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def deploy(
    target: str = typer.Argument(
        "claude-code",
        help="Target platform (claude-code, opencode, superpowers, cursor)",
    ),
    destination: Path | None = typer.Argument(  # noqa: B008
        None,
        help="Destination directory (default: platform default)",
        show_default=False,
    ),
    source: Path | None = typer.Option(  # noqa: B008
        None,
        "--source",
        "-s",
        help="Source build directory (default: .vibe/dist/<target>)",
        exists=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force overwrite existing files",
    ),
    backup: bool = typer.Option(
        True,
        "--backup/--no-backup",
        help="Backup existing files before overwriting",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview deployment without making changes",
    ),
) -> None:
    """Deploy configuration to target platform.

    This command installs the generated configuration files to
    the target platform's configuration directory.

    \b
    Examples:
        # Deploy to Claude Code default location
        vibe deploy claude-code

        # Deploy to custom location
        vibe deploy claude-code ./my-config

        # Deploy from custom source
        vibe deploy claude-code --source ./my-build

        # Force overwrite without backup
        vibe deploy claude-code --force --no-backup

        # Preview what would be deployed
        vibe deploy claude-code --dry-run
    """
    _execute_deploy(
        target=target,
        destination=destination,
        source=source,
        force=force,
        backup=backup,
        dry_run=dry_run,
    )

    # Show success message
    if destination is None:
        destination = _get_default_destination(target)

    console.print(
        f"\n[green]✓ Deployment complete![/green]\n"
        f"[dim]Configuration installed to:[/dim]\n"
        f"  [cyan]{destination}[/cyan]\n"
        f"[dim]Restart {target} to apply changes.[/dim]"
    )
    raise typer.Exit(0)


def _execute_deploy(
    target: str,
    destination: Path | None = None,
    source: Path | None = None,
    force: bool = False,
    backup: bool = True,
    dry_run: bool = False,
) -> None:
    """Internal deployment function.

    This function contains the actual deployment logic that can be
    called from other commands.

    Args:
        target: Target platform identifier
        destination: Destination directory (default: platform default)
        source: Source build directory (default: .vibe/dist/<target>)
        force: Force overwrite existing files
        backup: Backup existing files before overwriting
        dry_run: Preview deployment without making changes
    """

    # Set default source directory
    if source is None:
        source = Path(f".vibe/dist/{target}")

    # Check if source exists
    if not source.exists():
        console.print(
            f"[red]✗ Source directory not found: {source}[/red]\n"
            f"[dim]Run [cyan]vibe build {target}[/cyan] first[/dim]"
        )
        raise typer.Exit(1)

    # Get default destination
    if destination is None:
        destination = _get_default_destination(target)

    destination = Path(destination).expanduser().resolve()

    console.print(f"\n[bold cyan]🚀 Deploying to {target}[/bold cyan]\n{'=' * 40}\n")

    # Dry-run mode
    if dry_run:
        _preview_deploy(source, destination, target)
        return

    # Perform deployment
    try:
        # Backup existing files
        if backup and destination.exists():
            backup_path = _create_backup(destination)
            console.print(f"[dim]Backed up to: {backup_path}[/dim]\n")

        # Create destination directory
        destination.mkdir(parents=True, exist_ok=True)

        # Copy files
        source_files = list(source.rglob("*"))
        source_files = [f for f in source_files if f.is_file()]

        copied = 0
        skipped = 0
        errors = []

        for src_file in source_files:
            # Calculate relative path
            rel_path = src_file.relative_to(source)
            dst_file = destination / rel_path

            # Check if file exists and not forcing
            if dst_file.exists() and not force:
                skipped += 1
                console.print(f"[dim]⊘ Skipped (exists): {rel_path}[/dim]")
                continue

            # Create parent directories
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            try:
                shutil.copy2(src_file, dst_file)
                copied += 1
                console.print(f"[green]✓[/green] {rel_path}")
            except Exception as e:
                errors.append(f"{rel_path}: {e}")
                console.print(f"[red]✗[/red] {rel_path}: {e}")

        # Show summary
        console.print("\n[bold]Deployment Summary[/bold]\n")
        console.print(f"  [green]Copied:[/green] {copied} files")
        if skipped > 0:
            console.print(f"  [dim]Skipped:[/dim] {skipped} files (use --force to overwrite)")
        if errors:
            console.print(f"  [red]Errors:[/red] {len(errors)} files")

        if errors:
            console.print("\n[red]✗ Deployment completed with errors[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]✗ Deployment failed: {e}[/red]")
        raise typer.Exit(1) from None


def _get_default_destination(target: str) -> Path:
    """Get default destination for target platform.

    Args:
        target: Target platform identifier

    Returns:
        Default destination path
    """
    destinations = {
        "claude-code": Path("~/.claude"),
        "opencode": Path("~/.config/opencode"),
        "superpowers": Path("~/.config/superpowers"),
        "cursor": Path("~/.config/cursor"),
    }
    return destinations.get(target, Path(f"~/.{target}")).expanduser()


def _create_backup(destination: Path) -> Path:
    """Create backup of destination directory.

    Args:
        destination: Path to backup

    Returns:
        Path to backup directory
    """
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{destination.name}_backup_{timestamp}"
    backup_path = destination.parent / backup_name

    shutil.copytree(destination, backup_path)
    return backup_path


def _preview_deploy(source: Path, destination: Path, target: str) -> None:
    """Preview deployment without making changes.

    Args:
        source: Source directory
        destination: Destination directory
        target: Target platform name
    """
    console.print(
        "[bold cyan]🔍 DRY RUN - Deployment Preview[/bold cyan]\n"
        "[dim]No changes will be made.[/dim]\n\n"
    )

    console.print(f"[bold]Source:[/bold] {source}")
    console.print(f"[bold]Destination:[/bold] {destination}")
    console.print(f"[bold]Target:[/bold] {target}\n")

    # Count files that would be deployed
    source_files = list(source.rglob("*"))
    source_files = [f for f in source_files if f.is_file()]

    console.print(f"[bold]Files that would be deployed:[/bold] {len(source_files)}\n")

    # Show structure
    dirs = set()
    for f in source_files[:20]:  # Show first 20
        rel_path = f.relative_to(source)
        if rel_path.parent != Path():
            dirs.add(str(rel_path.parent))

    if dirs:
        console.print("[bold]Directories:[/bold]")
        for d in sorted(dirs)[:10]:
            console.print(f"  📁 {d}/")

    if len(source_files) > 20:
        console.print(f"  [dim]... and {len(source_files) - 20} more files[/dim]")

    console.print(f"\n[dim]To actually deploy, run:[/dim]\n  [cyan]vibe deploy {target}[/cyan]\n")
