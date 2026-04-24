"""CLI commands for A/B testing experiments.

Commands:
    vibe experiment list      — List experiments
    vibe experiment create    — Create a new experiment
    vibe experiment run       — Run an experiment
    vibe experiment analyze   — Analyze completed experiment
    vibe experiment delete    — Delete an experiment
"""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import typer
from rich.console import Console

from vibesop.core.experiment import (
    Experiment,
    ExperimentAnalyzer,
    ExperimentRunner,
    ExperimentStore,
    VariantConfig,
)

app = typer.Typer(name="experiment", help="A/B testing for routing strategies")
console = Console()

_EXPERIMENT_NAME_ARG = typer.Argument(..., help="Experiment name")


@app.command("list")
def list_experiments() -> None:
    """List all experiments."""
    store = ExperimentStore()
    names = store.list_experiments()

    if not names:
        console.print("[dim]No experiments found.[/dim]")
        console.print("\n[dim]Create one:[/dim]")
        console.print("  vibe experiment create <name> --queries \"q1\" \"q2\" --variants ...")
        return

    console.print("\n[bold]Experiments[/bold]\n")
    for name in names:
        exp = store.load(name)
        if exp:
            status_icon = "🟢" if exp.status == "completed" else "🟡" if exp.status == "running" else "⚪"
            winner_str = f" | Winner: [green]{exp.winner}[/green]" if exp.winner else ""
            console.print(f"  {status_icon} {name}{winner_str}")
    console.print()


@app.command("create")
def create_experiment(
    name: str = _EXPERIMENT_NAME_ARG,
    description: str = typer.Option("", "--description", "-d", help="Experiment description"),
    queries: list[str] = typer.Option([], "--query", "-q", help="Test queries (repeatable)"),  # noqa: B008
    variant_names: list[str] = typer.Option([], "--variant", "-v", help="Variant names (repeatable)"),  # noqa: B008
) -> None:
    """Create a new A/B testing experiment.

    Example:
        vibe experiment create my-test \
            --query "review code" --query "debug error" \
            --variant baseline --variant high-confidence
    """
    if not queries:
        console.print("[red]At least one --query is required[/red]")
        raise typer.Exit(1)

    if len(variant_names) < 2:
        console.print("[red]At least 2 --variant names are required[/red]")
        raise typer.Exit(1)

    variants = []
    for vname in variant_names:
        overrides: dict[str, Any] = {}
        if "high-confidence" in vname.lower():
            overrides["min_confidence"] = 0.8
        elif "no-ai" in vname.lower():
            overrides["enable_ai_triage"] = False
        elif "fast" in vname.lower():
            overrides["enable_embedding"] = False

        variants.append(VariantConfig(name=vname, overrides=overrides))

    experiment = Experiment(
        name=name,
        description=description,
        queries=queries,
        variants=variants,
        created_at=datetime.now(UTC).isoformat(),
    )

    store = ExperimentStore()
    store.save(experiment)
    console.print(f"[green]✓ Created experiment: {name}[/green]")
    console.print(f"  [dim]Queries: {len(queries)} | Variants: {len(variants)}[/dim]")


@app.command("run")
def run_experiment(
    name: str = _EXPERIMENT_NAME_ARG,
    project_root: Path | None = typer.Option(None, "--project-root", help="Project root"),  # noqa: B008
) -> None:
    """Run an experiment and collect metrics."""
    store = ExperimentStore()
    experiment = store.load(name)

    if not experiment:
        console.print(f"[red]Experiment not found: {name}[/red]")
        raise typer.Exit(1)

    if experiment.status == "completed":
        console.print(f"[yellow]Experiment '{name}' already completed. Use 'analyze' to view results.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]Running experiment: {name}[/bold]")
    console.print(f"  Queries: {len(experiment.queries)}")
    console.print(f"  Variants: {', '.join(v.name for v in experiment.variants)}\n")

    runner = ExperimentRunner(project_root or Path.cwd())

    def progress(variant: str, current: int, total: int) -> None:
        console.print(f"  [dim]{variant}: {current}/{total}[/dim]", end="\r")

    experiment = runner.run(experiment, progress_callback=progress)
    store.save(experiment)

    console.print(f"\n[green]✓ Experiment completed: {name}[/green]")
    console.print("  Run [cyan]vibe experiment analyze <name>[/cyan] to see results.")


@app.command("analyze")
def analyze_experiment(
    name: str = _EXPERIMENT_NAME_ARG,
) -> None:
    """Analyze a completed experiment and show winner."""
    store = ExperimentStore()
    experiment = store.load(name)

    if not experiment:
        console.print(f"[red]Experiment not found: {name}[/red]")
        raise typer.Exit(1)

    if experiment.status != "completed":
        console.print(f"[yellow]Experiment not completed. Run [cyan]vibe experiment run {name}[/cyan] first.[/yellow]")
        raise typer.Exit(1)

    analysis = ExperimentAnalyzer.analyze(experiment)

    if "error" in analysis:
        console.print(f"[red]{analysis['error']}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]📊 Experiment Results: {name}[/bold]\n")

    for vname, detail in analysis["details"].items():
        is_winner = vname == analysis["winner"]
        icon = "🏆" if is_winner else "  "
        color = "green" if is_winner else "white"
        console.print(
            f"{icon} [{color}]{vname}[/{color}]  (score: {detail['composite_score']:.3f})"
        )
        console.print(f"     Match rate: {detail['match_rate']:.1%}")
        console.print(f"     Avg confidence: {detail['avg_confidence']:.1%}")
        console.print(f"     Avg duration: {detail['avg_duration_ms']:.1f}ms")
        console.print(f"     Fallback rate: {detail['fallback_rate']:.1%}")
        console.print()

    console.print(f"[bold green]🏆 Winner: {analysis['winner']}[/bold green]")
    console.print(f"[dim]{analysis['recommendation']}[/dim]\n")


@app.command("delete")
def delete_experiment(
    name: str = _EXPERIMENT_NAME_ARG,
) -> None:
    """Delete an experiment."""
    store = ExperimentStore()
    if store.delete(name):
        console.print(f"[green]✓ Deleted experiment: {name}[/green]")
    else:
        console.print(f"[yellow]Experiment not found: {name}[/yellow]")


# Need to import here to avoid circular import at module level
from datetime import datetime  # noqa: E402
from typing import Any  # noqa: E402
