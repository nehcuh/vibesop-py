"""Router analytics and routing decision recording mixin.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol, cast

from vibesop.core.matching import RoutingContext
from vibesop.core.models import OrchestrationResult, SkillRoute

logger = logging.getLogger(__name__)


class _AnalyticsHost(Protocol):
    """Protocol defining the interface expected by RouterAnalyticsMixin."""

    project_root: Path
    _preference_booster: Any

    def _get_memory_manager(self) -> Any: ...
    def _get_instinct_learner(self) -> Any: ...


class RouterAnalyticsMixin:
    """Mixin providing execution recording and routing decision persistence.

    Intended for use with UnifiedRouter. Expects the following attributes
    on the host class:
        - project_root: Path
        - _preference_booster: PreferenceBooster
    """

    def _record_execution(
        self,
        query: str,
        result: OrchestrationResult,
        user_modified: bool = False,
        user_satisfied: bool | None = None,
    ) -> None:
        """Record execution to analytics store."""
        host = cast(_AnalyticsHost, self)
        from vibesop.core.analytics import AnalyticsStore, ExecutionRecord

        store = AnalyticsStore(storage_dir=host.project_root / ".vibe")
        record = ExecutionRecord(
            query=query,
            mode=result.mode.value,
            primary_skill=result.primary.skill_id if result.primary else None,
            plan_steps=[s.skill_id for s in result.execution_plan.steps]
            if result.execution_plan
            else [],
            step_count=len(result.execution_plan.steps) if result.execution_plan else 0,
            duration_ms=result.duration_ms,
            user_modified=user_modified,
            user_satisfied=user_satisfied,
            routing_layers=[layer.value for layer in result.routing_path],
        )
        store.record(record)

    def _record_routing_decision(
        self,
        query: str,
        match: SkillRoute,
        context: RoutingContext | None,
    ) -> None:
        """Record successful routing decision to memory and instinct systems."""
        try:
            host = cast(_AnalyticsHost, self)
            # Add to memory conversation if available
            if context and context.conversation_id:
                host._get_memory_manager().add_assistant_message(
                    context.conversation_id,
                    f"Routed to {match.skill_id} (confidence: {match.confidence:.2f})",
                    metadata={"skill_id": match.skill_id, "layer": match.layer.value},
                )

            # Extract a simple instinct: query pattern -> skill suggestion
            # Only record if query is non-trivial and confidence is high
            if match.confidence >= 0.7 and len(query) > 5:
                host._get_instinct_learner().learn(
                    pattern=query.lower(),
                    action=f"suggest {match.skill_id} skill",
                    context=match.layer.value,
                    tags=["routing", "auto_extracted"],
                    source="auto_routing",
                )

            # Record to preference learner for personalization
            try:
                learner = host._preference_booster.get_learner()
                learner.record_selection(match.skill_id, query, was_helpful=True)
            except Exception as e:
                logger.debug("Failed to record preference selection: %s", e)
        except (OSError, ValueError, RuntimeError) as e:
            logger.debug("Failed to record routing decision: %s", e)
