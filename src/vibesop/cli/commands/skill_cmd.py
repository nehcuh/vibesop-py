"""Skill lifecycle management CLI commands.

Provides:
- vibe skill list: List all skills with lifecycle state
- vibe skill enable <id>: Enable a skill (delegates to SkillConfigManager)
- vibe skill disable <id>: Disable a skill (delegates to SkillConfigManager)
- vibe skill status <id>: Show skill details
- vibe skill stale: Detect stale/underperforming skills
- vibe skill end-check: Session-end retention + suggestion review
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.skills.config_manager import SkillConfigManager
from vibesop.core.skills.lifecycle import SkillLifecycle, SkillLifecycleManager

app = typer.Typer(name="skill", help="Manage skill lifecycle")
console = Console()


def _load_skills(project_root: str = ".") -> list[dict[str, Any]]:
    """Load all available skills."""
    from vibesop.core.routing import UnifiedRouter

    router = UnifiedRouter(project_root=project_root)
    return router.get_candidates() or []


@app.command()
def list(
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all skills including archived"),
    project_only: bool = typer.Option(
        False, "--project", "-p", help="Show only project-scoped skills"
    ),
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
    from vibesop.core.skills import SkillManager

    manager = SkillManager()
    skill_info = manager.get_skill_info(skill_id)
    if not skill_info:
        console.print(f"[red]✗[/red] Skill '{skill_id}' not found")
        raise typer.Exit(1)

    config = SkillConfigManager.get_skill_config(skill_id)
    if config and config.enabled:
        console.print(f"[yellow]⚠ Skill '{skill_id}' is already enabled[/yellow]")
        return

    SkillConfigManager.update_skill_config(skill_id, {"enabled": True})
    console.print(f"[green]✓[/green] Skill '{skill_id}' enabled")


@app.command()
def disable(
    skill_id: str = typer.Argument(..., help="Skill ID to disable"),
) -> None:
    """Disable a skill from routing."""
    from vibesop.core.skills import SkillManager

    manager = SkillManager()
    skill_info = manager.get_skill_info(skill_id)
    if not skill_info:
        console.print(f"[red]✗[/red] Skill '{skill_id}' not found")
        raise typer.Exit(1)

    config = SkillConfigManager.get_skill_config(skill_id)
    if config and not config.enabled:
        console.print(f"[yellow]⚠ Skill '{skill_id}' is already disabled[/yellow]")
        return

    SkillConfigManager.update_skill_config(skill_id, {"enabled": False})
    console.print(f"[yellow]✓[/yellow] Skill '{skill_id}' disabled")


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
    current = (
        SkillLifecycle(lifecycle)
        if lifecycle in [s.value for s in SkillLifecycle]
        else SkillLifecycle.ACTIVE
    )
    valid_next = SkillLifecycleManager._valid_transitions().get(current, frozenset())
    next_states = ", ".join(s.value for s in valid_next) if valid_next else "none (terminal)"

    console.print(
        Panel(
            f"[bold]ID:[/bold] {skill_id}\n"
            f"[bold]Name:[/bold] {skill.get('name', 'N/A')}\n"
            f"[bold]State:[/bold] {lifecycle}\n"
            f"[bold]Enabled:[/bold] {'Yes' if enabled else 'No'}\n"
            f"[bold]Scope:[/bold] {skill.get('scope', 'global')}\n"
            f"[bold]Version:[/bold] {skill.get('version', '1.0.0')}\n"
            f"[bold]Valid transitions:[/bold] {next_states}",
            title=f"Skill Status: {skill_id}",
            border_style="blue" if enabled else "yellow",
        )
    )


@app.command()
def stale(
    auto_deprecate: bool = typer.Option(
        False, "--auto", "-a", help="Automatically deprecate stale skills"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
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

    # Separate into deprecate/warn/boost/archive categories
    to_archive = [s for s in suggestions if s.action == "archive"]
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
        "archive": ("[red]ARCHIVE[/red]", "red"),
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
    summary_parts = []
    if to_archive:
        summary_parts.append(f"[red]{len(to_archive)} to archive[/red]")
    if to_deprecate:
        summary_parts.append(f"[red]{len(to_deprecate)} to deprecate[/red]")
    if to_warn:
        summary_parts.append(f"[yellow]{len(to_warn)} to warn[/yellow]")
    if to_boost:
        summary_parts.append(f"[green]{len(to_boost)} performing well[/green]")
    console.print(f"\n[bold]Summary:[/bold] {', '.join(summary_parts)}")

    if (to_deprecate or to_archive) and not auto_deprecate:
        console.print(
            "\n[dim]Run `vibe skill stale --auto` to apply deprecations and archives automatically.[/dim]"
        )


@app.command()
def end_check(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Run end-of-session checks: retention + skill suggestions.

    Called automatically by the session-end hook, or manually
    to review skill health and auto-detected patterns.

    \b
    Examples:
        vibe skill end-check
        vibe skill end-check --json
    """
    from vibesop.core.skills.feedback_loop import FeedbackLoop

    loop = FeedbackLoop()
    result = loop.end_of_session_check()

    if json_output:
        import json

        console.print(json.dumps(result, indent=2, default=str))
        return

    retention = result.get("retention_actions", [])
    if retention:
        console.print(
            f"\n[yellow]Skill Health:[/yellow] [bold]{len(retention)}[/bold] action(s) suggested"
        )
        for r in retention:
            console.print(f"  [dim]{r['skill_id']}:[/dim] {r['action']} — {r['reason']}")
        console.print("  [dim]Run `vibe skill stale` for details.[/dim]")

    if result.get("should_prompt_suggestions"):
        pending = result.get("skill_suggestions_pending", 0)
        console.print(
            f"\n[bold cyan]Skill Suggestions:[/bold cyan] [bold]{pending}[/bold] pattern(s) detected"
        )
        console.print("  [dim]Run `vibe skills suggestions` to review and create skills.[/dim]")

    if not retention and not result.get("should_prompt_suggestions"):
        console.print("[green]All skills healthy. No new pattern suggestions.[/green]")
