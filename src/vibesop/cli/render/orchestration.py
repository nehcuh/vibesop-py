"""Orchestration result renderers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from vibesop.core.models import OrchestrationResult


def render_compact_orchestration(
    result: OrchestrationResult,
    console: Console | None = None,
) -> None:
    """Render a compact summary directly from OrchestrationResult."""
    if console is None:
        console = Console()

    table = Table(
        title="[bold cyan]🔍 Routing Summary[/bold cyan]",
        box=box.SIMPLE,
        show_header=False,
        padding=(0, 1),
    )
    table.add_column("Field", style="dim", justify="right")
    table.add_column("Value", style="bold")

    if result.mode.value == "single":
        if result.primary:
            if result.primary.layer.value == "fallback_llm":
                table.add_row("Selected", f"[yellow]{result.primary.skill_id}[/yellow]")
                table.add_row("Status", "[yellow]Fallback (no skill matched)[/yellow]")
            else:
                table.add_row("Selected", f"[green]{result.primary.skill_id}[/green]")
                table.add_row("Confidence", f"{result.primary.confidence:.0%}")
                table.add_row("Layer", result.primary.layer.value)
        else:
            table.add_row("Selected", "[yellow]No match[/yellow]")

        table.add_row("Duration", f"{result.duration_ms:.1f}ms")

        if result.alternatives:
            alt_lines = []
            for alt in result.alternatives[:3]:
                alt_lines.append(f"  • {alt.skill_id} ({alt.confidence:.0%} via {alt.layer.value})")
            table.add_row("Alternatives", "\n".join(alt_lines))
    else:
        plan = result.execution_plan
        if plan:
            table.add_row("Mode", "[cyan]Orchestrated[/cyan]")
            table.add_row("Steps", str(len(plan.steps)))
            table.add_row("Strategy", plan.execution_mode.value)

            step_lines = []
            for step in plan.steps:
                step_lines.append(f"  {step.step_number}. {step.skill_id} — {step.intent}")
            table.add_row("Plan", "\n".join(step_lines))

            if result.single_fallback:
                table.add_row(
                    "Fallback",
                    f"{result.single_fallback.skill_id} ({result.single_fallback.confidence:.0%})",
                )
        else:
            table.add_row("Mode", "[yellow]Orchestrated (no plan)[/yellow]")

    console.print(table)
    console.print()
