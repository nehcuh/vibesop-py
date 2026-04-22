"""Rich rendering for orchestration results and execution plans."""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from vibesop.core.models import ExecutionPlan, OrchestrationResult, StepStatus


def render_orchestration_result(
    result: OrchestrationResult,
    console: Console | None = None,
) -> None:
    """Render an orchestration result (single skill or multi-step plan)."""
    if console is None:
        console = Console()

    if result.mode.value == "single":
        _render_single_result(result, console)
    else:
        _render_orchestrated_result(result, console)


def _render_single_result(result: OrchestrationResult, console: Console) -> None:
    """Render single-skill fallback."""
    if result.primary:
        console.print(
            Panel(
                f"[bold green]✅ Matched:[/bold green] {result.primary.skill_id}\n"
                f"[dim]Confidence:[/dim] {result.primary.confidence:.0%}\n"
                f"[dim]Layer:[/dim] {result.primary.layer.value}",
                title="[bold]Single Skill Result[/bold]",
                border_style="blue",
            )
        )
    else:
        console.print(
            Panel(
                "[yellow]❓ No match found[/yellow]",
                title="[bold]Single Skill Result[/bold]",
                border_style="yellow",
            )
        )


def _render_orchestrated_result(result: OrchestrationResult, console: Console) -> None:
    """Render multi-step execution plan."""
    plan = result.execution_plan
    if plan is None:
        console.print("[red]Error: orchestrated result with no plan[/red]")
        return

    # Header
    header_text = (
        f"[bold]Query:[/bold] {plan.original_query}\n"
        f"[bold]Plan ID:[/bold] {plan.plan_id}\n"
        f"[dim]Detected intents:[/dim] {', '.join(plan.detected_intents)}\n"
        f"[dim]Steps:[/dim] {len(plan.steps)}"
    )

    console.print(
        Panel(
            header_text,
            title="[bold cyan]🔀 Multi-Intent Execution Plan[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    # Steps table
    table = Table(show_header=True, box=box.SIMPLE)
    table.add_column("Step", style="dim", justify="right")
    table.add_column("Skill", style="bold")
    table.add_column("Intent", style="italic")
    table.add_column("Status")

    status_icons = {
        StepStatus.PENDING: "⏳",
        StepStatus.IN_PROGRESS: "🔄",
        StepStatus.COMPLETED: "✅",
        StepStatus.SKIPPED: "⏭️",
    }

    for step in plan.steps:
        icon = status_icons.get(step.status, "❓")
        status_color = {
            StepStatus.PENDING: "dim",
            StepStatus.IN_PROGRESS: "yellow",
            StepStatus.COMPLETED: "green",
            StepStatus.SKIPPED: "dim",
        }.get(step.status, "white")

        table.add_row(
            str(step.step_number),
            step.skill_id,
            step.intent,
            f"[{status_color}]{icon} {step.status.value}[/{status_color}]",
        )

    console.print(table)

    if plan.reasoning:
        console.print(f"\n[dim]Reasoning:[/dim] {plan.reasoning}")

    if result.single_fallback:
        console.print(
            f"\n[dim]Fallback skill:[/dim] {result.single_fallback.skill_id} "
            f"({result.single_fallback.confidence:.0%})"
        )


def render_plan_status(plan: ExecutionPlan, console: Console | None = None) -> None:
    """Render current status of an active plan."""
    if console is None:
        console = Console()

    total = len(plan.steps)
    completed = sum(1 for s in plan.steps if s.status == StepStatus.COMPLETED)
    in_progress = sum(1 for s in plan.steps if s.status == StepStatus.IN_PROGRESS)
    pending = sum(1 for s in plan.steps if s.status == StepStatus.PENDING)
    skipped = sum(1 for s in plan.steps if s.status == StepStatus.SKIPPED)

    progress = f"{completed}/{total} completed"
    if in_progress:
        progress += f", {in_progress} in progress"
    if pending:
        progress += f", {pending} pending"
    if skipped:
        progress += f", {skipped} skipped"

    console.print(
        Panel(
            f"[bold]{plan.plan_id}[/bold]\n"
            f"{progress}\n"
            f"[dim]Status:[/dim] {plan.status.value}",
            title="[bold]Plan Status[/bold]",
            border_style="blue" if plan.status.value == "active" else "dim",
        )
    )

    # Show current step if active
    for step in plan.steps:
        if step.status == StepStatus.IN_PROGRESS:
            console.print(f"\n[bold yellow]Current step:[/bold yellow] {step.step_number}. {step.skill_id}")
            console.print(f"[dim]Query:[/dim] {step.input_query[:100]}...")
            break
