"""Skill lifecycle management CLI commands.

Provides:
- vibe skill list: List all skills with lifecycle state
- vibe skill enable <id>: Enable a skill
- vibe skill disable <id>: Disable a skill
- vibe skill status <id>: Show skill details
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.skills.lifecycle import SkillLifecycle, SkillLifecycleManager

app = typer.Typer(name="skill", help="Manage skill lifecycle")
console = Console()


def _load_skills(project_root: str = ".") -> list[dict[str, Any]]:
    """Load all available skills."""
    from vibesop.core.routing import UnifiedRouter
    router = UnifiedRouter(project_root=project_root)
    return router.get_candidates() or []


def _save_skill_state(skill_id: str, enabled: bool | None = None, lifecycle: str | None = None) -> bool:
    """Persist skill state change to .vibe/skills.json."""
    from pathlib import Path

    state_file = Path(".vibe") / "skills.json"
    state: dict[str, Any] = {}

    if state_file.exists():
        import json
        try:
            state = json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            state = {}

    if skill_id not in state:
        state[skill_id] = {}

    if enabled is not None:
        state[skill_id]["enabled"] = enabled
    if lifecycle is not None:
        state[skill_id]["lifecycle"] = lifecycle

    state_file.parent.mkdir(parents=True, exist_ok=True)
    import json
    state_file.write_text(json.dumps(state, indent=2))
    return True


@app.command()
def list(
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all skills including archived"),
    project_only: bool = typer.Option(False, "--project", "-p", help="Show only project-scoped skills"),
) -> None:
    """List all skills with their lifecycle state."""
    skills = _load_skills()

    table = Table(title="Skills")
    table.add_column("ID", style="bold")
    table.add_column("Name")
    table.add_column("State", justify="center")
    table.add_column("Scope", justify="center")
    table.add_column("Version")

    for skill in skills:
        lifecycle = skill.get("lifecycle", "active")
        if not show_all and lifecycle == "archived":
            continue
        if project_only and skill.get("scope", "global") != "project":
            continue

        enabled = skill.get("enabled", True)
        state_color = {
            "active": "green" if enabled else "yellow",
            "deprecated": "yellow",
            "draft": "dim",
            "archived": "red",
        }.get(lifecycle, "white")

        state_text = f"[{state_color}]{lifecycle}[/{state_color}]"
        if not enabled:
            state_text += " [dim](disabled)[/dim]"

        table.add_row(
            skill.get("id", "unknown"),
            skill.get("name", "")[:30],
            state_text,
            skill.get("scope", "global"),
            skill.get("version", "1.0.0"),
        )

    console.print(table)


@app.command()
def enable(
    skill_id: str = typer.Argument(..., help="Skill ID to enable"),
) -> None:
    """Enable a skill for routing."""
    if _save_skill_state(skill_id, enabled=True):
        console.print(f"[green]✓[/green] Skill '{skill_id}' enabled")
    else:
        console.print(f"[red]✗[/red] Failed to enable skill '{skill_id}'")
        raise typer.Exit(1)


@app.command()
def disable(
    skill_id: str = typer.Argument(..., help="Skill ID to disable"),
) -> None:
    """Disable a skill from routing."""
    if _save_skill_state(skill_id, enabled=False):
        console.print(f"[yellow]✓[/yellow] Skill '{skill_id}' disabled")
    else:
        console.print(f"[red]✗[/red] Failed to disable skill '{skill_id}'")
        raise typer.Exit(1)


@app.command()
def status(
    skill_id: str = typer.Argument(..., help="Skill ID to check"),
) -> None:
    """Show detailed status of a skill."""
    skills = _load_skills()
    skill = next((s for s in skills if s.get("id") == skill_id), None)

    if not skill:
        console.print(f"[red]✗[/red] Skill '{skill_id}' not found")
        raise typer.Exit(1)

    lifecycle = skill.get("lifecycle", "active")
    enabled = skill.get("enabled", True)

    # Show lifecycle transitions
    current = SkillLifecycle(lifecycle) if lifecycle in [s.value for s in SkillLifecycle] else SkillLifecycle.ACTIVE
    valid_next = SkillLifecycleManager._valid_transitions().get(current, frozenset())
    next_states = ", ".join(s.value for s in valid_next) if valid_next else "none (terminal)"

    console.print(Panel(
        f"[bold]ID:[/bold] {skill_id}\n"
        f"[bold]Name:[/bold] {skill.get('name', 'N/A')}\n"
        f"[bold]State:[/bold] {lifecycle}\n"
        f"[bold]Enabled:[/bold] {'Yes' if enabled else 'No'}\n"
        f"[bold]Scope:[/bold] {skill.get('scope', 'global')}\n"
        f"[bold]Version:[/bold] {skill.get('version', '1.0.0')}\n"
        f"[bold]Valid transitions:[/bold] {next_states}",
        title=f"Skill Status: {skill_id}",
        border_style="blue" if enabled else "yellow",
    ))


@app.command()
def stale(
    auto_deprecate: bool = typer.Option(
        False, "--auto", "-a", help="Automatically deprecate stale skills"
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output as JSON"
    ),
) -> None:
    """Detect stale or underperforming skills.

    Analyzes usage statistics to identify skills that haven't been used
    recently or have low quality scores. Skills with no recorded usage
    data are shown separately — these may be newly installed or never triggered.

    Examples:
        vibe skill stale              # Show report only
        vibe skill stale --auto       # Auto-deprecate F-grade skills
        vibe skill stale --json       # Machine-readable output
    """
    from vibesop.core.skills.feedback_loop import FeedbackLoop

    loop = FeedbackLoop()
    suggestions = loop.analyze_all(auto_deprecate=auto_deprecate)

    if json_output:
        import json
        report = loop.generate_report()
        console.print(json.dumps(report, indent=2, default=str))
        return

    if not suggestions:
        console.print("[green]✓[/green] No stale or underperforming skills detected.")
        return

    # Separate into deprecate/warn/boost categories
    to_deprecate = [s for s in suggestions if s.action == "deprecate"]
    to_warn = [s for s in suggestions if s.action == "warn"]
    to_boost = [s for s in suggestions if s.action == "boost"]

    table = Table(title="Skill Health Analysis", show_header=True)
    table.add_column("Skill ID", style="cyan")
    table.add_column("Action", style="bold")
    table.add_column("Grade", justify="center")
    table.add_column("Unused (days)", justify="right")
    table.add_column("Routes", justify="right")
    table.add_column("Reason", style="dim")

    action_styles = {
        "deprecate": ("[red]DEPRECATE[/red]", "red"),
        "warn": ("[yellow]WARN[/yellow]", "yellow"),
        "boost": ("[green]BOOST[/green]", "green"),
    }

    for s in suggestions:
        label, _ = action_styles.get(s.action, (s.action.upper(), "white"))
        days = str(s.days_since_last_use) if s.days_since_last_use is not None else "?"
        table.add_row(s.skill_id, label, s.grade, days, str(s.total_routes), s.reason)

    console.print(table)

    # Summary
    console.print(
        f"\n[bold]Summary:[/bold] "
        f"[red]{len(to_deprecate)} to deprecate[/red], "
        f"[yellow]{len(to_warn)} to warn[/yellow], "
        f"[green]{len(to_boost)} performing well[/green]"
    )

    if to_deprecate and not auto_deprecate:
        console.print(
            "\n[dim]Run `vibe skill stale --auto` to apply deprecations automatically.[/dim]"
        )
