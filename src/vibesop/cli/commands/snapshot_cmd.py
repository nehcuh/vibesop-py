"""Snapshot cleanup CLI commands.

Provides:
- vibe snapshot cleanup: Clean up old snapshots (default: keep 7 days)
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

from vibesop.installer.transactional import TransactionalInstaller

app = typer.Typer(name="snapshot", help="Manage installation snapshots")
console = Console()


@app.command()
def cleanup(
    days: int = typer.Option(7, "--days", "-d", help="Keep snapshots from the last N days"),
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
) -> None:
    """Clean up old snapshots, keeping only the last N days."""
    installer = TransactionalInstaller(
        snapshot_dir=__import__("pathlib").Path(project_root) / ".vibe" / "snapshots"
    )
    result = installer.cleanup_old_snapshots(days=days)

    console.print(
        Panel(
            f"[bold green]Snapshot cleanup complete[/bold green]\n\n"
            f"Kept: [bold]{result['kept']}[/bold] snapshots\n"
            f"Removed: [bold red]{result['removed']}[/bold red] snapshots\n"
            f"Retention: last {days} days",
            title="vibe snapshot cleanup",
            border_style="green",
        )
    )
