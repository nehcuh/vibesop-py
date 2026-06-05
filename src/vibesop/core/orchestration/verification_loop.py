"""Verification loop logic for adversarial workflow.

This module implements the retry loop for NEEDS_REVISION status,
allowing steps to be re-executed with verification feedback until
they pass or max retries are exceeded.

Phase 2 (v6.1.0): Adversarial Verification
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan, ExecutionStep

logger = logging.getLogger(__name__)


class VerificationLoopAction(StrEnum):
    """Action to take after verification."""

    CONTINUE = "continue"  # Proceed to next step
    RETRY = "retry"  # Re-execute the current step with feedback
    ESCALATE = "escalate"  # Escalate to user for decision
    TERMINATE = "terminate"  # Stop execution


@dataclass
class VerificationLoopConfig:
    """Configuration for verification loop behavior."""

    max_retries: int = 3  # Maximum number of retries for NEEDS_REVISION
    strictness: str = "standard"  # lenient, standard, strict
    auto_retry: bool = True  # Automatically retry on NEEDS_REVISION
    escalation_threshold: int = 2  # Escalate after this many consecutive failures


class VerificationLoopState(BaseModel):
    """State of the verification loop for a single step."""

    model_config = {"arbitrary_types_allowed": True}

    step_id: str = Field(..., description="Step being verified")
    retry_count: int = Field(default=0, description="Number of retries attempted")
    consecutive_failures: int = Field(default=0, description="Consecutive failure count")
    last_status: str = Field(default="", description="Last verification status")
    last_action: str = Field(default="", description="Last action taken")
    feedback_history: list[dict[str, Any]] = Field(
        default_factory=list, description="History of verification feedback"
    )


class VerificationLoop:
    """Manages verification loop for adversarial workflow.

    The verification loop:
    1. Executes a step
    2. Verifies the output with an independent verifier
    3. If PASSED → continue to next step
    4. If NEEDS_REVISION → retry with feedback (up to max_retries)
    5. If FAILED or max retries exceeded → escalate to user
    """

    def __init__(self, config: VerificationLoopConfig | None = None):
        """Initialize the verification loop.

        Args:
            config: Loop configuration (uses defaults if not provided)
        """
        self._config = config or VerificationLoopConfig()
        self._state: dict[str, VerificationLoopState] = {}

    def get_state(self, step_id: str) -> VerificationLoopState:
        """Get or create state for a step."""
        if step_id not in self._state:
            self._state[step_id] = VerificationLoopState(step_id=step_id)
        return self._state[step_id]

    def decide_action(
        self,
        step: ExecutionStep,
        verification_result: dict[str, Any],
    ) -> VerificationLoopAction:
        """Decide the next action after verification.

        Args:
            step: The execution step that was verified
            verification_result: Result from VerifierAgent

        Returns:
            Action to take: CONTINUE, RETRY, ESCALATE, or TERMINATE
        """
        state = self.get_state(step.step_id)
        status = verification_result.get("status", "passed")

        state.last_status = status

        if status == "passed":
            state.consecutive_failures = 0
            state.last_action = VerificationLoopAction.CONTINUE
            return VerificationLoopAction.CONTINUE

        if status == "failed":
            state.consecutive_failures += 1

            # Check if we should escalate
            if state.consecutive_failures >= self._config.escalation_threshold:
                state.last_action = VerificationLoopAction.ESCALATE
                return VerificationLoopAction.ESCALATE

            state.last_action = VerificationLoopAction.TERMINATE
            return VerificationLoopAction.TERMINATE

        if status == "needs_revision":
            state.retry_count += 1

            # Check if we've exceeded max retries
            if state.retry_count >= self._config.max_retries:
                state.last_action = VerificationLoopAction.ESCALATE
                return VerificationLoopAction.ESCALATE

            # Auto-retry if enabled
            if self._config.auto_retry:
                # Add feedback to history
                issues = verification_result.get("issues", [])
                state.feedback_history.append(
                    {
                        "retry_number": state.retry_count,
                        "status": status,
                        "issues": issues,
                        "reasoning": verification_result.get("reasoning", ""),
                    }
                )
                state.last_action = VerificationLoopAction.RETRY
                return VerificationLoopAction.RETRY

            # Manual retry required
            state.last_action = VerificationLoopAction.ESCALATE
            return VerificationLoopAction.ESCALATE

        # Unknown status - escalate to be safe
        state.last_action = VerificationLoopAction.ESCALATE
        return VerificationLoopAction.ESCALATE

    def build_retry_query(
        self,
        step: ExecutionStep,
        verification_result: dict[str, Any],
    ) -> str:
        """Build a retry query with verification feedback.

        Args:
            step: The execution step to retry
            verification_result: Result from VerifierAgent

        Returns:
            Query string with verification feedback incorporated
        """
        state = self.get_state(step.step_id)
        issues = verification_result.get("issues", [])
        reasoning = verification_result.get("reasoning", "")

        feedback_parts = []

        # Add summary of issues
        if issues:
            feedback_parts.append("验证反馈 (Verification Feedback):")
            for i, issue in enumerate(issues, 1):
                severity = issue.get("severity", "unknown")
                category = issue.get("category", "unknown")
                description = issue.get("description", "")
                suggested_fix = issue.get("suggested_fix", "")

                feedback_parts.append(f"{i}. [{severity.upper()}] {category}: {description}")
                if suggested_fix:
                    feedback_parts.append(f"   建议: {suggested_fix}")

        # Add reasoning
        if reasoning:
            feedback_parts.append(f"\n验证说明:\n{reasoning}")

        # Add retry context
        feedback_parts.append(
            f"\n这是第 {state.retry_count + 1}/{self._config.max_retries} 次尝试。"
        )

        # Combine with original query
        feedback = "\n".join(feedback_parts)
        return f"{step.input_query}\n\n{feedback}"

    def should_execute_step(self, step: ExecutionStep) -> bool:
        """Check if a step should be executed (skips verification-only steps).

        Args:
            step: Execution step to check

        Returns:
            True if step should execute, False if it's a verification-only step
        """
        # Verification steps are handled by the verifier, not the executor
        return not getattr(step, "is_verification_step", False)

    def get_summary(self) -> dict[str, Any]:
        """Get summary of verification loop activity.

        Returns:
            Dictionary with loop statistics
        """
        total_steps = len(self._state)
        total_retries = sum(s.retry_count for s in self._state.values())
        failed_steps = sum(1 for s in self._state.values() if s.last_status == "failed")

        return {
            "total_steps_verified": total_steps,
            "total_retries": total_retries,
            "failed_steps": failed_steps,
            "states": {step_id: s.model_dump() for step_id, s in self._state.items()},
        }


def execute_plan_with_verification(
    plan: ExecutionPlan,
    executor,
    verifier,
    loop_config: VerificationLoopConfig | None = None,
) -> dict[str, Any]:
    """Execute an execution plan with verification loop.

    This is the main entry point for adversarial workflow execution.
    It combines plan execution with verification and retry logic.

    Args:
        plan: Execution plan to execute
        executor: Function to execute a single step
        verifier: VerifierAgent instance
        loop_config: Optional loop configuration

    Returns:
        Dictionary with execution results and verification summary
    """
    from vibesop.core.orchestration.parallel_scheduler import execute_plan_sync

    loop = VerificationLoop(loop_config)
    results = {}
    verification_summary = []

    # Get execution order (topological sort respecting dependencies)
    execution_order = _get_execution_order(plan)

    for step_number in execution_order:
        step = next(s for s in plan.steps if s.step_number == step_number)

        # Skip verification-only steps (they're handled separately)
        if not loop.should_execute_step(step):
            continue

        # Execute the step
        try:
            result = executor(step)
            results[step.step_id] = result
        except Exception as e:
            logger.error("Step %s execution failed: %s", step.step_id, e)
            results[step.step_id] = {"error": str(e)}
            continue

        # Verify if this is an adversarial plan
        if plan.workflow_pattern == "adversarial":
            verification_result = verifier.verify(
                original_query=plan.original_query,
                step=step,
                execution_output=str(result),
            )

            verification_summary.append(
                {
                    "step_id": step.step_id,
                    "step_number": step.step_number,
                    "verification": verification_result.to_dict(),
                }
            )

            # Decide next action
            action = loop.decide_action(step, verification_result.to_dict())

            if action == VerificationLoopAction.RETRY:
                # Build retry query with feedback
                retry_query = loop.build_retry_query(step, verification_result.to_dict())

                # Create a modified step for retry
                retry_step = step.model_copy(update={"input_query": retry_query})

                # Execute retry
                try:
                    result = executor(retry_step)
                    results[step.step_id] = result
                except Exception as e:
                    logger.error("Step %s retry failed: %s", step.step_id, e)
                    results[step.step_id] = {"error": str(e)}

            elif action == VerificationLoopAction.ESCALATE:
                logger.warning(
                    "Step %s verification failed, escalating to user", step.step_id
                )
                # In a real implementation, this would prompt the user
                results[step.step_id] = {
                    "error": "Verification failed, user intervention required",
                    "verification_result": verification_result.to_dict(),
                }

    return {
        "results": results,
        "verification_summary": verification_summary,
        "loop_summary": loop.get_summary(),
    }


def _get_execution_order(plan: ExecutionPlan) -> list[int]:
    """Get execution order respecting dependencies.

    Args:
        plan: Execution plan

    Returns:
        List of step numbers in execution order
    """
    # Build dependency graph
    step_map = {s.step_id: s.step_number for s in plan.steps}
    dependencies = {s.step_number: s.dependencies for s in plan.steps}

    # Simple topological sort
    executed: set[int] = set()
    order: list[int] = []

    max_iterations = len(plan.steps) * 2
    iterations = 0

    while len(executed) < len(plan.steps) and iterations < max_iterations:
        iterations += 1
        for step in plan.steps:
            if step.step_number in executed:
                continue

            # Check if all dependencies are satisfied
            deps_satisfied = all(
                dep_id not in step_map or step_map[dep_id] in executed
                for dep_id in step.dependencies
            )

            if deps_satisfied:
                executed.add(step.step_number)
                order.append(step.step_number)

    return order
