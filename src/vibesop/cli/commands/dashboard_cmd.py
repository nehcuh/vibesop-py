"""``vibe dashboard`` — Start the web dashboard server."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

console = Console()


def dashboard(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        "-h",
        help="Host to bind to",
    ),
    port: int = typer.Option(
        8420,
        "--port",
        "-p",
        help="Port to listen on",
    ),
    open_browser: bool = typer.Option(
        True,
        "--open/--no-open",
        help="Automatically open browser",
    ),
    project_root: Path | None = typer.Option(
        None,
        "--project",
        "-P",
        help="Project root directory (default: auto-detect from cwd)",
    ),
) -> None:
    """Start the VibeSOP web dashboard for background visualization.

    Opens a local web server that displays:
      - Routing health & statistics
      - Recent routing history (from analytics.jsonl)
      - Trace decision trees (from traces/)
      - Multi-turn conversation history (from conversations/)
    """
    try:
        from vibesop.dashboard.server import run_server
    except ImportError:
        console.print(
            "[red]✗ Dashboard server module not found.[/red]\n"
            "[dim]This indicates a broken installation. Try:[/dim]\n"
            "  [cyan]uv tool install --reinstall vibesop[/cyan]"
        )
        raise typer.Exit(1) from None

    url = f"http://{host}:{port}"

    console.print()
    console.print(
        f"[bold cyan]⚡ VibeSOP Dashboard[/bold cyan]\n"
        f"[dim]Starting server at[/dim] [bold]{url}[/bold]\n"
    )

    if open_browser:
        import webbrowser

        webbrowser.open(url)

    console.print(
        "[dim]Press Ctrl+C to stop.[/dim]\n"
    )

    run_server(
        host=host,
        port=port,
        project_root=str(project_root) if project_root else None,
    )
