"""Plan execution event contract for the orchestration layer.

Append-only, per-plan event log backing observer UIs (e.g. a task-list
panel that renders plan steps, their status transitions, and reorchestration
mutations in real time).

Contract summary:
- ``PlanEventType``: plan_snapshot / step_transition / plan_terminal / plan_mutated
- ``event_seq`` is assigned by :class:`PlanEventLog` as the single writer,
  monotonically increasing from 1 per ``plan_id``.
- Each plan keeps a bounded ring window of recent events; consumers whose
  cursor fell out of the window resync via :meth:`PlanEventLog.replay`,
  which returns a full snapshot instead of deltas.

Scope note: ``step_transition`` covers ExecutionStep state changes only.
Squad patterns (AGENT_SQUAD/DEBATE/RED_TEAM) execute SquadStep members,
which are out of scope — squad plans emit plan_snapshot and plan_terminal
at plan level, but no per-member step transitions.

The log is pure Python state — no I/O, no transport. Emission is a
zero-overhead no-op when no log is injected into the engine.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan, ExecutionStep

logger = logging.getLogger(__name__)

#: Default per-plan ring window size (events retained for replay).
DEFAULT_WINDOW_SIZE = 1000


class PlanEventType(StrEnum):
    """Types of plan execution events."""

    PLAN_SNAPSHOT = "plan_snapshot"  # Full projection of the current plan state
    STEP_TRANSITION = "step_transition"  # A step changed status
    PLAN_TERMINAL = "plan_terminal"  # Execution reached a final state
    PLAN_MUTATED = "plan_mutated"  # Reorchestration changed the plan shape


class PlanEvent(BaseModel):
    """A single plan execution event.

    ``event_seq`` is 0 only for synthesized snapshots of a plan that has not
    emitted any event yet; all appended events are numbered from 1 upward.
    ``schema_version`` versions the payload contract for consumers.
    """

    plan_id: str = Field(..., description="Plan this event belongs to")
    event_seq: int = Field(..., ge=0, description="Per-plan monotonic sequence number")
    type: PlanEventType = Field(..., description="Event type")
    at: str = Field(..., description="ISO8601 UTC timestamp")
    payload: dict[str, Any] = Field(default_factory=dict, description="Type-specific payload")
    schema_version: int = Field(default=1, description="Payload contract version")

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict (StrEnum members serialized to their values)."""
        return self.model_dump(mode="json")


class ReplayResult(BaseModel):
    """Result of :meth:`PlanEventLog.replay`.

    When ``needs_snapshot`` is True the caller's cursor fell out of the
    retention window; ``snapshot`` carries the current full plan projection
    (its ``event_seq`` is the latest allocated seq and becomes the caller's
    new cursor) and ``events`` is empty — the snapshot already reflects every
    mutation up to that seq. ``snapshot`` is None when no plan reference was
    ever registered with the log; treat that as "plan state unknown" and
    surface an explicit plan-not-found/resync-failed state rather than
    rendering a stale list.
    """

    events: list[PlanEvent] = Field(default_factory=list)
    snapshot: PlanEvent | None = Field(default=None)
    needs_snapshot: bool = Field(default=False)


def plan_snapshot_projection(plan: ExecutionPlan) -> dict[str, Any]:
    """Build the UI-facing plan projection for ``plan_snapshot`` payloads.

    Deliberately excludes output text (``result_summary``, accumulated
    results) — the panel renders structure and status only.
    """
    return {
        "plan_id": plan.plan_id,
        "status": plan.status.value,
        "workflow_pattern": plan.workflow_pattern.value,
        "steps": [
            {
                "step_id": s.step_id,
                "step_number": s.step_number,
                "intent": s.intent,
                "status": s.status.value,
                "dynamic_status": s.dynamic_status.value if s.dynamic_status else None,
                "loop_iteration": s.loop_iteration,
                "started_at": s.started_at,
                "completed_at": s.completed_at,
                "dependencies": list(s.dependencies),
                "parallel_group": s.parallel_group,
            }
            for s in plan.steps
        ],
    }


def step_transition_payload(step: ExecutionStep, *, error: str | None = None) -> dict[str, Any]:
    """Build the canonical ``step_transition`` payload for a step's current state.

    Single constructor shared by WorkflowEngine and PlanCommandHandler so the
    payload shape cannot drift between emitters. ``dynamic_status`` and
    ``result_summary`` are included only when set; ``error`` only when given.
    """
    payload: dict[str, Any] = {
        "step_id": step.step_id,
        "step_number": step.step_number,
        "status": step.status.value,
        "loop_iteration": step.loop_iteration,
    }
    if step.dynamic_status is not None:
        payload["dynamic_status"] = step.dynamic_status.value
    if step.result_summary is not None:
        payload["result_summary"] = step.result_summary
    if error is not None:
        payload["error"] = error
    return payload


class _PlanLogState:
    """Per-plan mutable log state (internal)."""

    __slots__ = ("events", "next_seq", "plan", "subscribers")

    def __init__(self, window_size: int) -> None:
        self.events: deque[PlanEvent] = deque(maxlen=window_size)
        self.next_seq: int = 1
        self.subscribers: list[Callable[[PlanEvent], None]] = []
        self.plan: ExecutionPlan | None = None


class PlanEventLog:
    """Append-only, per-plan event log with replay and subscription support.

    Single writer for ``event_seq`` assignment: all allocation happens under
    one lock, so concurrent engines (e.g. tournament thread pool) cannot
    interleave sequence numbers within a plan.

    The log itself is thread-safe — every state mutation is lock-guarded.
    Subscriber callbacks are invoked synchronously but *outside* the lock,
    so a misbehaving subscriber can never corrupt the log or break the
    engine (exceptions are caught and logged).
    """

    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE) -> None:
        """Initialize the log.

        Args:
            window_size: Maximum events retained per plan for replay.
        """
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self._window_size = window_size
        self._logs: dict[str, _PlanLogState] = {}
        self._lock = threading.Lock()

    def _state_locked(self, plan_id: str) -> _PlanLogState:
        """Return or create per-plan state. Caller must hold the lock."""
        state = self._logs.get(plan_id)
        if state is None:
            state = _PlanLogState(self._window_size)
            self._logs[plan_id] = state
        return state

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def append(
        self,
        plan_id: str,
        event_type: PlanEventType,
        payload: dict[str, Any],
    ) -> PlanEvent:
        """Append an event, assigning the next per-plan ``event_seq``.

        Subscribers are notified synchronously after the event is persisted;
        subscriber exceptions are logged and swallowed.
        """
        with self._lock:
            state = self._state_locked(plan_id)
            event = PlanEvent(
                plan_id=plan_id,
                event_seq=state.next_seq,
                type=event_type,
                at=self._now(),
                payload=payload,
            )
            state.next_seq += 1
            state.events.append(event)
            subscribers = list(state.subscribers)

        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                logger.exception(
                    "Plan event subscriber raised for plan %s seq %d — ignored",
                    plan_id,
                    event.event_seq,
                )
        return event

    def replay(self, plan_id: str, since_seq: int) -> ReplayResult:
        """Replay events after ``since_seq`` for incremental sync.

        If ``since_seq`` is older than the oldest retained event, returns
        ``needs_snapshot=True`` with the current snapshot instead of deltas.
        """
        with self._lock:
            state = self._logs.get(plan_id)
            if state is None or not state.events:
                # Unknown plan, or nothing emitted yet — nothing to replay.
                return ReplayResult()
            oldest = state.events[0].event_seq
            if since_seq + 1 < oldest:
                # The first event the caller needs was evicted from the ring
                # window: resync from a full snapshot of the latest known
                # plan state instead of deltas.
                snapshot = self._snapshot_locked(plan_id, state)
                return ReplayResult(snapshot=snapshot, needs_snapshot=True)
            return ReplayResult(
                events=[e for e in state.events if e.event_seq > since_seq],
            )

    def snapshot(self, plan_id: str) -> PlanEvent | None:
        """Return the current plan projection as a ``plan_snapshot`` event.

        The event's ``event_seq`` is the latest allocated seq for the plan
        (0 when nothing was appended yet); it is synthesized, not appended.
        Returns None when no plan reference is known for ``plan_id``.
        """
        with self._lock:
            state = self._logs.get(plan_id)
            if state is None:
                return None
            return self._snapshot_locked(plan_id, state)

    def _snapshot_locked(self, plan_id: str, state: _PlanLogState) -> PlanEvent | None:
        """Build a snapshot event from the latest plan reference (lock held)."""
        if state.plan is None:
            return None
        return PlanEvent(
            plan_id=plan_id,
            event_seq=state.next_seq - 1,
            type=PlanEventType.PLAN_SNAPSHOT,
            at=self._now(),
            payload={"plan": plan_snapshot_projection(state.plan)},
        )

    def update_plan(self, plan: ExecutionPlan) -> None:
        """Register/refresh the latest plan reference used for snapshots.

        The engine mutates plan objects in place, so one call at run start
        keeps snapshots current; call again if the plan object is replaced.
        """
        with self._lock:
            self._state_locked(plan.plan_id).plan = plan

    def subscribe(self, plan_id: str, callback: Callable[[PlanEvent], None]) -> None:
        """Subscribe to future events for a plan (synchronous delivery)."""
        with self._lock:
            state = self._state_locked(plan_id)
            if callback not in state.subscribers:
                state.subscribers.append(callback)

    def unsubscribe(self, plan_id: str, callback: Callable[[PlanEvent], None]) -> None:
        """Remove a subscription; silently ignored when not subscribed."""
        with self._lock:
            state = self._logs.get(plan_id)
            if state is not None and callback in state.subscribers:
                state.subscribers.remove(callback)

    def latest_seq(self, plan_id: str) -> int:
        """Return the latest allocated seq for a plan (0 when none)."""
        with self._lock:
            state = self._logs.get(plan_id)
            return state.next_seq - 1 if state is not None else 0

    def drop_plan(self, plan_id: str) -> None:
        """Drop all retained state for a plan (events, plan ref, subscribers).

        The ring window bounds retained events, but the per-plan state entry
        itself — subscribers and the plan reference — lingers after a plan
        finishes. Integrators should call this once a plan reaches a
        terminal state and all consumers have resynced. Unknown plan_ids
        are silently ignored.
        """
        with self._lock:
            self._logs.pop(plan_id, None)
