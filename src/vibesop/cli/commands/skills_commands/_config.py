# pyright: ignore[reportPossiblyUnboundVariable, reportUnnecessaryComparison]
"""Config commands: enable, disable, scope, lifecycle."""

from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from vibesop.core.skills import SkillManager
from vibesop.core.skills.config_manager import SkillConfigManager

console = Console()


def enable(
    skill_id: str = typer.Argument(..., help="Skill ID to enable"),
) -> None:
    """Enable a skill for routing.

    \b
    Examples:
        # Enable a skill
        vibe skills enable my-skill

        # Enable a namespaced skill
        vibe skills enable gstack/review
    """
    manager = SkillManager()
    skill_info_data = manager.get_skill_info(skill_id)
    if not skill_info_data:
        console.print(f"[red]✗ Skill not found: {skill_id}[/red]")
        raise typer.Exit(1)

    config = SkillConfigManager.get_skill_config(skill_id)
    if config and config.enabled:
        console.print(f"[yellow]⚠ Skill '{skill_id}' is already enabled[/yellow]")
        return

    SkillConfigManager.update_skill_config(skill_id, {"enabled": True})
    console.print(f"[green]✓ Skill '{skill_id}' enabled[/green]")


def disable(
    skill_id: str = typer.Argument(..., help="Skill ID to disable"),
) -> None:
    """Disable a skill from routing.

    Disabled skills are excluded from routing candidates but remain installed.

    \b
    Examples:
        # Disable a skill
        vibe skills disable my-skill

        # Disable a namespaced skill
        vibe skills disable gstack/review
    """
    manager = SkillManager()
    skill_info_data = manager.get_skill_info(skill_id)
    if not skill_info_data:
        console.print(f"[red]✗ Skill not found: {skill_id}[/red]")
        raise typer.Exit(1)

    config = SkillConfigManager.get_skill_config(skill_id)
    if config and not config.enabled:
        console.print(f"[yellow]⚠ Skill '{skill_id}' is already disabled[/yellow]")
        return

    SkillConfigManager.update_skill_config(skill_id, {"enabled": False})
    console.print(f"[yellow]✓ Skill '{skill_id}' disabled[/yellow]")


def scope(
    skill_id: str = typer.Argument(..., help="Skill ID"),
    set_scope: str | None = typer.Option(
        None,
        "--set",
        help="Set scope: global, project, or session",
    ),
) -> None:
    """Get or set a skill's scope.

    \b
    Examples:
        # Show current scope
        vibe skills scope my-skill

        # Set to project scope
        vibe skills scope my-skill --set project

        # Set to global scope
        vibe skills scope my-skill --set global
    """
    manager = SkillManager()
    skill_info_data = manager.get_skill_info(skill_id)
    if not skill_info_data:
        console.print(f"[red]✗ Skill not found: {skill_id}[/red]")
        raise typer.Exit(1)

    config = SkillConfigManager.get_skill_config(skill_id)
    current_scope = config.scope if config else "global"

    if set_scope is None:
        console.print(f"[dim]Current scope for '{skill_id}':[/dim] [cyan]{current_scope}[/cyan]")
        if current_scope == "project":
            project_hash = (
                config.evaluation_context.get("project_hash", "unknown") if config else "unknown"
            )
            console.print(f"  [dim]Bound to project: {project_hash}[/dim]")
        return

    if set_scope not in ("global", "project", "session"):
        console.print(
            f"[red]✗ Invalid scope: {set_scope}. Must be global, project, or session.[/red]"
        )
        raise typer.Exit(1)

    import hashlib

    updates: dict[str, Any] = {"scope": set_scope}
    if set_scope == "project":
        project_hash = hashlib.md5(str(Path.cwd().resolve()).encode()).hexdigest()[:12]
        updates["evaluation_context"] = (
            config.evaluation_context.copy() if (config and config.evaluation_context) else {}
        )
        updates["evaluation_context"]["project_hash"] = project_hash

    SkillConfigManager.update_skill_config(skill_id, updates)
    console.print(f"[green]✓ Scope for '{skill_id}' set to {set_scope}[/green]")
    if set_scope == "project":
        console.print(
            f"  [dim]Bound to project: {updates.get('evaluation_context', {}).get('project_hash', 'unknown')}[/dim]"
        )


def lifecycle(
    skill_id: str = typer.Argument(..., help="Skill ID to inspect or modify"),
    set_state: str | None = typer.Option(
        None,
        "--set",
        help="Set lifecycle state: draft, active, deprecated, archived",
    ),
    reason: str | None = typer.Option(
        None,
        "--reason",
        help="Reason for state change (used with --set deprecated)",
    ),
    auto_review: bool = typer.Option(
        False,
        "--auto-review",
        help="Suggest lifecycle transitions based on evaluation data",
    ),
) -> None:
    """Show or change a skill's lifecycle state.

    \b
    Examples:
        # Show current lifecycle state
        vibe skills lifecycle my-skill

        # Mark as deprecated
        vibe skills lifecycle my-skill --set deprecated --reason "Replaced by v2"

        # Auto-review all skills
        vibe skills lifecycle --auto-review
    """
    from vibesop.core.skills.config_manager import SkillConfigManager, SkillLifecycleState

    if auto_review:
        _lifecycle_auto_review()
        return

    config = SkillConfigManager.get_skill_config(skill_id)
    if not config:
        console.print(f"[red]✗ Skill not found: {skill_id}[/red]")
        raise typer.Exit(1)

    current_state = config.lifecycle

    if set_state is None:
        state_colors = {
            "draft": "blue",
            "active": "green",
            "deprecated": "yellow",
            "archived": "dim",
        }
        color = state_colors.get(current_state, "white")
        console.print(
            f"[dim]Lifecycle state for '{skill_id}':[/dim] [{color}]{current_state}[/{color}]"
        )
        if current_state == "deprecated" and getattr(config, "deprecation_reason", None):
            console.print(f"  [dim]Reason: {config.deprecation_reason}[/dim]")
        return

    valid_states = [s.value for s in SkillLifecycleState]
    if set_state not in valid_states:
        console.print(
            f"[red]✗ Invalid state: {set_state}. Must be one of: {', '.join(valid_states)}[/red]"
        )
        raise typer.Exit(1)

    config.lifecycle = SkillLifecycleState(set_state)
    if reason:
        config.deprecation_reason = reason

    SkillConfigManager.update_skill_config(
        skill_id,
        {
            "lifecycle": set_state,
            "deprecation_reason": reason,
        },
    )

    state_colors = {
        "draft": "blue",
        "active": "green",
        "deprecated": "yellow",
        "archived": "dim",
    }
    color = state_colors.get(set_state, "white")
    console.print(
        f"[green]✓[/green] Lifecycle state for '{skill_id}' set to [{color}]{set_state}[/{color}]"
    )
    if reason:
        console.print(f"  [dim]Reason: {reason}[/dim]")


def _lifecycle_auto_review() -> None:
    from vibesop.core.skills.config_manager import SkillConfigManager
    from vibesop.core.skills.evaluator import RoutingEvaluator

    try:
        evaluator = RoutingEvaluator()
        all_evals = evaluator.evaluate_all_skills()
    except (OSError, ImportError, ValueError):
        console.print("[yellow]No evaluation data available.[/yellow]")
        return

    suggestions = []
    for skill_id, ev in all_evals.items():
        config = SkillConfigManager.get_skill_config(skill_id)
        current = config.lifecycle if config else "active"
        if current == "archived":
            continue
        if ev.grade == "F" and ev.total_routes >= 10 and current == "active":
            suggestions.append((skill_id, "deprecated", f"Grade F over {ev.total_routes} routes"))
        elif ev.grade == "A" and current == "draft":
            suggestions.append((skill_id, "active", "Grade A, ready for production"))

    if not suggestions:
        console.print("[dim]No lifecycle transitions suggested at this time.[/dim]")
        return

    console.print("[bold]🔍 Lifecycle Auto-Review[/bold]\n")
    for skill_id, suggested_state, reason_text in suggestions:
        console.print(
            f"  [cyan]{skill_id}[/cyan] → [yellow]{suggested_state}[/yellow] [dim]({reason_text})[/dim]"
        )
    console.print("\n[dim]Run `vibe skills lifecycle <skill> --set <state>` to apply.[/dim]")
