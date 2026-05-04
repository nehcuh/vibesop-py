# pyright: ignore[reportPossiblyUnboundVariable, reportUnnecessaryComparison]
"""Listing commands: list_skills, available, info."""

from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.skills import SkillManager, SkillStorage
from vibesop.core.skills.config_manager import SkillConfigManager
from vibesop.core.skills.evaluator import RoutingEvaluator

console = Console()


def list_skills(
    all_: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="List all skills including details",
    ),
    platform: str | None = typer.Option(
        None,
        "--platform",
        "-p",
        help="Filter by platform",
    ),
    show_scope: bool = typer.Option(
        False,
        "--show-scope",
        help="Show skill scope (global/project)",
    ),
    show_status: bool = typer.Option(
        False,
        "--show-status",
        help="Show enabled/disabled status",
    ),
) -> None:
    """List installed skills.

    \b
    Examples:
        # List all skills in central storage
        vibe skills list

        # Show detailed information
        vibe skills list --all

        # Show skills for a specific platform
        vibe skills list --platform claude-code
    """
    storage = SkillStorage()

    if platform:
        if platform not in storage.PLATFORM_SKILLS_DIRS:
            console.print(f"[red]✗ Unknown platform: {platform}[/red]")
            raise typer.Exit(1)

        linked = storage.get_linked_skills(platform)
        console.print(f"\n[bold]Skills linked to {platform}:[/bold]")
        console.print(f"  {len(linked)} skills\n")

        if linked:
            for skill_id in linked:
                is_link = (storage.PLATFORM_SKILLS_DIRS[platform] / skill_id).is_symlink()
                link_type = "[cyan]→[/cyan]" if is_link else "[dim]cp[/dim]"
                console.print(f"  {link_type} {skill_id}")

    elif all_ or show_scope or show_status:
        skills = storage.list_skills()

        table = Table(title="Installed Skills")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Version", style="yellow")
        if show_status:
            table.add_column("Status", style="white")
        if show_scope:
            table.add_column("Scope", style="magenta")
        table.add_column("Quality", justify="center")
        table.add_column("Source", style="dim")
        table.add_column("Installed", style="dim")

        evaluator = RoutingEvaluator()
        evals = evaluator.evaluate_all_skills()

        for skill_id, manifest in skills.items():
            source_str = f"{manifest.source.type}"
            if manifest.source.version:
                source_str += f"@{manifest.source.version}"

            evaluation = evals.get(skill_id)
            if evaluation and evaluation.total_routes >= 3:
                grade_colors = {
                    "A": "green",
                    "B": "green",
                    "C": "yellow",
                    "D": "yellow",
                    "F": "red",
                }
                quality_str = f"[{grade_colors.get(evaluation.grade, 'dim')}]{evaluation.grade}[/{grade_colors.get(evaluation.grade, 'dim')}]"
            else:
                quality_str = "[dim]—[/dim]"

            row = [
                skill_id,
                manifest.name,
                manifest.version,
            ]
            if show_status:
                config = SkillConfigManager.get_skill_config(skill_id)
                status = (
                    "[green]✓ enabled[/green]"
                    if (config and config.enabled)
                    else "[red]✗ disabled[/red]"
                )
                row.append(status)
            if show_scope:
                config = SkillConfigManager.get_skill_config(skill_id)
                scope = config.scope if config else "global"
                row.append(scope)
            row.extend([quality_str, source_str, manifest.installed_at[:10]])

            table.add_row(*row)

        console.print(table)
        console.print(f"\n[dim]Total: {len(skills)} skills[/dim]")

    else:
        skills = storage.list_skills()
        console.print("\n[bold]Installed Skills:[/bold]")
        console.print(f"  {len(skills)} skills\n")

        for skill_id in skills:
            console.print(f"  [cyan]{skill_id}[/cyan]")


def available(
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Filter by namespace"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
) -> None:
    """List all available skills from all sources.

    Shows skills from builtin, installed packs, and project directories.

    \b
    Examples:
        # List all available skills
        vibe skills available

        # Show detailed information
        vibe skills available --verbose

        # Filter by namespace
        vibe skills available --namespace gstack
    """
    manager = SkillManager()
    all_skills = manager.list_skills(namespace=namespace)

    if not all_skills:
        console.print("[yellow]No skills found.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]📚 Available Skills[/bold] ({len(all_skills)} total)\n")

    by_namespace: dict[str, list[dict[str, Any]]] = {}
    for skill in all_skills:
        ns = skill.get("namespace", "builtin")
        if ns not in by_namespace:
            by_namespace[ns] = []
        by_namespace[ns].append(skill)

    for ns in sorted(by_namespace.keys()):
        ns_skills = by_namespace[ns]
        console.print(f"[bold cyan]{ns}[/bold cyan] ({len(ns_skills)} skills)")
        for skill in ns_skills:
            sid: str = skill.get("id", "unknown")
            name: str = skill.get("name", sid)
            desc: str = skill.get("description", "")
            stype: str = skill.get("type", "prompt")
            if verbose:
                console.print(
                    f"  • [bold]{sid}[/bold] ([dim]{stype}[/dim])\n"
                    f"    Name: {name}\n"
                    f"    Description: {desc}\n"
                    f"    Tags: {skill.get('tags', [])}\n"
                    f"    Source: {skill.get('source', 'unknown')}"
                )
            else:
                console.print(f"  • [bold]{sid}[/bold] - {desc}")
        console.print()

    stats = manager.get_stats()
    console.print(f"[dim]Namespaces: {', '.join(stats['namespaces'])}[/dim]")


def info(
    skill_id: str = typer.Argument(..., help="Skill ID (e.g., gstack/review)"),
) -> None:
    """Show detailed information about a skill.

    \b
    Examples:
        # Show info for a skill
        vibe skills info systematic-debugging

        # Show info for namespaced skill
        vibe skills info gstack/review
    """
    manager = SkillManager()
    skill_info_data = manager.get_skill_info(skill_id)

    if not skill_info_data:
        console.print(f"[red]Skill not found: {skill_id}[/red]")
        raise typer.Exit(1)

    console.print(
        Panel.fit(
            f"[bold]{skill_info_data.get('name', skill_info_data['id'])}[/bold]\n\n"
            f"[dim]ID:[/dim] {skill_info_data['id']}\n"
            f"[dim]Type:[/dim] {skill_info_data.get('type', 'prompt')}\n"
            f"[dim]Namespace:[/dim] {skill_info_data.get('namespace', 'builtin')}\n"
            f"[dim]Version:[/dim] {skill_info_data.get('version', '1.0.0')}\n"
            f"[dim]Author:[/dim] {skill_info_data.get('author', 'N/A')}\n"
            f"[dim]Source:[/dim] {skill_info_data.get('source', 'unknown')}\n"
            f"\n[bold]Description[/bold]\n"
            f"{skill_info_data.get('description', 'No description')}\n"
            f"\n[bold]Intent[/bold]\n"
            f"{skill_info_data.get('intent', 'No intent specified')}\n"
            f"\n[bold]Tags[/bold]\n"
            f"{', '.join(skill_info_data.get('tags') or []) or 'None'}",
            title="[bold]Skill Info[/bold]",
            border_style="blue",
        )
    )
    if skill_info_data.get("source_file"):
        console.print(f"\n[dim]Source file: {skill_info_data['source_file']}[/dim]")

    try:
        evaluator = RoutingEvaluator()
        evaluation = evaluator.evaluate_skill(skill_id)
        if evaluation and evaluation.total_routes > 0:
            console.print("\n[bold]Quality Metrics[/bold]")
            console.print(f"  [dim]Routes:[/dim] {evaluation.total_routes}")
            console.print(f"  [dim]Success Rate:[/dim] {evaluation.success_rate:.0%}")
            console.print(f"  [dim]Avg Confidence:[/dim] {evaluation.avg_confidence:.0%}")
            console.print(f"  [dim]User Score:[/dim] {evaluation.user_score:.2f}")
            quality_color = (
                "green"
                if evaluation.quality_score >= 0.7
                else "yellow"
                if evaluation.quality_score >= 0.4
                else "red"
            )
            console.print(
                f"  [dim]Quality Score:[/dim] [{quality_color}]{evaluation.quality_score:.0%}[/{quality_color}]"
            )
            if evaluation.last_used:
                console.print(f"  [dim]Last Used:[/dim] {evaluation.last_used[:10]}")
    except (OSError, ValueError):
        pass
