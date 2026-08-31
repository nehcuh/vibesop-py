"""Observer-to-agent control-plane command contract.

Implements failure-intervention commands (retry/skip) that an observer UI
issues against a running plan. Skip has strict dependency semantics: a step
with downstream dependents cannot be skipped alone — the caller either gets
``rejected_dependency_blocked`` or opts into a cascading skip of the full
transitive closure.

Scope: the handler validates commands, mutates the in-place ExecutionPlan
(the same object WorkflowEngine mutates), and emits events through the
shared PlanEventLog. It does NOT re-schedule execution — the engine runs
synchronously, so when an accepted command takes effect is the integrator's
decision. The integrator reports completion via :meth:`complete_command`
once the affected step reaches a terminal state again, which releases the
in-flight slot so further commands on that step are accepted.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from vibesop.core.models import (
    DynamicNodeStatus,
    ExecutionPlan,
    ExecutionStep,
    StepStatus,
)
from vibesop.core.orchestration.events import (
    PlanEvent,
    PlanEventLog,
    PlanEventType,
    step_transition_payload,
)

logger = logging.getLogger(__name__)


class PlanCommandType(StrEnum):
    """Control-plane commands the panel may issue."""

    RETRY_STEP = "retry_step"  # Re-execute a failed step (loop_back semantics)
    SKIP_STEP = "skip_step"  # Mark a failed/pending step as skipped


class PlanCommand(BaseModel):
    """A single control-plane command issued by the panel.

    ``command_id`` is a caller-generated UUID and is the idempotency key:
    re-issued commands with the same id are rejected as duplicates without
    side effects.
    """

    command_id: str = Field(..., description="Caller-generated UUID (idempotency key)")
    plan_id: str = Field(..., description="Target plan")
    type: PlanCommandType = Field(..., description="Command type")
    step_id: str = Field(..., description="Target step")
    issued_at: str = Field(..., description="ISO8601 UTC timestamp from the caller")
    cascade: bool = Field(
        default=False,
        description="SKIP_STEP only: also skip all transitive downstream dependents",
    )


class PlanCommandStatus(StrEnum):
    """Outcome of applying a command."""

    ACCEPTED = "accepted"
    REJECTED_DUPLICATE = "rejected_duplicate"
    REJECTED_INVALID_STATE = "rejected_invalid_state"
    REJECTED_DEPENDENCY_BLOCKED = "rejected_dependency_blocked"


class PlanCommandResult(BaseModel):
    """Result of applying a command, including any events emitted."""

    command_id: str = Field(..., description="Echo of the command's idempotency key")
    status: PlanCommandStatus = Field(..., description="Acceptance outcome")
    reason: str | None = Field(default=None, description="Human-readable rejection reason")
    events: list[PlanEvent] = Field(
        default_factory=list,
        description="Events emitted while applying the command (empty on rejection)",
    )


class _PlanCommandState:
    """Per-plan command bookkeeping (internal)."""

    __slots__ = ("in_flight", "processed")

    def __init__(self) -> None:
        self.processed: set[str] = set()  # command_ids already applied or rejected
        self.in_flight: dict[str, str] = {}  # step_id -> command_id (accepted, not completed)


class PlanCommandHandler:
    """Validates and applies panel control-plane commands.

    The handler mutates the same ExecutionPlan object the engine holds and
    emits through the shared PlanEventLog, so panel subscribers observe
    command-driven transitions with the same seq ordering as engine-driven
    ones.

    Thread-safety: the handler's own bookkeeping is lock-guarded, so
    concurrent *handler* calls are safe. It is NOT safe against a
    concurrently running engine mutating the same plan — the integrator
    must serialize command application against engine execution (e.g.
    apply commands only between engine runs/steps).
    """

    def __init__(
        self,
        event_log: PlanEventLog,
        plan_provider: Callable[[str], ExecutionPlan | None],
    ) -> None:
        """Initialize the handler.

        Args:
            event_log: Shared plan event log (seq/subscription authority).
            plan_provider: Callable returning the live ExecutionPlan for a
                plan_id, or None when the plan is unknown.
        """
        self._events = event_log
        self._plan_provider = plan_provider
        self._plans: dict[str, _PlanCommandState] = {}
        self._command_plan: dict[str, str] = {}  # command_id -> plan_id (in-flight index)
        self._lock = threading.Lock()

    def apply(self, command: PlanCommand) -> PlanCommandResult:
        """Validate and apply a command.

        Rejection order: duplicate command_id → in-flight command on the same
        step → state validity → dependency check (skip only). Rejections
        produce no side effects and emit no events.

        The plan being terminal is NOT a rejection: the engine runs
        synchronously, so failure intervention (retry a failed step, skip a
        failed/pending step) is by nature a post-run action. Step-state
        gates are the validity authority.

        Only accepted commands consume the idempotency key: a rejected
        command may be re-issued with the same ``command_id`` once the
        blocking condition clears, while a duplicate of an accepted command
        is always ``rejected_duplicate``.
        """
        pending: list[tuple[PlanEventType, dict[str, Any]]] = []
        with self._lock:
            state = self._plans.setdefault(command.plan_id, _PlanCommandState())

            if command.command_id in state.processed:
                return PlanCommandResult(
                    command_id=command.command_id,
                    status=PlanCommandStatus.REJECTED_DUPLICATE,
                    reason="Command already processed (idempotency key reused)",
                )

            if command.step_id in state.in_flight:
                pending_id = state.in_flight[command.step_id]
                return PlanCommandResult(
                    command_id=command.command_id,
                    status=PlanCommandStatus.REJECTED_INVALID_STATE,
                    reason=(
                        f"Step {command.step_id} already has an in-flight command "
                        f"({pending_id}); wait for it to complete"
                    ),
                )

            plan = self._plan_provider(command.plan_id)
            if plan is None:
                return PlanCommandResult(
                    command_id=command.command_id,
                    status=PlanCommandStatus.REJECTED_INVALID_STATE,
                    reason=f"Plan {command.plan_id} not found",
                )
            # Keep the event log's snapshot reference current — commands may
            # arrive for plans the engine never registered (e.g. static plans).
            self._events.update_plan(plan)
            step = next((s for s in plan.steps if s.step_id == command.step_id), None)
            if step is None:
                return PlanCommandResult(
                    command_id=command.command_id,
                    status=PlanCommandStatus.REJECTED_INVALID_STATE,
                    reason=f"Step {command.step_id} not found in plan {command.plan_id}",
                )

            if command.type is PlanCommandType.RETRY_STEP:
                result = self._apply_retry(command, step, pending)
            else:
                result = self._apply_skip(command, plan, step, pending)

            if result.status is PlanCommandStatus.ACCEPTED:
                state.processed.add(command.command_id)
                state.in_flight[command.step_id] = command.command_id
                self._command_plan[command.command_id] = command.plan_id

        # Emit outside the handler lock: PlanEventLog.append invokes
        # subscribers synchronously, and a subscriber that re-enters
        # apply()/complete_command() must not deadlock on the lock we
        # would still be holding.
        if result.status is PlanCommandStatus.ACCEPTED:
            result.events = [
                self._events.append(command.plan_id, event_type, payload)
                for event_type, payload in pending
            ]
        return result

    def complete_command(self, command_id: str) -> bool:
        """Mark an accepted command as completed, releasing its in-flight slot.

        Called by the integrator once the affected step has reached a
        terminal state again (e.g. the retried step completed or failed).

        Returns:
            True when the command was in flight and is now completed;
            False for unknown or already-completed command ids.
        """
        with self._lock:
            plan_id = self._command_plan.pop(command_id, None)
            if plan_id is None:
                return False
            state = self._plans.get(plan_id)
            if state is None:
                return False
            for step_id, inflight_id in list(state.in_flight.items()):
                if inflight_id == command_id:
                    del state.in_flight[step_id]
            return True

    def drop_plan(self, plan_id: str) -> None:
        """Drop all command bookkeeping for a plan.

        Clears processed idempotency keys, in-flight entries, and the
        command_id index for the plan. Integrators should call this together
        with ``PlanEventLog.drop_plan`` once a plan is terminal. Unknown
        plan_ids are silently ignored.
        """
        with self._lock:
            state = self._plans.pop(plan_id, None)
            if state is None:
                return
            for command_id in list(self._command_plan):
                if self._command_plan[command_id] == plan_id:
                    del self._command_plan[command_id]

    def _apply_retry(
        self,
        command: PlanCommand,
        step: ExecutionStep,
        pending: list[tuple[PlanEventType, dict[str, Any]]],
    ) -> PlanCommandResult:
        """Apply RETRY_STEP: rewind a failed step (loop_back semantics).

        Mirrors workflow_engine's LOOP_BACK rewind — back to pending with
        DynamicNodeStatus.LOOPING and a bumped loop_iteration — with one
        deliberate difference: the engine's loop_back keeps the previous
        attempt's artifacts, while a user-commanded retry also clears the
        stale result_summary/started_at/completed_at so no failed-attempt
        residue leaks into the next attempt's context.
        ``cascade`` is meaningless for retry and ignored.
        """
        if step.status is not StepStatus.FAILED:
            return PlanCommandResult(
                command_id=command.command_id,
                status=PlanCommandStatus.REJECTED_INVALID_STATE,
                reason=(
                    f"retry_step requires a failed step; step {step.step_id} is {step.status.value}"
                ),
            )

        step.status = StepStatus.PENDING
        step.dynamic_status = DynamicNodeStatus.LOOPING
        step.loop_iteration += 1
        step.result_summary = None
        step.started_at = None
        step.completed_at = None

        pending.append(
            (
                PlanEventType.PLAN_MUTATED,
                {
                    "decision": "loop_back",
                    "loop_back_step_id": step.step_id,
                    "source": "user_command",
                    "command_id": command.command_id,
                },
            )
        )
        pending.append((PlanEventType.STEP_TRANSITION, step_transition_payload(step)))
        return PlanCommandResult(
            command_id=command.command_id,
            status=PlanCommandStatus.ACCEPTED,
        )

    def _apply_skip(
        self,
        command: PlanCommand,
        plan: ExecutionPlan,
        step: ExecutionStep,
        pending: list[tuple[PlanEventType, dict[str, Any]]],
    ) -> PlanCommandResult:
        """Apply SKIP_STEP with the review-mandated dependency semantics.

        No downstream dependents: skip the step directly. Dependents exist
        and ``cascade=False``: reject with the blocking step ids. Dependents
        and ``cascade=True``: skip the step plus the transitive closure of
        downstream dependents — but only dependents still in a mutable state
        (pending/failed). Dependents that already reached a terminal state
        (completed/skipped) or are in progress are left untouched and listed
        under ``excluded_terminal`` in the plan_mutated payload, so a cascade
        can never rewrite history (e.g. flip a completed step to skipped).
        """
        if step.status not in (StepStatus.FAILED, StepStatus.PENDING):
            return PlanCommandResult(
                command_id=command.command_id,
                status=PlanCommandStatus.REJECTED_INVALID_STATE,
                reason=(
                    f"skip_step requires a failed or pending step; "
                    f"step {step.step_id} is {step.status.value}"
                ),
            )

        downstream_ids = [s.step_id for s in plan.steps if step.step_id in s.dependencies]
        if downstream_ids and not command.cascade:
            return PlanCommandResult(
                command_id=command.command_id,
                status=PlanCommandStatus.REJECTED_DEPENDENCY_BLOCKED,
                reason=(
                    f"Step {step.step_id} has downstream dependents "
                    f"{downstream_ids}; re-issue with cascade=true to skip them too"
                ),
            )

        closure = [step]
        if downstream_ids:
            closure = self._skip_closure(plan, step.step_id)

        targets = [s for s in closure if s.status in (StepStatus.PENDING, StepStatus.FAILED)]
        excluded = [s.step_id for s in closure if s not in targets]

        for target in targets:
            target.status = StepStatus.SKIPPED
            pending.append((PlanEventType.STEP_TRANSITION, step_transition_payload(target)))

        # ReorchestrationDecision has no skip semantics and must not change;
        # the mutation is expressed via user_action with decision=null.
        mutation_payload: dict[str, Any] = {
            "decision": None,
            "user_action": "skip",
            "step_ids": [s.step_id for s in targets],
            "cascade": command.cascade,
            "source": "user_command",
            "command_id": command.command_id,
        }
        if excluded:
            mutation_payload["excluded_terminal"] = excluded
        pending.append((PlanEventType.PLAN_MUTATED, mutation_payload))
        return PlanCommandResult(
            command_id=command.command_id,
            status=PlanCommandStatus.ACCEPTED,
        )

    @staticmethod
    def _skip_closure(plan: ExecutionPlan, root_step_id: str) -> list[ExecutionStep]:
        """Return the root step plus all transitive downstream dependents.

        Breadth-first over the reverse dependency edges, in plan order.
        Cycles cannot loop forever: each step is visited at most once.
        """
        by_id = {s.step_id: s for s in plan.steps}
        ordered: list[ExecutionStep] = []
        seen = {root_step_id}
        frontier = [root_step_id]
        while frontier:
            current = frontier.pop(0)
            ordered.append(by_id[current])
            for candidate in plan.steps:
                if candidate.step_id not in seen and current in candidate.dependencies:
                    seen.add(candidate.step_id)
                    frontier.append(candidate.step_id)
        return ordered
