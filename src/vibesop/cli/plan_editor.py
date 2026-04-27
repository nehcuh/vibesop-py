"""Interactive execution plan editor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import questionary

if TYPE_CHECKING:
    from rich.console import Console


def _edit_execution_plan(result: Any, console: Console) -> bool:  # pyright: ignore[reportUnusedFunction]
    """Interactive execution plan editor.

    Returns True if plan was modified, False otherwise.
    """
    plan = result.execution_plan
    if plan is None or not plan.steps:
        console.print("[yellow]No steps to edit.[/yellow]")
        return False

    steps = list(plan.steps)
    while True:
        console.print("\n[bold]✏️  Edit Execution Plan[/bold]\n")
        for i, step in enumerate(steps, 1):
            marker = "  "
            console.print(f"  {marker}{i}. {step.skill_id} — {step.intent}")

        action = questionary.select(
            "Choose an action:",
            choices=[
                questionary.Choice("↑ Move step up", value="up"),
                questionary.Choice("↓ Move step down", value="down"),
                questionary.Choice("✗ Remove step", value="remove"),
                questionary.Choice("✓ Done editing", value="done"),
                questionary.Choice("↩️  Cancel", value="cancel"),
            ],
        ).ask()

        if action in ("done", None):
            if not steps:
                console.print("[yellow]⚠️  Plan has no steps. Edit cancelled.[/yellow]")
                return False
            plan.steps = steps
            for i, step in enumerate(steps, 1):
                step.step_number = i
            console.print("[green]✓ Plan updated[/green]")
            return True
        elif action == "cancel":
            console.print("[dim]Edit cancelled.[/dim]")
            return False
        elif action == "up":
            idx = questionary.select(
                "Select step to move up:",
                choices=[
                    questionary.Choice(f"{s.step_number}. {s.skill_id}", value=i)
                    for i, s in enumerate(steps)
                ],
            ).ask()
            if idx is not None and idx > 0:
                steps[idx - 1], steps[idx] = steps[idx], steps[idx - 1]
        elif action == "down":
            idx = questionary.select(
                "Select step to move down:",
                choices=[
                    questionary.Choice(f"{s.step_number}. {s.skill_id}", value=i)
                    for i, s in enumerate(steps)
                ],
            ).ask()
            if idx is not None and idx < len(steps) - 1:
                steps[idx + 1], steps[idx] = steps[idx], steps[idx + 1]
        elif action == "remove":
            idx = questionary.select(
                "Select step to remove:",
                choices=[
                    questionary.Choice(f"{s.step_number}. {s.skill_id}", value=i)
                    for i, s in enumerate(steps)
                ],
            ).ask()
            if idx is not None and len(steps) > 1:
                removed = steps.pop(idx)
                console.print(f"[dim]Removed step: {removed.skill_id}[/dim]")
            elif idx is not None:
                console.print("[yellow]Cannot remove the last step.[/yellow]")
