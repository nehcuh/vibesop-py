# pyright: ignore[reportPossiblyUnboundVariable, reportUnnecessaryComparison]
"""Health commands: status, health, ecosystem report."""

from typing import Any

import typer
from rich.console import Console

from vibesop.core.skills import SkillStorage
from vibesop.core.skills.evaluator import RoutingEvaluator

console = Console()


def status() -> None:
    """Show skill storage and health status."""
    storage = SkillStorage()

    central_exists = storage.CENTRAL_SKILLS_DIR.exists()
    central_count = len(storage.list_skills())

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

    console.print("\n[bold]Skill Storage Status[/bold]\n")

    central_status = "[green]✓[/green]" if central_exists else "[red]✗[/red]"
    console.print(f"{central_status} Central Storage: {storage.CENTRAL_SKILLS_DIR}")
    console.print(f"    [dim]Skills installed: {central_count}[/dim]\n")

    console.print("[bold]Platform Directories:[/bold]\n")
    for platform_name, info in platform_info.items():
        if info["exists"]:
            status_str = f"[green]{info['linked']} linked[/green]"
            symlink_count = info["symlinks"]
            console.print(f"  {platform_name}: {status_str} ({symlink_count} symlinks)")
        else:
            console.print(f"  {platform_name}: [dim]not created[/dim]")

    console.print("")

    try:
        from vibesop.integrations.health_monitor import SkillHealthMonitor

        monitor = SkillHealthMonitor()
        summary = monitor.get_health_summary()

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

    if ecosystem:
        _show_ecosystem_report(monitor)
        return

    if pack:
        status_result = monitor.check_local_health(pack)
        _display_health_status(status_result, verbose=verbose)
    else:
        all_health = monitor.check_all_local()

        if not all_health:
            console.print("[yellow]No skill packs found[/yellow]")
            return

        summary = monitor.get_health_summary()
        console.print("\n[bold]Skill Pack Health Check[/bold]\n")
        console.print(
            f"Total: [bold]{summary['total']}[/bold] packs | "
            f"[green]✓ {summary['healthy']} healthy[/green] | "
            f"[yellow]⚠ {summary['warning']} warnings[/yellow] | "
            f"[red]✗ {summary['critical']} critical[/red]\n"
        )

        for _pack_name, health_status in sorted(all_health.items()):
            _display_health_status(health_status, verbose=verbose)

        try:
            evaluator = RoutingEvaluator()
            all_evals = evaluator.evaluate_all_skills()
            if all_evals:
                console.print("\n[bold]Skill Quality Overview[/bold]\n")
                for skill_id, evaluation in sorted(
                    all_evals.items(), key=lambda x: x[1].quality_score, reverse=True
                )[:10]:
                    grade_color = {
                        "A": "green",
                        "B": "green",
                        "C": "yellow",
                        "D": "yellow",
                        "F": "red",
                    }.get(evaluation.grade, "dim")
                    icon = (
                        "✅"
                        if evaluation.grade in ("A", "B")
                        else "⚠️"
                        if evaluation.grade in ("C", "D")
                        else "❔"
                        if evaluation.grade == "?"
                        else "🗑️"
                    )
                    # "?" = no routing feedback: no data is not a bad score,
                    # so show "—" instead of a misleading 0%.
                    score_str = (
                        "—" if evaluation.grade == "?" else f"{evaluation.quality_score:.0%}"
                    )
                    console.print(
                        f"  {icon} [cyan]{skill_id}[/cyan] "
                        f"[{grade_color}]{evaluation.grade} ({score_str})[/{grade_color}] "
                        f"[dim]{evaluation.total_routes} uses[/dim]"
                    )
        except (OSError, ValueError):
            pass


def _show_ecosystem_report(monitor: Any) -> None:
    from datetime import datetime

    console.print(
        f"\n[bold]📊 Your Skill Ecosystem Health[/bold] [dim]({datetime.now().strftime('%Y-%m-%d')})[/dim]\n"
    )

    summary = monitor.get_health_summary()
    try:
        evaluator = RoutingEvaluator()
        all_evals = evaluator.evaluate_all_skills()
    except (OSError, ImportError, ValueError):
        all_evals = {}

    if not all_evals:
        console.print("[dim]No evaluation data yet. Use skills to generate feedback![/dim]")
        return

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

    if top_performers:
        console.print("[bold green]🏆 Top Performers[/bold green]")
        for sid, ev in top_performers[:5]:
            bar = "█" * int(ev.quality_score * 10) + "░" * (10 - int(ev.quality_score * 10))
            impact = "+0.05 boost" if ev.grade == "A" else "+0.02 boost"
            console.print(
                f"  [cyan]{sid:<30}[/cyan] {ev.grade}  {impact}  [dim]{bar}[/dim]  {ev.total_routes} routes"
            )
        console.print()

    if needs_attention:
        console.print("[bold yellow]⚠️  Needs Attention[/bold yellow]")
        for sid, ev in needs_attention[:5]:
            impact = "no change" if ev.grade == "C" else "-0.02 demote"
            console.print(
                f"  [cyan]{sid:<30}[/cyan] {ev.grade}  {impact}  [dim]{ev.total_routes} routes[/dim]"
            )
        console.print()

    if at_risk:
        console.print("[bold red]🗑️  At Risk[/bold red]")
        for sid, ev in at_risk[:5]:
            console.print(
                f"  [cyan]{sid:<30}[/cyan] {ev.grade}  -0.05 demote  [dim]{ev.total_routes} routes[/dim]"
            )
        console.print(
            "  [dim]Action: Run `vibe skills feedback --skill <id>` or `vibe skills disable <id>`[/dim]"
        )
        console.print()

    if insufficient:
        console.print("[bold blue]💡 Feedback Opportunities[/bold blue]")
        console.print(
            f"  [dim]{len(insufficient)} skills need more usage to reach reliable grading:[/dim]"
        )
        for sid, ev in insufficient[:3]:
            needed = 3 - ev.total_routes
            console.print(f"    • {sid}: {ev.total_routes}/3 routes (needs {needed} more)")
        console.print()

    console.print("[bold]📈 Ecosystem Stats[/bold]")
    console.print(f"  Total skills evaluated: {len(all_evals)}")
    console.print(f"  Packs: {summary.get('total', 0)} total, {summary.get('healthy', 0)} healthy")
    console.print()

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
    icon_map = {
        "healthy": ("✓", "green"),
        "warning": ("⚠", "yellow"),
        "critical": ("✗", "red"),
        "unknown": ("?", "dim"),
    }

    icon, color = icon_map.get(health_status.health, ("?", "dim"))

    console.print(
        f"[{color}]{icon}[/{color}] {health_status.name}: "
        f"[bold {color}]{health_status.health}[/bold {color}] "
        f"([dim]{health_status.skills_count} skills[/dim])"
    )

    if verbose and health_status.version != "unknown":
        console.print(f"  [dim]Version: {health_status.version}[/dim]")

    if verbose or health_status.health != "healthy":
        for reason in health_status.reasons:
            console.print(f"  [dim]• {reason}[/dim]")

    console.print("")
