"""Post-route ecosystem tips — subtle, data-driven nudges.

These tips appear after `vibe route` results and provide
contextual ecosystem awareness without being intrusive.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console


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


def render_ecosystem_tips(
    project_root: Path | None = None,
    console: Console | None = None,
) -> None:
    """Render subtle ecosystem tips after a routing result.

    Only shows tips when there are actionable items.
    Designed to be non-intrusive — skips if data is unavailable.
    """
    if console is None:
        console = Console()
    if project_root is None:
        project_root = Path.cwd()

    tips: list[str] = []

    low_quality = _count_low_quality_skills(project_root)
    if low_quality > 0:
        tips.append(
            f"[yellow]{low_quality} skill(s)[/yellow] have low quality scores "
            f"[dim]([cyan]vibe status[/cyan] for details)[/dim]"
        )

    stale = _count_stale_skills(project_root)
    if stale > 0:
        tips.append(
            f"[yellow]{stale} skill(s)[/yellow] may need cleanup "
            f"[dim]([cyan]vibe status[/cyan] for details)[/dim]"
        )

    if not tips:
        return

    console.print()
    for tip in tips[:2]:
        console.print(f"  [dim]💡 {tip}[/dim]")
