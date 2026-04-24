"""VibeSOP Agent Integration.

This module provides direct Python API for AI Agents (like Claude Code)
to use VibeSOP routing with their internal LLM, without requiring
external API key configuration.

Usage:
    >>> from vibesop.agent import AgentRouter
    >>>
    >>> # Create a simple LLM wrapper
    >>> class AgentLLM:
    ...     def call(self, prompt, max_tokens=100, temperature=0.1):
    ...         # Use Agent's internal LLM here
    ...         response = agent_internal_llm(prompt)
    ...         return SimpleResponse(content=response)
    >>>
    >>> # Route with Agent's LLM
    >>> router = AgentRouter()
    >>> router.set_llm(AgentLLM())
    >>> result = router.route("帮我审查代码质量")
    >>> print(result.primary.skill_id)  # gstack/review
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Any


class SimpleResponse:
    """Simple response wrapper for LLM output.

    Matches the interface expected by TriageService.
    """

    def __init__(self, content: str, model: str = "agent-internal", input_tokens: int = 0, output_tokens: int = 0):
        self.content = content
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.tokens_used = input_tokens + output_tokens


class SimpleLLM:
    """Simple LLM wrapper interface for Agent integration.

    Subclasses should implement the `call` method.

    Example:
        >>> class MyLLM(SimpleLLM):
        ...     def call(self, prompt, max_tokens=100, temperature=0.1):
        ...         response = my_llm_generate(prompt)
        ...         return SimpleResponse(content=response)
    """

    def configured(self) -> bool:
        """Check if the LLM is configured and ready to use.

        Returns:
            True if the LLM can generate responses
        """
        return True

    def call(self, prompt: str, max_tokens: int = 100, temperature: float = 0.1) -> SimpleResponse:
        """Call the LLM with the given prompt.

        Args:
            prompt: The prompt to send to the LLM
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            SimpleResponse with the LLM output
        """
        raise NotImplementedError("Subclasses must implement call()")


class AgentRouter:
    """Router wrapper for AI Agent integration.

    This class provides a simplified API for Agents to use VibeSOP routing
    with their internal LLM.

    Example:
        >>> from vibesop.agent import AgentRouter, SimpleResponse
        >>>
        >>> # Define LLM wrapper
        >>> class MyLLM:
        ...     def call(self, prompt, max_tokens=100, temperature=0.1):
        ...         response = self._agent.generate(prompt)
        ...         return SimpleResponse(content=response)
        >>>
        >>> # Route with Agent's LLM
        >>> router = AgentRouter()
        >>> router.set_llm(MyLLM())
        >>> result = router.route("debug the failing test")
        >>> if result.has_match:
        ...     skill_id = result.primary.skill_id
        ...     confidence = result.primary.confidence
    """

    def __init__(self, project_root: str | Path = "."):
        """Initialize the Agent router.

        Args:
            project_root: Path to project root directory
        """
        from vibesop.core.routing import UnifiedRouter

        self._router = UnifiedRouter(project_root=project_root)

    def set_llm(self, llm_provider: Any) -> None:
        """Inject the Agent's LLM for AI triage.

        The LLM provider must have a `call` method with signature:
            call(prompt: str, max_tokens: int, temperature: float) -> Response

        The Response object must have a `content` attribute with the LLM output.

        Args:
            llm_provider: Agent's LLM wrapper

        Example:
            >>> class AgentLLM:
            ...     def call(self, prompt, max_tokens=100, temperature=0.1):
            ...         return SimpleResponse(content=self._generate(prompt))
            >>> router.set_llm(AgentLLM())
        """
        self._router.set_llm(llm_provider)

    def route(self, query: str, enable_ai_triage: bool = True) -> Any:
        """Route a query to the best matching skill.

        Args:
            query: User query or intent
            enable_ai_triage: Whether to use AI triage (requires LLM to be set)

        Returns:
            RoutingResult object with primary match, alternatives, and metadata

        Note:
            When enable_ai_triage=True and an LLM is set via set_llm(),
            AI triage will be used for this call regardless of global config.
        """
        # If AI triage is requested and LLM is available, temporarily enable it
        if enable_ai_triage and self._router._llm is not None:
            # Store original configs
            original_router_config = self._router._config
            original_triage_config = self._router._triage_service._config
            try:
                # Create modified configs with AI triage enabled
                modified_config = original_router_config.model_copy(update={"enable_ai_triage": True})
                self._router._config = modified_config
                self._router._triage_service._config = modified_config
                result = self._router.route(query)
            finally:
                # Restore original configs
                self._router._config = original_router_config
                self._router._triage_service._config = original_triage_config
        else:
            result = self._router.route(query)

        return result

    def check_reroute(
        self,
        new_message: str,
        current_skill: str,
        enable_ai_triage: bool = True,
    ) -> dict[str, Any]:
        """Check if re-routing is suggested for a new message.

        This is useful for multi-turn conversations to detect when the
        user's intent has shifted.

        Args:
            new_message: The latest user message
            current_skill: The skill currently being used
            enable_ai_triage: Whether to use AI triage (requires LLM to be set)

        Returns:
            Dictionary with:
                - should_reroute: bool
                - recommended_skill: str | None
                - confidence: float
                - reason: str
                - current_skill: str
        """
        from vibesop.core.sessions import SessionContext

        # Enable AI triage temporarily if requested and LLM is available
        if enable_ai_triage and self._router._llm is not None:
            original_router_config = self._router._config
            original_triage_config = self._router._triage_service._config
            try:
                modified_config = original_router_config.model_copy(update={"enable_ai_triage": True})
                self._router._config = modified_config
                self._router._triage_service._config = modified_config
                ctx = SessionContext(project_root=self._router.project_root, router=self._router)
                ctx.set_current_skill(current_skill)
                suggestion = ctx.check_reroute_needed(new_message)
            finally:
                self._router._config = original_router_config
                self._router._triage_service._config = original_triage_config
        else:
            ctx = SessionContext(project_root=self._router.project_root, router=self._router)
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
        """Get summary of current routing session.

        Returns:
            Dictionary with session statistics
        """
        from vibesop.core.sessions import SessionContext

        ctx = SessionContext.load(project_root=self._router.project_root)
        return ctx.get_session_summary()

    # ================================================================
    # Orchestration API - Multi-intent detection and task decomposition
    # ================================================================

    def detect_intents(self, query: str) -> dict[str, Any]:
        """Detect if a query contains multiple distinct intents.

        Args:
            query: User query to analyze

        Returns:
            Dictionary with:
                - is_multi_intent: bool
                - confidence: float
                - reason: str
                - sub_queries: list[str] (if multi-intent detected)
        """
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
            "reason": "Multiple intent keywords detected" if should_decompose else "Single intent detected",
            "primary_skill": single_result.primary.skill_id if single_result.has_match else None,
        }

    def decompose(self, query: str) -> list[dict[str, str]]:
        """Decompose a complex query into independent sub-tasks.

        Args:
            query: User query that may contain multiple intents

        Returns:
            List of sub-task dictionaries with:
                - intent: str - brief description
                - query: str - self-contained sub-query
        """
        from vibesop.core.orchestration import TaskDecomposer

        # Initialize decomposer with injected LLM
        decomposer = TaskDecomposer(llm_client=self._router._llm)

        # Decompose query
        sub_tasks = decomposer.decompose(query)

        return [
            {"intent": task.intent, "query": task.query}
            for task in sub_tasks
        ]

    def build_plan(self, query: str, sub_tasks: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Build an execution plan for a complex query.

        Args:
            query: Original user query
            sub_tasks: Optional list of sub-tasks (if None, will auto-decompose)

        Returns:
            Dictionary with execution plan:
                - plan_id: str
                - original_query: str
                - steps: list[dict] - execution steps
                - detected_intents: list[str]
                - reasoning: str
        """
        from vibesop.core.orchestration import PlanBuilder, SubTask, TaskDecomposer

        # Auto-decompose if sub_tasks not provided
        if sub_tasks is None:
            decomposer = TaskDecomposer(llm_client=self._router._llm)
            raw_sub_tasks = decomposer.decompose(query)
            sub_tasks = [
                {"intent": task.intent, "query": task.query}
                for task in raw_sub_tasks
            ]

        # Convert to SubTask objects
        sub_task_objects = [
            SubTask(intent=t["intent"], query=t["query"])
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
        """Full orchestration: detect intents, decompose, and build plan.

        This is the main entry point for complex multi-intent queries.

        Args:
            query: User query that may contain multiple intents

        Returns:
            Dictionary with:
                - is_multi_intent: bool
                - plan: dict (execution plan if multi-intent)
                - single_result: dict (routing result if single-intent)
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
                    "confidence": single_result.primary.confidence if single_result.has_match else 0.0,
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
        """Load a skill's content for execution.

        Args:
            skill_id: Skill identifier (e.g., "gstack/review", "systematic-debugging")

        Returns:
            Skill file content or None if not found
        """
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
        """Get preview of parallel execution for a plan.

        Args:
            plan: Execution plan dictionary from build_plan()

        Returns:
            Dictionary with parallel execution preview:
                - total_steps: int
                - parallel_batches: int
                - max_parallel_steps: int
                - estimated_speedup: float
                - batches: list[dict] - details of each batch
        """
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
        """Execute an execution plan with parallel step support.

        Args:
            plan: Execution plan dictionary from build_plan()
            step_executor: Function to execute a single step.
                          Called with ExecutionStep dict, should return result.
            max_parallel: Maximum number of steps to run concurrently

        Returns:
            Dictionary with:
                - results: List of step results in order
                - duration_ms: Total execution time
                - steps_executed: Number of steps executed
                - parallel_batches: Number of parallel batches

        Example:
            >>> def my_executor(step):
            ...     skill_id = step["skill_id"]
            ...     query = step["input_query"]
            ...     # Execute skill and return result
            ...     return f"Executed {skill_id}"
            >>> plan = router.build_plan("测试并审查")
            >>> results = router.execute_plan(plan, my_executor)
        """
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


__all__ = [
    "AgentRouter",
    "SimpleLLM",
    "SimpleResponse",
]
