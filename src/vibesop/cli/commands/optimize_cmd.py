"""``vibe optimize`` — routing auto-optimization from analytics data.

Usage:
    vibe optimize                # Show recommendations (dry-run)
    vibe optimize --apply        # Apply safe optimizations
    vibe optimize --days 7       # Look back 7 days
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console

from vibesop.core.routing_health import RoutingHealthAnalyzer

app = typer.Typer(help="Routing auto-optimization from analytics data", invoke_without_command=True)
console = Console()
logger = logging.getLogger(__name__)


def _grade_color(grade: str) -> str:
    mapping = {"A": "green", "B": "blue", "C": "yellow", "D": "dark_orange", "F": "red"}
    return mapping.get(grade, "dim")


@app.callback(invoke_without_command=True)
def optimize(
    apply: bool = typer.Option(False, "--apply", help="Apply safe optimizations automatically"),
    days: int = typer.Option(30, "--days", help="Lookback window in days"),
) -> None:
    """Analyze routing data and suggest optimizations.

    Without --apply, shows what would be optimized.
    With --apply, applies safe optimizations (auto-deprecate F-grade skills,
    boost A-grade skills, flag high-latency skills for review).
    """
    project_root = Path.cwd()
    analyzer = RoutingHealthAnalyzer(project_root)

    # ── 1. Routing health ──────────────────────────────────────────────
    console.rule("[bold cyan]Routing Health[/bold cyan]")
    health = analyzer.analyze(days=days)
    insights = analyzer.get_actionable_insights(health)

    gc = _grade_color(health.health_grade)
    console.print(f"  Grade: [{gc}]{health.health_grade}[/{gc}]  "
                  f"Hit rate: {health.hit_rate:.0%}  "
                  f"Routes: {health.total_routes} ({days}d)")

    if health.p50_latency_ms > 0:
        console.print(f"  Latency: P50={health.p50_latency_ms:.0f}ms  "
                      f"P95={health.p95_latency_ms:.0f}ms  "
                      f"P99={health.p99_latency_ms:.0f}ms")

    if health.ai_triage_calls > 0:
        console.print(f"  AI triage: {health.ai_triage_calls} calls, "
                      f"${health.ai_triage_cost_usd:.3f}, "
                      f"{health.ai_triage_success_rate:.0%} success")

    # ── 2. Insights ────────────────────────────────────────────────────
    if insights:
        console.print()
        for insight in insights:
            console.print(f"  [yellow]•[/yellow] {insight}")

    # ── 3. Skill quality ───────────────────────────────────────────────
    console.print()
    console.rule("[bold cyan]Skill Quality[/bold cyan]")
    quality_actions = _load_quality_actions(project_root)
    if quality_actions:
        for action in quality_actions:
            icon = "✅" if action["applied"] else "📋"
            console.print(f"  {icon} [cyan]{action['skill_id']}[/cyan]: {action['reason']}")
    else:
        console.print("  [dim]No quality issues detected.[/dim]")

    # ── 4. Apply ───────────────────────────────────────────────────────
    if apply:
        applied = _apply_optimizations(project_root, days)
        console.print()
        console.rule("[bold green]Applied Optimizations[/bold green]")
        if applied:
            for skill_id in applied:
                console.print(f"  ✅ Optimized [cyan]{skill_id}[/cyan]")
        else:
            console.print("  [dim]No safe optimizations to apply.[/dim]")


def _load_quality_actions(project_root: Path) -> list[dict]:
    """Load skill quality actions from FeedbackLoop."""
    try:
        from vibesop.core.skills.evaluator import RoutingEvaluator
        from vibesop.core.skills.feedback_loop import FeedbackLoop

        evaluator = RoutingEvaluator(project_root=project_root)
        loop = FeedbackLoop(evaluator)
        suggestions = loop.analyze_all()

        actions = []
        for s in suggestions:
            if s.action == "deprecate":
                actions.append({
                    "skill_id": s.skill_id,
                    "reason": f"Deprecate: {s.reason} (grade {s.grade}, {s.total_routes} routes)",
                    "applied": False,
                })
            elif s.action == "warn":
                actions.append({
                    "skill_id": s.skill_id,
                    "reason": f"Warning: {s.reason} (grade {s.grade})",
                    "applied": False,
                })
            elif s.action == "boost":
                actions.append({
                    "skill_id": s.skill_id,
                    "reason": f"Boost: {s.reason} (grade {s.grade})",
                    "applied": False,
                })
        return actions
    except Exception as e:
        logger.debug("Skill quality analysis unavailable: %s", e)
        return []


def _apply_optimizations(project_root: Path, days: int) -> list[str]:
    """Apply safe auto-optimizations and return list of affected skill IDs."""
    applied: list[str] = []
    try:
        from vibesop.core.skills.evaluator import RoutingEvaluator
        from vibesop.core.skills.feedback_loop import FeedbackLoop

        evaluator = RoutingEvaluator(project_root=project_root)
        loop = FeedbackLoop(evaluator)
        applied = loop.apply_auto_actions()

        # Log to structured optimization log
        if applied:
            _log_optimization(project_root, applied, days)
    except Exception as e:
        logger.warning("Optimization apply failed: %s", e)

    return applied


def _log_optimization(project_root: Path, applied: list[str], days: int) -> None:
    """Append optimization record to structured log."""
    import json
    from datetime import datetime

    log_path = project_root / ".vibe" / "optimization-log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": "auto-optimize",
        "applied_skills": applied,
        "lookback_days": days,
    }
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.debug("Failed to write optimization log: %s", e)
