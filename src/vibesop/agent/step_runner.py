"""StepRunner — execution bridge between VibeSOP plans and AI Agents.

Provides a coordinated execution API for multi-step ExecutionPlans:
- Iterator-based pending step discovery (respects DAG dependencies)
- Step-to-step context accumulation and injection
- State persistence via PlanTracker for resume support
- Configurable error recovery (skip / retry / abort)

Entry points:
    StepRunner(plan)           — start a new plan execution
    StepRunner.resume(plan_id) — resume a partially completed plan
    runner.execute_all(executor) — one-shot full plan execution
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan, ExecutionStep

logger = logging.getLogger(__name__)


@dataclass
class PlanStepState:
    """Runtime state for a single plan step during execution."""

    step: ExecutionStep
    completed: bool = False
    failed: bool = False
    output: str = ""
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class StepRunContext:
    """Context passed to a skill when executing a plan step.

    Accumulates outputs from dependency steps so each step can
    reference upstream results (e.g. "based on the architecture
    analysis above, review the code quality...").
    """

    step: ExecutionStep
    dependency_outputs: dict[str, str] = field(default_factory=dict)

    def format_for_prompt(self) -> str:
        """Render upstream outputs as a Markdown block for the step's prompt."""
        if not self.dependency_outputs:
            return ""
        parts = ["\n\n## Previous Step Results\n"]
        for _step_id, output in self.dependency_outputs.items():
            parts.append("### Result from previous step:")
            parts.append(output)
            parts.append("")
        return "\n".join(parts)


class StepRunner:
    """Execution coordinator for multi-step VibeSOP plans.

    Manages step lifecycle (pending → in_progress → completed/failed),
    dependency resolution, context injection, and state persistence.

    Supports three execution modes:
    1. Iterator-based (agent controls each step):
        >>> runner = StepRunner(plan)
        >>> for step in runner.pending_steps():
        ...     ctx = runner.get_context(step)
        ...     result = agent.execute(step.skill_id, step.input_query, ctx)
        ...     runner.mark_completed(step, result)

    2. One-shot (runner drives execution with injected executor):
        >>> runner = StepRunner(plan)
        >>> results = runner.execute_all(my_executor)

    3. Resume (pick up a partially completed plan):
        >>> runner = StepRunner.resume(plan_id, project_root=".")
        >>> for step in runner.pending_steps():
        ...     ...
    """

    def __init__(
        self,
        plan: ExecutionPlan,
        project_root: str | Path = ".",
        max_parallel: int = 5,
        track_state: bool = True,
    ):
        self._plan = plan
        self._project_root = Path(project_root)
        self._max_parallel = max_parallel
        self._track_state = track_state

        self._states: dict[str, PlanStepState] = {}
        for step in plan.steps:
            already_completed = step.status.value in ("completed", "skipped")
            st = PlanStepState(
                step=step,
                completed=already_completed,
                output=step.result_summary or "",
            )
            self._states[step.step_id] = st

        if track_state:
            from vibesop.core.orchestration.plan_tracker import PlanTracker

            self._tracker = PlanTracker(storage_dir=self._project_root / ".vibe")
            self._tracker.create_plan(plan)
        else:
            self._tracker = None

    @classmethod
    def resume(
        cls,
        plan_id: str,
        project_root: str | Path = ".",
    ) -> StepRunner:
        """Resume a partially completed plan from persistent state.

        Args:
            plan_id: The plan ID to resume.
            project_root: Project root for locating persisted state.

        Returns:
            A StepRunner initialized with the plan's current state.

        Raises:
            ValueError: If the plan is not found.
        """
        from vibesop.core.orchestration.plan_tracker import PlanTracker

        tracker = PlanTracker(storage_dir=Path(project_root) / ".vibe")
        plan = tracker.get_plan(plan_id)
        if plan is None:
            raise ValueError(f"Plan {plan_id!r} not found in persisted state")

        runner = cls(plan, project_root=project_root)
        return runner

    @property
    def plan(self) -> ExecutionPlan:
        return self._plan

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self._states.values() if s.completed)

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self._states.values() if s.failed)

    @property
    def total_steps(self) -> int:
        return len(self._plan.steps)

    @property
    def is_complete(self) -> bool:
        return self.completed_count + self.failed_count == self.total_steps

    def pending_steps(self) -> list[ExecutionStep]:
        """Return steps that are ready to execute.

        A step is "ready" when:
        - It is not already completed or failed.
        - All its dependency steps have completed successfully.

        Steps are returned in plan order (step_number ascending).
        """
        ready: list[ExecutionStep] = []
        for step in self._plan.steps:
            st = self._states[step.step_id]
            if st.completed or st.failed:
                continue
            if self._dependencies_satisfied(step):
                ready.append(step)
        return ready

    def start_step(self, step: ExecutionStep) -> None:
        """Mark a step as in-progress (for status visibility)."""
        from vibesop.core.models import StepStatus

        st = self._states[step.step_id]
        st.started_at = datetime.now(UTC).isoformat()
        step.status = StepStatus.IN_PROGRESS
        self._persist_step(step)
        logger.info("Starting step %s (%s): %s", step.step_number, step.step_id, step.skill_id)

    def mark_completed(self, step: ExecutionStep, output: str = "") -> None:
        """Mark a step as successfully completed.

        Args:
            step: The completed step.
            output: The step's output (injected into downstream steps).
        """
        from vibesop.core.models import StepStatus

        st = self._states[step.step_id]
        st.completed = True
        st.output = output
        st.completed_at = datetime.now(UTC).isoformat()
        step.status = StepStatus.COMPLETED
        step.result_summary = output[:200] if output else ""
        self._persist_step(step)

    def mark_failed(self, step: ExecutionStep, error: str) -> None:
        """Mark a step as failed.

        Args:
            step: The failed step.
            error: Error description.
        """
        from vibesop.core.models import StepStatus

        st = self._states[step.step_id]
        st.failed = True
        st.error = error
        st.completed_at = datetime.now(UTC).isoformat()
        step.status = StepStatus.FAILED
        step.result_summary = f"Error: {error[:200]}"
        self._persist_step(step)

    def mark_skipped(self, step: ExecutionStep, reason: str = "") -> None:
        """Mark a step as skipped (not executed, not a failure).

        Args:
            step: The skipped step.
            reason: Why it was skipped.
        """
        from vibesop.core.models import StepStatus

        st = self._states[step.step_id]
        st.completed = True
        st.output = f"[SKIPPED] {reason}" if reason else "[SKIPPED]"
        st.completed_at = datetime.now(UTC).isoformat()
        step.status = StepStatus.SKIPPED
        step.result_summary = reason[:200] if reason else ""
        self._persist_step(step)

    def get_context(self, step: ExecutionStep) -> StepRunContext:
        """Build execution context with dependency step outputs.

        Returns a StepRunContext containing the outputs of all
        completed upstream steps, ready for injection into the
        skill's prompt.
        """
        dep_outputs: dict[str, str] = {}
        for dep_id in step.dependencies:
            dep_state = self._states.get(dep_id)
            if dep_state and dep_state.completed and not dep_state.failed:
                dep_outputs[dep_id] = dep_state.output
        return StepRunContext(step=step, dependency_outputs=dep_outputs)

    def execute_all(
        self,
        step_executor: callable,
        on_step_complete: callable | None = None,
        on_step_error: callable | None = None,
        fail_fast: bool = False,
    ) -> dict[str, Any]:
        """Execute all pending steps in topological order.

        Independent steps within each batch run via ParallelScheduler.

        Args:
            step_executor: Callable(ExecutionStep, StepRunContext) -> str (output)
            on_step_complete: Optional callback(ExecutionStep, output: str) called after each step
            on_step_error: Optional callback(ExecutionStep, error: Exception) called on failure.
                Return True to continue, False to abort.
            fail_fast: If True, abort on first failure. If False, skip failed steps and continue.

        Returns:
            Dict with:
                - completed: int
                - failed: int
                - skipped: int
                - results: list[dict] with step_id, output, error per step
        """

        results: list[dict[str, Any]] = []

        while True:
            batch = self.pending_steps()
            if not batch:
                break

            if len(batch) == 1:
                step = batch[0]
                self.start_step(step)
                ctx = self.get_context(step)
                try:
                    output = step_executor(step, ctx)
                    self.mark_completed(step, output)
                    if on_step_complete:
                        on_step_complete(step, output)
                    results.append(
                        {
                            "step_id": step.step_id,
                            "output": output,
                            "error": None,
                            "status": "completed",
                        }
                    )
                except Exception as e:
                    self.mark_failed(step, str(e))
                    should_continue = on_step_error(step, e) if on_step_error else not fail_fast
                    results.append(
                        {
                            "step_id": step.step_id,
                            "output": None,
                            "error": str(e),
                            "status": "failed",
                        }
                    )
                    if not should_continue or fail_fast:
                        break
            else:
                # Parallel batch: execute all pending steps concurrently
                import asyncio

                async def exec_step(s: ExecutionStep) -> tuple[ExecutionStep, str | Exception]:
                    self.start_step(s)
                    ctx = self.get_context(s)
                    try:
                        result = step_executor(s, ctx)
                        return (s, result)
                    except Exception as e:
                        return (s, e)

                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # Use semaphore to limit concurrency
                semaphore = asyncio.Semaphore(self._max_parallel)

                async def limited_exec(
                    s: ExecutionStep, _sem: asyncio.Semaphore = semaphore
                ) -> tuple[ExecutionStep, str | Exception]:
                    async with _sem:
                        return await exec_step(s)

                batch_results = loop.run_until_complete(
                    asyncio.gather(*(limited_exec(s) for s in batch), return_exceptions=True)
                )

                should_continue = True
                for step, step_result in batch_results:
                    if isinstance(step_result, Exception):
                        self.mark_failed(step, str(step_result))
                        if on_step_error:
                            should_continue = on_step_error(step, step_result)
                        else:
                            should_continue = not fail_fast
                        results.append(
                            {
                                "step_id": step.step_id,
                                "output": None,
                                "error": str(step_result),
                                "status": "failed",
                            }
                        )
                        if not should_continue or fail_fast:
                            # Stop processing remaining steps in this batch and break outer loop
                            for remaining_step in batch:
                                if (
                                    remaining_step.step_id != step.step_id
                                    and not self._states[remaining_step.step_id].completed
                                    and not self._states[remaining_step.step_id].failed
                                ):
                                    self.mark_skipped(
                                        remaining_step, "Batch aborted due to previous failure"
                                    )
                            break
                    else:
                        output = str(step_result) if step_result else ""
                        self.mark_completed(step, output)
                        if on_step_complete:
                            on_step_complete(step, output)
                        results.append(
                            {
                                "step_id": step.step_id,
                                "output": output,
                                "error": None,
                                "status": "completed",
                            }
                        )

                if not should_continue or fail_fast:
                    break

        skipped = sum(
            1
            for s in self._states.values()
            if s.completed and not s.failed and s.output.startswith("[SKIPPED]")
        )
        return {
            "completed": self.completed_count - skipped,
            "failed": self.failed_count,
            "skipped": skipped,
            "results": results,
        }

    def _dependencies_satisfied(self, step: ExecutionStep) -> bool:
        for dep_id in step.dependencies:
            dep_state = self._states.get(dep_id)
            if dep_state is None:
                return False
            if not dep_state.completed or dep_state.failed:
                return False
        return True

    def _persist_step(self, step: ExecutionStep) -> None:
        if not self._track_state or self._tracker is None:
            return
        try:
            status = step.status.value if hasattr(step.status, "value") else str(step.status)
            self._tracker.update_step_status(
                plan_id=self._plan.plan_id,
                step_id=step.step_id,
                status=status,
                result_summary=step.result_summary,
            )
        except (OSError, ValueError, RuntimeError) as e:
            logger.warning("Failed to persist step state: %s", e)
