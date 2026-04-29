"""Post-route ecosystem tips — subtle, data-driven nudges.

These tips appear after `vibe route` results and provide
contextual ecosystem awareness without being intrusive.

Features:
    - Rotating ecosystem tips (low quality, stale skills, discovery hints)
    - Auto badge checking on route events
    - Today's routing stats
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from rich.console import Console
import logging

logger = logging.getLogger(__name__)


# Tip rotation categories — one is picked based on query hash
_TIP_TEMPLATES: list[tuple[str, str]] = [
    ("status", "[cyan]vibe status[/cyan] [dim]— see your full ecosystem health[/dim]"),
    ("discover", "[cyan]vibe skill discover[/cyan] [dim]— browse community skills[/dim]"),
    ("cleanup", "[cyan]vibe skill cleanup[/cyan] [dim]— review and prune stale skills[/dim]"),
    ("list", "[cyan]vibe skill list[/cyan] [dim]— browse all 45+ available skills[/dim]"),
    ("recommend", "[cyan]vibe skills suggested[/cyan] [dim]— get personalized recommendations[/dim]"),
]


def _count_low_quality_skills(project_root: Path) -> int:
    try:
        from vibesop.core.skills.evaluator import RoutingEvaluator

        evaluator = RoutingEvaluator(project_root=project_root)
        low = evaluator.get_low_quality_skills(threshold=0.3, min_routes=3)
        return len(low)
    except Exception as e:
        return 0


def _count_stale_skills(project_root: Path) -> int:
    try:
        from vibesop.core.skills.feedback_loop import FeedbackLoop

        loop = FeedbackLoop(project_root=project_root)
        suggestions = loop.analyze_all(auto_deprecate=False)
        return sum(1 for s in suggestions if s.action == "deprecate")
    except Exception as e:
        return 0


def _get_today_stats(project_root: Path) -> dict:
    """Get today's routing statistics from analytics."""
    try:
        from vibesop.core.analytics import AnalyticsStore

        store = AnalyticsStore(storage_dir=project_root / ".vibe")
        records = store.list_records(limit=500)
    except Exception as e:
        return {"routes_today": 0, "top_skill": None}

    today = __import__("datetime").datetime.now().date().isoformat()
    today_records = [r for r in records if r.timestamp[:10] == today]

    top_skill = None
    if today_records:
        from collections import Counter

        skill_counts = Counter(
            r.primary_skill for r in today_records if r.primary_skill
        )
        if skill_counts:
            top_skill = skill_counts.most_common(1)[0][0]

    return {"routes_today": len(today_records), "top_skill": top_skill}


def _check_new_badges(project_root: Path, skill_id: str) -> list[str]:
    """Check if any new badges were earned from this route event."""
    try:
        from vibesop.core.analytics import AnalyticsStore
        from vibesop.core.badges import BadgeTracker, get_badge_display

        tracker = BadgeTracker()
        store = AnalyticsStore(storage_dir=project_root / ".vibe")
        records = store.list_records(limit=500)

        route_history = [
            {"skill_id": r.primary_skill} for r in records if r.primary_skill
        ]

        new_badges = tracker.check_route_event(skill_id, route_history)
        if not new_badges:
            return []

        lines: list[str] = []
        for b in new_badges:
            meta = get_badge_display(b.type)
            lines.append(f"{meta['icon']} [bold magenta]{meta['title']}[/bold magenta] — {meta['description']}")
        return lines
    except Exception as e:
        return []


def render_ecosystem_tips(
    project_root: Path | None = None,
    console: Console | None = None,
    query: str = "",
    routed_skill_id: str = "",
) -> None:
    """Render ecosystem tips and stats after a routing result.

    Shows:
        1. New badges (if any were just earned)
        2. Today's routing stats
        3. Urgent ecosystem warnings (low quality, stale skills)
        4. Rotating tip (based on query hash for variety)

    Designed to be non-intrusive — skips if data is unavailable.
    """
    if console is None:
        console = Console()
    if project_root is None:
        project_root = Path.cwd()

    has_content = False
    console.print()

    # 1. New badges
    if routed_skill_id:
        badges = _check_new_badges(project_root, routed_skill_id)
        if badges:
            for line in badges:
                console.print(f"  {line}")
            has_content = True

    # 2. Today's stats (only if non-trivial)
    stats = _get_today_stats(project_root)
    if stats["routes_today"] >= 2:
        parts = [f"[dim]{stats['routes_today']} routes today[/dim]"]
        if stats["top_skill"]:
            parts.append(f"[dim]top: [cyan]{stats['top_skill']}[/cyan][/dim]")
        console.print(f"  {' · '.join(parts)}")
        has_content = True

    # 3. Urgent warnings
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
            f"[yellow]{stale} stale skill(s)[/yellow] "
            f"[dim]— [cyan]vibe skill cleanup[/cyan][/dim]"
        )

    for tip in tips[:2]:
        console.print(f"  [dim]💡 {tip}[/dim]")
        has_content = True

    # 4. Rotating tip (only if nothing else was shown, or randomly)
    if tips and has_content:
        return  # Don't show rotating tip when there are warnings

    # Show rotating tip ~30% of the time
    seed = hashlib.md5(query.encode()).digest()[0] if query else 0

    if has_content or seed % 3 != 0:
        return

    _category, tip_text = _TIP_TEMPLATES[seed % len(_TIP_TEMPLATES)]
    console.print(f"  [dim]💡 {tip_text}[/dim]")
