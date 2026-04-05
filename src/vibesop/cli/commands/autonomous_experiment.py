# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
"""Autonomous experiment command for self-improvement.

Usage:
    vibe autonomous-experiment init      # Initialize experiment config
    vibe autonomous-experiment baseline  # Establish baseline
    vibe autonomous-experiment run       # Run one iteration
    vibe autonomous-experiment summary   # Show summary
    vibe autonomous-experiment apply     # Apply best result

Examples:
    # Initialize experiment
    vibe autonomous-experiment init --domain "routing-optimization"

    # Establish baseline
    vibe autonomous-experiment baseline

    # Run iterations (autonomous mode)
    vibe autonomous-experiment run --iterations 10

    # View summary
    vibe autonomous-experiment summary
"""

from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.experiment.autonomous import (
    AutonomousExperimentRunner,
    ExperimentConfig,
    create_experiment_config,
)

console = Console()


def init(
    domain: str = typer.Option(..., "--domain", "-d", help="Experiment domain"),
    objective: Optional[str] = typer.Option(
        None, "--objective", "-o", help="Objective description"
    ),
) -> None:
    """Initialize an autonomous experiment configuration."""
    config_path = Path(".vibe/experiment.yaml")

    if config_path.exists():
        console.print(f"[yellow]⚠️  {config_path} already exists[/yellow]")
        if not typer.confirm("Overwrite?"):
            raise typer.Exit()

    # Default rubric for skill optimization
    default_rubric = [
        {"id": "effectiveness", "weight": 0.4, "description": "How well it solves the problem"},
        {"id": "clarity", "weight": 0.3, "description": "Clarity of instructions/steps"},
        {"id": "efficiency", "weight": 0.3, "description": "Resource usage and speed"},
    ]

    config_content = f"""domain: {domain}
objective:
  description: "{objective or f"Optimize {domain}"}"
  evaluator:
    type: agent_judge
    rubric:
      - id: effectiveness
        weight: 0.4
        description: "How well it solves the problem"
      - id: clarity
        weight: 0.3
        description: "Clarity of instructions/steps"
      - id: efficiency
        weight: 0.3
        description: "Resource usage and speed"
scope:
  modifiable:
    - core/skills/{domain}/SKILL.md
  readonly:
    - core/policies/**
    - src/**
  test_command: null
constraints:
  max_iterations: 15
  time_budget_per_iteration: 180
  must_pass_tests: false
  stale_threshold: 5
"""

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_content)

    console.print(
        Panel(
            f"[green]✓ Created {config_path}[/green]\n\n"
            f"Domain: {domain}\n"
            f"Objective: {objective or f'Optimize {domain}'}\n\n"
            f"[dim]Next steps:[/dim]\n"
            f"1. Edit {config_path} to customize rubric and scope\n"
            f"2. Run: vibe autonomous-experiment baseline\n"
            f"3. Run: vibe autonomous-experiment run",
            title="Autonomous Experiment Initialized",
        )
    )


def baseline() -> None:
    """Establish baseline score."""
    config_path = Path(".vibe/experiment.yaml")

    if not config_path.exists():
        console.print("[red]✗ No experiment config found[/red]")
        console.print("[dim]Run: vibe autonomous-experiment init --domain <name>[/dim]")
        raise typer.Exit(1)

    config = ExperimentConfig.from_yaml(config_path)
    runner = AutonomousExperimentRunner(config)

    console.print(f"\n[bold cyan]🔬 Establishing Baseline[/bold cyan]\n{'=' * 50}\n")

    score = runner.establish_baseline()

    console.print(f"\n[green]✓ Baseline established: {score:.2f}[/green]")
    console.print(f"[dim]Results saved to: {runner.results_file}[/dim]")


def run(
    iterations: int = typer.Option(1, "--iterations", "-n", help="Number of iterations to run"),
    hypothesis: Optional[str] = typer.Option(None, "--hypothesis", "-h", help="Hypothesis to test"),
    prediction: Optional[str] = typer.Option(
        None, "--prediction", "-p", help="Predicted scores (JSON)"
    ),
) -> None:
    """Run experiment iteration(s)."""
    config_path = Path(".vibe/experiment.yaml")

    if not config_path.exists():
        console.print("[red]✗ No experiment config found[/red]")
        raise typer.Exit(1)

    config = ExperimentConfig.from_yaml(config_path)
    runner = AutonomousExperimentRunner(config)

    if runner.baseline_score is None:
        console.print("[yellow]⚠️  No baseline established[/yellow]")
        console.print("[dim]Run: vibe autonomous-experiment baseline[/dim]")
        raise typer.Exit(1)

    # If no specific hypothesis, enter autonomous mode
    if not hypothesis:
        console.print(f"\n[bold cyan]🤖 Autonomous Mode[/bold cyan]\n{'=' * 50}\n")
        console.print(f"Running up to {iterations} iterations...")
        console.print(f"Best score so far: {runner.best_score:.2f}")
        console.print("\n[dim]The system will:[/dim]")
        console.print("  1. Generate hypotheses based on beliefs")
        console.print("  2. Make predictions")
        console.print("  3. Evaluate results")
        console.print("  4. Keep or discard changes")
        console.print("  5. Update beliefs\n")

        # TODO: Implement full autonomous mode with hypothesis generation
        console.print("[yellow]⚠️  Full autonomous mode not yet implemented[/yellow]")
        console.print("[dim]Use --hypothesis to run manual iterations[/dim]")
        return

    # Manual mode with specific hypothesis
    import json

    pred_dict: dict[str, float] = {}
    if prediction:
        try:
            pred_dict = json.loads(prediction)
        except json.JSONDecodeError:
            console.print("[red]✗ Invalid prediction JSON[/red]")
            raise typer.Exit(1)

    console.print(f"\n[bold cyan]🧪 Running Iteration[/bold cyan]\n{'=' * 50}\n")
    console.print(f"Hypothesis: {hypothesis}")
    console.print(f"Prediction: {pred_dict}\n")

    result = runner.run_iteration(
        hypothesis=hypothesis,
        prediction=pred_dict,
        changes=[],  # User manages changes manually for now
    )

    runner.update_beliefs(result)

    # Show result
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value")

    table.add_row("Compound Score", f"{result.compound_score:.2f}")
    table.add_row("Prediction Accuracy", f"{result.prediction_accuracy:.2%}")
    table.add_row("Status", result.status.value)
    table.add_row("Best So Far", f"{runner.best_score:.2f}" if runner.best_score else "N/A")

    console.print(table)

    if result.status.value == "discarded":
        console.print("\n[yellow]⚠️  Changes discarded - no improvement[/yellow]")
    elif result.status.value == "success":
        console.print("\n[green]✓ Changes kept - new best score![/green]")


def summary() -> None:
    """Show experiment summary."""
    config_path = Path(".vibe/experiment.yaml")

    if not config_path.exists():
        console.print("[red]✗ No experiment config found[/red]")
        raise typer.Exit(1)

    config = ExperimentConfig.from_yaml(config_path)
    runner = AutonomousExperimentRunner(config)

    runner.print_summary()


def beliefs() -> None:
    """Show current beliefs."""
    beliefs_file = Path(".experiment/beliefs.md")

    if not beliefs_file.exists():
        console.print("[yellow]⚠️  No beliefs file found[/yellow]")
        console.print("[dim]Run some iterations first[/dim]")
        return

    content = beliefs_file.read_text()

    console.print(
        Panel(
            content,
            title="Experiment Beliefs",
            border_style="blue",
        )
    )


def results() -> None:
    """Show results table."""
    results_file = Path(".experiment/results.tsv")

    if not results_file.exists():
        console.print("[yellow]⚠️  No results file found[/yellow]")
        return

    import csv

    with open(results_file) as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)

    if not rows:
        console.print("[dim]No results yet[/dim]")
        return

    table = Table()
    for key in rows[0].keys():
        table.add_column(key.capitalize(), style="cyan" if key == "iteration" else None)

    for row in rows[-10:]:  # Show last 10
        table.add_row(*[row.get(k, "") for k in rows[0].keys()])

    console.print(f"\n[bold]Results (last {len(rows[-10:])} of {len(rows)}):[/bold]\n")
    console.print(table)


# Create the CLI app
app = typer.Typer(
    help="Autonomous experiments for self-improvement",
    name="autonomous-experiment",
)

app.command("init")(init)
app.command("baseline")(baseline)
app.command("run")(run)
app.command("summary")(summary)
app.command("beliefs")(beliefs)
app.command("results")(results)
