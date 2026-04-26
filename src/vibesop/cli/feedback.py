"""User feedback collection after orchestration."""

from __future__ import annotations

import contextlib
from typing import Any

import questionary
from rich.console import Console


def _collect_feedback(result: Any, router: Any, console: Console) -> None:
    """Collect user satisfaction feedback after orchestration."""
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
