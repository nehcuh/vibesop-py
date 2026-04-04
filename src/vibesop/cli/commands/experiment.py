# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false
"""VibeSOP experiment command - Manage A/B experiments.

This command allows running and managing A/B experiments
for testing different approaches.

Usage:
    vibe experiment create NAME
    vibe experiment start ID
    vibe experiment results ID
    vibe experiment list
    vibe experiment --help

Examples:
    # Create an experiment
    vibe experiment create "test-routing"

    # Start an experiment
    vibe experiment start exp123 --variants 2

    # Get results
    vibe experiment results exp123

    # List experiments
    vibe experiment list
"""

from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from vibesop.workflow.experiment import ExperimentManager

console = Console()


def experiment(
    action: str = typer.Argument(..., help="Action: create, start, stop, results, list"),
    experiment_id: Optional[str] = typer.Argument(None, help="Experiment ID or name"),
    variants: int = typer.Option(
        2,
        "--variants",
        "-v",
        help="Number of variants",
    ),
    traffic: int = typer.Option(
        50,
        "--traffic",
        "-t",
        help="Traffic percentage (0-100)",
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        "-d",
        help="Experiment description",
    ),
) -> None:
    """Manage A/B experiments."""
    manager = ExperimentManager()

    if action == "create":
        _do_create(manager, experiment_id, description, variants)
    elif action == "start":
        _do_start(manager, experiment_id, traffic)
    elif action == "stop":
        _do_stop(manager, experiment_id)
    elif action == "results":
        _do_results(manager, experiment_id)
    elif action == "list":
        _do_list(manager)
    elif action == "complete":
        _do_complete(manager, experiment_id)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n"
            f"[dim]Valid actions: create, start, stop, results, list, complete[/dim]"
        )
        raise typer.Exit(1)


def _do_create(
    manager: ExperimentManager,
    name: str | None,
    description: str | None,
    variants: int,
) -> None:
    """Create an experiment."""
    if not name:
        console.print("[red]✗ Name required for create action[/red]")
        console.print("[dim]Usage: vibe experiment create NAME[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]🧪 Creating Experiment[/bold cyan]\n{'=' * 40}\n")

    experiment: Any = manager.create_experiment(
        name=name, description=description or f"Experiment: {name}", variant_count=variants
    )  # type: ignore[reportCallIssue,reportUnknownVariableType]

    exp_id: str = str(experiment.experiment_id)
    console.print(f"[green]✓ Experiment created[/green]")
    console.print(f"  [dim]ID:[/dim] {exp_id}")
    console.print(f"  [dim]Name:[/dim] {name}")
    console.print(f"  [dim]Variants:[/dim] {variants}")

    console.print(f"\n[dim]Start the experiment with:[/dim]")
    console.print(f"  [cyan]vibe experiment start {exp_id}[/cyan]")


def _do_start(
    manager: ExperimentManager,
    experiment_id: str | None,
    traffic: int,
) -> None:
    """Start an experiment."""
    if not experiment_id:
        console.print("[red]✗ ID required for start action[/red]")
        console.print("[dim]Usage: vibe experiment start ID[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]▶️  Starting Experiment[/bold cyan]\n{'=' * 40}\n")

    try:
        manager.start_experiment(experiment_id, traffic_percentage=traffic)  # type: ignore[reportCallIssue]
        console.print(f"[green]✓ Experiment started[/green]")
        console.print(f"  [dim]ID:[/dim] {experiment_id}")
        console.print(f"  [dim]Traffic:[/dim] {traffic}%")
    except Exception as e:
        console.print(f"[red]✗ Failed to start experiment: {e}[/red]")
        raise typer.Exit(1)


def _do_stop(manager: ExperimentManager, experiment_id: str | None) -> None:
    """Stop an experiment."""
    if not experiment_id:
        console.print("[red]✗ ID required for stop action[/red]")
        console.print("[dim]Usage: vibe experiment stop ID[/dim]")
        raise typer.Exit(1)

    console.print("[dim]Stopping experiment...[/dim]")
    manager.stop_experiment(experiment_id)  # type: ignore[reportAttributeAccessIssue]
    console.print(f"[green]✓ Experiment stopped: {experiment_id}[/green]")


def _do_results(manager: ExperimentManager, experiment_id: str | None) -> None:
    """Show experiment results."""
    if not experiment_id:
        console.print("[red]✗ ID required for results action[/red]")
        console.print("[dim]Usage: vibe experiment results ID[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]📊 Experiment Results[/bold cyan]\n{'=' * 40}\n")

    try:
        results: Any = manager.get_results(experiment_id)  # type: ignore[reportAttributeAccessIssue]

        console.print(f"  [dim]ID:[/dim] {experiment_id}")
        console.print(f"  [dim]Status:[/dim] {results.get('status', 'unknown')}")

        if "variants" in results:
            table = Table()
            table.add_column("Variant", style="cyan")
            table.add_column("Participants")
            table.add_column("Success Rate")
            table.add_column("Avg Duration")

            for variant in results["variants"]:
                table.add_row(
                    f"Variant {variant['id']}",
                    str(variant.get("participants", 0)),
                    f"{variant.get('success_rate', 0):.1%}",
                    f"{variant.get('avg_duration_ms', 0)}ms",
                )

            console.print(table)

        if "winner" in results:
            console.print(f"\n[green]🏆 Winner: Variant {results['winner']}[/green]")

    except Exception as e:
        console.print(f"[red]✗ Failed to get results: {e}[/red]")
        raise typer.Exit(1)


def _do_list(manager: ExperimentManager) -> None:
    """List all experiments."""
    console.print(f"\n[bold cyan]📋 Experiments[/bold cyan]\n{'=' * 40}\n")

    experiments = manager.list_experiments()

    if not experiments:
        console.print("[dim]No experiments found[/dim]")
        console.print("\n[dim]Create one with: vibe experiment create NAME[/dim]")
        return

    table = Table()
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Variants", style="dim")
    table.add_column("Created", style="dim")

    for exp in experiments[:20]:
        status = exp.status.value if hasattr(exp.status, "value") else str(exp.status)
        status_color = "green" if status == "running" else "dim"

        created: Any = exp.created_at.strftime("%Y-%m-%d") if hasattr(exp, "created_at") else "N/A"

        table.add_row(
            exp.experiment_id[:12],
            exp.name[:30],
            f"[{status_color}]{status}[/{status_color}]",
            str(len(exp.variants) if hasattr(exp, "variants") else 0),
            str(created),
        )

    console.print(table)


def _do_complete(manager: ExperimentManager, experiment_id: str | None) -> None:
    """Complete an experiment and pick a winner."""
    if not experiment_id:
        console.print("[red]✗ ID required for complete action[/red]")
        console.print("[dim]Usage: vibe experiment complete ID[/dim]")
        raise typer.Exit(1)

    console.print("[dim]Completing experiment...[/dim]")

    try:
        winner: Any = manager.complete_experiment(experiment_id)  # type: ignore[reportAttributeAccessIssue]
        console.print(f"[green]✓ Experiment completed[/green]")
        console.print(f"  [dim]Winner:[/dim] Variant {winner}")
    except Exception as e:
        console.print(f"[red]✗ Failed to complete: {e}[/red]")
        raise typer.Exit(1)
