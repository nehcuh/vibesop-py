"""VibeSOP checkpoint command - Manage work state checkpoints.

This command allows creating, restoring, listing, and managing
checkpoints for saving and restoring work state.

Usage:
    vibe checkpoint save NAME
    vibe checkpoint restore ID
    vibe checkpoint list
    vibe checkpoint delete ID
    vibe checkpoint --help

Examples:
    # Save a checkpoint
    vibe checkpoint save "my-work"

    # List checkpoints
    vibe checkpoint list

    # Restore a checkpoint
    vibe checkpoint restore abc12345
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from vibesop.core.checkpoint.base import CheckpointStatus
from vibesop.core.checkpoint.manager import CheckpointManager

console = Console()


def checkpoint(
    action: str = typer.Argument(..., help="Action: save, restore, list, delete"),
    name_or_id: str | None = typer.Argument(None, help="Checkpoint name or ID"),
    description: str | None = typer.Option(
        None,
        "--description",
        "-d",
        help="Checkpoint description",
    ),
    tags: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--tag",
        "-t",
        help="Tags for categorization",
    ),
    snapshot_files: bool = typer.Option(
        False,
        "--snapshot",
        "-s",
        help="Snapshot current files",
    ),
) -> None:
    """Manage work state checkpoints.

    This command allows you to save and restore your work state,
    making it easy to switch between tasks or recover from errors.

    \b
    Examples:
        # Save a checkpoint
        vibe checkpoint save "my-work"

        # Save with description
        vibe checkpoint save "feature-x" --description "Working on feature X"

        # Save with tags
        vibe checkpoint save "bugfix" --tag urgent --tag backend

        # List all checkpoints
        vibe checkpoint list

        # Restore a checkpoint
        vibe checkpoint restore abc12345

        # Delete a checkpoint
        vibe checkpoint delete abc12345
    """
    manager = CheckpointManager()

    if action == "save":
        _do_save(manager, name_or_id, description, tags, snapshot_files)
    elif action == "restore":
        _do_restore(manager, name_or_id)
    elif action == "list":
        _do_list(manager)
    elif action == "delete":
        _do_delete(manager, name_or_id)
    elif action == "prune":
        _do_prune(manager)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n"
            f"[dim]Valid actions: save, restore, list, delete, prune[/dim]"
        )
        raise typer.Exit(1)


def _do_save(
    manager: CheckpointManager,
    name: str | None,
    description: str | None,
    tags: list[str] | None,
    snapshot_files: bool,
) -> None:
    """Save a checkpoint.

    Args:
        manager: CheckpointManager instance
        name: Checkpoint name
        description: Optional description
        tags: Optional tags
        snapshot_files: Whether to snapshot files
    """
    if not name:
        console.print("[red]✗ Name required for save action[/red]")
        console.print("[dim]Usage: vibe checkpoint save NAME[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]💾 Saving Checkpoint[/bold cyan]\n{'=' * 40}\n")

    # Snapshot files if requested
    files = None
    if snapshot_files:
        files = _get_current_files()
        console.print(f"[dim]Snapshotting {len(files)} files...[/dim]")

    # Create checkpoint
    checkpoint = manager.create_checkpoint(
        name=name,
        description=description or "",
        tags=tags or [],
        files=files,
    )

    console.print(
        f"[green]✓ Checkpoint saved[/green]\n"
        f"  [dim]ID:[/dim] {checkpoint.metadata.id}\n"
        f"  [dim]Name:[/dim] {checkpoint.metadata.name}\n"
        f"  [dim]Created:[/dim] {checkpoint.metadata.created_at}\n"
    )

    if snapshot_files and checkpoint.files:
        console.print(f"  [dim]Files:[/dim] {len(checkpoint.files)} snapshot")


def _do_restore(manager: CheckpointManager, checkpoint_id: str | None) -> None:
    """Restore a checkpoint.

    Args:
        manager: CheckpointManager instance
        checkpoint_id: Checkpoint ID to restore
    """
    if not checkpoint_id:
        console.print("[red]✗ ID required for restore action[/red]")
        console.print("[dim]Usage: vibe checkpoint restore ID[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]🔄 Restoring Checkpoint[/bold cyan]\n{'=' * 40}\n")

    # Find checkpoint by ID or name
    checkpoint = manager.get_checkpoint(checkpoint_id)
    if not checkpoint:
        all_checkpoints = manager.list_checkpoints()
        for cp in all_checkpoints:
            if cp.name == checkpoint_id:
                checkpoint = manager.get_checkpoint(cp.id)
                break

    if not checkpoint:
        console.print(f"[red]✗ Checkpoint not found: {checkpoint_id}[/red]")
        console.print("[dim]Run 'vibe checkpoint list' to see available checkpoints[/dim]")
        raise typer.Exit(1)

    restored = manager.restore_checkpoint(checkpoint.metadata.id)

    if not restored:
        console.print(f"[red]✗ Failed to restore checkpoint: {checkpoint_id}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[green]✓ Checkpoint restored[/green]\n"
        f"  [dim]ID:[/dim] {restored.metadata.id}\n"
        f"  [dim]Name:[/dim] {restored.metadata.name}\n"
        f"  [dim]Description:[/dim] {restored.metadata.description or 'None'}\n"
    )

    if restored.files:
        console.print(f"  [dim]Files:[/dim] {len(restored.files)} files available")
        console.print("\n[dim]Use the file contents to restore your work state.[/dim]")


def _do_list(manager: CheckpointManager) -> None:
    """List all checkpoints.

    Args:
        manager: CheckpointManager instance
    """
    console.print(f"\n[bold cyan]📋 Checkpoints[/bold cyan]\n{'=' * 40}\n")

    checkpoints = manager.list_checkpoints()

    if not checkpoints:
        console.print("[dim]No checkpoints found[/dim]")
        console.print("\n[dim]Create one with: vibe checkpoint save NAME[/dim]")
        raise typer.Exit(0)

    # Create table
    table = Table()
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Created", style="dim")
    table.add_column("Status")
    table.add_column("Tags", style="dim")

    for cp in checkpoints[:20]:  # Show first 20
        status_icon = "✓" if cp.status == CheckpointStatus.CREATED else "⊘"
        tags_str = ", ".join(cp.tags or [])[:30]

        table.add_row(
            cp.id,
            cp.name[:30],
            cp.created_at.strftime("%Y-%m-%d %H:%M"),
            status_icon,
            tags_str,
        )

    console.print(table)

    if len(checkpoints) > 20:
        console.print(f"\n[dim]... and {len(checkpoints) - 20} more checkpoints[/dim]")


def _do_delete(manager: CheckpointManager, checkpoint_id: str | None) -> None:
    """Delete a checkpoint.

    Args:
        manager: CheckpointManager instance
        checkpoint_id: Checkpoint ID to delete
    """
    if not checkpoint_id:
        console.print("[red]✗ ID required for delete action[/red]")
        console.print("[dim]Usage: vibe checkpoint delete ID[/dim]")
        raise typer.Exit(1)

    # Find and delete checkpoint
    checkpoint = manager.get_checkpoint(checkpoint_id)
    if not checkpoint:
        console.print(f"[red]✗ Checkpoint not found: {checkpoint_id}[/red]")
        raise typer.Exit(1)

    manager.delete_checkpoint(checkpoint.metadata.id)
    console.print(f"[green]✓ Checkpoint deleted: {checkpoint_id}[/green]")


def _do_prune(manager: CheckpointManager) -> None:
    """Prune old checkpoints.

    Args:
        manager: CheckpointManager instance
    """
    console.print("[dim]Pruning old checkpoints...[/dim]")
    count = manager.clear_old_checkpoints()
    console.print(f"[green]✓ Pruned {count} old checkpoints[/green]")


def _get_current_files() -> list[str]:
    """Get list of current working files.

    Returns:
        List of file paths
    """
    # Get common working files
    cwd = Path.cwd()
    files: list[str] = []

    # Python files
    for py_file in cwd.rglob("*.py"):
        if "venv" not in str(py_file) and ".venv" not in str(py_file):
            files.append(str(py_file))

    # Config files
    for config in ["pyproject.toml", "setup.py", "requirements.txt"]:
        path = cwd / config
        if path.exists():
            files.append(str(path))

    return files[:100]  # Limit to 100 files
