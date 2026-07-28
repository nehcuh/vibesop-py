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
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from vibesop.core.models import OrchestrationMode, OrchestrationResult
from vibesop.core.observability.tracer import bind_task_context, get_tracer

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from vibesop.core.routing.context_mixin import RoutingContext


class Orchestrator:
    """Handles multi-intent detection, task decomposition, and plan building."""

    def __init__(self, router: Any) -> None:
        self._router = router

    @contextmanager
    def _phase_span(self, phase: str, query: str) -> Generator[None, None, None]:
        """Open a ``workflow_node`` span for one orchestration phase.

        Each phase (routing / detection / decomposition / plan_building /
        complete) is wrapped so the dashboard's Orchestration Map can render
        phase boundaries. Spans share the parent trace opened by
        ``orchestrate()``.
        """
        with get_tracer().span(
            f"orchestrate:{phase}",
            kind="workflow_node",
            metadata={"phase": phase, "query": query[:200]},
        ):
            yield

    def orchestrate(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
        callbacks: Any | None = None,
        conversation_id: str | None = None,
        storage_dir: str | Path | None = None,
    ) -> OrchestrationResult:
        """Orchestrate a query — detect multi-intent and build execution plan if needed.

        Wraps the implementation in a trace context so all spans emitted during
        orchestration (phase workflow_node spans + downstream LLM spans via
        SpanWrappedProvider) share a single ``trace_id``. This is the natural
        trace root for any complex query (v3 Phase A Task 2).

        When ``conversation_id`` is provided, also writes
        ``orchestration_id`` (= plan_id when a plan was built) and
        ``orchestration_trace_id`` into the conversation metadata file (v3
        Phase A Task 5). This is the cross-process join key — ``contextvars``
        does NOT cross process boundaries, so the dashboard must read these
        from the persisted conversation JSON to JOIN conversation ↔ plan ↔
        spans. Best-effort: writeback failures never break orchestration.
        """
        with get_tracer().trace(
            "orchestrate",
            metadata={"query": query[:500]},
        ) as root_span:
            result = self._orchestrate_impl(
                query,
                candidates,
                context,
                callbacks,
                trace_id=root_span.trace_id,
            )
            if conversation_id:
                self._writeback_to_conversation(
                    conversation_id=conversation_id,
                    storage_dir=storage_dir,
                    plan=result.execution_plan,
                    trace_id=root_span.trace_id,
                )
            return result

    @staticmethod
    def _writeback_to_conversation(
        *,
        conversation_id: str,
        storage_dir: str | Path | None,
        plan: Any,
        trace_id: str,
    ) -> None:
        """Persist orchestration_id + trace_id to conversation metadata.

        Cross-process join contract (v3 Phase A Task 5):
        - ``orchestration_id`` = ``plan.plan_id`` (None when single-skill path
          was taken — no plan built).
        - ``orchestration_trace_id`` = the root 'orchestrate' span's trace_id,
          so the DAG rebuilder can join conversation ↔ spans.jsonl.

        Best-effort: any IO failure is logged + swallowed — orchestrate must
        never fail because of writeback.
        """
        try:
            from vibesop.core.conversation import ConversationContext

            ctx = ConversationContext(
                conversation_id=conversation_id,
                storage_dir=storage_dir or ".vibe/conversations",
            )
            ctx.metadata["orchestration_id"] = plan.plan_id if plan is not None else None
            ctx.metadata["orchestration_trace_id"] = trace_id
            ctx.save()
        except Exception as e:
            logger.warning(
                "Failed to write orchestration metadata to conversation %s: %s",
                conversation_id,
                e,
            )

    def _orchestrate_impl(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
        callbacks: Any | None = None,
        *,
        trace_id: str = "",
    ) -> OrchestrationResult:
        """Actual orchestration logic — see ``orchestrate()`` for trace wrapping.

        ``trace_id`` is the root trace's id (passed in by ``orchestrate()``).
        It's written into ``plan.metadata`` so the DAG rebuilder can JOIN
        plan ↔ spans.jsonl via ``metadata.trace_id == span.trace_id`` (v3
        Phase A Task 10, P0-2 mandatory). Empty string = tracing disabled
        → JOIN key omitted (DAG rebuilder will skip the plan).
        """
        from vibesop.core.orchestration.callbacks import (
            ErrorPolicy,
            NoOpCallbacks,
            OrchestrationPhase,
            PhaseInfo,
        )

        cb = callbacks if callbacks is not None else NoOpCallbacks()
        start_time = time.perf_counter()

        # 1. Single-skill routing (fast path)
        with self._phase_span("routing", query):
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
        with self._phase_span("detection", query):
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
        with self._phase_span("decomposition", query):
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

        with self._phase_span("plan_building", query):
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

            # Per-step classification with task_id binding (v3 Phase A Task 4).
            # Each classify_step() call emits an llm span via SpanWrappedProvider;
            # bind_task_context propagates step.step_id into the span so the DAG
            # rebuilder can JOIN step.spans = [s for s in spans if s.task_id == step.step_id].
            # grok+pi P0-1: NO plan_id fallback — every bound span must carry a step_id.
            step_classifier = ClassifierAgent(llm_client=self._router._llm)
            for step in plan.steps:
                idx = step.step_number - 1
                sub_task = sub_tasks[idx] if 0 <= idx < len(sub_tasks) else None
                with bind_task_context(step.step_id, step.assigned_role):
                    step_classifier.classify_step(step, sub_task)

            # Persist final plan state via PlanTracker so the DAG rebuilder
            # can JOIN plan ↔ spans.jsonl (v3 Phase A Task 10, P0-2). The
            # trace_id is the cross-process JOIN key — contextvars does NOT
            # cross process boundaries, so the rebuilder reads it from
            # ``plan.metadata["trace_id"]`` instead. Best-effort: persistence
            # failure must never break orchestration.
            if trace_id:
                plan.metadata["trace_id"] = trace_id
                plan.metadata["orchestration_id"] = plan.plan_id
                try:
                    self._router._get_plan_tracker().create_plan(plan)
                except Exception as e:
                    logger.warning(
                        "Failed to persist plan %s via PlanTracker: %s",
                        plan.plan_id,
                        e,
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

        with self._phase_span("complete", query):
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
