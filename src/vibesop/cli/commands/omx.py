"""omx/ skills CLI integration.

Provides convenient shortcuts for oh-my-codex engineering methodologies:
    vibe interview "build a todo app"     → omx/deep-interview
    vibe ralph "implement feature X"      → omx/ralph
    vibe plan "design auth system"        → omx/ralplan
    vibe team "run parallel tests"        → omx/team
    vibe ultrawork "batch refactor"       → omx/ultrawork
    vibe autopilot "build from scratch"   → omx/autopilot
    vibe ultraqa "test my website"        → omx/ultraqa
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="omx",
    help="oh-my-codex engineering methodologies",
    no_args_is_help=True,
)


@app.command()
def interview(
    query: str = typer.Argument(..., help="Task or feature to clarify requirements for"),
    working_dir: str = typer.Option(".", "--working-dir", "-C", help="Working directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be executed"),
) -> None:
    """Socratic requirements clarification with mathematical ambiguity scoring.

    Ask ONE question at a time. Re-score after each answer. Challenge assumptions.
    """
    from vibesop.cli.commands.execute import execute as execute_cmd

    execute_cmd("omx/deep-interview", query, working_dir=working_dir, dry_run=dry_run)


@app.command()
def ralph(
    query: str = typer.Argument(..., help="Task to implement with persistent completion"),
    working_dir: str = typer.Option(".", "--working-dir", "-C", help="Working directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be executed"),
) -> None:
    """Persistent completion loop with mandatory deslop pass and tiered verification.

    Never give up. Loops until the work is truly done.
    """
    from vibesop.cli.commands.execute import execute as execute_cmd

    execute_cmd("omx/ralph", query, working_dir=working_dir, dry_run=dry_run)


@app.command()
def plan(
    query: str = typer.Argument(..., help="Feature or system to plan"),
    working_dir: str = typer.Option(".", "--working-dir", "-C", help="Working directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be executed"),
) -> None:
    """Consensus planning with RALPLAN-DR structured deliberation and ADR output."""
    from vibesop.cli.commands.execute import execute as execute_cmd

    execute_cmd("omx/ralplan", query, working_dir=working_dir, dry_run=dry_run)


@app.command()
def team(
    query: str = typer.Argument(..., help="Work to distribute across parallel agents"),
    working_dir: str = typer.Option(".", "--working-dir", "-C", help="Working directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be executed"),
) -> None:
    """Multi-agent parallel execution with file-based coordination."""
    from vibesop.cli.commands.execute import execute as execute_cmd

    execute_cmd("omx/team", query, working_dir=working_dir, dry_run=dry_run)


@app.command()
def ultrawork(
    query: str = typer.Argument(..., help="Independent tasks to execute in parallel"),
    working_dir: str = typer.Option(".", "--working-dir", "-C", help="Working directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be executed"),
) -> None:
    """Tier-aware parallel execution engine for independent tasks."""
    from vibesop.cli.commands.execute import execute as execute_cmd

    execute_cmd("omx/ultrawork", query, working_dir=working_dir, dry_run=dry_run)


@app.command()
def autopilot(
    query: str = typer.Argument(..., help="Feature to build from idea to verified code"),
    working_dir: str = typer.Option(".", "--working-dir", "-C", help="Working directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be executed"),
) -> None:
    """Full autonomous lifecycle from idea to verified code."""
    from vibesop.cli.commands.execute import execute as execute_cmd

    execute_cmd("omx/autopilot", query, working_dir=working_dir, dry_run=dry_run)


@app.command()
def ultraqa(
    query: str = typer.Argument(..., help="Application or feature to QA test"),
    working_dir: str = typer.Option(".", "--working-dir", "-C", help="Working directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be executed"),
) -> None:
    """Autonomous QA cycling with architect diagnosis before fix."""
    from vibesop.cli.commands.execute import execute as execute_cmd

    execute_cmd("omx/ultraqa", query, working_dir=working_dir, dry_run=dry_run)


@app.command("list")
def list_skills() -> None:
    """List all omx/ engineering methodologies."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="omx/ Engineering Methodologies")
    table.add_column("Command", style="cyan")
    table.add_column("Skill ID", style="green")
    table.add_column("Description", style="white")

    skills = [
        (
            "vibe omx interview",
            "omx/deep-interview",
            "Socratic requirements clarification with ambiguity scoring",
        ),
        ("vibe omx ralph", "omx/ralph", "Persistent completion loop with deslop + verification"),
        ("vibe omx plan", "omx/ralplan", "Consensus planning with RALPLAN-DR deliberation"),
        ("vibe omx team", "omx/team", "Multi-agent parallel execution"),
        ("vibe omx ultrawork", "omx/ultrawork", "Tier-aware parallel execution"),
        ("vibe omx autopilot", "omx/autopilot", "Full autonomous lifecycle"),
        ("vibe omx ultraqa", "omx/ultraqa", "Autonomous QA cycling"),
    ]

    for cmd, skill_id, desc in skills:
        table.add_row(cmd, skill_id, desc)

    console.print(table)
