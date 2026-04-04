"""VibeSOP workflow command - Execute v2.0 workflows with type-safe orchestration.

This command provides the v2.0 workflow execution system with:
- Type-safe workflow definitions (Pydantic v2)
- State persistence and recovery
- Skill routing integration
- Dependency management

Usage:
    vibe workflow run WORKFLOW_FILE
    vibe workflow list
    vibe workflow resume WORKFLOW_ID
    vibe workflow --help

Examples:
    # Run a workflow
    vibe workflow run security-review.yaml

    # Run with custom input
    vibe workflow run workflow.yaml --input '{"test": "data"}'

    # List available workflows
    vibe workflow list

    # Resume interrupted workflow
    vibe workflow resume workflow-123
"""

from pathlib import Path
from typing import Any, Optional
import json
import asyncio
import os

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel


from vibesop.workflow import (
    WorkflowManager,
    WorkflowDefinition,
)
from vibesop.workflow.models import ExecutionStrategy as ExecStrategy
from vibesop.workflow.exceptions import WorkflowError

console = Console()


def _create_manager() -> WorkflowManager:
    """Create WorkflowManager with configurable directory from env var.

    Supports VIBE_WORKFLOW_DIR environment variable for testing and
    custom workflow directory locations.

    Returns:
        WorkflowManager instance
    """
    workflow_dir = os.environ.get("VIBE_WORKFLOW_DIR", ".vibe/workflows")
    project_root = Path(os.environ.get("VIBE_PROJECT_ROOT", "."))
    return WorkflowManager(project_root=project_root, workflow_dir=Path(workflow_dir))


def workflow(
    action: str = typer.Argument(..., help="Action: run, list, resume, validate"),
    workflow_file: Optional[Path] = typer.Argument(
        None,
        help="Workflow YAML file",
        exists=True,
    ),
    input_data: Optional[str] = typer.Option(
        None,
        "--input",
        "-i",
        help="Input data as JSON string",
    ),
    strategy: str = typer.Option(
        "sequential",
        "--strategy",
        "-s",
        help="Execution strategy: sequential, parallel, pipeline",
    ),
    workflow_id: Optional[str] = typer.Option(
        None,
        "--id",
        help="Workflow ID for resume action",
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
    """Execute v2.0 workflows with type-safe orchestration.

    This command provides the new workflow execution system with:
    - Pydantic v2 type validation
    - State persistence and recovery
    - Skill routing integration
    - Three execution strategies

    \b
    Examples:
        # Run a workflow
        vibe workflow run security-review.yaml

        # Run with custom input
        vibe workflow run workflow.yaml --input '{"test": "data"}'

        # Run with parallel strategy
        vibe workflow run workflow.yaml --strategy parallel

        # List available workflows
        vibe workflow list

        # Resume interrupted workflow
        vibe workflow resume workflow-abc123

        # Validate workflow definition
        vibe workflow validate workflow.yaml

        # Preview execution
        vibe workflow run workflow.yaml --dry-run

    \b
    Workflow format (YAML):
        name: my-workflow
        description: My workflow description
        stages:
          - name: stage1
            description: First stage
            skill_id: /skill/path
            required: true

          - name: stage2
            description: Second stage
            skill_id: /other/skill
            dependencies: [stage1]
            required: false
    """
    if action == "run":
        _do_run(workflow_file, input_data, strategy, dry_run, verbose)
    elif action == "list":
        _do_list()
    elif action == "resume":
        _do_resume(workflow_id, verbose)
    elif action == "validate":
        _do_validate(workflow_file)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n"
            f"[dim]Valid actions: run, list, resume, validate[/dim]"
        )
        raise typer.Exit(1)


def _do_run(
    workflow_file: Path | None,
    input_data: str | None,
    strategy: str,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Run a workflow.

    Args:
        workflow_file: Path to workflow file
        input_data: Input data as JSON string
        strategy: Execution strategy
        dry_run: Preview without executing
        verbose: Show detailed output
    """
    if not workflow_file:
        console.print("[red]✗ Workflow file required[/red]")
        console.print("[dim]Usage: vibe workflow run WORKFLOW_FILE[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]⚙️ Running Workflow (v2.0)[/bold cyan]\n{'=' * 40}\n")

    manager = _create_manager()

    # Parse input data
    input_dict: dict[str, Any] = {}
    if input_data:
        try:
            input_dict = json.loads(input_data)
        except json.JSONDecodeError as e:
            console.print(f"[red]✗ Invalid JSON input: {e}[/red]")
            raise typer.Exit(1)

    # Load workflow
    console.print(f"[dim]Loading workflow: {workflow_file}[/dim]\n")

    try:
        workflow = manager._load_workflow_from_file(workflow_file)  # type: ignore[reportPrivateUsage]
        if not workflow:
            console.print(f"[red]✗ Failed to load workflow[/red]")
            raise typer.Exit(1)

        console.print(f"[green]✓[/green] Loaded: [cyan]{workflow.name}[/cyan]")
        console.print(f"[dim]  Description: {workflow.description}[/dim]")
        console.print(f"[dim]  Stages: {len(workflow.stages)}[/dim]")
        console.print(f"[dim]  Strategy: {workflow.strategy}[/dim]\n")

    except Exception as e:
        console.print(f"[red]✗ Failed to load workflow: {e}[/red]")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(1)

    # Dry run
    if dry_run:
        _do_dry_run(workflow, workflow_file)
        return

    # Execute
    console.print(f"[bold]Strategy:[/bold] {strategy}\n")

    try:
        # Run async execution
        result = asyncio.run(
            manager.execute_workflow(
                workflow.name,
                input_dict or {},
                ExecStrategy(strategy) if strategy else None,
            )
        )

        # Show results
        _show_results(result)

    except WorkflowError as e:
        console.print(f"[red]✗ Workflow execution failed: {e}[/red]")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]✗ Unexpected error: {e}[/red]")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(1)


def _do_dry_run(workflow: WorkflowDefinition, workflow_file: Path) -> None:
    """Show dry-run preview.

    Args:
        workflow: Workflow definition
        workflow_file: Path to workflow file
    """
    console.print(
        Panel(
            f"[bold cyan]🔍 DRY RUN[/bold cyan]\n\n"
            f"[bold]Workflow:[/bold] {workflow.name}\n"
            f"[bold]Description:[/bold] {workflow.description}\n"
            f"[bold]Stages:[/bold] {len(workflow.stages)}\n"
            f"[bold]Strategy:[/bold] {workflow.strategy}\n"
            f"[bold]File:[/bold] {workflow_file}\n\n"
            f"[dim]Remove --dry-run to execute.[/dim]",
            title="[bold]Preview[/bold]",
            border_style="cyan",
        )
    )

    # Show stages
    console.print(f"\n[bold]Execution Order:[/bold]\n")

    for i, stage in enumerate(workflow.stages, 1):
        deps = f" (after: {', '.join(stage.dependencies)})" if stage.dependencies else ""
        skill = (
            f" [dim]skill: {stage.metadata.get('skill_id', 'N/A')}[/dim]"
            if stage.metadata.get("skill_id")
            else ""
        )
        console.print(f"  {i}. [cyan]{stage.name}[/cyan] - {stage.description}{deps}{skill}")
        if not stage.required:
            console.print(f"     [dim]Optional: will continue if this stage fails[/dim]")


def _do_list() -> None:
    """List available workflows."""
    console.print(f"\n[bold cyan]📋 Available Workflows[/bold cyan]\n{'=' * 40}\n")

    manager = _create_manager()

    try:
        workflows = manager.list_workflows()

        if not workflows:
            console.print("[dim]No workflow files found[/dim]")
            console.print("\n[dim]Create workflow files in: .vibe/workflows/[/dim]")
            return

        # Show workflows table
        table = Table()
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Description")
        table.add_column("Stages", justify="right")
        table.add_column("Strategy")
        table.add_column("Source", style="dim")

        for wf in workflows:
            table.add_row(
                wf["id"],
                wf["name"],
                wf["description"][:40] + "..."
                if len(wf.get("description", "")) > 40
                else wf.get("description", ""),
                str(wf.get("stages", 0)),
                wf.get("strategy", "sequential"),
                str(wf.get("source", ""))[:30],
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗ Failed to list workflows: {e}[/red]")
        raise typer.Exit(1)


def _do_resume(workflow_id: str | None, verbose: bool) -> None:
    """Resume a previously interrupted workflow.

    Args:
        workflow_id: Workflow execution ID
        verbose: Show detailed output
    """
    if not workflow_id:
        # List active workflows instead
        console.print(f"\n[bold cyan]🔄 Active Workflows[/bold cyan]\n{'=' * 40}\n")

        manager = _create_manager()

        try:
            active = manager.list_active_workflows()

            if not active:
                console.print("[dim]No active workflows found[/dim]")
                return

            # Show active workflows table
            table = Table()
            table.add_column("Workflow ID", style="cyan")
            table.add_column("Name")
            table.add_column("Status")
            table.add_column("Current Stage")
            table.add_column("Started At", style="dim")

            for state in active:
                sid: str = state.get("workflow_id", "")  # type: ignore[reportUnknownMemberType]
                sname: str = state.get("workflow_name", "")  # type: ignore[reportUnknownMemberType]
                sstatus: str = state.get("status", "")  # type: ignore[reportUnknownMemberType]
                cur_stage: str = state.get("current_stage") or "N/A"  # type: ignore[reportUnknownMemberType]
                started = state.get("started_at")  # type: ignore[reportUnknownMemberType]
                started_str = started.strftime("%Y-%m-%d %H:%M:%S") if started else "N/A"  # type: ignore[reportUnknownMemberType, reportUnionNotFolded]
                table.add_row(
                    sid[:24],
                    sname,
                    sstatus,
                    cur_stage,
                    started_str,
                )

            console.print(table)
            console.print("\n[dim]Use: vibe workflow resume --id WORKFLOW_ID[/dim]")

        except Exception as e:
            console.print(f"[red]✗ Failed to list active workflows: {e}[/red]")
            raise typer.Exit(1)

        return

    # Resume specific workflow
    console.print(f"\n[bold cyan]🔄 Resuming Workflow[/bold cyan]\n{'=' * 40}\n")
    console.print(f"[dim]Workflow ID: {workflow_id}[/dim]\n")

    manager = _create_manager()

    try:
        result = manager.resume_workflow(workflow_id)
        _show_results(result)

    except NotImplementedError:
        console.print("[yellow]⚠ Workflow resume is not yet implemented[/yellow]")
        console.print("[dim]This feature is planned for v2.1[/dim]")
    except Exception as e:
        console.print(f"[red]✗ Failed to resume workflow: {e}[/red]")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(1)


def _do_validate(workflow_file: Path | None) -> None:
    """Validate a workflow file.

    Args:
        workflow_file: Path to workflow file
    """
    if not workflow_file:
        console.print("[red]✗ Workflow file required[/red]")
        console.print("[dim]Usage: vibe workflow validate WORKFLOW_FILE[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]🔍 Validating Workflow[/bold cyan]\n{'=' * 40}\n")

    manager = _create_manager()

    try:
        workflow = manager._load_workflow_from_file(workflow_file)  # type: ignore[reportPrivateUsage]

        if not workflow:
            console.print("[red]✗ Failed to load workflow file[/red]")
            raise typer.Exit(1)

        # Pydantic v2 validation is automatic during loading
        console.print("[green]✓ Workflow is valid[/green]\n")

        # Show workflow details
        console.print(f"  [bold]Name:[/bold] {workflow.name}")
        console.print(f"  [bold]Description:[/bold] {workflow.description}")
        console.print(f"  [bold]Version:[/bold] {workflow.version}")
        console.print(f"  [bold]Stages:[/bold] {len(workflow.stages)}")
        console.print(f"  [bold]Strategy:[/bold] {workflow.strategy}")

        # Show stage summary
        if workflow.stages:
            console.print(f"\n  [bold]Stages:[/bold]")
            for stage in workflow.stages:
                required = "required" if stage.required else "optional"
                deps = f" (deps: {', '.join(stage.dependencies)})" if stage.dependencies else ""
                console.print(
                    f"    • [cyan]{stage.name}[/cyan]: {stage.description} [{required}]{deps}"
                )

    except Exception as e:
        console.print(f"[red]✗ Validation failed: {e}[/red]")
        raise typer.Exit(1)


def _show_results(result: Any) -> None:
    """Show execution results.

    Args:
        result: WorkflowResult from execution
    """
    console.print(f"\n[bold]Execution Results[/bold]\n")

    # Show status
    if result.success:
        console.print("[green]✓ Workflow completed successfully[/green]\n")
    else:
        console.print("[red]✗ Workflow failed[/red]\n")

    # Show summary
    console.print(f"  [bold]Total Stages:[/bold] {result.total_stages}")
    console.print(f"  [bold]Completed:[/bold] {len(result.completed_stages)}")
    console.print(f"  [bold]Failed:[/bold] {len(result.failed_stages)}")
    console.print(f"  [bold]Skipped:[/bold] {len(result.skipped_stages)}")
    console.print(f"  [bold]Completion:[/bold] {result.completion_percentage:.1f}%")
    console.print(f"  [bold]Execution Time:[/bold] {result.execution_time_seconds:.2f}s")

    # Show stage results
    if result.completed_stages:
        console.print(f"\n[bold]Completed Stages:[/bold]")
        for stage_name in result.completed_stages:
            console.print(f"  [green]✓[/green] {stage_name}")

    if result.failed_stages:
        console.print(f"\n[bold]Failed Stages:[/bold]")
        for stage_name in result.failed_stages:
            console.print(f"  [red]✗[/red] {stage_name}")

    if result.skipped_stages:
        console.print(f"\n[bold]Skipped Stages:[/bold]")
        for stage_name in result.skipped_stages:
            console.print(f"  [dim]⊘[/dim] {stage_name}")

    # Show errors
    if result.errors:
        console.print(f"\n[bold red]Errors:[/bold red]")
        for error in result.errors:
            console.print(f"  • {error}")
