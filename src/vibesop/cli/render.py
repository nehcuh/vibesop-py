"""CLI rendering functions — fallback, single-match, orchestration, and ecosystem tips."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from vibesop.core.models import OrchestrationResult

logger = logging.getLogger(__name__)


_TIP_TEMPLATES: list[tuple[str, str]] = [
    ("status", "[cyan]vibe status[/cyan] [dim]— see your full ecosystem health[/dim]"),
    ("market", "[cyan]vibe market search <query>[/cyan] [dim]— find skills on GitHub[/dim]"),
    ("cleanup", "[cyan]vibe skill cleanup[/cyan] [dim]— review and prune stale skills[/dim]"),
    ("list", "[cyan]vibe skill list[/cyan] [dim]— browse all 45+ available skills[/dim]"),
    (
        "recommend",
        "[cyan]vibe skills suggested[/cyan] [dim]— get personalized recommendations[/dim]",
    ),
]


def render_fallback_panel(result: Any, console: Console) -> None:
    alt_text = ""
    if result.alternatives:
        alt_text = "\n[bold]💡 Nearest installed skills:[/bold]\n"
        for alt in result.alternatives[:3]:
            desc = f" — {alt.description[:50]}" if alt.description else ""
            alt_text += f"  • {alt.skill_id} ({alt.confidence:.0%}){desc}\n"

    stale_text = _render_stale_suggestions()

    console.print(
        Panel(
            f"[bold yellow]No matching skill found[/bold yellow]\n\n"
            f"[dim]Query:[/dim] {result.original_query}\n"
            f"{alt_text}\n"
            f"[bold]What to do:[/bold]\n"
            f"  • [cyan]vibe market search <query>[/cyan] — search skills on GitHub\n"
            f"  • [cyan]vibe skills list[/cyan] — browse installed skills\n"
            f"  • Rephrase your query with more specific keywords\n"
            f"  • Your AI Agent can still handle this without a skill\n"
            f"{stale_text}",
            title="[bold]Routing Result[/bold]",
            border_style="yellow",
        )
    )


def _render_stale_suggestions() -> str:
    try:
        from vibesop.core.skills.feedback_loop import FeedbackLoop

        loop = FeedbackLoop()
        suggestions = loop.analyze_all()

        deprecated = [s for s in suggestions if s.action == "deprecate"]
        warned = [s for s in suggestions if s.action == "warn"]

        if not deprecated and not warned:
            return ""

        lines = ["\n[bold yellow]⚡ Skill Health:[/bold yellow]"]
        if deprecated:
            skill_names = ", ".join(s.skill_id for s in deprecated[:3])
            lines.append(
                f"  • [red]{len(deprecated)} skill(s) may need attention:[/red] "
                f"[dim]{skill_names}[/dim]"
            )
        if warned:
            skill_names = ", ".join(s.skill_id for s in warned[:3])
            lines.append(
                f"  • [yellow]{len(warned)} skill(s) could be reviewed:[/yellow] "
                f"[dim]{skill_names}[/dim]"
            )
        lines.append("  • Run [bold]vibe skill stale[/bold] for details and cleanup options")
        return "\n".join(lines)
    except Exception:
        return ""


def render_match_panel(result: Any, console: Console) -> None:
    primary = result.primary
    quality_str = ""
    grade = primary.metadata.get("grade")
    if grade:
        grade_colors = {"A": "green", "B": "green", "C": "yellow", "D": "yellow", "F": "red"}
        color = grade_colors.get(grade, "dim")
        quality_str = f"\n[dim]Quality:[/dim] [{color}]{grade}[/{color}]"
    habit_boost = primary.metadata.get("habit_boost")
    if habit_boost:
        quality_str += " [dim](habit)[/dim]"
        console.print("[dim]💡 Habit boost applied[/dim]")

    deprecated = primary.metadata.get("deprecated_warnings", [])
    if deprecated:
        console.print(
            f"\n[yellow]⚠️  Deprecated skills in ecosystem:[/yellow] {', '.join(deprecated)}"
        )

    console.print(
        Panel(
            f"[bold green]Matched:[/bold green] {primary.skill_id}\n"
            f"[dim]{primary.description[:120]}[/dim]\n\n"
            f"[dim]Confidence:[/dim] {primary.confidence:.0%}\n"
            f"[dim]Layer:[/dim] {primary.layer.value}\n"
            f"[dim]Source:[/dim] {primary.source}{quality_str}\n"
            f"[dim]Duration:[/dim] {result.duration_ms:.1f}ms",
            title="[bold]Routing Result[/bold]",
            border_style="blue",
        )
    )
    if result.alternatives:
        console.print("\n[bold]💡 Alternatives:[/bold]")
        for alt in result.alternatives[:3]:
            desc = f" — {alt.description[:50]}" if alt.description else ""
            console.print(f"  • {alt.skill_id} ({alt.confidence:.0%}){desc}")


def render_no_match(result: Any, console: Console) -> None:
    query = getattr(result, "original_query", getattr(result, "query", "your query"))

    suggestions = [
        "Try being more specific with your intent",
        "Use [cyan]vibe skills list[/cyan] to see available skills",
        "Use [cyan]vibe market search <query>[/cyan] to find skills on GitHub",
        "Check [cyan]vibe status[/cyan] for ecosystem health",
    ]

    if hasattr(result, "alternatives") and result.alternatives:
        best_alt = result.alternatives[0]
        suggestions.insert(
            0,
            f"[cyan]{best_alt.skill_id}[/cyan] was close "
            f"([dim]{best_alt.confidence:.0%}[/dim]) — try rephrasing",
        )

    suggestion_text = "\n".join(f"  • {s}" for s in suggestions[:4])

    console.print(
        Panel(
            f"[yellow]No matching skill found for:[/yellow] {query}\n\n"
            f"[bold]Suggestions:[/bold]\n{suggestion_text}",
            title="[bold]Routing Result[/bold]",
            border_style="yellow",
        )
    )


def render_compact_orchestration(
    result: OrchestrationResult,
    console: Console | None = None,
) -> None:
    if console is None:
        console = Console()

    table = Table(
        title="[bold cyan]🔍 Routing Summary[/bold cyan]",
        box=box.SIMPLE,
        show_header=False,
        padding=(0, 1),
    )
    table.add_column("Field", style="dim", justify="right")
    table.add_column("Value", style="bold")

    if result.mode.value == "single":
        if result.primary:
            if result.primary.layer.value == "fallback_llm":
                table.add_row("Selected", f"[yellow]{result.primary.skill_id}[/yellow]")
                table.add_row("Status", "[yellow]Fallback (no skill matched)[/yellow]")
            else:
                table.add_row("Selected", f"[green]{result.primary.skill_id}[/green]")
                desc = getattr(result.primary, "description", "")
                if desc:
                    table.add_row("Description", f"[dim]{desc[:100]}[/dim]")
                table.add_row("Confidence", f"{result.primary.confidence:.0%}")
                table.add_row("Layer", result.primary.layer.value)
        else:
            table.add_row("Selected", "[yellow]No match[/yellow]")

        table.add_row("Duration", f"{result.duration_ms:.1f}ms")

        if result.alternatives:
            alt_lines = []
            for alt in result.alternatives[:3]:
                alt_lines.append(f"  • {alt.skill_id} ({alt.confidence:.0%} via {alt.layer.value})")
            table.add_row("Alternatives", "\n".join(alt_lines))
    else:
        plan = result.execution_plan
        if plan:
            table.add_row("Mode", "[cyan]Orchestrated[/cyan]")
            table.add_row("Steps", str(len(plan.steps)))
            table.add_row("Strategy", plan.execution_mode.value)

            step_lines = []
            for step in plan.steps:
                step_lines.append(f"  {step.step_number}. {step.skill_id} — {step.intent}")
            table.add_row("Plan", "\n".join(step_lines))

            if result.single_fallback:
                table.add_row(
                    "Fallback",
                    f"{result.single_fallback.skill_id} ({result.single_fallback.confidence:.0%})",
                )
        else:
            table.add_row("Mode", "[yellow]Orchestrated (no plan)[/yellow]")

    console.print(table)
    console.print()

    query = getattr(result, "original_query", "")
    skill_id = result.primary.skill_id if result.primary else ""
    render_ecosystem_tips(
        project_root=Path.cwd(),
        console=console,
        query=query,
        routed_skill_id=skill_id,
    )


def _count_low_quality_skills(project_root: Path) -> int:
    try:
        from vibesop.core.skills.evaluator import RoutingEvaluator

        evaluator = RoutingEvaluator(project_root=project_root)
        low = evaluator.get_low_quality_skills(threshold=0.3, min_routes=3)
        return len(low)
    except Exception:
        return 0


def _count_stale_skills(project_root: Path) -> int:
    try:
        from vibesop.core.skills.feedback_loop import FeedbackLoop

        loop = FeedbackLoop(project_root=project_root)
        suggestions = loop.analyze_all(auto_deprecate=False)
        return sum(1 for s in suggestions if s.action == "deprecate")
    except Exception:
        return 0


def _get_today_stats(project_root: Path) -> dict[str, Any]:
    try:
        from vibesop.core.analytics import AnalyticsStore

        store = AnalyticsStore(storage_dir=project_root / ".vibe")
        records = store.list_records(limit=500)
    except Exception:
        return {"routes_today": 0, "top_skill": None}

    today = __import__("datetime").datetime.now().date().isoformat()
    today_records = [r for r in records if r.timestamp[:10] == today]

    top_skill = None
    if today_records:
        from collections import Counter

        skill_counts = Counter(r.primary_skill for r in today_records if r.primary_skill)
        if skill_counts:
            top_skill = skill_counts.most_common(1)[0][0]

    return {"routes_today": len(today_records), "top_skill": top_skill}


def _check_new_badges(project_root: Path, skill_id: str) -> list[str]:
    try:
        from vibesop.core.analytics import AnalyticsStore
        from vibesop.core.badges import BadgeTracker, get_badge_display

        tracker = BadgeTracker()
        store = AnalyticsStore(storage_dir=project_root / ".vibe")
        records = store.list_records(limit=500)

        route_history = [{"skill_id": r.primary_skill} for r in records if r.primary_skill]

        new_badges = tracker.check_route_event(skill_id, route_history)
        if not new_badges:
            return []

        lines: list[str] = []
        for b in new_badges:
            meta = get_badge_display(b.type)
            lines.append(
                f"{meta['icon']} [bold magenta]{meta['title']}[/bold magenta] — {meta['description']}"
            )
        return lines
    except Exception:
        return []


def render_ecosystem_tips(
    project_root: Path | None = None,
    console: Console | None = None,
    query: str = "",
    routed_skill_id: str = "",
) -> None:
    if console is None:
        console = Console()
    if project_root is None:
        project_root = Path.cwd()

    has_content = False
    console.print()

    if routed_skill_id:
        badges = _check_new_badges(project_root, routed_skill_id)
        if badges:
            for line in badges:
                console.print(f"  {line}")
            has_content = True

    stats = _get_today_stats(project_root)
    if stats["routes_today"] >= 2:
        parts = [f"[dim]{stats['routes_today']} routes today[/dim]"]
        if stats["top_skill"]:
            parts.append(f"[dim]top: [cyan]{stats['top_skill']}[/cyan][/dim]")
        console.print(f"  {' · '.join(parts)}")
        has_content = True

    tips: list[str] = []
    low_quality = _count_low_quality_skills(project_root)
    if low_quality > 0:
        tips.append(
            f"[yellow]{low_quality} skill(s)[/yellow] with low quality "
            f"[dim]— [cyan]vibe status[/cyan][/dim]"
        )

    stale = _count_stale_skills(project_root)
    if stale > 0:
        tips.append(
            f"[yellow]{stale} stale skill(s)[/yellow] [dim]— [cyan]vibe skill cleanup[/cyan][/dim]"
        )

    for tip in tips[:2]:
        console.print(f"  [dim]💡 {tip}[/dim]")
        has_content = True

    if tips and has_content:
        return

    seed = hashlib.md5(query.encode()).digest()[0] if query else 0

    if has_content or seed % 3 != 0:
        return

    _category, tip_text = _TIP_TEMPLATES[seed % len(_TIP_TEMPLATES)]
    console.print(f"  [dim]💡 {tip_text}[/dim]")


__all__ = [
    "render_compact_orchestration",
    "render_ecosystem_tips",
    "render_fallback_panel",
    "render_match_panel",
    "render_no_match",
]
