"""VibeSOP execute command - Execute external skills.

Usage:
    vibe execute <skill_id> [--context KEY=VALUE ...]
    vibe execute <skill_id> [--dry-run]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from vibesop.core.skills import SkillManager

console = Console()


def execute(
    skill_id: str = typer.Argument(
        ...,
        help="Skill ID to execute (e.g., superpowers/test-driven-development)",
    ),
    context: list[str] = typer.Option(
        [],
        "--context",
        "-c",
        help="Context variables as KEY=VALUE pairs",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Show workflow definition without executing",
    ),
    enable_execution: bool = typer.Option(
        False,
        "--execute",
        "-e",
        help="Enable local execution (for testing)",
    ),
    output_format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: json, text, or workflow",
    ),
) -> None:
    """Execute an external skill.

    \b
    Examples:
        # Show workflow definition (dry run)
        vibe execute superpowers/test-driven-development --dry-run

        # Execute with context variables
        vibe execute superpowers/test-driven-development --execute \\
            --context feature=Auth --context framework=pytest

        # Execute with JSON output
        vibe execute superpowers/tdd --execute --format json

        # Show workflow in pretty format
        vibe execute superpowers/tdd --dry-run --format workflow
    """
    manager = SkillManager(enable_execution=enable_execution)

    # Parse context variables
    context_dict: dict[str, Any] = {}
    for ctx in context:
        if "=" not in ctx:
            console.print(f"[red]✗ Invalid context format: {ctx}[/red]")
            console.print("[dim]Use KEY=VALUE format[/dim]")
            raise typer.Exit(1)

        key, value = ctx.split("=", 1)
        # Try to parse as JSON, otherwise use string
        try:
            context_dict[key] = json.loads(value)
        except json.JSONDecodeError:
            context_dict[key] = value

    # Dry run mode - show workflow definition
    if dry_run:
        definition = manager.get_skill_definition(skill_id)

        if not definition:
            console.print(f"[red]✗ Skill not found: {skill_id}[/red]")
            console.print("[dim]Run 'vibe skills list' to see available skills[/dim]")
            raise typer.Exit(1)

        workflow = definition["workflow"]

        if output_format == "workflow":
            _print_workflow_pretty(workflow)
        elif output_format == "json":
            console.print_json(json.dumps(workflow, indent=2))
        else:
            console.print(f"[green]✓ Loaded skill:[/green] {workflow['name']}")
            console.print(f"[dim]ID: {workflow['skill_id']}[/dim]")
            console.print(f"[dim]Steps: {len(workflow['steps'])}[/dim]")
            console.print(f"\n[bold]Workflow:[/bold]")
            for i, step in enumerate(workflow["steps"], 1):
                console.print(f"{i}. [{step['type']}] {step['description']}")

        return

    # Execute mode
    if not enable_execution:
        console.print("[yellow]⚠ Execution is disabled by default[/yellow]")
        console.print("[dim]Skills should be executed by AI agents (Claude Code, Cursor)[/dim]")
        console.print("\n[bold]Options:[/bold]")
        console.print("  --dry-run     Show workflow definition (recommended)")
        console.print("  --execute     Enable local execution (for testing)")
        console.print("\n[bold]Example:[/bold]")
        console.print(f"  vibe execute {skill_id} --dry-run --format workflow")
        raise typer.Exit(0)

    result = manager.execute_skill(skill_id, context=context_dict)

    # Output results
    if output_format == "json":
        console.print_json(json.dumps(result, indent=2))
    else:
        if result["success"]:
            console.print(f"[green]✓ Success[/green]")
            console.print(f"[dim]Skill: {result['skill_id']}[/dim]")
            console.print(f"[dim]Steps executed: {result.get('executed_steps', 'N/A')}[/dim]")

            if result.get("output"):
                console.print(f"\n[bold]Output:[/bold]")
                console.print(result["output"])
        else:
            console.print(f"[red]✗ Failed[/red]")
            console.print(f"[dim]Skill: {result['skill_id']}[/dim]")

            if result.get("error"):
                console.print(f"\n[red]Error:[/red]")
                console.print(result["error"])


def _print_workflow_pretty(workflow: dict[str, Any]) -> None:
    """Print workflow in a pretty formatted way."""
    console.print(f"\n[bold cyan]Workflow:[/bold cyan] {workflow['name']}")
    console.print(f"[dim]ID: {workflow['skill_id']}[/dim]")

    if workflow.get("description"):
        console.print(f"\n{workflow['description']}")

    console.print(f"\n[bold]Steps ({len(workflow['steps'])}):[/bold]\n")

    for i, step in enumerate(workflow["steps"], 1):
        step_type = step["type"]
        description = step["description"]

        # Color by type
        type_colors = {
            "instruction": "blue",
            "verification": "green",
            "tool_call": "yellow",
            "conditional": "magenta",
            "loop": "cyan",
        }
        color = type_colors.get(step_type, "white")

        console.print(f"{i}. [{color}]{step_type}[/{color}] {description}")

        # Show additional details
        if step.get("instruction"):
            instruction = step["instruction"]
            if len(instruction) > 100:
                instruction = instruction[:97] + "..."
            console.print(f"   [dim]{instruction}[/dim]")

        if step.get("tool_name"):
            console.print(f"   [dim]Tool: {step['tool_name']}[/dim]")

        if step.get("condition"):
            console.print(f"   [dim]If: {step['condition']} = {step.get('condition_value', 'true')}[/dim]")

        if step.get("max_iterations"):
            console.print(f"   [dim]Max iterations: {step['max_iterations']}[/dim]")

        console.print()

    # Show metadata
    if workflow.get("metadata"):
        console.print("[bold]Metadata:[/bold]")
        for key, value in workflow["metadata"].items():
            if key not in ["skill_id", "name"]:  # Already shown
                console.print(f"  {key}: {value}")
