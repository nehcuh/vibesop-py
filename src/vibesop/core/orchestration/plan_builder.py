"""Plan builder — converts sub-tasks into an ExecutionPlan with skill routing."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from vibesop.core.models import (
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    StepStatus,
)

if TYPE_CHECKING:
    from vibesop.core.routing.unified import UnifiedRouter

logger = logging.getLogger(__name__)


class PlanBuilder:
    """Builds an ExecutionPlan from decomposed sub-tasks.

    For each sub-task, routes to the best skill. Steps are ordered sequentially
    with simple context passing (prefix notes).
    """

    MIN_STEP_CONFIDENCE: float = 0.5

    def __init__(self, router: UnifiedRouter):
        self._router = router

    def build_plan(
        self,
        original_query: str,
        sub_tasks: list[Any],  # SubTask from task_decomposer
    ) -> ExecutionPlan:
        """Build execution plan from sub-tasks."""
        steps: list[ExecutionStep] = []
        detected_intents: list[str] = []
        reasoning_parts: list[str] = []

        for i, sub_task in enumerate(sub_tasks, 1):
            # Build contextualized query for this step
            contextualized_query = self._build_step_query(
                original_query, sub_task.query, i, steps
            )

            # Route to best skill for this sub-task
            route_result = self._router.route(contextualized_query)

            if route_result.primary is None:
                logger.warning("No skill match for sub-task %d: %s", i, sub_task.query[:50])
                continue

            if route_result.primary.confidence < self.MIN_STEP_CONFIDENCE:
                logger.warning(
                    "Low confidence (%s) for sub-task %d, skipping",
                    route_result.primary.confidence,
                    i,
                )
                continue

            detected_intents.append(sub_task.intent)
            reasoning_parts.append(
                f"Step {i}: '{sub_task.intent}' → {route_result.primary.skill_id} "
                f"({route_result.primary.confidence:.0%})"
            )

            steps.append(
                ExecutionStep(
                    step_id=str(uuid.uuid4())[:8],
                    step_number=i,
                    skill_id=route_result.primary.skill_id,
                    intent=sub_task.intent,
                    input_query=contextualized_query,
                    output_as=f"step_{i}_result",
                    status=StepStatus.PENDING,
                )
            )

        return ExecutionPlan(
            plan_id=str(uuid.uuid4())[:12],
            original_query=original_query,
            steps=steps,
            detected_intents=detected_intents,
            reasoning="; ".join(reasoning_parts) if reasoning_parts else "No decomposition reasoning",
            created_at=datetime.now(UTC).isoformat(),
            status=PlanStatus.PENDING,
        )

    def _build_step_query(
        self,
        _original_query: str,
        sub_task_query: str,
        step_number: int,
        previous_steps: list[ExecutionStep],
    ) -> str:
        """Build contextualized query for a step.

        v1: Simple prefix-based context passing.
        Each step gets the original query plus a note about previous steps.
        """
        if step_number == 1:
            return sub_task_query

        # Reference previous steps
        prev_refs = []
        for prev in previous_steps[-2:]:  # Reference last 2 steps max
            prev_refs.append(f"- {prev.intent} (completed)")

        context = "\n".join(prev_refs)
        return (
            f"{sub_task_query}\n\n"
            f"Context from previous steps:\n{context}"
        )
