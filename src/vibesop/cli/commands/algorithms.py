"""VibeSOP algorithms command - List available algorithm library functions.

Usage:
    vibe algorithms list
"""

import typer
from rich.console import Console
from rich.table import Table

from vibesop.core.algorithms import AlgorithmRegistry

console = Console()


def algorithms_list() -> None:
    """List all registered algorithms in the VibeSOP algorithm library."""
    algorithms = AlgorithmRegistry.list_algorithms()

    if not algorithms:
        console.print("[dim]No algorithms registered.[/dim]")
        raise typer.Exit(0)

    table = Table()
    table.add_column("Algorithm", style="cyan")
    table.add_column("Description")

    for algo in algorithms:
        table.add_row(algo["name"], algo["description"] or "[dim]—[/dim]")

    console.print(f"\n[bold cyan]🧠 Algorithm Library ({len(algorithms)} registered)[/bold cyan]\n")
    console.print(table)
    console.print()
