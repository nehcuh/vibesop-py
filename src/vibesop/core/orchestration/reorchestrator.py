"""Reorchestrator — post-step analysis for runtime plan re-evaluation.

After each step completes, the reorchestrator analyzes the execution state
and decides: continue, append steps, loop back, escalate, or terminate early.

Phase 3 (v6.2.0): Full Execution Dynamic
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from vibesop.core.models import ReorchestrationDecision

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan, ExecutionStep

logger = logging.getLogger(__name__)


class ReorchestrationAnalysis(BaseModel):
    """Result of re-orchestration analysis after a step completes."""

    decision: ReorchestrationDecision = Field(
        default=ReorchestrationDecision.CONTINUE,
        description="What to do next",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the decision",
    )
    reasoning: str = Field(
        default="",
        description="Why this decision was made",
    )
    new_sub_tasks: list[dict[str, str]] = Field(
        default_factory=list,
        description="New sub-tasks to append (for APPEND_STEPS)",
    )
    loop_target_step_id: str = Field(
        default="",
        description="Step ID to loop back to (for LOOP_BACK)",
    )
    escalation_message: str = Field(
        default="",
        description="Message for user (for ESCALATE)",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "new_sub_tasks": self.new_sub_tasks,
            "loop_target_step_id": self.loop_target_step_id,
            "escalation_message": self.escalation_message,
        }


class Reorchestrator:
    """Analyzes execution state and decides next action.

    The reorchestrator runs after each step completes in a dynamic workflow.
    It checks whether the original goals have been met and, if not, decides
    how to adjust the remaining plan.

    Fast path: if all detected intents have matching completed steps and
    no step failed, returns TERMINATE_EARLY without an LLM call.
    """

    def __init__(self, llm_client: Any):
        """Initialize the reorchestrator.

        Args:
            llm_client: LLM client for semantic analysis
        """
        self._llm = llm_client

    def analyze(
        self,
        plan: ExecutionPlan,
        completed_step: ExecutionStep,
        step_output: str,
        accumulated_results: dict[str, str] | None = None,
    ) -> ReorchestrationAnalysis:
        """Analyze execution state after a step completes.

        Args:
            plan: The current execution plan
            completed_step: The step that just completed
            step_output: The output from the completed step
            accumulated_results: Results from all previously completed steps

        Returns:
            ReorchestrationAnalysis with decision and optional new sub-tasks
        """
        # Fast path: check if all goals are met without LLM call
        if self._check_goals_met(plan, accumulated_results or {}):
            return ReorchestrationAnalysis(
                decision=ReorchestrationDecision.TERMINATE_EARLY,
                confidence=1.0,
                reasoning="All detected intents have been addressed by completed steps",
            )

        # Fast path: if step failed, escalate
        if completed_step.status.value == "failed":
            return ReorchestrationAnalysis(
                decision=ReorchestrationDecision.ESCALATE,
                confidence=0.9,
                reasoning=f"Step {completed_step.step_number} failed",
                escalation_message=f"Step '{completed_step.intent}' failed. Manual intervention needed.",
            )

        # LLM-based analysis for non-trivial cases
        return self._llm_analyze(plan, completed_step, step_output, accumulated_results)

    def _check_goals_met(
        self,
        plan: ExecutionPlan,
        accumulated_results: dict[str, str],
    ) -> bool:
        """Check if all original goals have been met.

        Simple heuristic: if we have at least as many completed results
        as detected intents, consider goals met.
        """
        if not plan.detected_intents:
            return False

        completed_count = len(accumulated_results)
        intent_count = len(plan.detected_intents)

        if completed_count < intent_count:
            return False

        # Check that all steps are completed or we've exceeded intent count
        completed_steps = sum(1 for s in plan.steps if s.status.value == "completed")
        return completed_steps >= intent_count

    def _llm_analyze(
        self,
        plan: ExecutionPlan,
        completed_step: ExecutionStep,
        step_output: str,
        accumulated_results: dict[str, str] | None,
    ) -> ReorchestrationAnalysis:
        """Use LLM to analyze execution state and decide next action."""
        prompt = self._build_analysis_prompt(plan, completed_step, step_output, accumulated_results)

        try:
            response = self._llm.call(prompt, temperature=0.1)
            content = getattr(response, "content", str(response))

            import json

            parsed = json.loads(content)
            return self._parse_analysis(parsed)
        except Exception as e:
            logger.warning("Reorchestration LLM analysis failed: %s", e)
            return ReorchestrationAnalysis(
                decision=ReorchestrationDecision.CONTINUE,
                confidence=0.5,
                reasoning="LLM analysis unavailable, continuing with planned steps",
            )

    def _build_analysis_prompt(
        self,
        plan: ExecutionPlan,
        completed_step: ExecutionStep,
        step_output: str,
        accumulated_results: dict[str, str] | None,
    ) -> str:
        """Build the re-orchestration analysis prompt."""
        completed_summary = ""
        if accumulated_results:
            items = [f"- {k}: {v[:100]}" for k, v in accumulated_results.items()]
            completed_summary = "\n".join(items)

        remaining = [
            f"- Step {s.step_number}: {s.intent} (status: {s.status.value})"
            for s in plan.steps
            if s.step_number > completed_step.step_number and s.status.value == "pending"
        ]
        remaining_text = "\n".join(remaining) if remaining else "None (all steps executed)"

        return f"""Analyze the execution state of a multi-step plan.

Original goal: {plan.original_query}
Detected intents: {", ".join(plan.detected_intents)}

Completed step: {completed_step.intent}
Step output: {step_output[:500]}

All completed results:
{completed_summary or "None yet"}

Remaining planned steps:
{remaining_text}

Decide the next action:
1. continue: proceed to next planned step
2. append_steps: discovered new work needed (provide sub-tasks as list)
3. loop_back: re-execute a previous step (provide step_id)
4. escalate: need user decision (provide message)
5. terminate_early: all goals are already met

Output JSON:
{{"decision": "continue|append_steps|loop_back|escalate|terminate_early", "confidence": 0.0-1.0, "reasoning": "brief explanation", "new_sub_tasks": [{{"intent": "...", "query": "..."}}], "loop_target_step_id": "", "escalation_message": ""}}

Only include fields relevant to your decision. No markdown."""

    def _parse_analysis(self, parsed: dict[str, Any]) -> ReorchestrationAnalysis:
        """Parse LLM analysis response."""
        decision_str = parsed.get("decision", "continue").lower()
        try:
            decision = ReorchestrationDecision(decision_str)
        except ValueError:
            decision = ReorchestrationDecision.CONTINUE

        return ReorchestrationAnalysis(
            decision=decision,
            confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
            reasoning=parsed.get("reasoning", ""),
            new_sub_tasks=parsed.get("new_sub_tasks", []),
            loop_target_step_id=parsed.get("loop_target_step_id", ""),
            escalation_message=parsed.get("escalation_message", ""),
        )
