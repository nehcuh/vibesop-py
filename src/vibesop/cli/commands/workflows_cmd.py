"""Cross-cutting workflow management commands.

Usage:
    vibe workflows                     List all cross-cutting workflows
    vibe workflows show <id>           Show workflow details
    vibe workflows create              Interactive wizard to create a workflow
    vibe workflows match <skill_ids>   Find workflows covering given skills
"""

from __future__ import annotations

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.orchestration.cross_cutting import CrossCuttingDiscovery

app = typer.Typer(name="workflows", help="Manage cross-cutting workflows", no_args_is_help=True)
console = Console()


@app.callback(invoke_without_command=True)
def _workflows_overview(ctx: typer.Context) -> None:  # pyright: ignore[reportUnusedFunction]
    """Show all cross-cutting workflows."""
    if ctx.invoked_subcommand is not None:
        return
    list_workflows()


@app.command()
def list_workflows(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """List all cross-cutting multi-skill workflows.

    Cross-cutting workflows define how multiple skills work together
    for complex tasks. They are stored in .vibe/skills/cross-cutting/.

    Inspired by SkillTree's cross-cutting/SKILL.md pattern.
    """
    discovery = CrossCuttingDiscovery()
    workflows = discovery.discover_all()

    if not workflows:
        console.print()
        console.print(
            Panel(
                "[dim]No cross-cutting workflows defined yet.[/dim]\n\n"
                "Create one with: [cyan]vibe workflows create[/cyan]\n\n"
                "Cross-cutting workflows define how multiple skills work "
                "together for complex tasks.",
                title="Cross-Cutting Workflows",
                border_style="dim",
            )
        )
        console.print()
        return

    if json_output:
        import json

        console.print(
            json.dumps([w.to_dict() for w in workflows], indent=2, ensure_ascii=False)
        )
        return

    console.print()
    console.rule("[bold cyan]Cross-Cutting Workflows[/bold cyan]")
    console.print()

    table = Table(show_header=True)
    table.add_column("Workflow", style="cyan")
    table.add_column("Skills", justify="center")
    table.add_column("Steps", justify="center")
    table.add_column("Description", max_width=50, style="dim")

    for wf in workflows:
        table.add_row(
            wf.id,
            str(wf.skill_count),
            str(wf.step_count or wf.skill_count),
            wf.description[:80],
        )

    console.print(table)
    console.print()
    console.print(
        f"[dim]{len(workflows)} workflow(s). "
        "View details: [cyan]vibe workflows show <id>[/cyan][/dim]"
    )
    console.print()


@app.command()
def show(
    workflow_id: str = typer.Argument(..., help="Workflow ID (e.g., cross-cutting/full-stack)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show details of a cross-cutting workflow."""
    discovery = CrossCuttingDiscovery()
    workflows = discovery.discover_all()

    wf = next((w for w in workflows if w.id == workflow_id), None)
    if not wf:
        # Try partial match
        matches = [w for w in workflows if workflow_id in w.id]
        if not matches:
            console.print(f"[red]Workflow not found: {workflow_id}[/red]")
            raise typer.Exit(1)
        wf = matches[0]

    if json_output:
        import json

        console.print(json.dumps(wf.to_dict(), indent=2, ensure_ascii=False))
        return

    console.print()
    console.rule(f"[bold cyan]{wf.name}[/bold cyan]")
    console.print()

    console.print(f"  [bold]ID:[/bold] {wf.id}")
    console.print(f"  [bold]Description:[/bold] {wf.description}")
    if wf.tags:
        console.print(f"  [bold]Tags:[/bold] {', '.join(wf.tags)}")
    if wf.trigger_when:
        console.print(f"  [bold]Trigger:[/bold] {wf.trigger_when}")

    console.print()
    console.print("[bold]Required Skills:[/bold]")
    for dep in wf.depends_on:
        console.print(f"  • [cyan]{dep}[/cyan]")

    if wf.steps:
        console.print()
        console.print("[bold]Workflow Steps:[/bold]")
        steps_sorted = sorted(wf.steps, key=lambda s: s.get("order", 99))
        for step in steps_sorted:
            skill = step.get("skill", "?")
            intent = step.get("intent", "")
            order = step.get("order", "?")
            console.print(f"  {order}. [cyan]{skill}[/cyan] — {intent}")

    console.print()
    console.print(
        "[dim]Use: [cyan]vibe route \"workflow: {name}\"[/cyan] to trigger this workflow[/dim]"
        .format(name=wf.id.split("/")[-1])
    )
    console.print()


@app.command()
def create() -> None:
    """Interactive wizard to create a cross-cutting workflow.

    Define how multiple skills work together for a complex task.
    The workflow is saved to .vibe/skills/cross-cutting/<name>/SKILL.md.
    """
    from vibesop.core.skills import SkillManager

    console.print()
    console.rule("[bold cyan]Create Cross-Cutting Workflow[/bold cyan]")
    console.print()

    # Step 1: Name
    name = questionary.text(
        "Workflow name (kebab-case):",
        validate=lambda t: bool(t) and " " not in t or "Use kebab-case (no spaces)",
    ).ask()
    if not name:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Step 2: Description
    description = questionary.text(
        "What does this workflow accomplish?",
        default="",
    ).ask()

    # Step 3: Select dependent skills
    manager = SkillManager()
    all_skills = manager.list_skills()
    skill_choices = [
        questionary.Choice(
            title=f"{s['id']} — {s.get('description', '')[:60]}",
            value=s["id"],
        )
        for s in sorted(all_skills, key=lambda x: x["id"])
    ]

    if not skill_choices:
        console.print("[red]No skills installed. Install skills first.[/red]")
        raise typer.Exit(1)

    depends_on = questionary.checkbox(
        "Select skills that are part of this workflow:",
        choices=skill_choices,
        validate=lambda selected: len(selected) >= 2 or "Select at least 2 skills",
    ).ask()

    if not depends_on or len(depends_on) < 2:
        console.print("[yellow]Need at least 2 skills. Cancelled.[/yellow]")
        return

    # Step 4: Tags
    tags_input = questionary.text(
        "Tags (comma-separated):",
        default="",
    ).ask()
    tags = [t.strip() for t in (tags_input or "").split(",") if t.strip()]

    # Step 5: Create
    discovery = CrossCuttingDiscovery()
    wf = discovery.create_workflow(
        name=name,
        description=description or f"Multi-skill workflow: {name}",
        depends_on=depends_on,
        tags=tags,
    )

    console.print()
    console.print(f"[green]✓ Workflow created:[/green] [bold]{wf.id}[/bold]")
    console.print(f"  Skills: {', '.join(depends_on)}")
    console.print(f"  File: {wf.source_file}")
    console.print()
    console.print("[dim]Use: [cyan]vibe workflows show {id}[/cyan] to inspect[/dim]".format(id=wf.id))


@app.command()
def match(
    skill_ids: str = typer.Argument(..., help="Comma-separated skill IDs to match against workflows"),
) -> None:
    """Find cross-cutting workflows that cover the given skills.

    Useful for discovering pre-defined workflows when you have
    specific skills installed.
    """
    ids = [s.strip() for s in skill_ids.split(",") if s.strip()]

    discovery = CrossCuttingDiscovery()
    matching = discovery.find_for_skills(ids)

    if not matching:
        console.print(
            f"[dim]No cross-cutting workflows found covering: {', '.join(ids)}[/dim]"
        )
        all_wfs = discovery.discover_all()
        if all_wfs:
            console.print(
                f"[dim]{len(all_wfs)} workflow(s) exist. "
                "Run [cyan]vibe workflows[/cyan] to browse.[/dim]"
            )
        return

    console.print()
    console.print(f"[bold]Workflows covering:[/bold] {', '.join(ids)}")
    console.print()

    for wf in matching:
        coverage = len(set(ids) & set(wf.depends_on)) / len(wf.depends_on)
        console.print(
            f"  [cyan]{wf.id}[/cyan] "
            f"([green]{coverage:.0%} coverage[/green]) — {wf.description[:60]}"
        )

    console.print()
