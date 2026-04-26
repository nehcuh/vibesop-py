"""User feedback collection after orchestration."""

from __future__ import annotations

import contextlib
from typing import Any

import questionary
from rich.console import Console


def _collect_feedback(result: Any, router: Any, console: Console) -> None:
    """Collect user satisfaction feedback after orchestration.

    Writes to AnalyticsStore (analytics.jsonl) and synchronizes with
    ExecutionFeedbackCollector (execution_feedback.json) so the
    RoutingEvaluator quality_boost can consume the data.
    """
    try:
        feedback = questionary.select(
            "Did this decomposition match your intent?",
            choices=[
                questionary.Choice("👍 Yes, perfect", value="yes"),
                questionary.Choice("🤔 Mostly, but could be improved", value="partial"),
                questionary.Choice("👎 No, wrong decomposition", value="no"),
                questionary.Choice("Skip", value="skip"),
            ],
        ).ask()

        if feedback == "skip":
            return

        satisfied = feedback == "yes"
        partial = feedback == "partial"

        from vibesop.core.analytics import AnalyticsStore
        store = AnalyticsStore()
        records = store.list_records(limit=1)
        if records:
            record = records[0]
            record.user_satisfied = satisfied
            record.user_modified = partial
            store.record(record)

        if satisfied and result.execution_plan:
            for step in result.execution_plan.steps:
                with contextlib.suppress(Exception):
                    router.record_selection(
                        step.skill_id, result.original_query, was_helpful=True
                    )

        # Synchronize feedback with evaluator data source
        _sync_to_evaluator(result, satisfied)

        if not satisfied:
            console.print(
                "[dim]Thanks for the feedback. We'll use this to improve routing.[/dim]"
            )
            record_deviation = questionary.confirm(
                "Would you like to record this as a routing deviation for analysis?",
                default=False,
            ).ask()
            if record_deviation:
                console.print(
                    '[dim]Use: vibe deviation record "<query>" "<skill>" <confidence> "<layer>"[/dim]'
                )
    except Exception:
        pass


def _sync_to_evaluator(result: Any, satisfied: bool) -> None:
    """Sync feedback to ExecutionFeedbackCollector for evaluator consumption.

    The RoutingEvaluator reads from ExecutionFeedbackCollector
    (execution_feedback.json) to compute quality scores. Without this
    sync, feedback collected by the CLI would never reach the evaluator,
    making the quality_boost in OptimizationService a no-op.
    """
    try:
        from pathlib import Path
        from vibesop.core.feedback import ExecutionFeedbackCollector

        project_root = getattr(result, "project_root", None)
        if project_root is None:
            project_root = Path(".")
        elif isinstance(project_root, str):
            project_root = Path(project_root)
        exec_path = project_root / ".vibe" / "execution_feedback.json"

        collector = ExecutionFeedbackCollector(storage_path=exec_path)

        primary = getattr(result, "primary", None)
        if primary and getattr(primary, "skill_id", None):
            collector.record(
                skill_id=primary.skill_id,
                was_helpful=satisfied,
                execution_success=satisfied,
            )
    except Exception:
        pass
