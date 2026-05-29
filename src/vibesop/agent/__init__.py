"""VibeSOP Agent Integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any


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

    def route(self, query: str, enable_ai_triage: bool = True) -> Any:
        """Route a query to the best matching skill.

        Args:
            query: Natural language query string.
            enable_ai_triage: Temporarily enable AI triage for this call.
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
                result = self._router.route_single(query)
            finally:
                # Restore original configs
                self._router.routing_config = original_router_config
                self._router.triage_service.config = original_triage_config
        else:
            result = self._router.route_single(query)

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
                ctx = SessionContext(project_root=str(self._router.project_root), router=self._router)
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

        # First, get single routing result for context
        single_result = self.route(query, enable_ai_triage=False)

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
        """Decompose a complex query into independent sub-tasks."""
        from vibesop.core.orchestration import TaskDecomposer

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
        self, query: str, sub_tasks: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        """Build an execution plan for a complex query."""
        from vibesop.core.orchestration import PlanBuilder, SubTask, TaskDecomposer

        # Auto-decompose if sub_tasks not provided. Keep SubTask objects directly
        # so the LLM-assigned skill_id (and task_type) are preserved into PlanBuilder.
        if sub_tasks is None:
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
        plan = plan_builder.build_plan(query, sub_task_objects)

        return {
            "plan_id": plan.plan_id,
            "original_query": plan.original_query,
            "steps": [
                {
                    "step_id": step.step_id,
                    "step_number": step.step_number,
                    "skill_id": step.skill_id,
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

    def orchestrate(self, query: str) -> dict[str, Any]:
        """Full orchestration: detect intents, decompose, and build plan."""
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

        # Step 2: Decompose and build plan
        plan = self.build_plan(query)

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
        from vibesop.core.models import ExecutionPlan, ExecutionStep
        from vibesop.core.orchestration.parallel_scheduler import ParallelScheduler

        # Reconstruct ExecutionPlan from dict
        execution_plan = ExecutionPlan(
            plan_id=plan["plan_id"],
            original_query=plan["original_query"],
            steps=[
                ExecutionStep(
                    step_id=s["step_id"],
                    step_number=s["step_number"],
                    skill_id=s["skill_id"],
                    intent=s["intent"],
                    input_query=s["input_query"],
                    output_as=s["output_as"],
                    status=s["status"],
                    dependencies=s.get("dependencies", []),
                    can_parallel=s.get("can_parallel", True),
                )
                for s in plan["steps"]
            ],
            detected_intents=plan["detected_intents"],
            reasoning=plan["reasoning"],
            created_at=plan.get("created_at", ""),
            status=plan.get("status", "pending"),
            execution_mode=plan.get("execution_mode", "sequential"),
        )

        scheduler = ParallelScheduler()
        return scheduler.get_execution_preview(execution_plan)

    def execute_plan(
        self,
        plan: dict[str, Any],
        step_executor: Any,
        max_parallel: int = 5,
    ) -> dict[str, Any]:
        """Execute an execution plan with parallel step support."""
        from vibesop.core.models import ExecutionPlan, ExecutionStep
        from vibesop.core.orchestration.parallel_scheduler import execute_plan_sync

        # Reconstruct ExecutionPlan from dict
        execution_plan = ExecutionPlan(
            plan_id=plan["plan_id"],
            original_query=plan["original_query"],
            steps=[
                ExecutionStep(
                    step_id=s["step_id"],
                    step_number=s["step_number"],
                    skill_id=s["skill_id"],
                    intent=s["intent"],
                    input_query=s["input_query"],
                    output_as=s["output_as"],
                    status=s["status"],
                    dependencies=s.get("dependencies", []),
                    can_parallel=s.get("can_parallel", True),
                )
                for s in plan["steps"]
            ],
            detected_intents=plan["detected_intents"],
            reasoning=plan["reasoning"],
            created_at=plan.get("created_at", ""),
            status=plan.get("status", "pending"),
            execution_mode=plan.get("execution_mode", "sequential"),
        )

        # Execute the plan
        return execute_plan_sync(execution_plan, step_executor, max_parallel)

    def create_runner(
        self,
        query: str,
        project_root: str | Path = ".",
    ) -> Any:
        """Create a StepRunner for a multi-intent query."""
        from vibesop.agent.step_runner import StepRunner

        orch = self.orchestrate(query)
        if not orch.get("is_multi_intent"):
            raise ValueError(
                "Query is single-intent. Use router.route() directly for single-skill routing."
            )

        plan_dict = orch["plan"]
        from vibesop.core.models import (
            ExecutionMode,
            ExecutionPlan,
            ExecutionStep,
            PlanStatus,
            StepStatus,
        )

        steps = [
            ExecutionStep(
                step_id=s["step_id"],
                step_number=s["step_number"],
                skill_id=s["skill_id"],
                intent=s.get("intent", ""),
                input_query=s.get("input_query", ""),
                output_as=s.get("output_as", ""),
                status=StepStatus(s.get("status", "pending")),
                dependencies=s.get("dependencies", []),
                can_parallel=s.get("can_parallel", True),
                parallel_group=s.get("parallel_group"),
            )
            for s in plan_dict["steps"]
        ]
        plan = ExecutionPlan(
            plan_id=plan_dict["plan_id"],
            original_query=plan_dict.get("original_query", query),
            steps=steps,
            detected_intents=plan_dict.get("detected_intents", []),
            reasoning=plan_dict.get("reasoning", ""),
            created_at=plan_dict.get("created_at", ""),
            status=PlanStatus(plan_dict.get("status", "pending")),
            execution_mode=ExecutionMode(plan_dict.get("execution_mode", "sequential")),
        )
        return StepRunner(plan, project_root=project_root)


__all__ = [
    "AgentRouter",
    "SimpleLLM",
    "SimpleResponse",
]
