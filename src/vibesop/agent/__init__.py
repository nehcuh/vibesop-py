"""VibeSOP Agent Integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibesop.core.exceptions import SingleIntentRoutingError


class SimpleResponse:
    """Simple response wrapper for LLM output."""

    def __init__(
        self,
        content: str,
        model: str = "agent-internal",
        input_tokens: int = 0,
        output_tokens: int = 0,
    ):
        self.content = content
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.tokens_used = input_tokens + output_tokens


class SimpleLLM:
    """Simple LLM wrapper interface for Agent integration."""

    def configured(self) -> bool:
        return True

    def call(self, prompt: str, max_tokens: int = 100, temperature: float = 0.1) -> SimpleResponse:
        raise NotImplementedError("Subclasses must implement call()")


class AgentRouter:
    """Router wrapper for AI Agent integration.

    Provides a simplified interface over UnifiedRouter for agents that need
    routing without managing the full orchestration lifecycle.

    Example:
        >>> router = AgentRouter()
        >>> router.set_llm(agent_llm)
        >>> result = router.route("debug this error")
        >>> if result.has_match:
        ...     skill = result.primary.skill_id
    """

    def __init__(self, project_root: str | Path = "."):
        from vibesop.core.routing import UnifiedRouter

        prompt_builder = self._build_prompt_builder()
        self._router = UnifiedRouter(
            project_root=project_root,
            prompt_builder=prompt_builder,
        )

    @staticmethod
    def _build_prompt_builder() -> Any:
        def builder(query: str, skills_summary: str, version: str) -> str:
            from vibesop.llm.triage_prompts import TriagePromptRegistry

            return TriagePromptRegistry.render(
                query=query,
                skills_summary=skills_summary,
                version=version,
            )

        return builder

    def set_llm(self, llm_provider: Any) -> None:
        """Inject the Agent's LLM for AI triage.

        Args:
            llm_provider: Object with call(prompt, max_tokens, temperature)
                returning a response with a .content attribute.
        """
        self._router.set_llm(llm_provider)

    def set_llm_factory(self, llm_factory: Any) -> None:
        """Inject an LLM factory for lazy provider creation.

        Args:
            llm_factory: Callable that returns an LLM provider.
        """
        self._router.set_llm_factory(llm_factory)

    def route(
        self, query: str, enable_ai_triage: bool = True, *, record_telemetry: bool = True
    ) -> Any:
        """Route a query to the best matching skill.

        Args:
            query: Natural language query string.
            enable_ai_triage: Temporarily enable AI triage for this call.
            record_telemetry: Forwarded to the underlying router — meta-callers
                (e.g. detect_intents) pass False so one user query is recorded
                once, not twice.
        """
        # If AI triage is requested and LLM is available, temporarily enable it
        if enable_ai_triage and self._router.llm is not None:
            # Store original configs
            original_router_config = self._router.routing_config
            original_triage_config = self._router.triage_service.config
            try:
                # Create modified configs with AI triage enabled
                modified_config = original_router_config.model_copy(
                    update={"enable_ai_triage": True}
                )
                self._router.routing_config = modified_config
                self._router.triage_service.config = modified_config
                result = self._router.route_single(query, record_telemetry=record_telemetry)
            finally:
                # Restore original configs
                self._router.routing_config = original_router_config
                self._router.triage_service.config = original_triage_config
        else:
            result = self._router.route_single(query, record_telemetry=record_telemetry)

        return result

    def check_reroute(
        self,
        new_message: str,
        current_skill: str,
        enable_ai_triage: bool = True,
    ) -> dict[str, Any]:
        """Check if re-routing is suggested for a new message."""
        from vibesop.core.sessions import SessionContext

        # Enable AI triage temporarily if requested and LLM is available
        if enable_ai_triage and self._router.llm is not None:
            original_router_config = self._router.routing_config
            original_triage_config = self._router.triage_service.config
            try:
                modified_config = original_router_config.model_copy(
                    update={"enable_ai_triage": True}
                )
                self._router.routing_config = modified_config
                self._router.triage_service.config = modified_config
                ctx = SessionContext(
                    project_root=str(self._router.project_root), router=self._router
                )
                ctx.set_current_skill(current_skill)
                suggestion = ctx.check_reroute_needed(new_message)
            finally:
                self._router.routing_config = original_router_config
                self._router.triage_service.config = original_triage_config
        else:
            ctx = SessionContext(project_root=str(self._router.project_root), router=self._router)
            ctx.set_current_skill(current_skill)
            suggestion = ctx.check_reroute_needed(new_message)

        return {
            "should_reroute": suggestion.should_reroute,
            "recommended_skill": suggestion.recommended_skill,
            "confidence": suggestion.confidence,
            "reason": suggestion.reason,
            "current_skill": suggestion.current_skill,
        }

    def get_session_summary(self) -> dict[str, Any]:
        from vibesop.core.sessions import SessionContext

        ctx = SessionContext.load(project_root=str(self._router.project_root))
        return ctx.get_session_summary()

    # ================================================================
    # Orchestration API - Multi-intent detection and task decomposition
    # ================================================================

    def detect_intents(self, query: str) -> dict[str, Any]:
        """Detect if a query contains multiple distinct intents."""
        from vibesop.core.orchestration import MultiIntentDetector

        # First, get single routing result for context. This is an auxiliary
        # pass — the caller's real route() comes later, so suppress telemetry
        # here to keep one record per user query (Pi P1 review).
        single_result = self.route(query, enable_ai_triage=False, record_telemetry=False)

        # Initialize detector
        detector = MultiIntentDetector()

        # Check if should decompose
        should_decompose = detector.should_decompose(query, single_result)

        return {
            "is_multi_intent": should_decompose,
            "confidence": 0.8 if should_decompose else 0.2,
            "reason": "Multiple intent keywords detected"
            if should_decompose
            else "Single intent detected",
            "primary_skill": single_result.primary.skill_id if single_result.has_match else None,
        }

    def decompose(self, query: str) -> list[dict[str, str]]:
        """Decompose a complex query into independent sub-tasks.

        Returns an empty list both for junk queries (harness-injected markup,
        rejected by the ``_is_junk_query`` guard) and for legitimate
        single-intent queries with nothing to decompose — the two cases are
        indistinguishable to the caller at this API layer. The ``vibe
        decompose`` CLI command prints a distinct rejection message for junk.
        """
        from vibesop.core.orchestration import TaskDecomposer
        from vibesop.core.routing.unified import _is_junk_query

        # Junk guard: harness-injected markup is not a user query — return an
        # empty decomposition (same predicate as the route() entry guard).
        if _is_junk_query(query):
            return []

        # Initialize decomposer with injected LLM
        decomposer = TaskDecomposer(llm_client=self._router.llm)

        # Pass the skill catalog so the LLM can pre-assign skill_id per sub-task —
        # without it, PlanBuilder falls back to skip_ai_triage routing and every
        # sub-task ends up at whichever skill the SCENARIO/INDEX layers pick first.
        skills = self._router.build_decomposition_skills(query=query)

        sub_tasks = decomposer.decompose(query, skills=skills)

        return [
            {
                "intent": task.intent,
                "query": task.query,
                "skill_id": task.skill_id,  # type: ignore[dict-item]
            }
            for task in sub_tasks
        ]

    def build_plan(
        self,
        query: str,
        sub_tasks: list[dict[str, str]] | None = None,
        plan_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build an execution plan for a complex query."""
        from vibesop.core.models import WorkflowPattern
        from vibesop.core.orchestration import PlanBuilder, SubTask, TaskDecomposer
        from vibesop.core.routing.unified import _is_junk_query

        # Auto-decompose if sub_tasks not provided. Keep SubTask objects directly
        # so the LLM-assigned skill_id (and task_type) are preserved into PlanBuilder.
        if sub_tasks is None:
            if _is_junk_query(query):
                # Junk guard: harness-injected markup is not a user query —
                # plan from an empty decomposition (same predicate as the
                # route() entry guard).
                sub_task_objects: list[SubTask] = []
            else:
                decomposer = TaskDecomposer(llm_client=self._router.llm)
                skills = self._router.build_decomposition_skills(query=query)
                sub_task_objects = decomposer.decompose(query, skills=skills)
        else:
            # External caller provided dicts — read skill_id/task_type if present.
            sub_task_objects = [
                SubTask(
                    intent=t["intent"],
                    query=t["query"],
                    skill_id=t.get("skill_id"),
                    task_type=t.get("task_type", ""),
                )
                for t in sub_tasks
            ]

        # Build plan
        plan_builder = PlanBuilder(router=self._router)

        # When the caller supplied intent_analysis (e.g. fast multi-role path)
        # pick a squad-oriented workflow pattern so PlanBuilder enters the
        # _build_squad_steps branch and produces per-role steps.
        effective_pattern: WorkflowPattern | None = None
        metadata_for_plan: dict[str, Any] = dict(plan_metadata or {})
        analysis_dict = metadata_for_plan.get("intent_analysis")
        if analysis_dict is not None:
            protocol = analysis_dict.get("collaboration_protocol", "sequential")
            if protocol == "debate":
                effective_pattern = WorkflowPattern.DEBATE
            elif protocol == "red_team":
                effective_pattern = WorkflowPattern.RED_TEAM
            else:
                effective_pattern = WorkflowPattern.AGENT_SQUAD

        if effective_pattern is not None:
            plan = plan_builder.build_plan(
                query,
                sub_task_objects,
                workflow_pattern=effective_pattern,
                metadata=metadata_for_plan,
            )
        else:
            plan = plan_builder.build_plan(query, sub_task_objects)

        return {
            "plan_id": plan.plan_id,
            "original_query": plan.original_query,
            "steps": [
                {
                    "step_id": step.step_id,
                    "step_number": step.step_number,
                    "skill_id": step.skill_id,
                    "skill_file": getattr(step, "skill_file", "") or "",
                    "intent": step.intent,
                    "input_query": step.input_query,
                    "output_as": step.output_as,
                    "status": step.status.value,
                }
                for step in plan.steps
            ],
            "detected_intents": plan.detected_intents,
            "reasoning": plan.reasoning,
            "status": plan.status.value,
        }

    def orchestrate(
        self,
        query: str,
        callbacks: Any | None = None,  # noqa: ARG002  # accepted for API compatibility
        context: Any | None = None,
    ) -> dict[str, Any]:
        """Full orchestration: detect intents, decompose, and build plan.

        Args:
            query: User query string.
            callbacks: Optional orchestration callbacks (e.g. LiveOrchestrationCallbacks).
                Currently unused by this synchronous path but accepted for
                API compatibility with ``AgentRuntime.handle_query`` so callers
                can pass it through without triggering ``TypeError``.
            context: Optional routing context. When its ``metadata`` carries
                an ``intent_analysis`` payload (e.g. from IntentInterceptor's
                fast multi-role path), the analysis is forwarded to
                :meth:`build_plan` so the squad-oriented workflow pattern
                triggers per-role steps and ``agent_squad`` metadata.
        """
        # Step 1: Detect intents
        intent_detection = self.detect_intents(query)

        if not intent_detection["is_multi_intent"]:
            # Single intent - return routing result
            single_result = self.route(query)
            return {
                "is_multi_intent": False,
                "single_result": {
                    "skill_id": single_result.primary.skill_id if single_result.has_match else None,
                    "confidence": single_result.primary.confidence
                    if single_result.has_match
                    else 0.0,
                    "layer": single_result.primary.layer.value if single_result.has_match else None,
                },
            }

        # Step 2: Decompose and build plan. Pass intent_analysis through when
        # the caller attached one (e.g. IntentInterceptor fast multi-role path)
        # so PlanBuilder can enter the squad branch.
        ctx_metadata: dict[str, Any] = {}
        if context is not None:
            ctx_metadata = dict(getattr(context, "metadata", None) or {})

        plan = self.build_plan(query, plan_metadata=ctx_metadata or None)

        return {
            "is_multi_intent": True,
            "plan": plan,
        }

    def load_skill(self, skill_id: str) -> str | None:
        """Load a skill's content for execution."""
        from vibesop.core.skills import SkillLoader

        loader = SkillLoader(project_root=self._router.project_root)

        # Get the skill definition
        loaded_skill = loader.get_skill(skill_id)
        if loaded_skill and loaded_skill.source_file:
            return loaded_skill.source_file.read_text(encoding="utf-8")

        return None

    # ================================================================
    # Parallel Execution API - Execute plans with parallel steps
    # ================================================================

    def get_parallel_preview(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Get preview of parallel execution for a plan."""
        from vibesop.core.models import ExecutionPlan
        from vibesop.core.orchestration.parallel_scheduler import ParallelScheduler

        # v7.0.10: use ExecutionPlan.from_dict instead of manual field-by-field
        # reconstruction. Previously each call site picked a different subset
        # of fields, silently dropping parallel_group / metadata / step_type.
        execution_plan = ExecutionPlan.from_dict(plan)

        scheduler = ParallelScheduler()
        return scheduler.get_execution_preview(execution_plan)

    def execute_plan(
        self,
        plan: dict[str, Any],
        step_executor: Any,
        max_parallel: int = 5,
    ) -> dict[str, Any]:
        """Execute an execution plan with parallel step support."""
        from vibesop.core.models import ExecutionPlan
        from vibesop.core.orchestration.parallel_scheduler import execute_plan_sync

        # v7.0.10: see get_parallel_preview — from_dict closes schema drift.
        execution_plan = ExecutionPlan.from_dict(plan)

        # Execute the plan
        return execute_plan_sync(execution_plan, step_executor, max_parallel)

    def create_runner(
        self,
        query: str,
        project_root: str | Path = ".",
        event_log: Any | None = None,
    ) -> Any:
        """Create a StepRunner for a multi-intent query.

        ``event_log`` (optional ``PlanEventLog``) is threaded into the
        dynamic-plan WorkflowEngine so external observers can subscribe to
        plan execution events — the integration point for the v8.3 event
        contract.
        """
        from vibesop.agent.step_runner import StepRunner

        orch = self.orchestrate(query)
        if not orch.get("is_multi_intent"):
            raise SingleIntentRoutingError(
                "Query is single-intent. Use router.route() directly for single-skill routing."
            )

        plan_dict = orch["plan"]
        from vibesop.core.models import ExecutionPlan

        # v7.0.10: use from_dict to avoid manual field-by-field rebuild that
        # silently dropped step_type / metadata / estimated_* fields.
        plan = ExecutionPlan.from_dict(plan_dict)
        return StepRunner(plan, project_root=project_root, event_log=event_log)


__all__ = [
    "AgentRouter",
    "SimpleLLM",
    "SimpleResponse",
]
