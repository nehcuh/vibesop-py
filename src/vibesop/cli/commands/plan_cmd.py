"""Plan management CLI commands.

vibe plan list
vibe plan show <plan_id>
vibe plan status
vibe plan complete-step <step_id> [--result "summary"]
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from vibesop.cli.orchestration_report import render_orchestration_result, render_plan_status
from vibesop.core.models import StepStatus
from vibesop.core.orchestration import PlanTracker

app = typer.Typer(name="plan", help="Manage multi-skill execution plans")
console = Console()


def _get_tracker() -> PlanTracker:
    return PlanTracker(storage_dir=Path.cwd() / ".vibe")


@app.command("list")
def plan_list(
    limit: int = typer.Option(10, "--limit", "-n", help="Max plans to show"),
) -> None:
    """List recent execution plans."""
    tracker = _get_tracker()
    plans = tracker.list_plans(limit=limit)

    if not plans:
        console.print("[dim]No execution plans found.[/dim]")
        raise typer.Exit(0)

    console.print(f"[bold]Recent Plans ({len(plans)}):[/bold]\n")
    for plan in plans:
        status_icon = {
            "pending": "⏳",
            "active": "🔄",
            "completed": "✅",
        }.get(plan.status.value, "❓")

        console.print(
            f"{status_icon} [bold]{plan.plan_id}[/bold] "
            f"[dim]({len(plan.steps)} steps, {plan.status.value})[/dim]"
        )
        console.print(f"   [dim]{plan.original_query[:60]}...[/dim]\n")


@app.command("show")
def plan_show(
    plan_id: str = typer.Argument(..., help="Plan ID to show"),
) -> None:
    """Show details of a specific execution plan."""
    tracker = _get_tracker()
    plan = tracker.get_plan(plan_id)

    if plan is None:
        console.print(f"[red]Plan {plan_id} not found[/red]")
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
    plan = tracker.get_active_plan()

    if plan is None:
        console.print("[dim]No active plan.[/dim]")
        raise typer.Exit(0)

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
        plan = tracker.get_active_plan()
        if plan is None:
            console.print("[red]No active plan. Use --plan to specify.[/red]")
            raise typer.Exit(1)
        plan_id = plan.plan_id

    tracker.update_step_status(
        plan_id=plan_id,
        step_id=step_id,
        status=StepStatus.COMPLETED,
        result_summary=result,
    )
    console.print(f"[green]✅ Step {step_id} marked as completed[/green]")
