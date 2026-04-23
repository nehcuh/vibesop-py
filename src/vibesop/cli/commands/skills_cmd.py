# pyright: ignore[reportPossiblyUnboundVariable, reportUnnecessaryComparison]
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

import questionary
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

    elif all_ or show_scope or show_status:
        # Show detailed information
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

        # Load evaluations once for quality warnings
        from vibesop.core.skills.evaluator import RoutingEvaluator
        evaluator = RoutingEvaluator()
        evals = evaluator.evaluate_all_skills()

        for skill_id, manifest in skills.items():
            source_str = f"{manifest.source.type}"
            if manifest.source.version:
                source_str += f"@{manifest.source.version}"

            # Quality warning for low-grade skills
            evaluation = evals.get(skill_id)
            if evaluation and evaluation.total_routes >= 3:
                grade_colors = {"A": "green", "B": "green", "C": "yellow", "D": "yellow", "F": "red"}
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
                status = "[green]✓ enabled[/green]" if (config and config.enabled) else "[red]✗ disabled[/red]"
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
    ecosystem: bool = typer.Option(
        False,
        "--ecosystem",
        "-e",
        help="Show gamified ecosystem health report",
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

        # Show ecosystem health report
        vibe skills health --ecosystem
    """
    from vibesop.integrations.health_monitor import SkillHealthMonitor

    monitor = SkillHealthMonitor()

    # Ecosystem gamified report
    if ecosystem:
        _show_ecosystem_report(monitor)
        return

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
        for _pack_name, health_status in sorted(all_health.items()):
            _display_health_status(health_status, verbose=verbose)

        # Show evaluation metrics (Phase 3)
        try:
            evaluator = RoutingEvaluator()
            all_evals = evaluator.evaluate_all_skills()
            if all_evals:
                console.print("\n[bold]Skill Quality Overview[/bold]\n")
                for skill_id, evaluation in sorted(
                    all_evals.items(), key=lambda x: x[1].quality_score, reverse=True
                )[:10]:
                    grade_color = {
                        "A": "green", "B": "green", "C": "yellow",
                        "D": "yellow", "F": "red",
                    }.get(evaluation.grade, "dim")
                    icon = "✅" if evaluation.grade in ("A", "B") else "⚠️" if evaluation.grade in ("C", "D") else "🗑️"
                    console.print(
                        f"  {icon} [cyan]{skill_id}[/cyan] "
                        f"[{grade_color}]{evaluation.grade} ({evaluation.quality_score:.0%})[/{grade_color}] "
                        f"[dim]{evaluation.total_routes} uses[/dim]"
                    )
        except (OSError, ValueError):
            pass


def _show_ecosystem_report(monitor: Any) -> None:
    """Render gamified ecosystem health report."""
    from datetime import datetime

    console.print(f"\n[bold]📊 Your Skill Ecosystem Health[/bold] [dim]({datetime.now().strftime('%Y-%m-%d')})[/dim]\n")

    # Gather data
    summary = monitor.get_health_summary()
    try:
        evaluator = RoutingEvaluator()
        all_evals = evaluator.evaluate_all_skills()
    except (OSError, ImportError, ValueError):
        all_evals = {}

    if not all_evals:
        console.print("[dim]No evaluation data yet. Use skills to generate feedback![/dim]")
        return

    # Group by grade
    top_performers = []
    needs_attention = []
    at_risk = []
    insufficient = []

    for skill_id, ev in sorted(all_evals.items(), key=lambda x: x[1].quality_score, reverse=True):
        if ev.total_routes < 3:
            insufficient.append((skill_id, ev))
        elif ev.grade in ("A", "B"):
            top_performers.append((skill_id, ev))
        elif ev.grade in ("C", "D"):
            needs_attention.append((skill_id, ev))
        else:
            at_risk.append((skill_id, ev))

    # Top Performers
    if top_performers:
        console.print("[bold green]🏆 Top Performers[/bold green]")
        for sid, ev in top_performers[:5]:
            bar = "█" * int(ev.quality_score * 10) + "░" * (10 - int(ev.quality_score * 10))
            impact = "+0.05 boost" if ev.grade == "A" else "+0.02 boost"
            console.print(
                f"  [cyan]{sid:<30}[/cyan] {ev.grade}  {impact}  [dim]{bar}[/dim]  {ev.total_routes} routes"
            )
        console.print()

    # Needs Attention
    if needs_attention:
        console.print("[bold yellow]⚠️  Needs Attention[/bold yellow]")
        for sid, ev in needs_attention[:5]:
            impact = "no change" if ev.grade == "C" else "-0.02 demote"
            console.print(
                f"  [cyan]{sid:<30}[/cyan] {ev.grade}  {impact}  [dim]{ev.total_routes} routes[/dim]"
            )
        console.print()

    # At Risk
    if at_risk:
        console.print("[bold red]🗑️  At Risk[/bold red]")
        for sid, ev in at_risk[:5]:
            console.print(
                f"  [cyan]{sid:<30}[/cyan] {ev.grade}  -0.05 demote  [dim]{ev.total_routes} routes[/dim]"
            )
        console.print("  [dim]Action: Run `vibe skills feedback --skill <id>` or `vibe skills disable <id>`[/dim]")
        console.print()

    # Insufficient Data
    if insufficient:
        console.print("[bold blue]💡 Feedback Opportunities[/bold blue]")
        console.print(f"  [dim]{len(insufficient)} skills need more usage to reach reliable grading:[/dim]")
        for sid, ev in insufficient[:3]:
            needed = 3 - ev.total_routes
            console.print(f"    • {sid}: {ev.total_routes}/3 routes (needs {needed} more)")
        console.print()

    # Summary stats
    console.print("[bold]📈 Ecosystem Stats[/bold]")
    console.print(f"  Total skills evaluated: {len(all_evals)}")
    console.print(f"  Packs: {summary.get('total', 0)} total, {summary.get('healthy', 0)} healthy")
    console.print()

    # Badges
    from vibesop.core.badges import BadgeTracker, get_badge_display

    tracker = BadgeTracker()
    badges = tracker.list_badges()
    if badges:
        console.print("[bold]🎖️  Earned Badges[/bold]")
        for badge in badges:
            meta = get_badge_display(badge.type)
            console.print(f"  {meta['icon']} {meta['title']}")
        console.print()
    else:
        console.print("[dim]No badges yet. Give feedback to earn your first one![/dim]")
        console.print()


def _display_health_status(health_status: Any, verbose: bool = False) -> None:
    """Display health status for a single pack.

    Args:
        health_status: HealthStatus object
        verbose: Show detailed information
    """
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
            console.print("\n[bold]Quality Metrics[/bold]")
            console.print(f"  [dim]Routes:[/dim] {evaluation.total_routes}")
            console.print(f"  [dim]Success Rate:[/dim] {evaluation.success_rate:.0%}")
            console.print(f"  [dim]Avg Confidence:[/dim] {evaluation.avg_confidence:.0%}")
            console.print(f"  [dim]User Score:[/dim] {evaluation.user_score:.2f}")
            quality_color = "green" if evaluation.quality_score >= 0.7 else "yellow" if evaluation.quality_score >= 0.4 else "red"
            console.print(f"  [dim]Quality Score:[/dim] [{quality_color}]{evaluation.quality_score:.0%}[/{quality_color}]")
            if evaluation.last_used:
                console.print(f"  [dim]Last Used:[/dim] {evaluation.last_used[:10]}")
    except (OSError, ValueError):
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
    table.add_column("Routing Impact", justify="center")

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
    # Routing impact from quality_boost adjustments
    impact_map = {
        "A": "[green]+0.05 boost[/green]",
        "B": "[green]+0.02 boost[/green]",
        "C": "[dim]no change[/dim]",
        "D": "[yellow]-0.02 demote[/yellow]",
        "F": "[red]-0.05 demote[/red]",
    }

    for evaluation in filtered:
        color = grade_colors.get(evaluation.grade, "dim")
        icon = grade_icons.get(evaluation.grade, "")
        impact = impact_map.get(evaluation.grade, "—")
        # Only show impact if sufficient data
        if evaluation.total_routes < 3:
            impact = "[dim]insufficient data[/dim]"
        table.add_row(
            evaluation.skill_id,
            f"[{color}]{evaluation.grade}[/{color}] {icon}",
            f"{evaluation.quality_score:.0%}",
            str(evaluation.total_routes),
            f"{evaluation.success_rate:.0%}" if evaluation.total_routes > 0 else "—",
            f"{evaluation.user_score:.2f}",
            impact,
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(filtered)} skills[/dim]")
    console.print("[dim]Routing impact only applies when total_routes >= 3[/dim]")


def scope(
    skill_id: str = typer.Argument(..., help="Skill ID"),
    set_scope: str = typer.Option(
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
        return

    if set_scope not in ("global", "project", "session"):
        console.print(f"[red]✗ Invalid scope: {set_scope}. Must be global, project, or session.[/red]")
        raise typer.Exit(1)

    SkillConfigManager.set_scope(skill_id, set_scope)
    console.print(f"[green]✓ Scope for '{skill_id}' set to {set_scope}[/green]")


def feedback(
    skill_id: str = typer.Option(..., "--skill", "-s", help="Skill ID"),
    query: str = typer.Option(..., "--query", "-q", help="Original user query"),
    helpful: str | None = typer.Option(
        None,
        "--helpful",
        "-h",
        help="Was the skill helpful? (yes/no)",
    ),
    success: str | None = typer.Option(
        None,
        "--success",
        help="Did execution succeed? (yes/no)",
    ),
    execution_time: float | None = typer.Option(
        None,
        "--time",
        "-t",
        help="Execution time in milliseconds",
    ),
    notes: str | None = typer.Option(
        None,
        "--notes",
        "-n",
        help="Optional notes",
    ),
) -> None:
    """Record post-execution feedback for a skill.

    \b
    Examples:
        # Mark a skill as helpful
        vibe skills feedback --skill gstack/review --query "review code" --helpful yes

        # Report execution failure with notes
        vibe skills feedback --skill gstack/review --query "review code" --success no --notes "missed edge case"
    """
    from vibesop.core.feedback import ExecutionFeedbackCollector

    collector = ExecutionFeedbackCollector()

    was_helpful = None
    if helpful is not None:
        was_helpful = helpful.lower() in ("yes", "true", "1", "y")

    execution_success = None
    if success is not None:
        execution_success = success.lower() in ("yes", "true", "1", "y")

    collector.collect(
        skill_id=skill_id,
        query=query,
        was_helpful=was_helpful,
        execution_success=execution_success,
        execution_time_ms=execution_time,
        notes=notes,
    )

    console.print(f"[green]✓ Feedback recorded for '{skill_id}'[/green]")
    if was_helpful is not None:
        icon = "👍" if was_helpful else "👎"
        console.print(f"  [dim]Helpful: {icon}[/dim]")
    if execution_success is not None:
        icon = "✅" if execution_success else "❌"
        console.print(f"  [dim]Execution: {icon}[/dim]")

    # Check for newly earned badges
    from vibesop.core.badges import BadgeTracker, get_badge_display

    tracker = BadgeTracker()
    new_badges = tracker.check_feedback_event()
    for badge in new_badges:
        meta = get_badge_display(badge.type)
        console.print()
        console.print(f"[bold yellow]{meta['icon']}  New Badge: {meta['title']}[/bold yellow]")
        console.print(f"   [dim]{meta['description']}[/dim]")


def create(
    name: str | None = typer.Option(None, help="Skill name (kebab-case)"),
    description: str | None = typer.Option(None, help="What this skill does"),
    from_template: str | None = typer.Option(None, "--from", help="Base on existing skill"),
    namespace: str = typer.Option("custom", help="Skill namespace"),
    interactive: bool = typer.Option(True, help="Use interactive wizard"),
) -> None:
    """Create a new skill from natural language or an existing template.

    \b
    Examples:
        # Interactive wizard
        vibe skills create

        # Create from existing skill template
        vibe skills create --from gstack/review --name my-review

        # Non-interactive
        vibe skills create --name security-audit --description "Scan for vulnerabilities"
    """
    manager = SkillManager()

    # Copy from template if specified
    if from_template:
        template_info = manager.get_skill_info(from_template)
        if not template_info:
            console.print(f"[red]✗ Template skill not found: {from_template}[/red]")
            raise typer.Exit(1)

        if not name:
            name = questionary.text(
                "New skill name:",
                default=f"my-{from_template.split('/')[-1]}",
            ).ask()
            if not name:
                console.print("[yellow]Cancelled.[/yellow]")
                return

        skill_dir = Path.cwd() / ".vibe" / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Copy SKILL.md and modify header
        template_path = template_info.get("source_file")
        if template_path:
            template_text = Path(template_path).read_text()
            # Replace header fields
            new_text = template_text.replace(
                f"id: {from_template}",
                f"id: {namespace}/{name}"
            ).replace(
                f"name: {from_template.split('/')[-1]}",
                f"name: {name}"
            )
            if description:
                new_text = new_text.replace(
                    f"description: {template_info.get('description', '')}",
                    f"description: {description}"
                )
            (skill_dir / "SKILL.md").write_text(new_text)
        else:
            # Generate minimal SKILL.md
            _generate_skill_md(skill_dir, name, description or f"{name} skill", namespace)

        console.print(f"[green]✓ Created skill from template:[/green] {skill_dir}")
        console.print("[dim]Next steps:[/dim]")
        console.print(f"  1. Edit {skill_dir}/SKILL.md")
        console.print(f"  2. Run [bold]vibe skills validate {namespace}/{name}[/bold]")
        console.print(f"  3. Run [bold]vibe skills enable {namespace}/{name}[/bold]")
        return

    keywords: str | None = None

    # Interactive wizard (when no --from specified)
    if interactive and not name:
        console.print("[bold]✨ Skill Creation Wizard[/bold]\n")
        name = questionary.text(
            "Skill name (kebab-case):",
            validate=lambda t: bool(t) or "Name is required",
        ).ask()
        if not name:
            console.print("[yellow]Cancelled.[/yellow]")
            return

        description = questionary.text(
            "What does this skill do?",
            default=description or "",
        ).ask()

        keywords = questionary.text(
            "Trigger keywords (comma-separated):",
        ).ask()

        namespace = questionary.text(
            "Namespace:",
            default=namespace,
        ).ask() or namespace

    if not name:
        console.print("[red]✗ Skill name is required[/red]")
        raise typer.Exit(1)

    skill_dir = Path.cwd() / ".vibe" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    _generate_skill_md(
        skill_dir,
        name,
        description or f"{name} skill",
        namespace,
        keywords=keywords if interactive else None,
    )

    console.print(f"[green]✓ Created skill:[/green] {skill_dir}")
    console.print("[dim]Next steps:[/dim]")
    console.print(f"  1. Edit {skill_dir}/SKILL.md")
    console.print(f"  2. Run [bold]vibe skills validate {namespace}/{name}[/bold]")
    console.print(f"  3. Run [bold]vibe skills enable {namespace}/{name}[/bold]")


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
        # Show current state
        state_colors = {
            "draft": "blue",
            "active": "green",
            "deprecated": "yellow",
            "archived": "dim",
        }
        color = state_colors.get(current_state, "white")
        console.print(f"[dim]Lifecycle state for '{skill_id}':[/dim] [{color}]{current_state}[/{color}]")
        if current_state == "deprecated" and getattr(config, "deprecation_reason", None):
            console.print(f"  [dim]Reason: {config.deprecation_reason}[/dim]")
        return

    # Validate state
    valid_states = [s.value for s in SkillLifecycleState]
    if set_state not in valid_states:
        console.print(f"[red]✗ Invalid state: {set_state}. Must be one of: {', '.join(valid_states)}[/red]")
        raise typer.Exit(1)

    # Update state
    config.lifecycle = set_state
    if reason:
        config.deprecation_reason = reason

    SkillConfigManager.update_skill_config(skill_id, {
        "lifecycle": set_state,
        "deprecation_reason": reason,
    })

    state_colors = {
        "draft": "blue",
        "active": "green",
        "deprecated": "yellow",
        "archived": "dim",
    }
    color = state_colors.get(set_state, "white")
    console.print(f"[green]✓[/green] Lifecycle state for '{skill_id}' set to [{color}]{set_state}[/{color}]")
    if reason:
        console.print(f"  [dim]Reason: {reason}[/dim]")


def _lifecycle_auto_review() -> None:
    """Suggest lifecycle transitions based on evaluation data."""
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
    for skill_id, suggested_state, reason in suggestions:
        console.print(f"  [cyan]{skill_id}[/cyan] → [yellow]{suggested_state}[/yellow] [dim]({reason})[/dim]")
    console.print("\n[dim]Run `vibe skills lifecycle <skill> --set <state>` to apply.[/dim]")


def _generate_skill_md(
    skill_dir: Path,
    name: str,
    description: str,
    namespace: str,
    keywords: str | None = None,
) -> None:
    """Generate a minimal SKILL.md file."""
    tags = ""
    if keywords:
        tag_list = [k.strip() for k in keywords.split(",") if k.strip()]
        tags = f"\ntags: [{', '.join(tag_list)}]"

    content = f"""---
id: {namespace}/{name}
name: {name}
description: {description}{tags}
intent: general
namespace: {namespace}
version: 1.0.0
type: prompt
---

# {name.replace("-", " ").title()}

## Overview

{description}

## Workflow

1. Step one
2. Step two
3. Step three

## Usage

```bash
vibe route "your query here"
```
"""
    (skill_dir / "SKILL.md").write_text(content)
