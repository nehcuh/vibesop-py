"""VibeSOP status command — unified ecosystem health snapshot.

Usage:
    vibe status

Displays:
    - Skill ecosystem health (total count, grade distribution A-F)
    - Recent routing activity
    - Personalized recommendations
    - Warnings (low quality, stale skills)
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel

console = Console()


def _grade_color(grade: str) -> str:
    mapping = {"A": "green", "B": "blue", "C": "yellow", "D": "dark_orange", "F": "red"}
    return mapping.get(grade, "dim")


def _grade_bar(counts: dict[str, int], total: int) -> str:
    if total == 0:
        return "[dim]no skills evaluated[/dim]"
    grades = ["A", "B", "C", "D", "F"]
    parts: list[str] = []
    for g in grades:
        c = counts.get(g, 0)
        pct = c / total * 100 if total > 0 else 0
        color = _grade_color(g)
        parts.append(f"[{color}]{g}: {c} ({pct:.0f}%)[/{color}]")
    return "  ".join(parts)


def _load_ecosystem_health(project_root: Path) -> Panel:
    """Build ecosystem health panel."""
    try:
        from vibesop.core.routing import UnifiedRouter

        router = UnifiedRouter(project_root=project_root)
        candidates = router.get_candidates() or []
        total = len(candidates)
    except Exception:
        return Panel(
            "[dim]Unable to load skill candidates[/dim]",
            title="[bold]Ecosystem Health[/bold]",
            border_style="dim",
            box=ROUNDED,
        )

    try:
        from vibesop.core.skills.evaluator import RoutingEvaluator

        evaluator = RoutingEvaluator(project_root=project_root)
        evals = evaluator.evaluate_all_skills()

        grade_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        for e in evals.values():
            grade_counts[e.grade] = grade_counts.get(e.grade, 0) + 1
        evaluated = len(evals)
    except Exception:
        evaluated = 0
        grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}

    lines: list[str] = []
    lines.append(f"[bold]{total}[/bold] skills installed")

    if evaluated > 0:
        lines.append(f"[dim]{evaluated} with evaluation data[/dim]")
        lines.append("")
        lines.append(_grade_bar(grade_counts, evaluated))
    else:
        lines.append("")
        lines.append(
            "[dim]No evaluation data yet. Use skills to collect feedback.[/dim]"
        )

    content = "\n".join(lines)
    return Panel(content, title="[bold]Ecosystem Health[/bold]", border_style="cyan", box=ROUNDED)


def _load_recent_activity(project_root: Path) -> Panel:
    """Build recent activity panel from analytics."""
    try:
        from vibesop.core.analytics import AnalyticsStore

        store = AnalyticsStore(storage_dir=project_root / ".vibe")
        records = store.list_records(limit=10)
    except Exception:
        return Panel(
            "[dim]No analytics data available[/dim]",
            title="[bold]Recent Activity[/bold]",
            border_style="dim",
            box=ROUNDED,
        )

    if not records:
        return Panel(
            "[dim]No routing activity yet. Try [bold]vibe route[/bold] to get started![/dim]",
            title="[bold]Recent Activity[/bold]",
            border_style="dim",
            box=ROUNDED,
        )

    lines: list[str] = []
    for r in records[:5]:
        skill = r.primary_skill or "(no match)"
        ts = r.timestamp[:16] if len(r.timestamp) >= 16 else r.timestamp
        mode_str = "[orch]" if r.mode == "orchestrated" else "[route]"
        lines.append(f"[dim]{mode_str}[/dim] [cyan]{skill}[/cyan] [dim]{ts}[/dim]")

    content = "\n".join(lines)
    return Panel(content, title="[bold]Recent Activity[/bold]", border_style="blue", box=ROUNDED)


def _load_recommendations() -> Panel:
    """Build personalized recommendations panel."""
    try:
        from vibesop.core.skills.recommender import SkillRecommender

        recommender = SkillRecommender()
        recs = recommender.recommend_for_project()
        missing = recommender.detect_missing_skills()
        all_recs = list(recs) + [
            r for r in missing if r.skill_id not in {s.skill_id for s in recs}
        ]
    except Exception:
        return Panel(
            "[dim]Recommendations not available[/dim]",
            title="[bold]For You[/bold]",
            border_style="dim",
            box=ROUNDED,
        )

    if not all_recs:
        return Panel(
            "[dim]You have all recommended skills for this project![/dim]",
            title="[bold]For You[/bold]",
            border_style="green",
            box=ROUNDED,
        )

    lines: list[str] = []
    for r in all_recs[:5]:
        lines.append(
            f"[cyan]{r.skill_id}[/cyan] [dim]—[/dim] {r.reason[:80]}"
        )

    content = "\n".join(lines)
    return Panel(content, title="[bold]For You[/bold]", border_style="green", box=ROUNDED)


def _load_warnings(project_root: Path) -> Panel:
    """Build warnings panel for low-quality or stale skills."""
    warnings: list[str] = []

    try:
        from vibesop.core.skills.evaluator import RoutingEvaluator

        evaluator = RoutingEvaluator(project_root=project_root)
        low_quality = evaluator.get_low_quality_skills(threshold=0.3, min_routes=3)
        for e in low_quality[:3]:
            warnings.append(
                f"[yellow]{e.skill_id}[/yellow] — grade [red]{e.grade}[/red], "
                f"quality {e.quality_score:.0%}"
            )
    except Exception:
        pass

    try:
        from vibesop.core.skills.feedback_loop import FeedbackLoop

        loop = FeedbackLoop(project_root=project_root)
        suggestions = loop.analyze_all(auto_deprecate=False)
        for s in suggestions[:3]:
            if s.action == "deprecate" and s.skill_id not in [
                w.split(" —")[0].replace("[yellow]", "").replace("[/yellow]", "")
                for w in warnings
            ]:
                warnings.append(
                    f"[yellow]{s.skill_id}[/yellow] — [red]suggested deprecation[/red]: "
                    f"{s.reason[:60]}"
                )
    except Exception:
        pass

    if not warnings:
        return Panel(
            "[green]No warnings — ecosystem looks healthy![/green]",
            title="[bold]Warnings[/bold]",
            border_style="green",
            box=ROUNDED,
        )

    content = "\n".join(warnings)
    return Panel(content, title="[bold]Warnings[/bold]", border_style="yellow", box=ROUNDED)


def status(
    no_color: bool = typer.Option(
        False, "--no-color", help="Disable colored output"
    ),
) -> None:
    """Show a unified snapshot of your VibeSOP skill ecosystem.

    Displays ecosystem health, recent activity, personalized
    recommendations, and warnings — all in one view.

    This is the default command when running `vibe` with no arguments.
    """
    global console  # noqa: PLW0603
    if no_color:
        console = Console(no_color=True)

    project_root = Path.cwd()

    # Header
    console.print()
    console.rule("[bold cyan]VibeSOP Status[/bold cyan]")

    # Ecosystem health
    console.print()
    console.print(_load_ecosystem_health(project_root))

    # Recent activity
    console.print(_load_recent_activity(project_root))

    # Recommendations
    console.print(_load_recommendations())

    # Warnings
    console.print(_load_warnings(project_root))

    # Footer
    console.print()
    console.print(
        "[dim]Commands:[/dim] "
        "[cyan]vibe route <query>[/cyan] [dim]|[/dim] "
        "[cyan]vibe skills list[/cyan] [dim]|[/dim] "
        "[cyan]vibe --help[/cyan]"
    )
    console.print()
