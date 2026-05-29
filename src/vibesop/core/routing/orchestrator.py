"""Orchestrator — multi-intent detection and execution planning.

Extracted from UnifiedRouter.orchestrate() to separate routing concerns
from orchestration concerns.

Usage:
    orchestrator = Orchestrator(router)
    result = orchestrator.orchestrate("分析架构并生成测试")
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from vibesop.core.models import OrchestrationMode, OrchestrationResult

if TYPE_CHECKING:
    from vibesop.core.routing.context_mixin import RoutingContext


class Orchestrator:
    """Handles multi-intent detection, task decomposition, and plan building."""

    def __init__(self, router: Any) -> None:
        self._router = router

    def orchestrate(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
        callbacks: Any | None = None,
    ) -> OrchestrationResult:
        """Orchestrate a query — detect multi-intent and build execution plan if needed."""
        from vibesop.core.orchestration.callbacks import (
            ErrorPolicy,
            NoOpCallbacks,
            OrchestrationPhase,
            PhaseInfo,
        )

        cb = callbacks if callbacks is not None else NoOpCallbacks()
        start_time = time.perf_counter()

        # 1. Single-skill routing (fast path)
        cb.on_phase_start(
            PhaseInfo(
                phase=OrchestrationPhase.ROUTING,
                message="Analyzing query for skill match...",
                progress=0.0,
            )
        )
        single_result = self._router._single_skill_route(query, candidates, context)
        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.ROUTING,
                message=f"Single-skill match: {single_result.primary.skill_id if single_result.primary else 'none'}",
                progress=0.2,
                metadata={
                    "primary_confidence": single_result.primary.confidence
                    if single_result.primary
                    else 0.0
                },
            )
        )

        # 2. Check if orchestration is enabled
        if not self._router._config.enable_orchestration:
            return self._router._to_orchestration_result(single_result, query)

        # 3. Multi-intent detection
        cb.on_phase_start(
            PhaseInfo(
                phase=OrchestrationPhase.DETECTION,
                message="Detecting multiple intents...",
                progress=0.2,
            )
        )
        detector = self._router._get_multi_intent_detector()
        should_decompose = detector.should_decompose(
            query, single_result, llm_client=self._router._llm
        )
        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.DETECTION,
                message=f"Multi-intent detected: {should_decompose}",
                progress=0.4,
                metadata={"should_decompose": should_decompose},
            )
        )

        if not should_decompose:
            return self._router._to_orchestration_result(single_result, query)

        # 4. Decompose into sub-tasks
        cb.on_phase_start(
            PhaseInfo(
                phase=OrchestrationPhase.DECOMPOSITION,
                message="Decomposing query into sub-tasks...",
                progress=0.4,
            )
        )
        decomposer = self._router._get_task_decomposer()
        try:
            skills = self._router._build_decomposition_skills(candidates, query=query)
            sub_tasks = decomposer.decompose(query, skills=skills)
        except Exception as e:
            policy = cb.on_phase_error(
                PhaseInfo(
                    phase=OrchestrationPhase.DECOMPOSITION,
                    message="Task decomposition failed",
                    progress=0.4,
                ),
                e,
                ErrorPolicy.ABORT,
            )
            if policy == ErrorPolicy.ABORT:
                return self._router._to_orchestration_result(single_result, query)
            sub_tasks = []

        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.DECOMPOSITION,
                message=f"Decomposed into {len(sub_tasks)} sub-tasks",
                progress=0.6,
                metadata={"sub_task_count": len(sub_tasks)},
            )
        )

        if len(sub_tasks) <= 1:
            return self._router._to_orchestration_result(single_result, query)

        # 5. Build execution plan
        cb.on_phase_start(
            PhaseInfo(
                phase=OrchestrationPhase.PLAN_BUILDING,
                message="Building execution plan...",
                progress=0.6,
            )
        )
        builder = self._router._get_plan_builder()
        try:
            plan = builder.build_plan(query, sub_tasks)
        except Exception as e:
            policy = cb.on_phase_error(
                PhaseInfo(
                    phase=OrchestrationPhase.PLAN_BUILDING,
                    message="Plan building failed",
                    progress=0.6,
                ),
                e,
                ErrorPolicy.ABORT,
            )
            if policy == ErrorPolicy.ABORT:
                return self._router._to_orchestration_result(single_result, query)
            plan = cast("Any", None)

        if not plan or not plan.steps:
            cb.on_phase_complete(
                PhaseInfo(
                    phase=OrchestrationPhase.PLAN_BUILDING,
                    message="No valid plan could be built, falling back to single skill",
                    progress=0.8,
                )
            )
            return self._router._to_orchestration_result(single_result, query)

        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.PLAN_BUILDING,
                message=f"Execution plan built with {len(plan.steps)} steps",
                progress=0.9,
                metadata={"step_count": len(plan.steps), "strategy": plan.execution_mode.value},
            )
        )

        duration_ms = (time.perf_counter() - start_time) * 1000

        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query=query,
            execution_plan=plan,
            single_fallback=single_result.primary,
            layer_details=single_result.layer_details,
            duration_ms=duration_ms,
        )

        # Record execution analytics
        self._router._record_execution(query, result)

        cb.on_plan_ready(plan)
        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.COMPLETE,
                message="Orchestration complete",
                progress=1.0,
            )
        )

        return result
