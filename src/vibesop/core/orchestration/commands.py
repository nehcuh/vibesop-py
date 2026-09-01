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
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

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

    @field_validator("issued_at")
    @classmethod
    def _issued_at_must_be_iso8601(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(f"issued_at must be an ISO8601 timestamp, got {value!r}") from e
        return value


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
        self.processed: set[str] = set()  # accepted command_ids (idempotency keys)
        self.in_flight: dict[str, str] = {}  # step_id -> command_id (accepted, not completed)


class PlanCommandHandler:
    """Validates and applies panel control-plane commands.

    The handler mutates the same ExecutionPlan object the engine holds and
    emits through the shared PlanEventLog, so panel subscribers observe
    command-driven transitions with the same seq ordering as engine-driven
    ones. A command's plan mutation and its event emission are atomic with
    respect to other commands: events are appended while the handler lock
    is still held, so the log's seq order equals the mutation order and a
    superseded payload can never land after the event that superseded it
    (C1, 20260831 adversarial review).

    Thread-safety: the handler's own bookkeeping is lock-guarded, so
    concurrent *handler* calls are safe. The lock is an RLock: a subscriber
    that synchronously re-enters apply()/complete_command() from its
    callback runs on the emitting thread and re-enters without deadlocking
    (FC3). One re-entry restriction applies: while a command's events are
    being emitted, a nested apply() for the SAME plan is rejected
    (rejected_invalid_state, retryable — no side effects, idempotency key
    not consumed). Payloads are materialized before the emission loop, so
    a nested command mutating the plan mid-emission would let the outer
    command's stale payloads land after the nested command's newer events,
    silently breaking the seq-order-equals-mutation-order invariant above;
    the guard closes that interleave. Issue the follow-up command after
    the callback returns instead. Nested commands for OTHER plans are
    unaffected. For the same reason, re-entering complete_command() or
    drop_plan() for the emitting plan mid-emission raises RuntimeError
    (completing would release the in-flight slot before the command's
    effects settle; dropping would erase the idempotency keys of the batch
    being emitted). Use ONE handler per plan: two handlers sharing a log
    hold independent locks, so the mutation-emission atomicity above does
    not hold across handlers. Subscriber contract: callbacks must be fast
    and non-blocking, and must not wait on handler operations from another
    thread — cross-thread rendezvous during emission deadlocks. The lock
    is shared across all plans, so a slow subscriber delays command
    application for every plan (engine execution is unaffected — it never
    takes this lock). It is NOT safe against a concurrently running engine
    mutating the same plan — the integrator must serialize command
    application against engine execution (e.g. apply commands only between
    engine runs/steps).
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
        # RLock so a re-entrant subscriber (FC3) can re-enter
        # apply()/complete_command() from its callback on the emitting
        # thread without deadlocking.
        self._lock = threading.RLock()
        # Plan ids whose command events are currently being emitted on this
        # thread. A nested apply() for one of these plans is rejected (see
        # the class docstring): payloads are materialized before emission,
        # so a mid-emission mutation would let stale outer payloads land
        # after the nested command's newer events (C1 follow-up).
        self._emitting: set[str] = set()

    def apply(self, command: PlanCommand) -> PlanCommandResult:
        """Validate and apply a command.

        Rejection order: duplicate command_id → in-flight command_id on
        another plan → in-flight command on the same step → mid-emission
        re-entry on the same plan → state validity → dependency check
        (skip only). Rejections produce no *command-bookkeeping* side
        effects and emit no events (a known plan is still registered with
        the event log for snapshots).

        The plan being terminal is NOT a rejection: the engine runs
        synchronously, so failure intervention (retry a failed step, skip a
        failed/pending step) is by nature a post-run action. Step-state
        gates are the validity authority.

        Only accepted commands consume the idempotency key: a rejected
        command may be re-issued with the same ``command_id`` once the
        blocking condition clears, while a duplicate of an accepted command
        is always ``rejected_duplicate``.

        If event emission itself fails mid-flush, the bookkeeping is rolled
        back (the idempotency key is NOT wedged — the command can be
        re-issued once the emitter recovers), while the plan mutation stays
        applied and events already appended are not retracted — a replayed
        view may lag the plan by the un-emitted transitions until the next
        event or a snapshot resync.
        """
        pending: list[tuple[PlanEventType, dict[str, Any]]] = []
        with self._lock:
            # Look up, don't create: a rejected command must leave no
            # bookkeeping behind ("rejections produce no side effects").
            state = self._plans.get(command.plan_id)

            if state is not None and command.command_id in state.processed:
                return PlanCommandResult(
                    command_id=command.command_id,
                    status=PlanCommandStatus.REJECTED_DUPLICATE,
                    reason="Command already processed (idempotency key reused)",
                )

            owner_plan = self._command_plan.get(command.command_id)
            if owner_plan is not None and owner_plan != command.plan_id:
                # The in-flight index is global: re-using an in-flight
                # command_id on another plan would overwrite the index entry
                # and wedge the first plan's in-flight slot forever
                # (complete_command would only ever release the second one).
                # Retryable once the first command completes.
                return PlanCommandResult(
                    command_id=command.command_id,
                    status=PlanCommandStatus.REJECTED_INVALID_STATE,
                    reason=(
                        f"Command {command.command_id} is in flight on plan "
                        f"{owner_plan}; command ids must be unique across plans "
                        "while in flight"
                    ),
                )

            if state is not None and command.step_id in state.in_flight:
                pending_id = state.in_flight[command.step_id]
                return PlanCommandResult(
                    command_id=command.command_id,
                    status=PlanCommandStatus.REJECTED_INVALID_STATE,
                    reason=(
                        f"Step {command.step_id} already has an in-flight command "
                        f"({pending_id}); wait for it to complete"
                    ),
                )

            if command.plan_id in self._emitting:
                # A subscriber callback is re-entering apply() for the plan
                # whose events are being emitted on this thread. Applying it
                # now would interleave its mutation+events between this
                # command's pre-materialized payload appends, so a stale
                # outer payload could land after the nested command's newer
                # events (C1). Reject retryably: re-issue once the callback
                # has returned. Other plans are unaffected.
                return PlanCommandResult(
                    command_id=command.command_id,
                    status=PlanCommandStatus.REJECTED_INVALID_STATE,
                    reason=(
                        f"Plan {command.plan_id} is emitting command events on this "
                        "thread; re-issue the command after the subscriber "
                        "callback returns"
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

            if command.type == PlanCommandType.RETRY_STEP:
                result = self._apply_retry(command, step, pending)
            else:
                result = self._apply_skip(command, plan, step, pending)

            if result.status is PlanCommandStatus.ACCEPTED:
                state = self._plans.setdefault(command.plan_id, _PlanCommandState())
                state.processed.add(command.command_id)
                state.in_flight[command.step_id] = command.command_id
                self._command_plan[command.command_id] = command.plan_id
                # Emit while still holding the handler lock: mutation and
                # emission stay atomic, so the log's seq order equals the
                # mutation order and a payload materialized under the lock
                # can never land after a newer event for the same step
                # (C1, 20260831 adversarial review). Re-entrant subscribers
                # are safe: PlanEventLog.append invokes callbacks on this
                # thread and the RLock lets them re-enter apply()/
                # complete_command() without deadlocking (FC3). The
                # _emitting guard above closes the remaining same-thread
                # interleave: a nested command for this plan is rejected
                # before it can mutate between these appends.
                self._emitting.add(command.plan_id)
                try:
                    result.events = [
                        self._events.append(command.plan_id, event_type, payload)
                        for event_type, payload in pending
                    ]
                except BaseException:
                    # Append-level failure mid-flush (subscriber exceptions
                    # are already swallowed by PlanEventLog.append): roll the
                    # bookkeeping back so the idempotency key is not wedged
                    # and the command can be re-issued once the emitter
                    # recovers. The plan mutation itself stays applied.
                    state.processed.discard(command.command_id)
                    if state.in_flight.get(command.step_id) == command.command_id:
                        del state.in_flight[command.step_id]
                    self._command_plan.pop(command.command_id, None)
                    if not state.processed and not state.in_flight:
                        self._plans.pop(command.plan_id, None)
                    raise
                finally:
                    self._emitting.discard(command.plan_id)
        return result

    def complete_command(self, command_id: str) -> bool:
        """Mark an accepted command as completed, releasing its in-flight slot.

        Called by the integrator once the affected step has reached a
        terminal state again (e.g. the retried step completed or failed).

        Returns:
            True when the command was in flight and is now completed;
            False for unknown or already-completed command ids.

        Raises:
            RuntimeError: when re-entered from a subscriber callback while
                the command's own plan is mid-emission on this thread —
                completing now would release the in-flight slot before the
                command's effects settle. Call it after the callback
                returns. (Inside a subscriber the error is logged and
                swallowed by ``PlanEventLog.append``.)
        """
        with self._lock:
            plan_id = self._command_plan.get(command_id)
            if plan_id is not None and plan_id in self._emitting:
                raise RuntimeError(
                    f"complete_command({command_id!r}) re-entered while plan "
                    f"{plan_id!r} is emitting command events on this thread; "
                    "call it after the subscriber callback returns"
                )
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
        with ``PlanEventLog.drop_plan`` once a plan is terminal — this
        method first, then the log (the log has no emission-window guard).
        Do not call ``PlanEventLog.drop_plan`` from a subscriber callback
        while this handler is emitting the plan. Unknown plan_ids are
        silently ignored.

        Raises:
            RuntimeError: when re-entered from a subscriber callback while
                this plan is mid-emission on this thread — dropping now
                would erase the idempotency keys of the command batch being
                emitted, letting an accepted command be applied twice. Call
                it after the callback returns.
        """
        with self._lock:
            if plan_id in self._emitting:
                raise RuntimeError(
                    f"drop_plan({plan_id!r}) re-entered while the plan is "
                    "emitting command events on this thread; call it after "
                    "the subscriber callback returns"
                )
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
        if step.status != StepStatus.FAILED:
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
        (completed/skipped) are listed under ``excluded_terminal``; dependents
        currently executing (in_progress) are left running and listed under
        ``excluded_in_flight`` — a cascade never rewrites history and never
        renames live work as terminal.
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
        # Complete partition of StepStatus's five values; a future sixth
        # status would silently vanish from both lists — extend here (FC8).
        excluded_terminal = [
            s.step_id for s in closure if s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
        ]
        excluded_in_flight = [s.step_id for s in closure if s.status == StepStatus.IN_PROGRESS]

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
        if excluded_terminal:
            mutation_payload["excluded_terminal"] = excluded_terminal
        if excluded_in_flight:
            mutation_payload["excluded_in_flight"] = excluded_in_flight
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
