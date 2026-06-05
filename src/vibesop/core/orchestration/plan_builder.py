"""Plan builder — converts sub-tasks into an ExecutionPlan with skill routing."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from vibesop.core.matching import RoutingContext

# Built-in management tools that should never be assigned to sub-tasks.
# These are VibeSOP's own CLI/slash-command tools, not domain skills.
_MANAGEMENT_SKILL_IDS: frozenset[str] = frozenset({
    "builtin/slash-orchestrate",
    "builtin/slash-route",
    "builtin/slash-help",
    "builtin/slash-list",
    "builtin/slash-install",
    "builtin/slash-evaluate",
    "slash-orchestrate",
    "slash-route",
    "slash-help",
    "slash-list",
    "slash-install",
    "slash-evaluate",
})
from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    RoutingLayer,
    StepStatus,
    TrustLevel,
    WorkflowPattern,
)
from vibesop.core.orchestration.patterns import (
    DEPENDENCY_INDICATORS,
    PARALLEL_KEYWORDS,
    SEQUENTIAL_KEYWORDS,
)

if TYPE_CHECKING:
    from vibesop.core.routing.unified import UnifiedRouter

logger = logging.getLogger(__name__)

# Standard capability tags and their task_type mapping
# When a sub-task has task_type X, prefer skills with capability X
CAPABILITY_TO_TASK_TYPE: dict[str, str] = {
    "analysis": "analysis",
    "review": "review",
    "design": "design",
    "debug": "debug",
    "refactor": "refactor",
    "plan": "plan",
    "test": "test",
    "deploy": "deploy",
    "clarify": "clarify",
    "optimize": "optimize",
    "security": "security",
    "document": "document",
}



class PlanBuilder:
    """Builds an ExecutionPlan from decomposed sub-tasks.

    For each sub-task, routes to the best skill. Steps can be ordered
    sequentially or in parallel based on dependencies.

    Parallel detection:
    - Keywords like "同时", "parallel", "simultaneously" trigger parallel mode
    - Dependencies are inferred from task descriptions
    - Steps without dependencies can run in parallel

    Capability matching (v5.5):
    - Skills have capability tags (analysis, review, design, debug, etc.)
    - Sub-tasks have task_types
    - Matching boosts confidence for skills whose capabilities align with task_type
    """

    MIN_STEP_CONFIDENCE: float = 0.3

    def __init__(self, router: UnifiedRouter):
        self._router = router
        self._capability_cache: dict[str, list[str]] = {}

    def _get_skill_capabilities(self, skill_id: str) -> list[str]:
        """Fetch capability tags for a skill from the skill loader.

        Tries the router's skill_loader first, then the candidate_manager's,
        then falls back to an empty list. Results are cached per instance.
        """
        if skill_id in self._capability_cache:
            return self._capability_cache[skill_id]

        caps: list[str] = []

        # 1. Try router's direct skill_loader
        skill_loader = getattr(self._router, "_skill_loader", None)
        if skill_loader is not None:
            try:
                loaded = skill_loader.get_skill(skill_id)
                if loaded is not None:
                    caps = loaded.metadata.capabilities or []
            except Exception:
                pass

        # 2. Try candidate_manager's skill_loader
        if not caps:
            candidate_manager = getattr(self._router, "_candidate_manager", None)
            if candidate_manager is not None:
                cm_loader = getattr(candidate_manager, "_skill_loader", None)
                if cm_loader is not None:
                    try:
                        loaded = cm_loader.get_skill(skill_id)
                        if loaded is not None:
                            caps = loaded.metadata.capabilities or []
                    except Exception:
                        pass

        self._capability_cache[skill_id] = caps
        return caps

    def _capability_score(self, capabilities: list[str], task_type: str) -> float:
        """Score a skill's match against a task type based on capability tags.

        Returns 0.0-1.0 where:
        - 1.0 = exact capability match
        - 0.5 = related capability (e.g., "analysis" for "debug" task)
        - 0.0 = no matching capability
        """
        if not task_type:
            return 0.0
        if task_type in capabilities:
            return 1.0
        # Related capability scoring
        related: dict[str, list[str]] = {
            "debug": ["analysis"],
            "analysis": ["debug", "optimize"],
            "optimize": ["analysis"],
            "review": ["security", "test"],
            "test": ["review", "debug"],
            "design": ["plan"],
            "plan": ["design"],
            "clarify": ["analysis", "design"],
        }
        related_caps = related.get(task_type, [])
        overlap = set(capabilities) & set(related_caps)
        return 0.5 if overlap else 0.0

    def _select_best_by_capability(
        self,
        primary_skill_id: str,
        primary_confidence: float,
        alternatives: list[Any],  # list[SkillRoute]
        task_type: str,
    ) -> tuple[str, float]:
        """Select the best skill for a task_type, considering capabilities.

        Returns (skill_id, adjusted_confidence).
        """
        if not task_type:
            return primary_skill_id, primary_confidence

        primary_caps = self._get_skill_capabilities(primary_skill_id)
        best_skill = primary_skill_id
        best_score = (
            primary_confidence + self._capability_score(primary_caps, task_type) * 0.15
        )

        for alt in alternatives:
            alt_caps = self._get_skill_capabilities(alt.skill_id)
            alt_score = alt.confidence + self._capability_score(alt_caps, task_type) * 0.15
            if alt_score > best_score:
                best_score = alt_score
                best_skill = alt.skill_id

        return best_skill, min(best_score, 1.0)

    def build_plan(
        self,
        original_query: str,
        sub_tasks: list[Any],  # SubTask from task_decomposer
        workflow_pattern: WorkflowPattern = WorkflowPattern.SEQUENTIAL,
    ) -> ExecutionPlan:
        """Build execution plan from sub-tasks with parallel support.

        Args:
            original_query: The user's original query
            sub_tasks: Decomposed sub-tasks
            workflow_pattern: Dynamic workflow pattern selected by ClassifierAgent
        """
        # Detect execution mode (legacy) or use pattern-driven mode
        execution_mode = self._detect_execution_mode(original_query, sub_tasks)
        # Override mode based on workflow pattern
        execution_mode = self._pattern_to_execution_mode(workflow_pattern, execution_mode)

        steps: list[ExecutionStep] = []
        detected_intents: list[str] = []
        reasoning_parts: list[str] = []

        # Sub-tasks should use lightweight local matching only (keyword/scenario).
        # Pass skip_ai_triage through RoutingContext instead of mutating config
        # to keep the router thread-safe and avoid N serial LLM calls.
        sub_context = RoutingContext(skip_ai_triage=True)

        last_step_id: str | None = None
        for i, sub_task in enumerate(sub_tasks, 1):
            # Build contextualized query for this step
            contextualized_query = self._build_step_query(original_query, sub_task.query, i, steps)

            # Route to best skill for this sub-task
            # Prefer LLM-assigned skill_id from decomposition if available
            pre_assigned = getattr(sub_task, "skill_id", None)
            if pre_assigned and pre_assigned != "null" and pre_assigned not in _MANAGEMENT_SKILL_IDS:
                skill_id = pre_assigned
                confidence = 0.99
            else:
                # Use single-skill routing for sub-tasks to avoid recursive
                # orchestration (which would trigger repeated multi-intent detection
                # and cause exponential LLM calls / timeouts).
                route_method = getattr(self._router, "_single_skill_route", None)
                if route_method is None:
                    route_method = getattr(self._router, "orchestrate", None)
                if route_method is None:
                    route_method = getattr(self._router, "route", None)
                if route_method is None:
                    logger.warning("Router has no route method, skipping sub-task %d", i)
                    continue
                route_result = route_method(contextualized_query, context=sub_context)

                if route_result.primary is None:
                    logger.warning("No skill match for sub-task %d: %s", i, sub_task.query[:50])
                    continue

                is_fallback = (
                    route_result.primary.layer == RoutingLayer.FALLBACK_LLM
                    or route_result.primary.skill_id == "fallback-llm"
                )
                if is_fallback:
                    logger.warning(
                        "Fallback LLM for sub-task %d, using anyway: %s",
                        i,
                        sub_task.query[:50],
                    )

                if route_result.primary.confidence < self.MIN_STEP_CONFIDENCE and not is_fallback:
                    logger.warning(
                        "Low confidence (%s) for sub-task %d, using anyway",
                        route_result.primary.confidence,
                        i,
                    )

                skill_id = route_result.primary.skill_id
                confidence = route_result.primary.confidence
                alternatives = getattr(route_result, "alternatives", [])

                # Never assign VibeSOP management tools (slash-*) to sub-tasks.
                # These are CLI meta-tools, not domain skills. Try the best
                # alternative instead; if none, skip the step.
                if skill_id in _MANAGEMENT_SKILL_IDS:
                    if alternatives:
                        alt = alternatives[0]
                        logger.info(
                            "Sub-task %d: management skill '%s' → alternative '%s'",
                            i, skill_id, alt.skill_id,
                        )
                        skill_id = alt.skill_id
                        confidence = alt.confidence
                    else:
                        logger.warning(
                            "Sub-task %d: management skill '%s' matched but no "
                            "alternatives available — skipping step",
                            i, skill_id,
                        )
                        continue

                # Apply capability matching boost when sub-task has a task_type
                task_type = getattr(sub_task, "task_type", None) or ""
                if task_type and alternatives:
                    adjusted_id, adjusted_conf = self._select_best_by_capability(
                        skill_id,
                        confidence,
                        alternatives,
                        task_type,
                    )
                    if adjusted_id != skill_id:
                        logger.info(
                            "Capability boost: sub-task %d '%s' → %s (task_type=%s)",
                            i,
                            sub_task.intent,
                            adjusted_id,
                            task_type,
                        )
                        skill_id = adjusted_id
                        confidence = adjusted_conf

            detected_intents.append(sub_task.intent)
            reasoning_parts.append(f"Step {i}: '{sub_task.intent}' → {skill_id} ({confidence:.0%})")

            step_number = len(steps) + 1
            step_id = str(uuid.uuid4())[:8]

            # Determine dependencies based on execution mode
            dependencies, can_parallel = self._determine_dependencies(
                step_number, sub_task, execution_mode, last_step_id
            )

            steps.append(
                ExecutionStep(
                    step_id=step_id,
                    step_number=step_number,
                    skill_id=skill_id,
                    intent=sub_task.intent,
                    original_query_segment=sub_task.original_intent or sub_task.query,
                    input_query=contextualized_query,
                    output_as=f"step_{step_number}_result",
                    status=StepStatus.PENDING,
                    dependencies=dependencies,
                    can_parallel=can_parallel,
                )
            )
            last_step_id = step_id

        # Apply pattern-specific step adjustments
        steps = self._apply_pattern(steps, workflow_pattern, original_query)

        return ExecutionPlan(
            plan_id=str(uuid.uuid4())[:12],
            original_query=original_query,
            steps=steps,
            detected_intents=detected_intents,
            reasoning="; ".join(reasoning_parts)
            if reasoning_parts
            else "No decomposition reasoning",
            created_at=datetime.now(UTC).isoformat(),
            status=PlanStatus.PENDING,
            execution_mode=execution_mode,
            workflow_pattern=workflow_pattern,
        )

    def _detect_execution_mode(
        self,
        original_query: str,
        sub_tasks: list[Any],
    ) -> ExecutionMode:
        """Detect if parallel execution should be used.

        Args:
            original_query: The user's original query
            sub_tasks: List of decomposed sub-tasks

        Returns:
            ExecutionMode (SEQUENTIAL, PARALLEL, or MIXED)
        """
        query_lower = original_query.lower()

        # Check for explicit parallel keywords
        has_parallel_keyword = any(kw in query_lower for kw in PARALLEL_KEYWORDS)

        # Check for sequential keywords
        has_sequential_keyword = any(kw in query_lower for kw in SEQUENTIAL_KEYWORDS)

        # Multiple tasks without explicit sequence = parallel
        if len(sub_tasks) > 1 and has_parallel_keyword:
            return ExecutionMode.PARALLEL

        if len(sub_tasks) > 1 and not has_sequential_keyword:
            # Default to PARALLEL for multiple independent tasks
            return ExecutionMode.PARALLEL

        return ExecutionMode.SEQUENTIAL

    def _determine_dependencies(
        self,
        step_number: int,
        sub_task: Any,
        execution_mode: ExecutionMode,
        previous_step_id: str | None = None,
    ) -> tuple[list[str], bool]:
        """Determine dependencies and parallel capability for a step.

        Args:
            step_number: The step's position in the final plan (1-indexed)
            sub_task: The SubTask object
            execution_mode: The detected execution mode
            previous_step_id: The step_id of the last successfully added step,
                              if any. Used to create valid dependency references.

        Returns:
            Tuple of (dependencies list, can_parallel bool)
        """
        if execution_mode == ExecutionMode.SEQUENTIAL:
            # Sequential: each step depends on the previous actual step
            if step_number > 1 and previous_step_id is not None:
                return [previous_step_id], False
            return [], True

        if execution_mode == ExecutionMode.PARALLEL:
            # Parallel: no dependencies (all can run together)
            return [], True

        # MIXED mode: infer from task description
        # Check for dependency indicators in the intent
        intent_lower = sub_task.intent.lower()
        has_dependency = any(indicator in intent_lower for indicator in DEPENDENCY_INDICATORS)

        if has_dependency and step_number > 1 and previous_step_id is not None:
            return [previous_step_id], False

        return [], True

    # ── Pattern-aware plan generation ────────────────────────────────────────

    @staticmethod
    def _pattern_to_execution_mode(
        pattern: WorkflowPattern,
        detected_mode: ExecutionMode,
    ) -> ExecutionMode:
        """Map workflow pattern to execution mode.

        Patterns drive the high-level structure; execution_mode controls
        how the agent executor interprets dependencies.

        Only override the detected mode when the pattern explicitly demands
        it.  SEQUENTIAL (the default) preserves legacy keyword-based
        detection so existing tests and callers keep their behaviour.
        """
        if pattern == WorkflowPattern.SEQUENTIAL:
            return detected_mode
        if pattern in (WorkflowPattern.PARALLEL, WorkflowPattern.FAN_OUT):
            return ExecutionMode.PARALLEL
        if pattern == WorkflowPattern.ADVERSARIAL:
            # Adversarial runs sequentially (execute → verify)
            return ExecutionMode.SEQUENTIAL
        return detected_mode

    def _apply_pattern(
        self,
        steps: list[ExecutionStep],
        pattern: WorkflowPattern,
        original_query: str,
    ) -> list[ExecutionStep]:
        """Apply workflow pattern to step list.

        May modify dependencies, can_parallel flags, or append
        synthetic steps (e.g. synthesise for FAN_OUT, verify for ADVERSARIAL).
        """
        if pattern == WorkflowPattern.FAN_OUT:
            return self._apply_fan_out(steps, original_query)
        if pattern == WorkflowPattern.ADVERSARIAL:
            return self._apply_adversarial(steps, original_query)
        if pattern == WorkflowPattern.PARALLEL:
            return self._apply_parallel(steps)
        # SEQUENTIAL: nothing to change
        return steps

    def _apply_fan_out(
        self,
        steps: list[ExecutionStep],
        original_query: str,
    ) -> list[ExecutionStep]:
        """FAN_OUT: all sub-tasks parallel, then synthesise step."""
        if len(steps) <= 1:
            return steps

        # Clear dependencies so all run in parallel
        for step in steps:
            step.dependencies = []
            step.can_parallel = True

        # Append a synthesise step
        synthesise_step = ExecutionStep(
            step_id=str(uuid.uuid4())[:8],
            step_number=len(steps) + 1,
            skill_id="builtin/slash-orchestrate",  # meta skill for synthesis
            intent="综合所有并行步骤的结果",
            original_query_segment=original_query,
            input_query=(
                f"综合以下并行分析的结果，给出统一结论:\n"
                + "\n".join(f"- 步骤 {s.step_number} ({s.skill_id}): {s.intent}" for s in steps)
            ),
            output_as="synthesis_result",
            status=StepStatus.PENDING,
            dependencies=[s.step_id for s in steps],
            can_parallel=False,
        )
        steps.append(synthesise_step)
        return steps

    def _apply_adversarial(
        self,
        steps: list[ExecutionStep],
        original_query: str,
    ) -> list[ExecutionStep]:
        """ADVERSARIAL: execute steps, then verify."""
        if not steps:
            return steps

        # Steps run sequentially (existing dependency chain)
        # Append a verify step that depends on all previous steps
        last_step = steps[-1]
        verify_step = ExecutionStep(
            step_id=str(uuid.uuid4())[:8],
            step_number=len(steps) + 1,
            skill_id="gstack/investigate",  # investigation/review skill for verification
            intent="独立验证执行结果",
            original_query_segment=original_query,
            input_query=(
                f"独立验证以下步骤的执行结果是否完整、正确:\n"
                + "\n".join(f"- 步骤 {s.step_number} ({s.skill_id}): {s.intent}" for s in steps)
                + "\n\n请检查:\n"
                "1. 所有要求是否都已满足\n"
                "2. 是否有遗漏或错误\n"
                "3. 边缘情况是否被考虑"
            ),
            output_as="verification_result",
            status=StepStatus.PENDING,
            dependencies=[last_step.step_id],
            can_parallel=False,
            is_verification_step=True,  # Mark as verification step for Phase 2
            trust_level=TrustLevel.QUARANTINE,  # Verifier runs in quarantine mode
        )
        steps.append(verify_step)
        return steps

    def _apply_parallel(self, steps: list[ExecutionStep]) -> list[ExecutionStep]:
        """PARALLEL: clear dependencies so all steps run concurrently."""
        for step in steps:
            step.dependencies = []
            step.can_parallel = True
        return steps

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
        return f"{sub_task_query}\n\nContext from previous steps:\n{context}"
