"""VibeSOP status command — unified ecosystem health snapshot.

Usage:
    vibe status

Displays:
    - Welcome (first-run) / Badge showcase
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


def _get_skill_count(project_root: Path) -> int:
    """Get total skill count without loading UnifiedRouter."""
    try:
        from vibesop.core.routing.candidate_manager import CandidateManager

        mgr = CandidateManager(project_root)
        candidates = mgr.get_candidates()
        return len(candidates)
    except Exception:
        return 0


def _load_ecosystem_health(project_root: Path) -> Panel:
    """Build ecosystem health panel."""
    total = _get_skill_count(project_root)

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
            "[dim]No evaluation data yet. Skills are evaluated as you use them.[/dim]"
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
            "[dim]No routing activity yet.\n"
            "Try [bold cyan]vibe route \"help me debug this error\"[/bold cyan] to get started![/dim]",
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


def _load_badges() -> Panel | None:
    """Build badges showcase panel."""
    try:
        from vibesop.core.badges import BadgeTracker, get_badge_display

        tracker = BadgeTracker()
        badges = tracker.list_badges()
    except Exception:
        return None

    if not badges:
        return None

    lines: list[str] = []
    for b in badges[:8]:
        meta = get_badge_display(b.type)
        date = b.awarded_at[:10] if len(b.awarded_at) >= 10 else b.awarded_at
        lines.append(
            f"{meta['icon']} [bold]{meta['title']}[/bold] [dim]—[/dim] "
            f"{meta['description']} [dim]({date})[/dim]"
        )

    content = "\n".join(lines)
    return Panel(content, title="[bold]Achievements[/bold]", border_style="magenta", box=ROUNDED)


def _load_suggestions_count() -> int:
    """Get count of pending skill creation suggestions."""
    try:
        from vibesop.core.skills.suggestion_collector import SkillSuggestionCollector

        collector = SkillSuggestionCollector()
        return len(collector.get_pending())
    except Exception:
        return 0


def _load_community_trending() -> Panel | None:
    """Build community trending skills panel from GitHub Issues."""
    try:
        import json
        import os
        import urllib.request

        token = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", ""))
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = (
            "https://api.github.com/repos/nehcuh/vibesop-py/issues"
            "?labels=skill-share&state=open&per_page=5&sort=reactions&direction=desc"
        )
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            issues = json.loads(resp.read())

        if not issues:
            return None

        lines: list[str] = []
        for issue in issues[:5]:
            title = issue.get("title", "").replace("[技能分享] ", "").strip()
            reactions = issue.get("reactions", {}).get("+1", 0)
            url_link = issue.get("html_url", "")
            lines.append(
                f"[cyan][link={url_link}]{title}[/link][/cyan] "
                f"[dim]👍 {reactions}[/dim]"
            )

        content = "\n".join(lines)
        return Panel(
            content,
            title="[bold]Community Trending[/bold]",
            border_style="cyan",
            box=ROUNDED,
        )
    except Exception:
        return None


def _detect_first_run(project_root: Path) -> bool:
    """Check if this appears to be the first run."""
    analytics_exists = (project_root / ".vibe" / "analytics.jsonl").exists()
    feedback_exists = (project_root / ".vibe" / "feedback.jsonl").exists()
    return not analytics_exists and not feedback_exists


def _load_welcome(is_first: bool) -> Panel | None:
    """Build welcome panel for first-time users."""
    if not is_first:
        return None

    content = (
        "[bold]Welcome to VibeSOP![/bold]  Your AI-powered skill operating system.\n\n"
        "[dim]Getting started:[/dim]\n"
        "  [cyan]vibe route \"help me debug this\"[/cyan]  [dim]— route a query to the best skill[/dim]\n"
        "  [cyan]vibe skills list[/cyan]             [dim]— browse your 45+ available skills[/dim]\n"
        "  [cyan]vibe status[/cyan]                   [dim]— return to this dashboard[/dim]\n\n"
        "[dim]VibeSOP manages your skills so your AI agent can focus on execution.[/dim]"
    )
    return Panel(
        content,
        title="[bold cyan]Welcome to VibeSOP[/bold cyan]",
        border_style="cyan",
        box=ROUNDED,
    )


def status(
    no_color: bool = typer.Option(
        False, "--no-color", help="Disable colored output"
    ),
) -> None:
    """Show a unified snapshot of your VibeSOP skill ecosystem.

    Displays ecosystem health, recent activity, personalized
    recommendations, warnings, and achievements — all in one view.

    This is the default command when running `vibe` with no arguments.
    """
    global console  # noqa: PLW0603
    if no_color:
        console = Console(no_color=True)

    project_root = Path.cwd()

    is_first = _detect_first_run(project_root)

    # Header
    console.print()
    console.rule("[bold cyan]VibeSOP Status[/bold cyan]")

    # Welcome (first-run only)
    welcome = _load_welcome(is_first)
    if welcome:
        console.print()
        console.print(welcome)

    # Badge showcase
    badges = _load_badges()
    if badges:
        console.print()
        console.print(badges)

    # Ecosystem health
    console.print()
    console.print(_load_ecosystem_health(project_root))

    # Recent activity
    console.print(_load_recent_activity(project_root))

    # Recommendations
    console.print(_load_recommendations())

    # Warnings
    console.print(_load_warnings(project_root))

    # Community trending
    trending = _load_community_trending()
    if trending:
        console.print(trending)

    # Skill suggestions
    suggestion_count = _load_suggestions_count()
    if suggestion_count > 0:
        console.print(
            Panel(
                f"[bold cyan]{suggestion_count}[/bold cyan] new skill pattern(s) detected "
                f"from your workflows\n"
                f"[dim]Run [cyan]vibe skills suggestions[/cyan] to review and create skills[/dim]",
                title="[bold]Skill Suggestions[/bold]",
                border_style="green",
                box=ROUNDED,
            )
        )

    # Footer
    console.print()
    console.print(
        "[dim]Commands:[/dim] "
        "[cyan]vibe route <query>[/cyan] [dim]|[/dim] "
        "[cyan]vibe skills list[/cyan] [dim]|[/dim] "
        "[cyan]vibe --help[/cyan]"
    )
    console.print()
