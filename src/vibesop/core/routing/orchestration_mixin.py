"""Router orchestration mixin - multi-intent detection and execution planning.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

from typing import Any

from vibesop.core.models import OrchestrationMode, OrchestrationResult, RoutingResult
from vibesop.core.orchestration import MultiIntentDetector, PlanBuilder, PlanTracker
from vibesop.core.orchestration.task_decomposer import TaskDecomposer


class RouterOrchestrationMixin:
    """Mixin providing multi-intent detection and execution planning methods.

    Intended for use with UnifiedRouter. Expects the following attributes
    on the host class:
        - _config: RoutingConfig
        - _multi_intent_detector: MultiIntentDetector | None
        - _task_decomposer: TaskDecomposer | None
        - _plan_builder: PlanBuilder | None
        - _plan_tracker: PlanTracker | None
        - _triage_service: TriageService
        - project_root: Path
    """

    def _to_orchestration_result(self, result: RoutingResult, query: str) -> OrchestrationResult:
        """Convert a single RoutingResult to OrchestrationResult."""
        return OrchestrationResult(
            mode=OrchestrationMode.SINGLE,
            original_query=query,
            primary=result.primary,
            alternatives=result.alternatives,
            routing_path=result.routing_path,
            layer_details=result.layer_details,
            duration_ms=result.duration_ms,
        )

    def _get_multi_intent_detector(self) -> MultiIntentDetector:
        if self._multi_intent_detector is None:  # type: ignore[attr-defined]
            self._multi_intent_detector = MultiIntentDetector()  # type: ignore[attr-defined]
        return self._multi_intent_detector  # type: ignore[attr-defined]

    def _get_task_decomposer(self) -> TaskDecomposer:
        if self._task_decomposer is None:  # type: ignore[attr-defined]
            llm = self._init_decomposer_llm()  # type: ignore[attr-defined]
            self._task_decomposer = TaskDecomposer(llm_client=llm)  # type: ignore[attr-defined]
        return self._task_decomposer  # type: ignore[attr-defined]

    def _init_decomposer_llm(self) -> Any | None:
        """Initialize LLM client for TaskDecomposer, independent of TriageService.

        Tries in order:
        1. Agent Runtime LLM (set via set_llm())
        2. TriageService's cached LLM
        3. Direct provider creation from environment
        """
        # 1. Agent Runtime LLM
        agent_llm = getattr(self, "_llm", None)  # type: ignore[attr-defined]
        if agent_llm is not None:
            return agent_llm

        # 2. TriageService's cached LLM
        triage_llm = getattr(self._triage_service, "_llm", None)  # type: ignore[attr-defined]
        if triage_llm is not None:
            return triage_llm

        # 3. Direct provider from environment
        try:
            from vibesop.llm.factory import create_provider

            provider = create_provider()
            if provider.configured():
                return provider
        except Exception:
            pass

        return None

    def _get_plan_builder(self) -> PlanBuilder:
        if self._plan_builder is None:  # type: ignore[attr-defined]
            self._plan_builder = PlanBuilder(router=self)  # type: ignore[attr-defined]
        return self._plan_builder  # type: ignore[attr-defined]

    def _get_plan_tracker(self) -> PlanTracker:
        if self._plan_tracker is None:  # type: ignore[attr-defined]
            self._plan_tracker = PlanTracker(  # type: ignore[attr-defined]
                storage_dir=self.project_root / ".vibe"  # type: ignore[attr-defined]
            )
        return self._plan_tracker  # type: ignore[attr-defined]
