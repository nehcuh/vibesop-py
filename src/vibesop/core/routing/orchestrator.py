"""Orchestrator — multi-intent detection and execution planning.

Extracted from UnifiedRouter.orchestrate() to separate routing concerns
from orchestration concerns.

Usage:
    orchestrator = Orchestrator(router)
    result = orchestrator.orchestrate("分析架构并生成测试")
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any, cast

from vibesop.core.models import OrchestrationMode, OrchestrationResult
from vibesop.core.observability.tracer import get_tracer

logger = logging.getLogger(__name__)

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
        """Orchestrate a query — detect multi-intent and build execution plan if needed.

        Wraps the implementation in a trace context so all spans emitted during
        orchestration (phase workflow_node spans + downstream LLM spans via
        SpanWrappedProvider) share a single ``trace_id``. This is the natural
        trace root for any complex query (v3 Phase A Task 2).
        """
        with get_tracer().trace(
            "orchestrate",
            metadata={"query": query[:500]},
        ):
            return self._orchestrate_impl(query, candidates, context, callbacks)

    def _orchestrate_impl(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
        callbacks: Any | None = None,
    ) -> OrchestrationResult:
        """Actual orchestration logic — see ``orchestrate()`` for trace wrapping."""
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

        # 5. Classify workflow pattern (Phase 1: generative dynamic)
        cb.on_phase_start(
            PhaseInfo(
                phase=OrchestrationPhase.PLAN_BUILDING,
                message="Selecting workflow pattern...",
                progress=0.55,
            )
        )
        from vibesop.core.models import ClassifierResult, WorkflowPattern
        from vibesop.core.orchestration.classifier import ClassifierAgent

        classifier = ClassifierAgent(llm_client=self._router._llm)
        classification = classifier.classify(query, sub_tasks)

        # Check for explicit overrides from CLI (e.g. --pattern fan_out --verify)
        if context is not None:
            hint = getattr(context, "strategy_hint", None) or ""
            # Parse space-separated key:value pairs from strategy_hint
            hint_tokens = {}
            for token in hint.split():
                if ":" in token:
                    k, v = token.split(":", 1)
                    hint_tokens[k.strip()] = v.strip()

            if "workflow_pattern" in hint_tokens:
                override = hint_tokens["workflow_pattern"]
                with contextlib.suppress(ValueError):  # Invalid override, keep classifier result
                    classification = ClassifierResult(
                        pattern=WorkflowPattern(override),
                        confidence=1.0,
                        reasoning=f"User explicitly selected {override} pattern",
                    )

            # Store verify hint for plan execution phase
            if "verify" in hint_tokens:
                context._verify_hint = hint_tokens["verify"]
        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.PLAN_BUILDING,
                message=f"Pattern: {classification.pattern.value} ({classification.confidence:.0%})",
                progress=0.6,
                metadata={
                    "pattern": classification.pattern.value,
                    "confidence": classification.confidence,
                    "reasoning": classification.reasoning,
                },
            )
        )

        # 6. Build execution plan with pattern awareness
        cb.on_phase_start(
            PhaseInfo(
                phase=OrchestrationPhase.PLAN_BUILDING,
                message="Building execution plan...",
                progress=0.6,
            )
        )
        builder = self._router._get_plan_builder()

        # Carry intent analysis from the routing context so PlanBuilder can
        # enter the squad path (per-role steps + agent_squad metadata) when
        # the interceptor decided MULTI_AGENT_SQUAD. Without this passthrough,
        # the analysis attached to RoutingContext.metadata is silently dropped.
        plan_metadata: dict[str, Any] = dict(getattr(classification, "metadata", None) or {})
        effective_pattern = classification.pattern
        if context is not None:
            ctx_metadata = getattr(context, "metadata", None) or {}
            # Read intent_analysis: first-class field first, fall back to the
            # legacy metadata backchannel for code paths not yet migrated
            # (deprecated; will be removed in v7.1).
            ctx_analysis_dict = getattr(context, "intent_analysis", None)
            if ctx_analysis_dict is None:
                ctx_analysis_dict = ctx_metadata.get("intent_analysis")
            # Same field-first / metadata-fallback policy for interception_mode.
            interception_mode = getattr(context, "interception_mode", None) or ""
            if not interception_mode:
                interception_mode = ctx_metadata.get("_interception_mode", "")
            if ctx_analysis_dict is not None:
                # Prefer the context's analysis — the interceptor already
                # committed to MULTI_AGENT_SQUAD and built a complete analysis.
                plan_metadata["intent_analysis"] = ctx_analysis_dict

                # Force a squad-oriented pattern when the interceptor flagged
                # multi_agent_squad; otherwise PlanBuilder skips _build_squad_steps.
                if interception_mode == "multi_agent_squad" and effective_pattern not in (
                    WorkflowPattern.AGENT_SQUAD,
                    WorkflowPattern.DEBATE,
                    WorkflowPattern.RED_TEAM,
                ):
                    protocol = ctx_analysis_dict.get("collaboration_protocol", "sequential")
                    if protocol == "debate":
                        effective_pattern = WorkflowPattern.DEBATE
                    elif protocol == "red_team":
                        effective_pattern = WorkflowPattern.RED_TEAM
                    else:
                        effective_pattern = WorkflowPattern.AGENT_SQUAD

        try:
            plan = builder.build_plan(
                query,
                sub_tasks,
                workflow_pattern=effective_pattern,
                metadata=plan_metadata,
            )
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

        # 7. Apply --verify override: force adversarial pattern if verification requested
        verify_hint = getattr(context, "_verify_hint", None) if context else None
        if verify_hint and plan.workflow_pattern != WorkflowPattern.ADVERSARIAL:
            from vibesop.core.models import ExecutionMode, TrustLevel

            original_pattern = plan.workflow_pattern
            plan.workflow_pattern = WorkflowPattern.ADVERSARIAL
            plan.execution_mode = ExecutionMode.SEQUENTIAL

            # Append verification step to the plan
            from vibesop.core.orchestration.plan_builder import PlanBuilder

            PlanBuilder._apply_adversarial(plan.steps, query)
            # Mark the new verification step with QUARANTINE trust
            if plan.steps:
                plan.steps[-1].is_verification_step = True
                plan.steps[-1].trust_level = TrustLevel.QUARANTINE

            logger.info(
                "--verify: upgraded plan from %s to adversarial (%d steps)",
                original_pattern.value,
                len(plan.steps),
            )

        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.PLAN_BUILDING,
                message=f"Execution plan built with {len(plan.steps)} steps ({'dynamic' if WorkflowPattern(plan.workflow_pattern) in (WorkflowPattern.LOOP_UNTIL_DRY, WorkflowPattern.TOURNAMENT) else 'static'})",
                progress=0.9,
                metadata={
                    "step_count": len(plan.steps),
                    "strategy": plan.execution_mode.value,
                    "pattern": plan.workflow_pattern.value,
                },
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

        # P3: on unattended runs (CLI flagged context.metadata
        # ["_sequence_unattended"]), record the plan's skill sequence as
        # application-only telemetry (success=False). Interactive runs record
        # in the CLI confirmation flow instead — explicit user confirmation is
        # the only success=True source — so this path never double-counts.
        self._record_plan_sequence(query, plan, context)

        cb.on_plan_ready(plan)
        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.COMPLETE,
                message="Orchestration complete",
                progress=1.0,
            )
        )

        return result

    def _record_plan_sequence(self, query: str, plan: Any, context: Any) -> None:
        """Record the plan's skill sequence on unattended runs (P3 telemetry).

        Gated on the CLI's ``_sequence_unattended`` context flag so interactive
        runs — where the confirmation flow records the explicit signal — are
        never double-counted. Application-only: success=False per the privacy
        rule. Fully fault-tolerant.
        """
        try:
            if not (context and context.metadata.get("_sequence_unattended")):
                return
            steps = [s.skill_id for s in plan.steps if getattr(s, "skill_id", None)]
            if len(steps) < 3:
                return
            self._router._get_instinct_learner().record_sequence(
                steps=steps, success=False, context=query
            )
        except Exception as e:  # telemetry must never break orchestration
            logger.debug("Failed to record plan sequence: %s", e)
