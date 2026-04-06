"""VibeSOP instinct command - Manage adaptive decision patterns."""

import typer
from rich.console import Console

from vibesop.core.instinct.learner import InstinctLearner

console = Console()


def instinct(
    action: str = typer.Argument(..., help="Action: stats, learn"),
    context: str | None = typer.Argument(None, help="Context description"),
    decision: str | None = typer.Option(
        None,
        "--decision",
        "-d",
        help="Decision that was made",
    ),
    outcome: str = typer.Option(
        "positive",
        "--outcome",
        "-o",
        help="Outcome: positive, negative, neutral",
    ),
) -> None:
    """Manage adaptive decision patterns."""
    learner = InstinctLearner()

    if action == "stats":
        _do_stats(learner)
    elif action == "learn":
        _do_learn(learner, context, decision, outcome)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n[dim]Valid actions: stats, learn[/dim]"
        )
        raise typer.Exit(1)


def _do_stats(learner: InstinctLearner) -> None:
    """Show instinct statistics."""
    console.print(f"\n[bold cyan]📊 Instinct Statistics[/bold cyan]\n{'=' * 40}\n")

    stats = learner.get_statistics()

    console.print(f"  [dim]Total patterns:[/dim] {stats.get('total_patterns', 0)}")
    console.print(f"  [dim]Total decisions:[/dim] {stats.get('total_decisions', 0)}")
    console.print(f"  [dim]Overall success rate:[/dim] {stats.get('overall_success_rate', 0):.1%}")

    if "decisions_by_action" in stats:
        console.print("\n[bold]Decisions by Action:[/bold]")
        for action_name, count in stats["decisions_by_action"].items():
            console.print(f"  {action_name}: {count}")


def _do_learn(
    learner: InstinctLearner,
    context: str | None,
    decision: str | None,
    outcome: str,
) -> None:
    """Learn from a decision."""
    if not context:
        console.print("[red]✗ Context required for learn action[/red]")
        console.print("[dim]Usage: vibe instinct learn CONTEXT --decision DECISION[/dim]")
        raise typer.Exit(1)

    if not decision:
        console.print("[red]✗ --decision required for learn action[/red]")
        raise typer.Exit(1)

    success = outcome.lower() in ("positive", "good", "success", "+", "1", "true")

    learner.record_selection(decision, context, was_helpful=success)

    console.print(
        f"[green]✓ Learned from decision[/green]\n"
        f"  [dim]Context:[/dim] {context}\n"
        f"  [dim]Decision:[/dim] {decision}\n"
        f"  [dim]Outcome:[/dim] {outcome}\n"
    )
