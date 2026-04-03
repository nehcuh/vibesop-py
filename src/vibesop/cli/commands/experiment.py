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

from pathlib import Path
from typing import Optional

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
    """Manage A/B experiments.

    This command allows you to run experiments to test different
    approaches and compare their effectiveness.

    \b
    Examples:
        # Create an experiment
        vibe experiment create "test-routing" --description "Test new routing"

        # Start an experiment with 3 variants
        vibe experiment start exp123 --variants 3 --traffic 20

        # Stop an experiment
        vibe experiment stop exp123

        # Get results
        vibe experiment results exp123

        # List all experiments
        vibe experiment list
    """
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
    """Create an experiment.

    Args:
        manager: ExperimentManager instance
        name: Experiment name
        description: Optional description
        variants: Number of variants
    """
    if not name:
        console.print("[red]✗ Name required for create action[/red]")
        console.print("[dim]Usage: vibe experiment create NAME[/dim]")
        raise typer.Exit(1)

    console.print(
        f"\n[bold cyan]🧪 Creating Experiment[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    # Create experiment
    experiment = manager.create_experiment(
        name=name,
        description=description or f"Experiment: {name}",
        variant_count=variants,
    )

    console.print(
        f"[green]✓ Experiment created[/green]\n"
        f"  [dim]ID:[/dim] {experiment.experiment_id}\n"
        f"  [dim]Name:[/dim] {name}\n"
        f"  [dim]Variants:[/dim] {variants}\n"
    )

    console.print(
        f"\n[dim]Start the experiment with:[/dim]\n"
        f"  [cyan]vibe experiment start {experiment.experiment_id}[/cyan]\n"
    )


def _do_start(
    manager: ExperimentManager,
    experiment_id: str | None,
    traffic: int,
) -> None:
    """Start an experiment.

    Args:
        manager: ExperimentManager instance
        experiment_id: Experiment ID
        traffic: Traffic percentage
    """
    if not experiment_id:
        console.print("[red]✗ ID required for start action[/red]")
        console.print("[dim]Usage: vibe experiment start ID[/dim]")
        raise typer.Exit(1)

    console.print(
        f"\n[bold cyan]▶️  Starting Experiment[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    try:
        manager.start_experiment(experiment_id, traffic_percentage=traffic)
        console.print(
            f"[green]✓ Experiment started[/green]\n"
            f"  [dim]ID:[/dim] {experiment_id}\n"
            f"  [dim]Traffic:[/dim] {traffic}%\n"
        )
    except Exception as e:
        console.print(f"[red]✗ Failed to start experiment: {e}[/red]")
        raise typer.Exit(1)


def _do_stop(manager: ExperimentManager, experiment_id: str | None) -> None:
    """Stop an experiment.

    Args:
        manager: ExperimentManager instance
        experiment_id: Experiment ID
    """
    if not experiment_id:
        console.print("[red]✗ ID required for stop action[/red]")
        console.print("[dim]Usage: vibe experiment stop ID[/dim]")
        raise typer.Exit(1)

    console.print("[dim]Stopping experiment...[/dim]")
    manager.stop_experiment(experiment_id)
    console.print(f"[green]✓ Experiment stopped: {experiment_id}[/green]")


def _do_results(manager: ExperimentManager, experiment_id: str | None) -> None:
    """Show experiment results.

    Args:
        manager: ExperimentManager instance
        experiment_id: Experiment ID
    """
    if not experiment_id:
        console.print("[red]✗ ID required for results action[/red]")
        console.print("[dim]Usage: vibe experiment results ID[/dim]")
        raise typer.Exit(1)

    console.print(
        f"\n[bold cyan]📊 Experiment Results[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    try:
        results = manager.get_results(experiment_id)

        # Show summary
        console.print(f"  [dim]ID:[/dim] {experiment_id}")
        console.print(f"  [dim]Status:[/dim] {results.get('status', 'unknown')}\n")

        # Show variant results
        if "variants" in results:
            table = Table()
            table.add_column("Variant", style="cyan")
            table.add_column("Participants")
            table.add_column("Success Rate")
            table.add_column("Avg Duration")

            for variant in results["variants"]:
                table.add_row(
                    f"Variant {variant['id']}",
                    str(variant.get('participants', 0)),
                    f"{variant.get('success_rate', 0):.1%}",
                    f"{variant.get('avg_duration_ms', 0)}ms",
                )

            console.print(table)

        # Show winner
        if "winner" in results:
            console.print(f"\n[green]🏆 Winner: Variant {results['winner']}[/green]")

    except Exception as e:
        console.print(f"[red]✗ Failed to get results: {e}[/red]")
        raise typer.Exit(1)


def _do_list(manager: ExperimentManager) -> None:
    """List all experiments.

    Args:
        manager: ExperimentManager instance
    """
    console.print(
        f"\n[bold cyan]📋 Experiments[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    experiments = manager.list_experiments()

    if not experiments:
        console.print("[dim]No experiments found[/dim]")
        console.print("\n[dim]Create one with: vibe experiment create NAME[/dim]")
        return

    # Create table
    table = Table()
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Variants", style="dim")
    table.add_column("Created", style="dim")

    for exp in experiments[:20]:
        status_color = "green" if exp.status == "running" else "dim"
        status = exp.status.value if hasattr(exp.status, "value") else str(exp.status)

        table.add_row(
            exp.experiment_id[:12],
            exp.name[:30],
            f"[{status_color}]{status}[/{status_color}]",
            str(len(exp.variants) if hasattr(exp, "variants") else 0),
            exp.created_at.strftime("%Y-%m-%d") if hasattr(exp, "created_at") else "N/A",
        )

    console.print(table)


def _do_complete(manager: ExperimentManager, experiment_id: str | None) -> None:
    """Complete an experiment and pick a winner.

    Args:
        manager: ExperimentManager instance
        experiment_id: Experiment ID
    """
    if not experiment_id:
        console.print("[red]✗ ID required for complete action[/red]")
        console.print("[dim]Usage: vibe experiment complete ID[/dim]")
        raise typer.Exit(1)

    console.print("[dim]Completing experiment...[/dim]")

    try:
        winner = manager.complete_experiment(experiment_id)
        console.print(f"[green]✓ Experiment completed[/green]")
        console.print(f"  [dim]Winner:[/dim] Variant {winner}")
    except Exception as e:
        console.print(f"[red]✗ Failed to complete: {e}[/red]")
        raise typer.Exit(1)
