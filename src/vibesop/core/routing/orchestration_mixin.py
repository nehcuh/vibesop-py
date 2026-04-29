"""Router orchestration mixin - multi-intent detection and execution planning.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from vibesop.core.models import OrchestrationMode, OrchestrationResult, RoutingResult
from vibesop.core.orchestration import MultiIntentDetector, PlanBuilder, PlanTracker
from vibesop.core.orchestration.task_decomposer import TaskDecomposer

if TYPE_CHECKING:
    from vibesop.core.routing.triage_service import TriageService


logger = logging.getLogger(__name__)


class _OrchestrationHost(Protocol):
    """Protocol defining the interface expected by RouterOrchestrationMixin."""

    _multi_intent_detector: MultiIntentDetector | None
    _task_decomposer: TaskDecomposer | None
    _plan_builder: PlanBuilder | None
    _plan_tracker: PlanTracker | None
    _triage_service: TriageService
    project_root: Path
    _llm: Any | None
    logger: logging.Logger

    def _init_decomposer_llm(self) -> Any | None: ...


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
        host = cast(_OrchestrationHost, self)
        if host._multi_intent_detector is None:
            host._multi_intent_detector = MultiIntentDetector()
        return host._multi_intent_detector

    def _get_task_decomposer(self) -> TaskDecomposer:
        host = cast(_OrchestrationHost, self)
        if host._task_decomposer is None:
            llm = host._init_decomposer_llm()
            host._task_decomposer = TaskDecomposer(llm_client=llm)
        return host._task_decomposer

    def _init_decomposer_llm(self) -> Any | None:
        """Initialize LLM client for TaskDecomposer, independent of TriageService.

        Tries in order:
        1. Agent Runtime LLM (set via set_llm())
        2. TriageService's cached LLM
        3. Direct provider creation from environment
        """
        host = cast(_OrchestrationHost, self)

        # 1. Agent Runtime LLM
        agent_llm = getattr(host, "_llm", None)
        if agent_llm is not None:
            return agent_llm

        # 2. TriageService's cached LLM
        triage_llm = getattr(host._triage_service, "_llm", None)
        if triage_llm is not None:
            return triage_llm

        # 3. Direct provider from environment
        try:
            from vibesop.llm.factory import create_provider

            provider = create_provider()
            if provider.configured():
                return provider
        except Exception as e:
            host.logger.warning("Failed to initialize LLM provider: %s", e)

        return None

    def _get_plan_builder(self) -> PlanBuilder:
        host = cast(_OrchestrationHost, self)
        if host._plan_builder is None:
            host._plan_builder = PlanBuilder(router=self)
        return host._plan_builder

    def _get_plan_tracker(self) -> PlanTracker:
        host = cast(_OrchestrationHost, self)
        if host._plan_tracker is None:
            host._plan_tracker = PlanTracker(
                storage_dir=host.project_root / ".vibe"
            )
        return host._plan_tracker
