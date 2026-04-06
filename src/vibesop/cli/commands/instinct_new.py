"""VibeSOP instinct command - Manage learned patterns.

This command allows you to learn from experience and
extract reusable instincts for better decision-making.

Usage:
    vibe instinct stats
    vibe instinct learn PATTERN --action ACTION
    vibe instinct list
    vibe instinct export
    vibe instinct --help

Examples:
    # Show statistics
    vibe instinct stats

    # Learn a new instinct
    vibe instinct learn "user asks about debugging" --action "suggest systematic-debugging"

    # List all instincts
    vibe instinct list

    # Find matching instincts
    vibe instinct match "how do I debug this error"

    # Export for routing
    vibe instinct export
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.instinct.learner import InstinctLearner

console = Console()


def stats() -> None:
    """Show instinct statistics."""
    learner = InstinctLearner()
    stats_data = learner.get_stats()

    console.print(f"\n[bold cyan]📊 Instinct Statistics[/bold cyan]\n{'=' * 40}\n")

    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value")

    table.add_row("Total Instincts", str(stats_data["total_instincts"]))
    table.add_row("Reliable Instincts", str(stats_data["reliable_instincts"]))
    table.add_row("Average Confidence", f"{stats_data['avg_confidence']:.2%}")

    console.print(table)

    if stats_data["by_source"]:
        console.print("\n[bold]By Source:[/bold]")
        for source, count in stats_data["by_source"].items():
            console.print(f"  {source}: {count}")


def learn(
    pattern: str = typer.Argument(..., help="Pattern to match (what to look for)"),
    action: str = typer.Option(..., "--action", "-a", help="Action to take when pattern matches"),
    context: str | None = typer.Option(None, "--context", "-c", help="When this applies"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Tag for categorization"),
) -> None:
    """Learn a new instinct."""
    learner = InstinctLearner()

    instinct = learner.learn(
        pattern=pattern,
        action=action,
        context=context or "",
        tags=[tag] if tag else [],
        source="manual",
    )

    console.print(
        Panel(
            f"[green]✓ Learned new instinct[/green]\n\n"
            f"[dim]Pattern:[/dim] {pattern}\n"
            f"[dim]Action:[/dim] {action}\n"
            f"[dim]ID:[/dim] {instinct.id}\n"
            f"[dim]Confidence:[/dim] {instinct.confidence:.2%}",
            title="Instinct Learned",
        )
    )


def list_all(
    reliable_only: bool = typer.Option(
        False, "--reliable", "-r", help="Show only reliable instincts"
    ),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag"),
) -> None:
    """List all instincts."""
    learner = InstinctLearner()

    if reliable_only:
        instincts = learner.get_reliable_instincts(tag=tag)
        title = "Reliable Instincts"
    else:
        instincts = list(learner._instincts.values())
        if tag:
            instincts = [i for i in instincts if tag in i.tags]
        title = "All Instincts"

    if not instincts:
        console.print("[dim]No instincts found[/dim]")
        return

    console.print(f"\n[bold cyan]{title}[/bold cyan] ({len(instincts)})\n{'=' * 60}\n")

    table = Table()
    table.add_column("ID", style="cyan", max_width=20)
    table.add_column("Pattern", max_width=40)
    table.add_column("Action", max_width=30)
    table.add_column("Conf", justify="right")
    table.add_column("Success", justify="right")

    for instinct in instincts[:20]:  # Show first 20
        table.add_row(
            instinct.id[:16],
            instinct.pattern[:40],
            instinct.action[:30],
            f"{instinct.confidence:.0%}",
            f"{instinct.success_count}/{instinct.total_applications}",
        )

    console.print(table)

    if len(instincts) > 20:
        console.print(f"\n[dim]... and {len(instincts) - 20} more[/dim]")


def match(
    query: str = typer.Argument(..., help="Query to match against instincts"),
    context: str | None = typer.Option(None, "--context", "-c", help="Additional context"),
    min_confidence: float = typer.Option(
        0.5, "--min-confidence", help="Minimum confidence threshold"
    ),
) -> None:
    """Find instincts matching a query."""
    learner = InstinctLearner()

    matches = learner.find_matching(query, context or "", min_confidence)

    if not matches:
        console.print("[dim]No matching instincts found[/dim]")
        return

    console.print(f"\n[bold cyan]Matching Instincts[/bold cyan]\n{'=' * 60}\n")

    for i, instinct in enumerate(matches[:5], 1):
        console.print(f"{i}. [cyan]{instinct.pattern}[/cyan]")
        console.print(f"   Action: {instinct.action}")
        console.print(
            f"   Confidence: {instinct.confidence:.0%} ({instinct.success_count} successes)"
        )
        console.print()


def record(
    instinct_id: str = typer.Argument(..., help="ID of the instinct"),
    success: bool = typer.Option(
        ..., "--success/--failure", help="Whether the instinct led to success"
    ),
) -> None:
    """Record outcome of using an instinct."""
    learner = InstinctLearner()

    if instinct_id not in learner._instincts:
        console.print(f"[red]✗ Instinct not found: {instinct_id}[/red]")
        raise typer.Exit(1)

    learner.record_outcome(instinct_id, success)

    instinct = learner._instincts[instinct_id]
    console.print(
        f"[green]✓ Recorded outcome[/green]\n"
        f"  Instinct: {instinct.pattern[:40]}...\n"
        f"  Outcome: {'Success' if success else 'Failure'}\n"
        f"  New confidence: {instinct.confidence:.0%}\n"
        f"  Success rate: {instinct.success_rate:.0%} ({instinct.total_applications} trials)"
    )


def export(
    output: str | None = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
) -> None:
    """Export instincts for routing."""
    import json

    learner = InstinctLearner()
    routing_data = learner.export_for_routing()

    json_output = json.dumps(routing_data, indent=2)

    if output:
        Path(output).write_text(json_output)
        console.print(f"[green]✓ Exported {len(routing_data)} instincts to {output}[/green]")
    else:
        console.print(json_output)


# Create the CLI app
app = typer.Typer(
    help="Manage learned instincts and patterns",
    name="instinct",
)

app.command("stats")(stats)
app.command("learn")(learn)
app.command("list")(list_all)
app.command("match")(match)
app.command("record")(record)
app.command("export")(export)
