"""VibeSOP instinct command - Manage adaptive decision patterns.

This command allows viewing and managing learned instinct
patterns for adaptive decision-making.

Usage:
    vibe instinct stats
    vibe instinct learn CONTEXT --decision DECISION --outcome positive
    vibe instinct --help

Examples:
    # Show statistics
    vibe instinct stats

    # Learn from a decision
    vibe instinct learn "error handling" --decision "use systematic-debugging" --outcome positive
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from vibesop.workflow.instinct import InstinctManager, DecisionContext, ActionType, ConfidenceLevel

console = Console()


def instinct(
    action: str = typer.Argument(..., help="Action: stats, learn"),
    context: Optional[str] = typer.Argument(None, help="Context description"),
    decision: Optional[str] = typer.Option(
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
    """Manage adaptive decision patterns.

    This command allows you to learn from decisions and
    view statistics about adaptive patterns.

    \b
    Examples:
        # Show statistics
        vibe instinct stats

        # Learn from a decision
        vibe instinct learn "error handling" --decision "use systematic-debugging" --outcome positive
    """
    manager = InstinctManager()

    if action == "stats":
        _do_stats(manager)
    elif action == "learn":
        _do_learn(manager, context, decision, outcome)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n"
            f"[dim]Valid actions: stats, learn[/dim]"
        )
        raise typer.Exit(1)


def _do_stats(manager: InstinctManager) -> None:
    """Show instinct statistics.

    Args:
        manager: InstinctManager instance
    """
    console.print(
        f"\n[bold cyan]📊 Instinct Statistics[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    stats = manager.get_statistics()

    console.print(f"  [dim]Total patterns:[/dim] {stats.get('total_patterns', 0)}")
    console.print(f"  [dim]Total decisions:[/dim] {stats.get('total_decisions', 0)}")
    console.print(f"  [dim]Overall success rate:[/dim] {stats.get('overall_success_rate', 0):.1%}")

    # Show by action
    if "decisions_by_action" in stats:
        console.print(f"\n[bold]Decisions by Action:[/bold]")
        for action, count in stats["decisions_by_action"].items():
            console.print(f"  {action}: {count}")


def _do_learn(
    manager: InstinctManager,
    context: str | None,
    decision: str | None,
    outcome: str,
) -> None:
    """Learn from a decision.

    Args:
        manager: InstinctManager instance
        context: Decision context description
        decision: Decision that was made
        outcome: Outcome of the decision
    """
    if not context:
        console.print("[red]✗ Context required for learn action[/red]")
        console.print("[dim]Usage: vibe instinct learn CONTEXT --decision DECISION[/dim]")
        raise typer.Exit(1)

    if not decision:
        console.print("[red]✗ --decision required for learn action[/red]")
        raise typer.Exit(1)

    # Map outcome to boolean
    success = outcome.lower() in ("positive", "good", "success", "+", "1", "true")

    # Create a decision context
    decision_context = DecisionContext(
        situation_type="general",
        user_goal=context,
        recent_history=[],
        success_rate=0.5,
        time_pressure=0.5,
        complexity=0.5,
    )

    # Create and record the decision
    from vibesop.workflow.instinct import Decision
    from datetime import datetime
    import uuid

    recorded_decision = Decision(
        decision_id=str(uuid.uuid4())[:8],
        action_type=ActionType.USE_SKILL,
        target=decision,
        confidence=ConfidenceLevel.MEDIUM,
        reason=f"User chose: {decision}",
        context=decision_context,
        outcome=None,
        timestamp=datetime.now().isoformat(),
    )

    # Add to decision history (required for persistence)
    manager._decisions.append(recorded_decision)

    # Record outcome
    manager.record_outcome(recorded_decision, success, outcome)

    console.print(
        f"[green]✓ Learned from decision[/green]\n"
        f"  [dim]Context:[/dim] {context}\n"
        f"  [dim]Decision:[/dim] {decision}\n"
        f"  [dim]Outcome:[/dim] {outcome}\n"
    )
