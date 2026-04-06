"""VibeSOP worktree command - Git worktree management.

This command manages git worktrees for isolated development.

Usage:
    vibe worktree list
    vibe worktree create BRANCH
    vibe worktree remove BRANCH
    vibe worktree cleanup

Examples:
    # List worktrees
    vibe worktree list

    # Create a new worktree
    vibe worktree create feature-x

    # Remove a worktree
    vibe worktree remove feature-x
"""

import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def worktree(
    action: str = typer.Argument(..., help="Action: list, create, remove, cleanup, finish"),
    name_or_branch: str | None = typer.Argument(None, help="Branch name"),
    base: str = typer.Option(
        "main",
        "--base",
        "-b",
        help="Base branch for new worktree",
    ),
    location: Path | None = typer.Option(  # noqa: B008
        None,
        "--location",
        "-l",
        help="Custom location for worktree",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force action without confirmation",
    ),
) -> None:
    """Manage git worktrees.

    This command creates and manages git worktrees for
    isolated parallel development.

    \b
    Examples:
        # List all worktrees
        vibe worktree list

        # Create a new worktree for a branch
        vibe worktree create feature-branch

        # Create worktree at custom location
        vibe worktree create feature-x --location ../feature-x

        # Remove a worktree
        vibe worktree remove feature-branch

        # Clean up finished worktrees
        vibe worktree cleanup
    """
    if action == "list":
        _do_list()
    elif action == "create":
        _do_create(name_or_branch, base, location)
    elif action == "remove":
        _do_remove(name_or_branch, force)
    elif action == "cleanup":
        _do_cleanup(force)
    elif action == "finish":
        _do_finish(name_or_branch)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n"
            f"[dim]Valid actions: list, create, remove, cleanup, finish[/dim]"
        )
        raise typer.Exit(1)


def _do_list() -> None:
    """List all worktrees."""
    console.print(f"\n[bold cyan]🌳 Git Worktrees[/bold cyan]\n{'=' * 40}\n")

    try:
        # Get git worktree list
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            console.print("[dim]No worktrees found[/dim]")
            console.print("\n[dim]Create one with: vibe worktree create BRANCH[/dim]")
            return

        # Parse worktree list
        lines = result.stdout.strip().split("\n")
        worktrees = []

        for line in lines:
            if not line:
                continue
            parts = line.split(" ")
            if len(parts) >= 3:
                worktrees.append(
                    {
                        "commit": parts[0],
                        "branch": parts[1].strip("[]"),
                        "path": parts[2],
                    }
                )

        if not worktrees:
            console.print("[dim]No worktrees found[/dim]")
            return

        # Display table
        table = Table()
        table.add_column("Branch", style="cyan")
        table.add_column("Commit", style="dim")
        table.add_column("Path")

        for wt in worktrees:
            # Get relative path if possible
            try:
                path = Path(wt["path"])
                if path.exists():
                    rel_path = path.relative_to(Path.cwd())
                    display_path = f"[dim]{rel_path}[/dim]" if "/" in str(rel_path) else str(path)
                else:
                    display_path = wt["path"]
            except Exception:
                display_path = wt["path"]

            table.add_row(
                wt["branch"],
                wt["commit"][:8],
                display_path,
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(worktrees)} worktrees[/dim]")

    except Exception as e:
        console.print(f"[red]✗ Error listing worktrees: {e}[/red]")


def _do_create(branch: str | None, _base: str, location: Path | None) -> None:
    """Create a new worktree.

    Args:
        branch: Branch name
        base: Base branch
        location: Custom location
    """
    if not branch:
        console.print("[red]✗ Branch name required[/red]")
        console.print("[dim]Usage: vibe worktree create BRANCH[/dim]")
        raise typer.Exit(1)

    console.print(f"[dim]Creating worktree for branch: {branch}[/dim]")

    # Prepare git worktree add command
    cmd = ["git", "worktree", "add"]

    if location:
        cmd.extend([str(location), branch])
    else:
        cmd.extend([f".git/worktrees/{branch}", branch])

    try:
        subprocess.run(cmd, check=True)
        console.print("[green]✓ Worktree created[/green]\n")
        console.print(f"  Branch: {branch}")
        if location:
            console.print(f"  Location: {location}")
        console.print("\n[dim]To use the worktree:[/dim]")
        console.print(f"  [cyan]cd {location or f'.git/worktrees/{branch}'}[/cyan]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]✗ Failed to create worktree: {e}[/red]")
        raise typer.Exit(1) from None


def _do_remove(branch: str | None, force: bool) -> None:
    """Remove a worktree.

    Args:
        branch: Branch name
        force: Force removal
    """
    if not branch:
        console.print("[red]✗ Branch name required[/red]")
        console.print("[dim]Usage: vibe worktree remove BRANCH[/dim]")
        raise typer.Exit(1)

    if not force:
        console.print(f"[yellow]⚠️  This will remove the worktree for '{branch}'[/yellow]")
        console.print("[dim]Use --force to proceed without confirmation[/dim]")
        raise typer.Exit(1)

    console.print(f"[dim]Removing worktree: {branch}[/dim]")

    try:
        subprocess.run(
            ["git", "worktree", "remove", branch],
            check=True,
        )
        console.print("[green]✓ Worktree removed[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]✗ Failed to remove worktree: {e}[/red]")
        raise typer.Exit(1) from None


def _do_cleanup(_force: bool) -> None:
    """Clean up finished/merged branches worktrees."""
    console.print("[dim]Cleaning up worktrees for merged branches...[/dim]")

    # List worktrees
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        console.print("[dim]No worktrees to clean up[/dim]")
        return

    lines = result.stdout.strip().split("\n")
    count = 0

    for line in lines:
        if not line:
            continue
        parts = line.split(" ")
        if len(parts) >= 2:
            branch = parts[1].strip("[]")
            # Check if branch is merged
            try:
                merge_result = subprocess.run(
                    ["git", "branch", "--merged", branch],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if branch in merge_result.stdout:
                    console.print(f"[dim]Removing merged branch worktree: {branch}[/dim]")
                    subprocess.run(
                        ["git", "worktree", "remove", branch],
                        capture_output=True,
                        check=False,
                    )
                    count += 1
            except Exception:
                pass
    console.print(f"[green]✓ Cleaned up {count} worktree(s)[/green]")


def _do_finish(branch: str | None) -> None:
    """Finish working on a worktree branch.

    Args:
        branch: Branch name
    """
    if not branch:
        console.print("[red]✗ Branch name required[/red]")
        console.print("[dim]Usage: vibe worktree finish BRANCH[/dim]")
        raise typer.Exit(1)

    console.print(f"[bold]Finishing work on: {branch}[/bold]\n")

    console.print("[dim]Next steps:[/dim]")
    console.print(f"  1. [cyan]git checkout {branch}[/cyan]")
    console.print(f"  2. [cyan]git merge {branch}[/cyan]")
    console.print(f"  3. [cyan]vibe worktree remove {branch}[/cyan]")
