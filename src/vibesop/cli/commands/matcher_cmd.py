"""CLI commands for custom matcher plugin management.

Commands:
    vibe matcher list      — List registered custom matchers
    vibe matcher register  — Register a new matcher from a Python file
    vibe matcher remove    — Remove a registered matcher
    vibe matcher reload    — Reload all matchers from disk
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from vibesop.core.matching.plugin import MatcherPluginRegistry

app = typer.Typer(name="matcher", help="Manage custom matcher plugins")
console = Console()

_PROJECT_ROOT_OPTION = typer.Option(
    None, "--project-root", help="Project root directory"
)


@app.command("list")
def list_matchers(
    project_root: Path | None = _PROJECT_ROOT_OPTION,
) -> None:
    """List all registered custom matcher plugins."""
    root = project_root or Path.cwd()
    registry = MatcherPluginRegistry(root)
    plugins = registry.list_plugins()

    if not plugins:
        console.print("[dim]No custom matchers registered.[/dim]")
        console.print("\n[dim]Create one:[/dim]")
        console.print("  1. Write a Python file with a `match(query, candidate) -> float` function")
        console.print("  2. vibe matcher register <path>")
        return

    console.print("\n[bold]Custom Matchers[/bold]\n")
    for p in plugins:
        console.print(f"  [cyan]{p.name}[/cyan]  (weight: {p.weight})")
        if p.description:
            console.print(f"    [dim]{p.description}[/dim]")
        console.print(f"    [dim]Source: {p.source_file}[/dim]")
        console.print()


@app.command("register")
def register_matcher(
    file_path: Path = typer.Argument(..., help="Path to matcher Python file"),  # noqa: B008
    project_root: Path | None = _PROJECT_ROOT_OPTION,
) -> None:
    """Register a new custom matcher plugin from a Python file.

    The file must define a `match(query: str, candidate: dict) -> float` function.
    Optional: NAME, DESCRIPTION, WEIGHT variables.
    """
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)

    root = project_root or Path.cwd()
    registry = MatcherPluginRegistry(root)
    plugin = registry.register(file_path)

    if plugin:
        console.print(f"[green]✓ Registered matcher: {plugin.name}[/green]")
        if plugin.description:
            console.print(f"  [dim]{plugin.description}[/dim]")
    else:
        console.print("[red]✗ Failed to register matcher[/red]")
        console.print("[dim]Ensure the file defines a `match(query, candidate) -> float` function.[/dim]")
        raise typer.Exit(1)


@app.command("remove")
def remove_matcher(
    name: str = typer.Argument(..., help="Name of the matcher to remove"),
    project_root: Path | None = _PROJECT_ROOT_OPTION,
) -> None:
    """Remove a registered custom matcher."""
    root = project_root or Path.cwd()
    registry = MatcherPluginRegistry(root)
    if registry.remove(name):
        console.print(f"[green]✓ Removed matcher: {name}[/green]")
    else:
        console.print(f"[yellow]Matcher not found: {name}[/yellow]")


@app.command("reload")
def reload_matchers(
    project_root: Path | None = _PROJECT_ROOT_OPTION,
) -> None:
    """Reload all custom matchers from disk."""
    root = project_root or Path.cwd()
    registry = MatcherPluginRegistry(root)
    registry.reload()
    count = len(registry.list_plugins())
    console.print(f"[green]✓ Reloaded {count} matcher(s)[/green]")
