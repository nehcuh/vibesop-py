"""StepRunner — execution bridge between VibeSOP plans and AI Agents.

Provides a coordinated execution API for multi-step ExecutionPlans:
- Iterator-based pending step discovery (respects DAG dependencies)
- Step-to-step context accumulation and injection
- State persistence via PlanTracker for resume support
- Configurable error recovery (skip / retry / abort)

All execution lanes (static serial/parallel batches, dynamic WorkflowEngine
plans, and squad-oriented patterns) normalize into one terminal vocabulary:
``StepOutcome`` per step and one shared ``PlanOutcome`` aggregation. The
legacy result dicts only gain keys (``blocked``, ``final_status``,
``review_status``); existing keys are preserved. Counter contract: ``failed``
counts every unsuccessful terminal step (blocked steps count in both
``failed`` and ``blocked``); ``final_status`` derives from real failures
(``failed - blocked``); ``review_status`` carries the review-acceptance axis.

Entry points:
    StepRunner(plan)           — start a new plan execution
    StepRunner.resume(plan_id) — resume a partially completed plan
    runner.execute_all(executor) — one-shot full plan execution
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan, ExecutionStep
    from vibesop.core.orchestration.workflow_engine import (
        DynamicExecutionResult,
        SquadExecutionResult,
    )

logger = logging.getLogger(__name__)


class StepOutcomeStatus(StrEnum):
    """Unified terminal status of a single step execution (B3).

    ``blocked`` means the step ran but its output is a blocked sentinel
    (``blocked: <缺什么>`` / ``{"status": "blocked"}``) — work needs human
    input or evidence, which is distinct from a real ``failed`` outcome.
    """

    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class StepOutcome:
    """Unified per-step terminal outcome emitted by every StepRunner lane."""

    step_id: str
    skill_id: str
    status: StepOutcomeStatus
    output: Any = None
    error: str | None = None


@dataclass
class PlanOutcome:
    """Shared terminal aggregation for a full plan execution.

    Every public lane (static, dynamic, squad) reports through this single
    structure; the legacy result dicts expose the same counters plus
    ``final_status`` so callers never see a per-lane vocabulary.

    Counter contract (Kimi B3 gate, F1): ``failed`` counts every
    unsuccessful terminal step — a blocked-sentinel step is persisted via
    ``mark_failed`` and therefore counts in BOTH ``failed`` and ``blocked``
    (blocked is an additional breakdown, not a subtraction). ``final_status``
    derives from ``real_failed = failed - blocked``.
    """

    plan_id: str
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    blocked: int = 0
    final_status: str = "completed"
    review_status: str = "not_required"
    steps: list[StepOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "completed": self.completed,
            "failed": self.failed,
            "skipped": self.skipped,
            "blocked": self.blocked,
            "final_status": self.final_status,
            "review_status": self.review_status,
        }


def _is_blocked_output(output: Any) -> bool:
    """True when an executor output is a *blocked* sentinel (vs a failed one).

    Mirrors the blocked branch of
    :func:`vibesop.core.orchestration.verification_loop.is_acceptance_failure`
    without counting ``failed`` sentinels as blocked.
    """
    if isinstance(output, dict):
        return str(output.get("status", "")).strip().lower() == "blocked"
    if output is None:
        return False
    text = str(output).strip().lower()
    return text == "blocked" or text.startswith("blocked:")


def _classify_output(output: Any) -> StepOutcomeStatus:
    """Map a raw executor output to the unified terminal vocabulary."""
    from vibesop.core.orchestration.verification_loop import is_acceptance_failure

    if not is_acceptance_failure(output):
        return StepOutcomeStatus.SUCCESS
    return StepOutcomeStatus.BLOCKED if _is_blocked_output(output) else StepOutcomeStatus.FAILED


def _derive_final_status(outcome: PlanOutcome) -> str:
    """Shared final_status rule for lanes without an engine verdict.

    ``failed`` already includes blocked steps (F1 contract), so the real-failure
    count is ``failed - blocked``:
    - no unsuccessful terminal step → ``completed``
    - real failures present → ``failed`` (or ``partial`` when some steps completed)
    - only blocked steps (no real failure) → ``blocked`` (or ``partial``)
    """
    real_failed = outcome.failed - outcome.blocked
    if outcome.failed == 0 and outcome.blocked == 0:
        return "completed"
    if real_failed > 0:
        return "partial" if outcome.completed > 0 else "failed"
    return "partial" if outcome.completed > 0 else "blocked"


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
        llm_client: Any = None,
        event_log: Any | None = None,
    ):
        self._plan = plan
        self._project_root = Path(project_root)
        self._max_parallel = max_parallel
        self._track_state = track_state
        self._llm_client = llm_client
        self._event_log = event_log

        self._states: dict[str, PlanStepState] = {}
        for step in plan.steps:
            already_completed = step.status.value in ("completed", "skipped")
            st = PlanStepState(
                step=step,
                completed=already_completed,
                output=step.result_summary or "",
            )
            self._states[step.step_id] = st

        if track_state and plan.metadata.get("execution_ready", False):
            # Blocked plans are refused at handoff (PlanExecutor gates) — do not
            # re-persist them here either, so the JSONL record never presents a
            # blocked plan as an actively-tracked executable.
            from vibesop.core.orchestration.plan_tracker import PlanTracker

            self._tracker = PlanTracker(storage_dir=self._project_root / ".vibe")
            self._tracker.create_plan(plan)
        else:
            if track_state and not plan.metadata.get("execution_ready", False):
                # Distinguish "blocked, intentionally untracked" from "never
                # annotated, wiring gap" (8.3.1-P1-3): both skip the tracker,
                # but a missing key means the plan never got a verdict at all.
                if "execution_ready" in plan.metadata:
                    logger.info(
                        "StepRunner: plan %s is blocked; state persistence skipped",
                        plan.plan_id,
                    )
                else:
                    logger.warning(
                        "StepRunner: plan %s has no execution_ready annotation; "
                        "state persistence disabled — inject the plan annotator "
                        "at plan build time so the verdict is truthful",
                        plan.plan_id,
                    )
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
        from vibesop.core.exceptions import PlanNotFoundError
        from vibesop.core.orchestration.plan_tracker import PlanTracker

        tracker = PlanTracker(storage_dir=Path(project_root) / ".vibe")
        plan = tracker.get_plan(plan_id)
        if plan is None:
            raise PlanNotFoundError(plan_id)

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
        step_executor: Callable[..., Any],
        on_step_complete: Callable[..., Any] | None = None,
        on_step_error: Callable[..., Any] | None = None,
        fail_fast: bool = False,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute all pending steps in topological order.

        Independent steps within each batch run via ParallelScheduler.
        For dynamic plans (LOOP_UNTIL_DRY, TOURNAMENT, PROMPT_CHAIN) and
        squad-oriented patterns (AGENT_SQUAD, DEBATE, RED_TEAM), delegates
        to WorkflowEngine — squad plans enter the engine's
        handoff/review/revision gates instead of a simplified parallel branch.

        Args:
            step_executor: Callable(ExecutionStep, StepRunContext) -> str (output)
            on_step_complete: Optional callback(ExecutionStep, output: str) called after each step
            on_step_error: Optional callback(ExecutionStep, error: Exception) called on failure.
                Return True to continue, False to abort.
            fail_fast: If True, abort on first failure. If False, skip failed steps and continue.
                Only a *real* failure (exception or failed/blocked sentinel) aborts:
                an all-success parallel batch never stops downstream steps (D06).
            context: Optional base context for squad-oriented plans (forwarded
                to the WorkflowEngine run).

        Returns:
            Dict with:
                - plan_id: str (anchor metadata; each per-step results entry
                  carries step_id — together they let a UI deep-link a step
                  output message to the plan step that produced it)
                - completed: int
                - failed: int — every unsuccessful terminal step, INCLUDING
                  blocked-sentinel steps (blocked is an additional breakdown:
                  failed ⊇ blocked, restored HEAD contract F1)
                - skipped: int
                - blocked: int (added by B3 — blocked-sentinel steps, also
                  counted in failed)
                - final_status: str (completed/partial/failed/blocked; derived
                  from real failures = failed − blocked; the dynamic lane
                  delivers the WorkflowEngine verdict)
                - review_status: str (added by B3 — review acceptance dimension;
                  "not_required" for static plans, accepted/rejected/error for
                  squad plans; ``all_succeeded``-style consumers must treat
                  execution success and review acceptance as separate axes)
                - results: list[dict] with step_id, output, error, status per
                  step (static/squad lanes; status keeps the legacy value
                  domain completed/failed/skipped — F2) plus the additive
                  ``outcome_status`` key carrying the shared StepOutcomeStatus
                  verdict (JSON-transportable producer fact for consumers of
                  the plain dict) — the dynamic lane preserves its legacy dict
                  shape keyed by step identity
                - dynamic: bool
                - pattern: str (squad/dynamic lanes)
        """

        # D08: engine.is_dynamic BEFORE any agent_squad_id check. Squad-oriented
        # patterns carry agent_squad_id on their steps, but they must enter the
        # WorkflowEngine (handoff/review/revision gates) — not a simplified
        # parallel string-matching branch that bypasses those gates.
        from vibesop.core.orchestration.workflow_engine import WorkflowEngine

        if WorkflowEngine.is_dynamic(self._plan):
            return self._execute_dynamic_plan(
                step_executor, on_step_complete, on_step_error, context
            )

        results: list[dict[str, Any]] = []
        outcomes: list[StepOutcome] = []
        # Steps whose output was a blocked sentinel are persisted via
        # mark_failed (StepStatus has no blocked member — RR06 debt), which
        # is exactly why they land in the failed counter; per F1 they count
        # in BOTH failed and blocked (blocked is an additional breakdown of
        # the failed count, never a subtraction).
        blocked_ids: set[str] = set()

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
                    status = _classify_output(output)

                    if status is StepOutcomeStatus.SUCCESS:
                        self.mark_completed(step, output)
                        if on_step_complete:
                            on_step_complete(step, output)
                        results.append(
                            {
                                "step_id": step.step_id,
                                "output": output,
                                "error": None,
                                "status": "completed",
                                "outcome_status": StepOutcomeStatus.SUCCESS.value,
                            }
                        )
                        outcomes.append(
                            StepOutcome(
                                step.step_id, step.skill_id, StepOutcomeStatus.SUCCESS, output
                            )
                        )
                        continue

                    error = str(output)
                    self.mark_failed(step, error)
                    if status is StepOutcomeStatus.BLOCKED:
                        blocked_ids.add(step.step_id)
                    # K-2 symmetry with the parallel batch path: acceptance
                    # failures (blocked/failed sentinels) do not fire
                    # on_step_error; only genuine exceptions do.
                    # F2: the per-step entry status keeps the legacy value
                    # domain (completed/failed) — blocked granularity is
                    # expressed by the blocked counter, the StepOutcome status
                    # and the additive ``outcome_status`` entry key (the
                    # producer's shared verdict, JSON-transportable), not by a
                    # new entry status value. The raw output is preserved on
                    # the entry (additive) so the dict sentinel shape stays
                    # recoverable on the adapter's dict-only fallback path.
                    results.append(
                        {
                            "step_id": step.step_id,
                            "output": output,
                            "error": error,
                            "status": "failed",
                            "outcome_status": status.value,
                        }
                    )
                    outcomes.append(
                        StepOutcome(
                            step.step_id,
                            step.skill_id,
                            status,
                            error=error,
                        )
                    )
                    if fail_fast:
                        break
                except Exception as e:
                    self.mark_failed(step, str(e))
                    should_continue = on_step_error(step, e) if on_step_error else not fail_fast
                    results.append(
                        {
                            "step_id": step.step_id,
                            "output": None,
                            "error": str(e),
                            "status": "failed",
                            "outcome_status": StepOutcomeStatus.FAILED.value,
                        }
                    )
                    outcomes.append(
                        StepOutcome(
                            step.step_id, step.skill_id, StepOutcomeStatus.FAILED, error=str(e)
                        )
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
                    old_loop = asyncio.get_running_loop()
                except RuntimeError:
                    old_loop = None

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
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
                finally:
                    asyncio.set_event_loop(old_loop)
                    loop.close()

                # D06: break only on a REAL failure in this batch (mirrors the
                # serial branch above). With fail_fast=True an all-success
                # batch must fall through so downstream dependent steps run.
                batch_failed = False
                should_continue = True
                for item in batch_results:
                    if isinstance(item, Exception):
                        # Should not happen with return_exceptions=True, but guard anyway
                        continue
                    step, step_result = item  # pyright: ignore[reportGeneralTypeIssues]
                    if isinstance(step_result, Exception):
                        batch_failed = True
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
                                "outcome_status": StepOutcomeStatus.FAILED.value,
                            }
                        )
                        outcomes.append(
                            StepOutcome(
                                step.step_id,
                                step.skill_id,
                                StepOutcomeStatus.FAILED,
                                error=str(step_result),
                            )
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
                        # 8.3.1 (A-2): run the acceptance-failure predicate on
                        # the RAW result first (dict shapes like
                        # {"status": "failed"} are unreachable once str()-ed);
                        # only then stringify for storage. Mirror the serial
                        # branch: no on_step_error callback (K-2 symmetry).
                        status = _classify_output(step_result)
                        if status is not StepOutcomeStatus.SUCCESS:
                            batch_failed = True
                            output = str(step_result)
                            self.mark_failed(step, output)
                            if status is StepOutcomeStatus.BLOCKED:
                                blocked_ids.add(step.step_id)
                            should_continue = not fail_fast
                            # F2: entry status keeps the legacy value domain
                            # (completed/failed) — blocked granularity lives in
                            # the blocked counter, the StepOutcome, the
                            # additive ``outcome_status`` entry key and the
                            # adapter. The raw output is preserved on the entry
                            # (additive) so the dict sentinel shape stays
                            # recoverable on the adapter's dict-only fallback path.
                            results.append(
                                {
                                    "step_id": step.step_id,
                                    "output": step_result,
                                    "error": output,
                                    "status": "failed",
                                    "outcome_status": status.value,
                                }
                            )
                            outcomes.append(
                                StepOutcome(step.step_id, step.skill_id, status, error=output)
                            )
                            if not should_continue or fail_fast:
                                for remaining_step in batch:
                                    if (
                                        remaining_step.step_id != step.step_id
                                        and not self._states[remaining_step.step_id].completed
                                        and not self._states[remaining_step.step_id].failed
                                    ):
                                        self.mark_skipped(
                                            remaining_step,
                                            "Batch aborted due to previous failure",
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
                                    "outcome_status": StepOutcomeStatus.SUCCESS.value,
                                }
                            )
                            outcomes.append(
                                StepOutcome(
                                    step.step_id, step.skill_id, StepOutcomeStatus.SUCCESS, output
                                )
                            )

                if batch_failed and (not should_continue or fail_fast):
                    break

        # F6 (restored HEAD resume contract): only steps that can NEVER run in
        # this plan — a (transitive) dependency failed or was itself skipped —
        # are marked skipped. Steps that were simply not dispatched yet (the
        # run aborted via fail_fast / on_step_error) stay PENDING so a later
        # pending_steps()/resume() pass can still execute them.
        def _unrunnable_due_to_dependency(step: ExecutionStep) -> bool:
            for dep_id in step.dependencies:
                dep_state = self._states.get(dep_id)
                if dep_state is None:
                    continue
                if dep_state.failed:
                    return True
                if dep_state.completed and dep_state.output.startswith("[SKIPPED]"):
                    return True
            return False

        changed = True
        while changed:
            changed = False
            for step in self._plan.steps:
                st = self._states[step.step_id]
                if st.completed or st.failed:
                    continue
                if _unrunnable_due_to_dependency(step):
                    self.mark_skipped(step, "dependency failed or was skipped")
                    changed = True

        skipped = sum(
            1
            for s in self._states.values()
            if s.completed and not s.failed and s.output.startswith("[SKIPPED]")
        )
        blocked = len(blocked_ids)
        # F1: failed counts every unsuccessful terminal step — blocked-sentinel
        # steps are persisted via mark_failed and count in BOTH failed and
        # blocked (restored HEAD contract).
        outcome = PlanOutcome(
            plan_id=self._plan.plan_id,
            completed=self.completed_count - skipped,
            failed=self.failed_count,
            skipped=skipped,
            blocked=blocked,
            review_status="not_required",
            steps=outcomes,
        )
        outcome.final_status = _derive_final_status(outcome)
        self._last_plan_outcome = outcome
        return {
            "plan_id": self._plan.plan_id,
            "completed": outcome.completed,
            "failed": outcome.failed,
            "skipped": outcome.skipped,
            "blocked": outcome.blocked,
            "final_status": outcome.final_status,
            "review_status": outcome.review_status,
            "results": results,
        }

    @property
    def last_plan_outcome(self) -> PlanOutcome | None:
        """Terminal aggregation of the most recent execute_all() run, if any.

        This is the shared :class:`PlanOutcome` face over whichever lane
        executed the plan; the legacy dict returned by execute_all carries
        the same counters (``blocked``, ``final_status`` included).
        """
        return getattr(self, "_last_plan_outcome", None)

    def _execute_dynamic_plan(
        self,
        step_executor: Callable[..., Any],
        on_step_complete: Callable[..., Any] | None,
        on_step_error: Callable[..., Any] | None,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Route dynamic plans (incl. squad patterns) through the WorkflowEngine.

        Squad-oriented plans delegate to ``WorkflowEngine.run_async`` via
        ``WorkflowEngine.run`` — the engine owns handoff/review/revision
        gates. There is deliberately no parallel dispatch branch here.
        """
        from vibesop.core.orchestration.workflow_engine import (
            DynamicExecutionResult,
            SquadExecutionResult,
            WorkflowEngine,
        )

        engine = WorkflowEngine(llm_client=self._llm_client, event_log=self._event_log)

        # The engine's squad paths call executor(step, context) with an
        # internal SquadStep; non-squad engine paths call executor(step) with
        # the plan's own ExecutionStep. The public contract is unchanged:
        # step_executor always receives the plan's ExecutionStep (so
        # step.skill_id / step.input_query / every other original field are
        # available verbatim). Squad steps are translated back to the real
        # plan step by step_id — never by skill guessing, and never by
        # passing the SquadStep itself.
        plan_steps_by_id = {s.step_id: s for s in self._plan.steps}

        def _wrap_executor(step: Any, *args: Any) -> Any:
            ctx = args[0] if args else self.get_context(step)
            plan_step = plan_steps_by_id.get(getattr(step, "step_id", None))
            return step_executor(plan_step if plan_step is not None else step, ctx)

        run_result = engine.run(self._plan, _wrap_executor, context=context)
        if isinstance(run_result, SquadExecutionResult):
            return self._squad_result_dict(run_result, on_step_complete, on_step_error)
        if not isinstance(run_result, DynamicExecutionResult):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"Expected DynamicExecutionResult, got {type(run_result).__name__}")
        return self._dynamic_result_dict(run_result)

    def _dynamic_result_dict(self, dyn_result: DynamicExecutionResult) -> dict[str, Any]:
        """Normalize a DynamicExecutionResult into the shared outcome (D07).

        The legacy ``results`` dict shape is preserved verbatim — keyed by
        step/plan identity, never converted to a list. The statistics are
        real counters derived from the recorded values, and ``final_status``
        is the WorkflowEngine verdict (previously hardcoded to failed=0 and
        never delivered).

        Post-corrective (P2): the bridge also syncs the runner's own state
        with the engine results. The engine's loop stamps a step COMPLETED
        before the sentinel classification happens and never touches the
        runner's ``_states``, so without this sync the public counters said
        failed/blocked while ``failed_count`` stayed 0, ``pending_steps()``
        still returned the failed step, and a sentinel-returning step kept
        StepStatus.COMPLETED. ``skipped`` counts only steps the engine
        explicitly skipped (StepStatus.SKIPPED, e.g. LOOP_UNTIL_DRY
        verification steps); steps left PENDING by an aborted run are still
        resumable and are NOT reported as skipped.
        """
        from vibesop.core.models import StepStatus
        from vibesop.core.orchestration.verification_loop import is_acceptance_failure

        results_map = dyn_result.results  # legacy dict shape — pass through unchanged
        values = list(results_map.values())
        # F1: failed counts every acceptance failure, INCLUDING blocked values
        # (blocked is an additional breakdown, restored HEAD contract).
        blocked = sum(1 for v in values if _is_blocked_output(v))
        failed = sum(1 for v in values if is_acceptance_failure(v))
        completed = len(values) - failed

        # Bring the runner state and the shared PlanOutcome.steps to the
        # engine's side: one StepOutcome per step the engine actually
        # recorded, and mark_failed/mark_completed so failed_count() /
        # pending_steps() / is_complete describe the run that happened.
        step_outcomes: list[StepOutcome] = []
        for step in self._plan.steps:
            if step.step_id not in results_map:
                continue
            value = results_map[step.step_id]
            status = _classify_output(value)
            if status is StepOutcomeStatus.SUCCESS:
                self.mark_completed(step, str(value) if value is not None else "")
                step_outcomes.append(StepOutcome(step.step_id, step.skill_id, status, value))
            else:
                error = str(value)
                self.mark_failed(step, error)
                step_outcomes.append(StepOutcome(step.step_id, step.skill_id, status, error=error))

        skipped = sum(1 for s in self._plan.steps if s.status is StepStatus.SKIPPED)

        outcome = PlanOutcome(
            plan_id=self._plan.plan_id,
            completed=completed,
            failed=failed,
            skipped=skipped,
            blocked=blocked,
            final_status=dyn_result.final_status,
            review_status="not_required",
            steps=step_outcomes,
        )
        self._last_plan_outcome = outcome
        return {
            "plan_id": self._plan.plan_id,
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "blocked": blocked,
            "final_status": dyn_result.final_status,
            "review_status": outcome.review_status,
            "results": results_map,
            "dynamic": True,
            "pattern": dyn_result.pattern.value,
        }

    def _squad_result_dict(
        self,
        squad_result: SquadExecutionResult,
        on_step_complete: Callable[..., Any] | None,
        on_step_error: Callable[..., Any] | None,
    ) -> dict[str, Any]:
        """Normalize a SquadExecutionResult into the shared outcome (D08).

        Blocked review verdicts (genuine hard rejects reported by the
        engine) surface as ``blocked`` — never as completed. Steps map by
        step_id: the PlanBuilder squad path uses the same step ids on the
        ExecutionPlan steps and the AgentSquad steps.
        """
        outputs: dict[str, Any] = squad_result.output or {}
        verdicts = squad_result.verdicts or []
        blocked_roles: set[str] = set(getattr(squad_result, "blocked_roles", None) or [])
        engine_blocked = bool(getattr(squad_result, "blocked", False))

        results: list[dict[str, Any]] = []
        step_outcomes: list[StepOutcome] = []
        completed = failed = skipped = blocked = 0

        for step in self._plan.steps:
            role = step.assigned_role or ""
            if step.step_id not in outputs:
                # Revision rounds re-run only a subset; a step without a
                # recorded output never executed.
                self.mark_skipped(step, "not executed by squad run")
                results.append(
                    {
                        "step_id": step.step_id,
                        "output": None,
                        "error": None,
                        "status": "skipped",
                        "outcome_status": StepOutcomeStatus.SKIPPED.value,
                    }
                )
                step_outcomes.append(
                    StepOutcome(step.step_id, step.skill_id, StepOutcomeStatus.SKIPPED)
                )
                skipped += 1
                continue

            output = outputs[step.step_id]
            status = _classify_output(output)
            if status is StepOutcomeStatus.SUCCESS and role in blocked_roles:
                # The review gate hard-rejected this role's work — the step
                # ran, but the plan is blocked on evidence/revision.
                status = StepOutcomeStatus.BLOCKED

            if status is StepOutcomeStatus.SUCCESS:
                text = str(output) if output is not None else ""
                self.mark_completed(step, text)
                if on_step_complete:
                    on_step_complete(step, text)
                results.append(
                    {
                        "step_id": step.step_id,
                        "output": output,
                        "error": None,
                        "status": "completed",
                        "outcome_status": StepOutcomeStatus.SUCCESS.value,
                    }
                )
                step_outcomes.append(
                    StepOutcome(step.step_id, step.skill_id, StepOutcomeStatus.SUCCESS, output)
                )
                completed += 1
            else:
                error = str(output)
                if status is StepOutcomeStatus.BLOCKED and role in blocked_roles:
                    issues = [
                        str(v.revision_feedback or ", ".join(v.issues) or "review blocked")
                        for v in verdicts
                        if not v.passed and not v.requires_revision and v.target_role == role
                    ]
                    error = (
                        issues[-1] if issues else "blocked: review gate rejected this role's work"
                    )
                # StepStatus has no blocked member (RR06 terminal-vocabulary
                # debt) — persist as failed with the blocked reason.
                self.mark_failed(step, error)
                if status is StepOutcomeStatus.FAILED and on_step_error:
                    on_step_error(step, RuntimeError(error))
                # F2: entry status keeps the legacy value domain
                # (completed/failed/skipped); blocked granularity is carried by
                # the blocked counter, the StepOutcome status, the additive
                # ``outcome_status`` entry key and the adapter.
                results.append(
                    {
                        "step_id": step.step_id,
                        "output": None,
                        "error": error,
                        "status": "failed",
                        "outcome_status": status.value,
                    }
                )
                step_outcomes.append(StepOutcome(step.step_id, step.skill_id, status, error=error))
                if status is StepOutcomeStatus.BLOCKED:
                    # F1: blocked steps count in BOTH failed and blocked.
                    blocked += 1
                    failed += 1
                else:
                    failed += 1

        if engine_blocked:
            final_status = "blocked"
        elif failed - blocked > 0:
            final_status = "partial" if completed > 0 else "failed"
        elif any(not v.passed and v.requires_revision for v in verdicts):
            final_status = "partial"
        else:
            final_status = "completed"

        review_status = str(getattr(squad_result, "review_status", None) or "accepted")
        outcome = PlanOutcome(
            plan_id=self._plan.plan_id,
            completed=completed,
            failed=failed,
            skipped=skipped,
            blocked=blocked,
            final_status=final_status,
            review_status=review_status,
            steps=step_outcomes,
        )
        self._last_plan_outcome = outcome
        return {
            "plan_id": self._plan.plan_id,
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "blocked": blocked,
            "final_status": final_status,
            "review_status": review_status,
            "results": results,
            "dynamic": True,
            "pattern": self._plan.workflow_pattern.value,
            "verdicts": [v.model_dump() if hasattr(v, "model_dump") else v for v in verdicts],
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
                status=status,  # pyright: ignore[reportArgumentType]
                result_summary=step.result_summary,
            )
        except (OSError, ValueError, RuntimeError) as e:
            logger.warning("Failed to persist step state: %s", e)
