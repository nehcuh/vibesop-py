"""Plan management CLI commands.

vibe plan list
vibe plan show <plan_id>
vibe plan status
vibe plan complete-step <step_id> [--result "summary"]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from vibesop.cli.orchestration_report import render_orchestration_result, render_plan_status
from vibesop.core.models import StepStatus
from vibesop.core.orchestration import PlanTracker

app = typer.Typer(name="plan", help="Manage multi-skill execution plans")
console = Console()


def _get_tracker() -> PlanTracker:
    return PlanTracker(storage_dir=Path.cwd() / ".vibe")


def _safe_tracker_read(op: Any, *args: Any, **kwargs: Any):
    """Run a tracker read/update; lock contention is a clean CLI error (8.3.1 C-U1)."""
    from vibesop.utils.file_lock import CouldNotLock

    try:
        return op(*args, **kwargs)
    except CouldNotLock:
        console.print("[red]Plan store is locked by another process; try again shortly.[/red]")
        raise typer.Exit(1) from None


@app.command("list")
def plan_list(
    limit: int = typer.Option(10, "--limit", "-n", help="Max plans to show"),
) -> None:
    """List recent execution plans."""
    tracker = _get_tracker()
    plans = _safe_tracker_read(tracker.list_plans, limit=limit)

    if not plans:
        console.print("[dim]No execution plans found.[/dim]")
        raise typer.Exit(0)

    console.print(f"[bold]Recent Plans ({len(plans)}):[/bold]\n")
    for plan in plans:
        blocked = not plan.metadata.get("execution_ready", False)
        status_icon = {
            "pending": "⏳",
            "active": "🔄",
            "completed": "✅",
            "failed": "❌",
            "partial": "⚠️",
            "terminated_early": "🛑",
        }.get(plan.status.value, "❓")
        if blocked:
            status_icon = "🚫"

        state_label = "blocked" if blocked else plan.status.value
        console.print(
            f"{status_icon} [bold]{plan.plan_id}[/bold] "
            f"[dim]({len(plan.steps)} steps, {state_label})[/dim]"
        )
        if blocked:
            reasons = ", ".join(
                str(b.get("reason", "?")) for b in (plan.metadata.get("blocked_steps") or [])[:2]
            )
            console.print(f"   [red]blocked: {reasons}[/red]")
        console.print(f"   [dim]{plan.original_query[:60]}...[/dim]\n")


def _blocked_notice(plan: Any) -> str:
    from vibesop.agent.runtime.skill_injector import SkillInjector

    return SkillInjector.blocked_plan_notice(plan.to_dict())


@app.command("show")
def plan_show(
    plan_id: str = typer.Argument(..., help="Plan ID to show"),
) -> None:
    """Show details of a specific execution plan."""
    tracker = _get_tracker()
    plan = _safe_tracker_read(tracker.get_plan, plan_id)

    if plan is None:
        console.print(f"[red]Plan {plan_id} not found[/red]")
        raise typer.Exit(1)

    if not plan.metadata.get("execution_ready", False):
        console.print(f"[red]{_blocked_notice(plan)}[/red]")
        raise typer.Exit(1)

    from vibesop.core.models import OrchestrationMode, OrchestrationResult

    result = OrchestrationResult(
        mode=OrchestrationMode.ORCHESTRATED,
        original_query=plan.original_query,
        execution_plan=plan,
    )
    render_orchestration_result(result, console=console)


@app.command("status")
def plan_status() -> None:
    """Show status of the active execution plan."""
    tracker = _get_tracker()
    plan = _safe_tracker_read(tracker.get_active_plan)

    if plan is None:
        console.print("[dim]No active plan.[/dim]")
        raise typer.Exit(0)

    if not plan.metadata.get("execution_ready", False):
        console.print(f"[red]{_blocked_notice(plan)}[/red]")
        raise typer.Exit(1)

    render_plan_status(plan, console=console)


@app.command("complete-step")
def plan_complete_step(
    step_id: str = typer.Argument(..., help="Step ID to mark complete"),
    result: str | None = typer.Option(None, "--result", "-r", help="Brief result summary"),
    plan_id: str | None = typer.Option(
        None, "--plan", "-p", help="Plan ID (defaults to active plan)"
    ),
) -> None:
    """Mark an execution step as completed."""
    tracker = _get_tracker()

    if plan_id is None:
        plan = _safe_tracker_read(tracker.get_active_plan)
        if plan is None:
            console.print("[red]No active plan. Use --plan to specify.[/red]")
            raise typer.Exit(1)
    else:
        plan = _safe_tracker_read(tracker.get_plan, plan_id)
        if plan is None:
            console.print(f"[red]Plan {plan_id} not found[/red]")
            raise typer.Exit(1)

    if not plan.metadata.get("execution_ready", False):
        # Blocked plans must not be mutated toward completion.
        console.print(f"[red]Plan {plan.plan_id} is blocked:[/red]")
        console.print(f"[red]{_blocked_notice(plan)}[/red]")
        raise typer.Exit(1)

    _safe_tracker_read(
        tracker.update_step_status,
        plan_id=plan.plan_id,
        step_id=step_id,
        status=StepStatus.COMPLETED,
        result_summary=result,
    )
    console.print(f"[green]✅ Step {step_id} marked as completed[/green]")
