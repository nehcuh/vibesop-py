"""VibeSOP skills command - Manage skill storage.

Usage:
    vibe skills list
    vibe skills available
    vibe skills info <skill_id>
    vibe skills install <skill_id>
    vibe skills link <skill_id> <platform>
    vibe skills unlink <skill_id> <platform>
    vibe skills remove <skill_id>
    vibe skills sync
"""

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.evaluation import RoutingEvaluator
from vibesop.core.skills import SkillManager, SkillStorage
from vibesop.core.skills.config_manager import SkillConfigManager

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
        # Show skills linked to a specific platform
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

    elif all_:
        # Show detailed information
        skills = storage.list_skills()

        table = Table(title="Installed Skills")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Version", style="yellow")
        table.add_column("Source", style="dim")
        table.add_column("Installed", style="dim")

        for skill_id, manifest in skills.items():
            source_str = f"{manifest.source.type}"
            if manifest.source.version:
                source_str += f"@{manifest.source.version}"

            table.add_row(
                skill_id,
                manifest.name,
                manifest.version,
                source_str,
                manifest.installed_at[:10],
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(skills)} skills[/dim]")

    else:
        # Simple list
        skills = storage.list_skills()
        console.print("\n[bold]Installed Skills:[/bold]")
        console.print(f"  {len(skills)} skills\n")

        for skill_id in skills:
            console.print(f"  [cyan]{skill_id}[/cyan]")


def install(
    skill_id: str = typer.Argument(..., help="Skill identifier"),
    source: Path | None = typer.Option(  # noqa: B008
        None,
        "--source",
        "-s",
        help="Local path to skill directory",
    ),
    url: str | None = typer.Option(
        None,
        "--url",
        "-u",
        help="Remote URL to download skill from",
    ),
    overwrite: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite if already exists",
    ),
) -> None:
    """Install a skill to central storage.

    \b
    Examples:
        # Install from project
        vibe skills install systematic-debugging

        # Install from local path
        vibe skills install my-skill --source ./skills/my-skill

        # Install from remote URL
        vibe skills install my-skill --url https://example.com/skill.tar.gz

        # Overwrite existing
        vibe skills install systematic-debugging --force
    """
    storage = SkillStorage()

    # Determine source
    if url:
        console.print(f"[dim]Downloading {skill_id} from {url}...[/dim]")
        success, msg = storage.install_from_remote(skill_id, url, overwrite)
    elif source:
        success, msg = storage.install_skill(skill_id, source, overwrite)
    else:
        # Try to find in project
        project_skills = Path("core") / "skills" / skill_id
        if project_skills.exists():
            success, msg = storage.install_skill(skill_id, project_skills, overwrite)
        else:
            console.print(f"[red]✗ Skill not found in project: {skill_id}[/red]")
            console.print("[dim]Use --source or --url to specify location[/dim]")
            raise typer.Exit(1)

    if success:
        console.print(f"[green]✓ {msg}[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")
        raise typer.Exit(1)


def link(
    skill_id: str = typer.Argument(..., help="Skill identifier"),
    platform: str = typer.Argument(..., help="Target platform"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing link",
    ),
) -> None:
    """Link a skill to a platform.

    Creates a symlink from the platform's skills directory to the
    central storage location.

    \b
    Examples:
        # Link skill to claude-code
        vibe skills link systematic-debugging claude-code

        # Force overwrite existing
        vibe skills link systematic-debugging claude-code --force
    """
    storage = SkillStorage()

    success, msg = storage.link_to_platform(skill_id, platform, force)

    if success:
        console.print(f"[green]✓ {msg}[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")
        raise typer.Exit(1)


def unlink(
    skill_id: str = typer.Argument(..., help="Skill identifier"),
    platform: str = typer.Argument(..., help="Target platform"),
) -> None:
    """Unlink a skill from a platform.

    Removes the symlink but keeps the skill in central storage.

    \b
    Examples:
        vibe skills unlink systematic-debugging claude-code
    """
    storage = SkillStorage()

    success, msg = storage.unlink_from_platform(skill_id, platform)

    if success:
        console.print(f"[green]✓ {msg}[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")
        raise typer.Exit(1)


def remove(
    skill_id: str = typer.Argument(..., help="Skill identifier"),
    unlink_all: bool = typer.Option(
        False,
        "--unlink-all",
        "-u",
        help="Also remove from all platforms",
    ),
) -> None:
    """Remove a skill from central storage.

    WARNING: This will delete the skill from central storage.

    \b
    Examples:
        # Remove from central storage (if not linked)
        vibe skills remove old-skill

        # Remove and unlink from all platforms
        vibe skills remove old-skill --unlink-all
    """
    storage = SkillStorage()

    # Check if skill is linked to any platforms
    linked_platforms = []
    for platform_name in storage.PLATFORM_SKILLS_DIRS:
        platform_path = storage.PLATFORM_SKILLS_DIRS[platform_name] / skill_id
        if platform_path.exists():
            linked_platforms.append(platform_name)

    if linked_platforms and not unlink_all:
        console.print(f"[yellow]⚠ Skill is linked to: {', '.join(linked_platforms)}[/yellow]")
        console.print("[dim]Use --unlink-all to remove from all platforms[/dim]")
        console.print("[dim]Or unlink manually first:[/dim]")
        for platform_name in linked_platforms:
            console.print(f"  [dim]vibe skills unlink {skill_id} {platform_name}[/dim]")
        raise typer.Exit(1)

    success, msg = storage.remove_skill(skill_id, unlink_all=True)

    if success:
        console.print(f"[green]✓ {msg}[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")
        raise typer.Exit(1)


def sync(
    platform: str = typer.Argument(..., help="Target platform"),
    project_root: Path = typer.Option(  # noqa: B008
        Path(),
        "--root",
        "-r",
        help="Project root directory",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing links",
    ),
) -> None:
    """Sync all project skills to a platform.

    Installs all skills from core/skills/ to central storage
    and creates symlinks for the specified platform.

    \b
    Examples:
        # Sync to claude-code
        vibe skills sync claude-code

        # Sync from different project root
        vibe skills sync claude-code --root /path/to/vibesop

        # Force overwrite
        vibe skills sync claude-code --force
    """
    from rich.progress import Progress

    storage = SkillStorage()

    with Progress("[progress.bar.default]{}".format(" {task.description}")) as progress:
        task = progress.add_task(
            f"Syncing skills to {platform}",
            total=100,
        )

        installed, linked, _messages = storage.sync_project_skills(
            project_root=project_root,
            platform=platform,
            force=force,
        )

        progress.update(task, completed=100)

    console.print("\n[green]✓ Sync complete![/green]")
    console.print(f"  [dim]Installed:[/dim] {installed} skills")
    console.print(f"  [dim]Linked:[/dim] {linked} skills")


def status() -> None:
    """Show skill storage and health status."""
    storage = SkillStorage()

    # Check central storage
    central_exists = storage.CENTRAL_SKILLS_DIR.exists()
    central_count = len(storage.list_skills())

    # Collect platform info
    platform_info = {}
    for platform_name, platform_dir in storage.PLATFORM_SKILLS_DIRS.items():
        if platform_dir.exists():
            linked = storage.get_linked_skills(platform_name)
            platform_info[platform_name] = {
                "exists": True,
                "linked": len(linked),
                "symlinks": sum(1 for s in platform_dir.iterdir() if s.is_symlink())
                if platform_dir.exists()
                else 0,
            }
        else:
            platform_info[platform_name] = {
                "exists": False,
                "linked": 0,
                "symlinks": 0,
            }

    # Display status
    console.print("\n[bold]Skill Storage Status[/bold]\n")

    # Central storage
    central_status = "[green]✓[/green]" if central_exists else "[red]✗[/red]"
    console.print(f"{central_status} Central Storage: {storage.CENTRAL_SKILLS_DIR}")
    console.print(f"    [dim]Skills installed: {central_count}[/dim]\n")

    # Platform directories
    console.print("[bold]Platform Directories:[/bold]\n")
    for platform_name, info in platform_info.items():
        if info["exists"]:
            status = f"[green]{info['linked']} linked[/green]"
            symlink_count = info["symlinks"]
            console.print(f"  {platform_name}: {status} ({symlink_count} symlinks)")
        else:
            console.print(f"  {platform_name}: [dim]not created[/dim]")

    console.print("")

    # Health check (summary only)
    try:
        from vibesop.integrations.health_monitor import SkillHealthMonitor

        monitor = SkillHealthMonitor()
        summary = monitor.get_health_summary()

        # Display brief health summary
        console.print("[bold]Skill Pack Health:[/bold]\n")
        console.print(f"  Total: {summary['total']} packs, {summary['total_skills']} skills")
        console.print(
            f"  [green]✓ Healthy: {summary['healthy']}[/green] | "
            f"[yellow]⚠ Warning: {summary['warning']}[/yellow] | "
            f"[red]✗ Critical: {summary['critical']}[/red]"
        )
        console.print("\n[dim]Tip: Run 'vibe skills health' for detailed health check[/dim]\n")
    except Exception as e:
        console.print(f"[yellow]⚠ Could not check skill health: {e}[/yellow]\n")


def health(
    pack: str | None = typer.Option(
        None,
        "--pack",
        "-p",
        help="Check specific skill pack only",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed health information",
    ),
) -> None:
    """Check skill pack health status.

    \b
    Examples:
        # Check all skill packs
        vibe skills health

        # Check specific pack
        vibe skills health --pack gstack

        # Show detailed information
        vibe skills health --verbose
    """
    from vibesop.integrations.health_monitor import SkillHealthMonitor

    monitor = SkillHealthMonitor()

    if pack:
        # Check single pack
        status = monitor.check_local_health(pack)
        _display_health_status(status, verbose=verbose)
    else:
        # Check all packs
        all_health = monitor.check_all_local()

        if not all_health:
            console.print("[yellow]No skill packs found[/yellow]")
            return

        # Show summary
        summary = monitor.get_health_summary()
        console.print("\n[bold]Skill Pack Health Check[/bold]\n")
        console.print(
            f"Total: [bold]{summary['total']}[/bold] packs | "
            f"[green]✓ {summary['healthy']} healthy[/green] | "
            f"[yellow]⚠ {summary['warning']} warnings[/yellow] | "
            f"[red]✗ {summary['critical']} critical[/red]\n"
        )

        # Show details for each pack
        for pack_name, health_status in sorted(all_health.items()):
            _display_health_status(health_status, verbose=verbose)


def _display_health_status(health_status, verbose: bool = False) -> None:
    """Display health status for a single pack.

    Args:
        health_status: HealthStatus object
        verbose: Show detailed information
    """
    from vibesop.integrations.health_monitor import HealthStatus

    # Determine icon and color
    icon_map = {
        "healthy": ("✓", "green"),
        "warning": ("⚠", "yellow"),
        "critical": ("✗", "red"),
        "unknown": ("?", "dim"),
    }

    icon, color = icon_map.get(health_status.health, ("?", "dim"))

    # Display pack status
    console.print(
        f"[{color}]{icon}[/{color}] {health_status.name}: "
        f"[bold {color}]{health_status.health}[/bold {color}] "
        f"([dim]{health_status.skills_count} skills[/dim])"
    )

    if verbose and health_status.version != "unknown":
        console.print(f"  [dim]Version: {health_status.version}[/dim]")

    # Display reasons if verbose or if not healthy
    if verbose or health_status.health != "healthy":
        for reason in health_status.reasons:
            console.print(f"  [dim]• {reason}[/dim]")

    console.print("")


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

    # Show evaluation metrics if available
    try:
        evaluator = RoutingEvaluator()
        evaluation = evaluator.evaluate_skill(skill_id)
        if evaluation and evaluation.total_routes > 0:
            console.print(f"\n[bold]Quality Metrics[/bold]")
            console.print(f"  [dim]Routes:[/dim] {evaluation.total_routes}")
            console.print(f"  [dim]Success Rate:[/dim] {evaluation.success_rate:.0%}")
            console.print(f"  [dim]Avg Confidence:[/dim] {evaluation.avg_confidence:.0%}")
            console.print(f"  [dim]User Score:[/dim] {evaluation.user_score:.2f}")
            quality_color = "green" if evaluation.quality_score >= 0.7 else "yellow" if evaluation.quality_score >= 0.4 else "red"
            console.print(f"  [dim]Quality Score:[/dim] [{quality_color}]{evaluation.quality_score:.0%}[/{quality_color}]")
            if evaluation.last_used:
                console.print(f"  [dim]Last Used:[/dim] {evaluation.last_used[:10]}")
    except Exception:
        # Silently skip if evaluation data is not available
        pass


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
    # Verify skill exists
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
    # Verify skill exists
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


def report(
    grade: str | None = typer.Option(
        None,
        "--grade",
        "-g",
        help="Filter by grade (A, B, C, D, F)",
    ),
    suggest_removal: bool = typer.Option(
        False,
        "--suggest-removal",
        help="Show only skills recommended for removal (grade F)",
    ),
) -> None:
    """Show skill quality report with grades.

    \b
    Examples:
        # Show all skills with grades
        vibe skills report

        # Show only skills needing attention
        vibe skills report --grade D

        # Show skills recommended for removal
        vibe skills report --suggest-removal
    """
    from rich.table import Table

    evaluator = RoutingEvaluator()
    all_evals = evaluator.evaluate_all_skills()

    if not all_evals:
        console.print("[yellow]No evaluation data available.[/yellow]")
        console.print("[dim]Use skills to generate feedback data.[/dim]")
        raise typer.Exit(0)

    # Filter
    filtered = list(all_evals.values())
    if suggest_removal:
        filtered = [e for e in filtered if e.grade == "F"]
    elif grade:
        filtered = [e for e in filtered if e.grade == grade.upper()]

    if not filtered:
        console.print("[dim]No skills match the filter criteria.[/dim]")
        raise typer.Exit(0)

    # Sort by quality score descending
    filtered.sort(key=lambda e: e.quality_score, reverse=True)

    table = Table(title="Skill Quality Report")
    table.add_column("Skill", style="cyan")
    table.add_column("Grade", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Routes", justify="right")
    table.add_column("Success", justify="right")
    table.add_column("User Score", justify="right")

    grade_colors = {
        "A": "green",
        "B": "green",
        "C": "yellow",
        "D": "yellow",
        "F": "red",
    }
    grade_icons = {
        "A": "✅",
        "B": "✅",
        "C": "✓",
        "D": "⚠️",
        "F": "🗑️",
    }

    for evaluation in filtered:
        color = grade_colors.get(evaluation.grade, "dim")
        icon = grade_icons.get(evaluation.grade, "")
        table.add_row(
            evaluation.skill_id,
            f"[{color}]{evaluation.grade}[/{color}] {icon}",
            f"{evaluation.quality_score:.0%}",
            str(evaluation.total_routes),
            f"{evaluation.success_rate:.0%}" if evaluation.total_routes > 0 else "—",
            f"{evaluation.user_score:.2f}",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(filtered)} skills[/dim]")
