"""VibeSOP cascade command - Execute multi-step workflows.

This command executes complex multi-step workflows with
dependencies and error handling.

Usage:
    vibe cascade run WORKFLOW_FILE
    vibe cascade validate WORKFLOW_FILE
    vibe cascade list
    vibe cascade --help

Examples:
    # Run a workflow
    vibe cascade run workflow.yaml

    # Run with dry-run
    vibe cascade run workflow.yaml --dry-run

    # Validate a workflow
    vibe cascade validate workflow.yaml
"""

from pathlib import Path
from typing import Any, Optional, cast

import typer
from rich.console import Console
from rich.table import Table

from vibesop.workflow.cascade import CascadeExecutor

console = Console()


def cascade(
    action: str = typer.Argument(..., help="Action: run, validate, list"),
    workflow_file: Optional[Path] = typer.Argument(
        None,
        help="Workflow YAML file",
        exists=True,
    ),
    strategy: str = typer.Option(
        "sequential",
        "--strategy",
        "-s",
        help="Execution strategy: sequential, parallel, pipeline",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview execution without running",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output",
    ),
) -> None:
    """Execute multi-step workflows.

    This command runs workflows defined in YAML files, executing
    multiple steps with dependencies and error handling.

    \b
    Examples:
        # Run a workflow
        vibe cascade run workflow.yaml

        # Run with parallel execution
        vibe cascade run workflow.yaml --strategy parallel

        # Validate without running
        vibe cascade validate workflow.yaml

        # Preview execution
        vibe cascade run workflow.yaml --dry-run

    \b
    Workflow format:
        name: My Workflow
        steps:
          - id: step1
            name: First Step
            run: echo "Hello"
          - id: step2
            name: Second Step
            run: echo "World"
            depends_on: [step1]
    """
    if action == "run":
        _do_run(workflow_file, strategy, dry_run, verbose)
    elif action == "validate":
        _do_validate(workflow_file)
    elif action == "list":
        _do_list()
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n[dim]Valid actions: run, validate, list[/dim]"
        )
        raise typer.Exit(1)


def _do_run(
    workflow_file: Path | None,
    strategy: str,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Run a workflow.

    Args:
        workflow_file: Path to workflow file
        strategy: Execution strategy
        dry_run: Preview without executing
        verbose: Show detailed output
    """
    if not workflow_file:
        console.print("[red]✗ Workflow file required[/red]")
        console.print("[dim]Usage: vibe cascade run WORKFLOW_FILE[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]🌊 Running Workflow[/bold cyan]\n{'=' * 40}\n")

    executor = CascadeExecutor()

    # Load workflow
    console.print(f"[dim]Loading workflow: {workflow_file}[/dim]\n")

    try:
        workflow = executor.load_workflow(workflow_file)
        console.print(f"[green]✓[/green] Loaded: {workflow.name}")
        console.print(f"[dim]  Steps: {len(workflow.steps)}[/dim]\n")
    except Exception as e:
        console.print(f"[red]✗ Failed to load workflow: {e}[/red]")
        raise typer.Exit(1)

    # Dry run
    if dry_run:
        _do_dry_run(executor, workflow, workflow_file)
        return

    # Execute
    console.print(f"[bold]Strategy:[/bold] {strategy}\n")

    try:
        # Note: executor.run() signature may vary
        result = executor.execute(
            workflow_file,
            strategy=strategy,
            verbose=verbose,
        )

        # Show results
        _show_results(result)

    except Exception as e:
        console.print(f"[red]✗ Execution failed: {e}[/red]")
        raise typer.Exit(1)


def _do_dry_run(executor: CascadeExecutor, workflow, workflow_file: Path) -> None:
    """Show dry-run preview.

    Args:
        executor: CascadeExecutor instance
        workflow: Loaded workflow
        workflow_file: Path to workflow file
    """
    console.print(
        Panel(
            f"[bold cyan]🔍 DRY RUN[/bold cyan]\n\n"
            f"[bold]Workflow:[/bold] {workflow.name}\n"
            f"[bold]Steps:[/bold] {len(workflow.steps)}\n"
            f"[bold]File:[/bold] {workflow_file}\n\n"
            f"[dim]Remove --dry-run to execute.[/dim]",
            title="[bold]Preview[/bold]",
            border_style="cyan",
        )
    )

    # Show step order
    console.print(f"\n[bold]Execution Order:[/bold]\n")

    for i, step in enumerate(workflow.steps, 1):
        deps = f" (after: {', '.join(step.dependencies)})" if step.dependencies else ""
        console.print(f"  {i}. [cyan]{step.step_id}[/cyan] - {step.name}{deps}")


def _do_validate(workflow_file: Path | None) -> None:
    """Validate a workflow file.

    Args:
        workflow_file: Path to workflow file
    """
    if not workflow_file:
        console.print("[red]✗ Workflow file required[/red]")
        console.print("[dim]Usage: vibe cascade validate WORKFLOW_FILE[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]🔍 Validating Workflow[/bold cyan]\n{'=' * 40}\n")

    executor = CascadeExecutor()

    try:
        workflow = executor.load_workflow(workflow_file)
        errors = executor.validate_workflow(workflow)

        if errors:
            console.print(f"[red]✗ Validation failed with {len(errors)} errors[/red]\n")
            for error in errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)
        else:
            console.print("[green]✓ Workflow is valid[/green]\n")
            console.print(f"  Name: {workflow.name}")
            console.print(f"  Steps: {len(workflow.steps)}")

    except FileNotFoundError:
        console.print(f"[red]✗ File not found: {workflow_file}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]✗ Validation error: {e}[/red]")
        raise typer.Exit(1)


def _do_list() -> None:
    """List available workflows."""
    console.print(f"\n[bold cyan]📋 Available Workflows[/bold cyan]\n{'=' * 40}\n")

    # Look for workflow files
    workflow_paths = [
        Path(".vibe/workflows"),
        Path("workflows"),
        Path("."),
    ]

    found = []
    for base_path in workflow_paths:
        if base_path.exists():
            for yaml_file in base_path.rglob("*.yaml"):
                if "cascade" in yaml_file.name.lower() or "workflow" in yaml_file.name.lower():
                    found.append(yaml_file)

    if not found:
        console.print("[dim]No workflow files found[/dim]")
        console.print("\n[dim]Create a workflow file in: .vibe/workflows/[/dim]")
        return

    # Show found workflows
    for workflow_file in found:
        rel_path = workflow_file.relative_to(Path.cwd())
        console.print(f"  📄 {rel_path}")


def _show_results(result) -> None:
    """Show execution results.

    Args:
        result: Execution result
    """
    console.print(f"\n[bold]Execution Results[/bold]\n")

    # Show status
    if hasattr(result, "success") and result.success:
        console.print("[green]✓ Workflow completed successfully[/green]\n")
    elif hasattr(result, "success") and not result.success:
        console.print("[red]✗ Workflow failed[/red]\n")

    # Show step results
    if hasattr(result, "step_results") and result.step_results:
        table = Table()
        table.add_column("Step", style="cyan")
        table.add_column("Status")
        table.add_column("Duration", style="dim")

        for step_result in result.step_results:
            status_icon = "✓" if step_result.status == "completed" else "✗"
            duration = f"{step_result.duration_ms}ms" if step_result.duration_ms else "N/A"

            table.add_row(
                step_result.step_id,
                status_icon,
                duration,
            )

        console.print(table)
