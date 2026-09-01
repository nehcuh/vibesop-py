"""Tests for the control-plane command contract (commands.py).

Covers retry/skip validation, idempotency, in-flight rejection, skip
dependency semantics, event payloads, and the complete_command lifecycle
(design background: docs/archive/chrome-sidepanel-task-plan-panel.md §2.6/§3.2).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vibesop.core.models import (
    DynamicNodeStatus,
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    StepStatus,
    WorkflowPattern,
)
from vibesop.core.orchestration.commands import (
    PlanCommand,
    PlanCommandHandler,
    PlanCommandStatus,
    PlanCommandType,
)
from vibesop.core.orchestration.events import PlanEventLog, PlanEventType


def _make_plan(plan_id: str = "plan-cmd") -> ExecutionPlan:
    """Plan with three steps: s2 depends on s1, s3 depends on s2."""
    return ExecutionPlan(
        plan_id=plan_id,
        original_query="command test",
        steps=[
            ExecutionStep(step_id="s1", step_number=1, skill_id="t", intent="Task 1"),
            ExecutionStep(
                step_id="s2", step_number=2, skill_id="t", intent="Task 2", dependencies=["s1"]
            ),
            ExecutionStep(
                step_id="s3", step_number=3, skill_id="t", intent="Task 3", dependencies=["s2"]
            ),
        ],
        workflow_pattern=WorkflowPattern.SEQUENTIAL,
        execution_mode=ExecutionMode.SEQUENTIAL,
    )


def _make_handler(plan: ExecutionPlan, window_size: int = 100):
    log = PlanEventLog(window_size=window_size)
    plans = {plan.plan_id: plan}
    handler = PlanCommandHandler(log, plans.get)
    return handler, log


def _cmd(
    command_id: str,
    plan_id: str = "plan-cmd",
    type: PlanCommandType = PlanCommandType.RETRY_STEP,
    step_id: str = "s1",
    cascade: bool = False,
) -> PlanCommand:
    return PlanCommand(
        command_id=command_id,
        plan_id=plan_id,
        type=type,
        step_id=step_id,
        issued_at="2026-08-30T12:00:00+00:00",
        cascade=cascade,
    )


def _fail_step(plan: ExecutionPlan, step_id: str) -> None:
    step = next(s for s in plan.steps if s.step_id == step_id)
    step.status = StepStatus.FAILED
    step.result_summary = "boom"
    step.started_at = "2026-08-30T11:00:00+00:00"
    step.completed_at = "2026-08-30T11:01:00+00:00"


# --- Idempotency and in-flight ---


def test_duplicate_command_id_rejected_without_side_effects() -> None:
    plan = _make_plan()
    _fail_step(plan, "s1")
    handler, log = _make_handler(plan)

    first = handler.apply(_cmd("c-1"))
    assert first.status == PlanCommandStatus.ACCEPTED

    second = handler.apply(_cmd("c-1"))
    assert second.status == PlanCommandStatus.REJECTED_DUPLICATE
    assert second.events == []
    # Exactly the two events from the first application, nothing more.
    assert len(log.replay(plan.plan_id, since_seq=0).events) == 2


def test_in_flight_command_blocks_new_command_on_same_step() -> None:
    plan = _make_plan()
    _fail_step(plan, "s1")
    handler, _ = _make_handler(plan)

    handler.apply(_cmd("c-1"))
    blocked = handler.apply(_cmd("c-2"))

    assert blocked.status == PlanCommandStatus.REJECTED_INVALID_STATE
    assert "in-flight" in (blocked.reason or "")
    assert blocked.events == []


def test_in_flight_does_not_block_other_steps() -> None:
    plan = _make_plan()
    _fail_step(plan, "s1")
    _fail_step(plan, "s3")
    handler, _ = _make_handler(plan)

    handler.apply(_cmd("c-1", step_id="s1"))
    other = handler.apply(_cmd("c-2", step_id="s3"))

    assert other.status == PlanCommandStatus.ACCEPTED


def test_complete_command_releases_in_flight_slot() -> None:
    plan = _make_plan()
    _fail_step(plan, "s1")
    handler, _ = _make_handler(plan)

    handler.apply(_cmd("c-1"))
    assert handler.complete_command("c-1") is True
    assert handler.complete_command("c-1") is False  # already completed
    assert handler.complete_command("unknown") is False

    # Step fails again after the retry ran; a new command is now accepted.
    _fail_step(plan, "s1")
    retry = handler.apply(_cmd("c-2"))
    assert retry.status == PlanCommandStatus.ACCEPTED


def test_rejected_command_does_not_consume_idempotency_key() -> None:
    plan = _make_plan()  # s1 is pending — retry requires failed
    handler, _ = _make_handler(plan)

    rejected = handler.apply(_cmd("c-1"))
    assert rejected.status == PlanCommandStatus.REJECTED_INVALID_STATE
    assert plan.plan_id not in handler._plans
    assert "c-1" not in handler._command_plan

    _fail_step(plan, "s1")
    retried = handler.apply(_cmd("c-1"))
    assert retried.status == PlanCommandStatus.ACCEPTED


# --- RETRY_STEP ---


def test_retry_failed_step_rewinds_with_loop_back_semantics() -> None:
    plan = _make_plan()
    _fail_step(plan, "s1")
    handler, log = _make_handler(plan)

    result = handler.apply(_cmd("c-1"))

    assert result.status == PlanCommandStatus.ACCEPTED
    step = plan.steps[0]
    assert step.status == StepStatus.PENDING
    assert step.dynamic_status == DynamicNodeStatus.LOOPING
    assert step.loop_iteration == 1
    assert step.result_summary is None
    assert step.started_at is None
    assert step.completed_at is None

    events = log.replay(plan.plan_id, since_seq=0).events
    assert result.events == events
    mutation, transition = events
    assert mutation.type == PlanEventType.PLAN_MUTATED
    assert mutation.payload == {
        "decision": "loop_back",
        "loop_back_step_id": "s1",
        "source": "user_command",
        "command_id": "c-1",
    }
    assert transition.type == PlanEventType.STEP_TRANSITION
    assert transition.payload["status"] == "pending"
    assert transition.payload["dynamic_status"] == "looping"
    assert transition.payload["loop_iteration"] == 1


def test_retry_rejects_non_failed_step() -> None:
    plan = _make_plan()
    handler, _ = _make_handler(plan)

    for status in (StepStatus.PENDING, StepStatus.IN_PROGRESS, StepStatus.COMPLETED):
        plan.steps[0].status = status
        result = handler.apply(_cmd(f"c-{status.value}"))
        assert result.status == PlanCommandStatus.REJECTED_INVALID_STATE
        assert status.value in (result.reason or "")


def test_unknown_plan_or_step_rejected() -> None:
    plan = _make_plan()
    handler, _ = _make_handler(plan)

    no_plan = handler.apply(_cmd("c-1", plan_id="nope"))
    assert no_plan.status == PlanCommandStatus.REJECTED_INVALID_STATE
    assert "not found" in (no_plan.reason or "")
    assert "nope" not in handler._plans
    assert "c-1" not in handler._command_plan

    no_step = handler.apply(_cmd("c-2", step_id="nope"))
    assert no_step.status == PlanCommandStatus.REJECTED_INVALID_STATE
    assert plan.plan_id not in handler._plans
    assert "c-2" not in handler._command_plan


# --- SKIP_STEP ---


def test_skip_without_downstream_succeeds() -> None:
    plan = _make_plan()
    _fail_step(plan, "s3")  # leaf step: no dependents
    handler, log = _make_handler(plan)

    result = handler.apply(_cmd("c-1", type=PlanCommandType.SKIP_STEP, step_id="s3"))

    assert result.status == PlanCommandStatus.ACCEPTED
    assert plan.steps[2].status == StepStatus.SKIPPED

    events = log.replay(plan.plan_id, since_seq=0).events
    transition, mutation = events
    assert transition.type == PlanEventType.STEP_TRANSITION
    assert transition.payload["step_id"] == "s3"
    assert transition.payload["status"] == "skipped"
    assert mutation.type == PlanEventType.PLAN_MUTATED
    assert mutation.payload["decision"] is None
    assert mutation.payload["user_action"] == "skip"
    assert mutation.payload["step_ids"] == ["s3"]
    assert mutation.payload["cascade"] is False
    assert mutation.payload["command_id"] == "c-1"


def test_skip_with_downstream_blocked_without_cascade() -> None:
    plan = _make_plan()
    _fail_step(plan, "s1")
    handler, log = _make_handler(plan)

    result = handler.apply(_cmd("c-1", type=PlanCommandType.SKIP_STEP, step_id="s1"))

    assert result.status == PlanCommandStatus.REJECTED_DEPENDENCY_BLOCKED
    assert "s2" in (result.reason or "")
    assert result.events == []
    assert plan.steps[0].status == StepStatus.FAILED  # untouched
    assert log.replay(plan.plan_id, since_seq=0).events == []


def test_skip_cascade_skips_transitive_closure() -> None:
    plan = _make_plan()
    _fail_step(plan, "s1")
    handler, log = _make_handler(plan)

    result = handler.apply(_cmd("c-1", type=PlanCommandType.SKIP_STEP, step_id="s1", cascade=True))

    assert result.status == PlanCommandStatus.ACCEPTED
    assert [s.status for s in plan.steps] == [
        StepStatus.SKIPPED,
        StepStatus.SKIPPED,
        StepStatus.SKIPPED,
    ]

    events = log.replay(plan.plan_id, since_seq=0).events
    transitions = [e for e in events if e.type == PlanEventType.STEP_TRANSITION]
    assert [e.payload["step_id"] for e in transitions] == ["s1", "s2", "s3"]
    assert all(e.payload["status"] == "skipped" for e in transitions)
    mutation = events[-1]
    assert mutation.payload["user_action"] == "skip"
    assert mutation.payload["step_ids"] == ["s1", "s2", "s3"]
    assert mutation.payload["cascade"] is True


def test_skip_pending_step_allowed() -> None:
    plan = _make_plan()  # all steps pending; s3 is a leaf
    handler, _ = _make_handler(plan)

    result = handler.apply(_cmd("c-1", type=PlanCommandType.SKIP_STEP, step_id="s3"))

    assert result.status == PlanCommandStatus.ACCEPTED
    assert plan.steps[2].status == StepStatus.SKIPPED


def test_skip_rejects_in_progress_or_completed_step() -> None:
    plan = _make_plan()
    handler, _ = _make_handler(plan)

    for status in (StepStatus.IN_PROGRESS, StepStatus.COMPLETED):
        plan.steps[2].status = status
        result = handler.apply(
            _cmd(f"c-{status.value}", type=PlanCommandType.SKIP_STEP, step_id="s3")
        )
        assert result.status == PlanCommandStatus.REJECTED_INVALID_STATE


def test_command_events_share_log_seq_with_engine_events() -> None:
    """Commands append to the same per-plan log: seqs interleave with any
    pre-existing engine events in one monotonic sequence."""
    plan = _make_plan()
    _fail_step(plan, "s3")
    handler, log = _make_handler(plan)
    log.append(plan.plan_id, PlanEventType.PLAN_SNAPSHOT, {"plan": {}})  # engine-emitted

    result = handler.apply(_cmd("c-1", type=PlanCommandType.SKIP_STEP, step_id="s3"))

    assert [e.event_seq for e in result.events] == [2, 3]


# --- Review-driven regression tests ---


def test_cascade_skip_preserves_terminal_downstream() -> None:
    """A failed ← B completed ← C completed: cascading skip of A must not
    rewrite B/C to skipped; they are listed under excluded_terminal."""
    plan = _make_plan()
    _fail_step(plan, "s1")
    plan.steps[1].status = StepStatus.COMPLETED
    plan.steps[2].status = StepStatus.COMPLETED
    handler, log = _make_handler(plan)

    result = handler.apply(_cmd("c-1", type=PlanCommandType.SKIP_STEP, step_id="s1", cascade=True))

    assert result.status == PlanCommandStatus.ACCEPTED
    assert plan.steps[0].status == StepStatus.SKIPPED
    assert plan.steps[1].status == StepStatus.COMPLETED  # untouched
    assert plan.steps[2].status == StepStatus.COMPLETED  # untouched

    events = log.replay(plan.plan_id, since_seq=0).events
    transitions = [e for e in events if e.type == PlanEventType.STEP_TRANSITION]
    assert [e.payload["step_id"] for e in transitions] == ["s1"]  # only s1 transitioned
    mutation = events[-1]
    assert mutation.payload["step_ids"] == ["s1"]
    assert mutation.payload["excluded_terminal"] == ["s2", "s3"]


def test_cascade_skip_reports_in_flight_dependent_separately() -> None:
    """FC8 (20260831 review): an in_progress dependent is neither skipped
    nor terminal — the cascade leaves it running and reports it under
    ``excluded_in_flight``, never under ``excluded_terminal``."""
    plan = _make_plan()
    _fail_step(plan, "s1")
    plan.steps[1].status = StepStatus.IN_PROGRESS
    handler, log = _make_handler(plan)

    result = handler.apply(_cmd("c-1", type=PlanCommandType.SKIP_STEP, step_id="s1", cascade=True))

    assert result.status == PlanCommandStatus.ACCEPTED
    assert plan.steps[0].status == StepStatus.SKIPPED
    assert plan.steps[1].status == StepStatus.IN_PROGRESS  # left running
    assert plan.steps[2].status == StepStatus.SKIPPED  # pending → skipped

    mutation = [
        e
        for e in log.replay(plan.plan_id, since_seq=0).events
        if e.type == PlanEventType.PLAN_MUTATED
    ][-1]
    assert mutation.payload["excluded_in_flight"] == ["s2"]
    assert "excluded_terminal" not in mutation.payload


def test_plan_command_rejects_non_iso8601_issued_at() -> None:
    """B-F9 residue (20260831 review): issued_at is a contract field fed by
    external callers — a non-ISO8601 value must fail validation."""
    with pytest.raises(ValidationError, match="ISO8601"):
        PlanCommand(
            command_id="c-bad",
            plan_id="plan-cmd",
            type=PlanCommandType.RETRY_STEP,
            step_id="s1",
            issued_at="not-a-date",
        )


def test_command_accepted_on_terminal_plan_after_failure() -> None:
    """FC2 (20260831 review): the engine runs synchronously, so failure
    intervention is by nature post-run — a terminal plan status must NOT
    reject retry/skip. Step-state gates are the validity authority."""
    plan = _make_plan()
    _fail_step(plan, "s3")
    plan.status = PlanStatus.FAILED
    handler, log = _make_handler(plan)

    result = handler.apply(_cmd("c-1", type=PlanCommandType.SKIP_STEP, step_id="s3"))

    assert result.status == PlanCommandStatus.ACCEPTED
    assert result.events, "accepted command must emit its events"
    assert log.replay(plan.plan_id, since_seq=0).events


def test_engine_failure_then_retry_accepted_post_run() -> None:
    """End-to-end FC2: engine.run() with a failing executor marks the plan
    FAILED (not COMPLETED), and a panel-issued retry on the failed step is
    accepted afterwards."""
    from vibesop.core.orchestration.workflow_engine import WorkflowEngine

    plan = _make_plan(plan_id="plan-fc2")
    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)

    def boom(step):
        raise RuntimeError(f"boom-{step.step_id}")

    engine.run(plan, boom)

    assert plan.status == PlanStatus.FAILED
    assert plan.steps[0].status == StepStatus.FAILED

    handler = PlanCommandHandler(log, {"plan-fc2": plan}.get)
    result = handler.apply(_cmd("c-retry", plan_id="plan-fc2", step_id="s1"))
    assert result.status == PlanCommandStatus.ACCEPTED
    assert plan.steps[0].status == StepStatus.PENDING


def test_reentrant_subscriber_does_not_deadlock() -> None:
    """FC3 (20260831 review): PlanEventLog.append invokes subscribers
    synchronously; a subscriber that issues another command must not
    deadlock on the handler lock — the lock is an RLock and the callback
    re-enters on the emitting thread.

    C1 follow-up (20260831 re-review): a nested apply() for the SAME plan
    during emission is rejected retryably — payloads are materialized
    before the emission loop, so a mid-emission mutation would let the
    outer command's stale payloads land after the nested command's newer
    events. Re-issued after the callback returns, the same command_id is
    accepted (rejections do not consume the idempotency key)."""
    import threading

    plan = _make_plan()
    _fail_step(plan, "s1")
    _fail_step(plan, "s3")
    handler, log = _make_handler(plan)

    nested_results: list[PlanCommandStatus] = []
    issued = threading.Event()

    def reentering_subscriber(event):
        # Fire once: without this guard the nested command's own events
        # re-invoke this subscriber, and the idempotency gate (correctly)
        # rejects the second application — that path is covered elsewhere.
        if issued.is_set():
            return
        issued.set()
        # Same-plan command from inside the callback: blocked by the
        # mid-emission re-entry guard (C1 follow-up), with no side effects.
        nested = handler.apply(_cmd("c-nested", type=PlanCommandType.SKIP_STEP, step_id="s3"))
        nested_results.append(nested.status)

    log.subscribe(plan.plan_id, reentering_subscriber)

    done = threading.Event()
    outer_status: list[PlanCommandStatus] = []

    def run_outer():
        outer_status.append(handler.apply(_cmd("c-outer")).status)
        done.set()

    thread = threading.Thread(target=run_outer, daemon=True)
    thread.start()
    assert done.wait(timeout=5), "apply() deadlocked: subscriber re-entry blocked the handler lock"
    thread.join(timeout=5)
    assert not thread.is_alive(), "apply() deadlocked: emitting thread never returned"

    assert outer_status == [PlanCommandStatus.ACCEPTED]
    assert nested_results == [PlanCommandStatus.REJECTED_INVALID_STATE]
    # The idempotency key survived the rejection: the same command_id is
    # accepted once issued outside the emission window.
    retried = handler.apply(_cmd("c-nested", type=PlanCommandType.SKIP_STEP, step_id="s3"))
    assert retried.status == PlanCommandStatus.ACCEPTED
    assert plan.steps[2].status == StepStatus.SKIPPED


def test_mid_emission_reentry_cannot_diverge_replay_view() -> None:
    """C1 follow-up (20260831 re-review): deterministic reproducer of the
    stale-payload interleave the emission guard closes. Pre-guard, a
    subscriber re-entering apply() with a cascade skip landed its
    mutation+events BETWEEN the outer command's appends, so the outer's
    pre-materialized s2=pending payload was appended last — the replayed
    final view for s2 said pending while the plan said skipped. With the
    guard, the nested command is rejected and the replayed final view can
    never diverge from plan truth."""
    plan = _make_plan()
    _fail_step(plan, "s2")  # outer retry target
    handler, log = _make_handler(plan)

    fired: list[bool] = []
    nested_status: list[PlanCommandStatus] = []

    def cascade_during_emission(event):
        if fired:
            return
        fired.append(True)
        # s1 is pending; its cascade closure covers s2/s3 — pre-guard this
        # rewrote s2 to SKIPPED between the outer command's appends.
        nested_status.append(
            handler.apply(
                _cmd("c-inner", type=PlanCommandType.SKIP_STEP, step_id="s1", cascade=True)
            ).status
        )

    log.subscribe(plan.plan_id, cascade_during_emission)

    outer = handler.apply(_cmd("c-outer", step_id="s2"))  # retry s2
    assert outer.status == PlanCommandStatus.ACCEPTED
    assert fired, "subscriber never ran"
    assert nested_status == [PlanCommandStatus.REJECTED_INVALID_STATE]

    # The follow-up lands whole, after the outer flush.
    follow_up = handler.apply(
        _cmd("c-inner", type=PlanCommandType.SKIP_STEP, step_id="s1", cascade=True)
    )
    assert follow_up.status == PlanCommandStatus.ACCEPTED

    replayed = log.replay(plan.plan_id, since_seq=0).events
    last_status: dict[str, str] = {}
    for event in replayed:
        if event.type is PlanEventType.STEP_TRANSITION:
            last_status[event.payload["step_id"]] = event.payload["status"]
    for step in plan.steps:
        assert last_status.get(step.step_id) == step.status.value


def test_mid_emission_reentry_other_plan_accepted() -> None:
    """The emission guard is per-plan: a subscriber command for a DIFFERENT
    plan applies normally mid-emission."""
    plan_a = _make_plan(plan_id="plan-a")
    plan_b = _make_plan(plan_id="plan-b")
    _fail_step(plan_a, "s1")
    _fail_step(plan_b, "s1")
    log = PlanEventLog(window_size=100)
    plans = {"plan-a": plan_a, "plan-b": plan_b}
    handler = PlanCommandHandler(log, plans.get)

    fired: list[bool] = []
    nested_status: list[PlanCommandStatus] = []

    def cross_plan_subscriber(event):
        if fired:
            return
        fired.append(True)
        nested_status.append(handler.apply(_cmd("c-b", plan_id="plan-b", step_id="s1")).status)

    log.subscribe("plan-a", cross_plan_subscriber)

    outer = handler.apply(_cmd("c-a", plan_id="plan-a", step_id="s1"))

    assert outer.status == PlanCommandStatus.ACCEPTED
    assert nested_status == [PlanCommandStatus.ACCEPTED]
    assert plan_b.steps[0].status == StepStatus.PENDING  # retry rewound it


def test_complete_command_during_emission_raises() -> None:
    """Re-entering complete_command() for the emitting plan mid-emission is
    a programming error: it would release the in-flight slot before the
    command's effects settle, letting a follow-up command target a step
    whose intervention is still in flight. After the callback returns the
    same call completes normally."""
    plan = _make_plan()
    _fail_step(plan, "s1")
    handler, log = _make_handler(plan)

    caught: list[str] = []

    def completing_subscriber(event):
        if caught:
            return
        try:
            handler.complete_command("c-outer")
        except RuntimeError as exc:
            caught.append(str(exc))

    log.subscribe(plan.plan_id, completing_subscriber)

    outer = handler.apply(_cmd("c-outer"))
    assert outer.status == PlanCommandStatus.ACCEPTED
    assert caught, "complete_command during emission did not raise"
    assert "emitting" in caught[0]

    # After the callback the completion lands normally.
    assert handler.complete_command("c-outer") is True


def test_drop_plan_during_emission_raises_and_preserves_idempotency() -> None:
    """Re-entering drop_plan() mid-emission would erase the idempotency keys
    of the batch being emitted, letting an accepted command be applied
    twice. It raises instead; the keys survive (re-issuing the outer
    command_id is still rejected_duplicate)."""
    plan = _make_plan()
    _fail_step(plan, "s1")
    handler, log = _make_handler(plan)

    caught: list[str] = []

    def dropping_subscriber(event):
        if caught:
            return
        try:
            handler.drop_plan(plan.plan_id)
        except RuntimeError as exc:
            caught.append(str(exc))

    log.subscribe(plan.plan_id, dropping_subscriber)

    outer = handler.apply(_cmd("c-outer"))
    assert outer.status == PlanCommandStatus.ACCEPTED
    assert caught, "drop_plan during emission did not raise"

    assert handler.apply(_cmd("c-outer")).status == PlanCommandStatus.REJECTED_DUPLICATE


def test_emission_failure_rolls_back_bookkeeping() -> None:
    """An append-level failure mid-flush must not wedge the idempotency key:
    bookkeeping is rolled back so the command can be re-issued once the
    emitter recovers (the plan mutation itself stays applied, so the
    re-issue is then judged by the state gates, not the duplicate gate)."""
    plan = _make_plan()
    _fail_step(plan, "s1")
    handler, log = _make_handler(plan)

    original_append = log.append

    def failing_append(*args, **kwargs):
        raise RuntimeError("emitter down")

    log.append = failing_append  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="emitter down"):
            handler.apply(_cmd("c-1"))
    finally:
        log.append = original_append  # type: ignore[method-assign]

    # Not wedged: the same command_id is re-issuable. The mutation already
    # rewound s1 to PENDING, so the retry now hits the state gate — proof
    # the duplicate gate did not swallow it.
    second = handler.apply(_cmd("c-1"))
    assert second.status == PlanCommandStatus.REJECTED_INVALID_STATE
    assert "requires a failed step" in second.reason
    # The in-flight slot was rolled back too.
    assert handler.complete_command("c-1") is False
    # First-command rollback must not leave an empty _plans tombstone.
    assert plan.plan_id not in handler._plans


def test_transitive_reentry_guard_covers_a_to_b_to_a() -> None:
    """The emission guard is transitive across nested emissions: while plan
    A emits, a callback command on plan B is accepted and emits B's events;
    a B-side callback re-entering apply() for A is still rejected because
    A remains in _emitting until its whole flush completes."""
    plan_a = _make_plan(plan_id="plan-a")
    plan_b = _make_plan(plan_id="plan-b")
    _fail_step(plan_a, "s1")
    _fail_step(plan_b, "s1")
    log = PlanEventLog(window_size=100)
    plans = {"plan-a": plan_a, "plan-b": plan_b}
    handler = PlanCommandHandler(log, plans.get)

    b_status: list[PlanCommandStatus] = []
    reentry_a_status: list[PlanCommandStatus] = []

    def b_subscriber(event):
        # B's own emission: re-entering for A must still be guarded. Target
        # A's pending leaf s3 with a skip — s3 has no dependents, so it
        # clears every earlier gate (no in-flight entry, no dependency
        # block). Without the _emitting guard this command would be
        # ACCEPTED and this test would go red.
        reentry_a_status.append(
            handler.apply(
                _cmd("c-a2", plan_id="plan-a", type=PlanCommandType.SKIP_STEP, step_id="s3")
            ).status
        )

    def a_subscriber(event):
        if b_status:
            return
        b_status.append(handler.apply(_cmd("c-b", plan_id="plan-b", step_id="s1")).status)

    log.subscribe("plan-b", b_subscriber)
    log.subscribe("plan-a", a_subscriber)

    outer = handler.apply(_cmd("c-a", plan_id="plan-a", step_id="s1"))

    assert outer.status == PlanCommandStatus.ACCEPTED
    # Assert re-entry first: if the guard is gone this is ACCEPTED (not
    # DEPENDENCY_BLOCKED), which is the pin. The b_status check is second
    # because an accepted re-entry can cascade extra A events and make
    # a_subscriber fire again (duplicate c-b) before this function returns.
    assert reentry_a_status
    assert all(s == PlanCommandStatus.REJECTED_INVALID_STATE for s in reentry_a_status)
    assert b_status == [PlanCommandStatus.ACCEPTED]


def test_command_id_in_flight_on_other_plan_rejected() -> None:
    """The in-flight index is global: re-using an in-flight command_id on a
    different plan must be rejected — accepting it would overwrite the index
    entry and wedge the first plan's in-flight slot forever. Retryable once
    the first command completes."""
    plan_a = _make_plan(plan_id="plan-a")
    plan_b = _make_plan(plan_id="plan-b")
    _fail_step(plan_a, "s1")
    _fail_step(plan_b, "s1")
    log = PlanEventLog(window_size=100)
    plans = {"plan-a": plan_a, "plan-b": plan_b}
    handler = PlanCommandHandler(log, plans.get)

    first = handler.apply(_cmd("c-shared", plan_id="plan-a", step_id="s1"))
    assert first.status == PlanCommandStatus.ACCEPTED

    conflict = handler.apply(_cmd("c-shared", plan_id="plan-b", step_id="s1"))
    assert conflict.status == PlanCommandStatus.REJECTED_INVALID_STATE
    assert "in flight on plan plan-a" in conflict.reason

    # A's in-flight slot is untouched by the rejected conflict.
    blocked = handler.apply(_cmd("c-other", plan_id="plan-a", step_id="s1"))
    assert blocked.status == PlanCommandStatus.REJECTED_INVALID_STATE
    assert "in-flight" in blocked.reason

    # Once the first completes, the id is free for plan B.
    assert handler.complete_command("c-shared") is True
    retry_on_b = handler.apply(_cmd("c-shared", plan_id="plan-b", step_id="s1"))
    assert retry_on_b.status == PlanCommandStatus.ACCEPTED


def test_apply_registers_plan_for_snapshots() -> None:
    """Handler-side update_plan: replay/snapshot work for plans the engine
    never registered with the log."""
    plan = _make_plan()
    _fail_step(plan, "s3")
    handler, log = _make_handler(plan)

    handler.apply(_cmd("c-1", type=PlanCommandType.SKIP_STEP, step_id="s3"))

    snapshot = log.snapshot(plan.plan_id)
    assert snapshot is not None
    assert snapshot.payload["plan"]["steps"][2]["status"] == "skipped"


def test_handler_drop_plan_clears_bookkeeping() -> None:
    plan = _make_plan()
    _fail_step(plan, "s1")
    handler, _ = _make_handler(plan)
    handler.apply(_cmd("c-1"))

    handler.drop_plan("plan-cmd")

    assert handler.complete_command("c-1") is False  # index cleared
    # Idempotency keys cleared: the same command_id can be applied again.
    _fail_step(plan, "s1")
    plan.status = PlanStatus.ACTIVE
    again = handler.apply(_cmd("c-1"))
    assert again.status == PlanCommandStatus.ACCEPTED
    handler.drop_plan("unknown")  # silently ignored


def test_post_terminal_drop_then_retry_emits_visible_deltas() -> None:
    """C2 (20260831 adversarial review): the engine reaches a terminal state,
    the integrator follows the documented lifecycle and drops both handler
    and log state, and the user then retries the failed step (FC2: accepted
    on a terminal plan). The retry's events must continue the dropped
    stream's seq — if the rebuilt log restarts at seq 1, an old-cursor
    consumer's replay silently returns an empty delta with no
    needs_snapshot/history_lost flag and the mutation is invisible forever."""
    plan = _make_plan(plan_id="plan-c2")
    _fail_step(plan, "s1")
    handler, log = _make_handler(plan)

    # Simulate the engine lifecycle: events up to a failed terminal.
    log.update_plan(plan)
    log.append("plan-c2", PlanEventType.PLAN_TERMINAL, {"final_status": "failed"})
    assert log.latest_seq("plan-c2") == 1

    # Integrator drops both sides per the documented terminal lifecycle.
    handler.drop_plan("plan-c2")
    log.drop_plan("plan-c2")

    # User retries the failed step post-run (FC2: must be accepted).
    result = handler.apply(_cmd("c-retry-post-drop", plan_id="plan-c2", step_id="s1"))
    assert result.status == PlanCommandStatus.ACCEPTED
    assert plan.steps[0].status == StepStatus.PENDING

    # The retry's events continue the dropped stream (seq 2, 3 — not 1, 2),
    # so the old-cursor (since_seq=1) consumer sees them as a plain delta.
    assert [e.event_seq for e in result.events] == [2, 3]
    replay = log.replay("plan-c2", since_seq=1)
    assert [e.event_seq for e in replay.events] == [2, 3]
    assert replay.needs_snapshot is False
    assert replay.history_lost is False
    # Folding the delta onto the pre-drop view converges to the true state.
    last_transition = replay.events[-1]
    assert last_transition.payload["step_id"] == "s1"
    assert last_transition.payload["status"] == "pending"


def test_skip_cascade_diamond_dependency_dedupes() -> None:
    """Diamond: s4 depends on both s2 and s3 — the closure must contain each
    step exactly once."""
    plan = ExecutionPlan(
        plan_id="plan-diamond",
        original_query="diamond",
        steps=[
            ExecutionStep(step_id="s1", step_number=1, skill_id="t", intent="A"),
            ExecutionStep(
                step_id="s2", step_number=2, skill_id="t", intent="B", dependencies=["s1"]
            ),
            ExecutionStep(
                step_id="s3", step_number=3, skill_id="t", intent="C", dependencies=["s1"]
            ),
            ExecutionStep(
                step_id="s4", step_number=4, skill_id="t", intent="D", dependencies=["s2", "s3"]
            ),
        ],
        workflow_pattern=WorkflowPattern.SEQUENTIAL,
        execution_mode=ExecutionMode.SEQUENTIAL,
    )
    _fail_step(plan, "s1")
    handler, _ = _make_handler(plan)

    result = handler.apply(
        _cmd(
            "c-1",
            plan_id="plan-diamond",
            type=PlanCommandType.SKIP_STEP,
            step_id="s1",
            cascade=True,
        )
    )

    assert result.status == PlanCommandStatus.ACCEPTED
    mutation = result.events[-1]
    assert mutation.payload["step_ids"] == ["s1", "s2", "s3", "s4"]
    assert all(s.status == StepStatus.SKIPPED for s in plan.steps)


def test_skip_cascade_cyclic_plan_terminates() -> None:
    """A dependency cycle (s1 ↔ s2) must not loop the closure forever."""
    plan = ExecutionPlan(
        plan_id="plan-cycle",
        original_query="cycle",
        steps=[
            ExecutionStep(
                step_id="s1", step_number=1, skill_id="t", intent="A", dependencies=["s2"]
            ),
            ExecutionStep(
                step_id="s2", step_number=2, skill_id="t", intent="B", dependencies=["s1"]
            ),
        ],
        workflow_pattern=WorkflowPattern.SEQUENTIAL,
        execution_mode=ExecutionMode.SEQUENTIAL,
    )
    _fail_step(plan, "s1")
    handler, _ = _make_handler(plan)

    result = handler.apply(
        _cmd(
            "c-1", plan_id="plan-cycle", type=PlanCommandType.SKIP_STEP, step_id="s1", cascade=True
        )
    )

    assert result.status == PlanCommandStatus.ACCEPTED
    mutation = result.events[-1]
    assert sorted(mutation.payload["step_ids"]) == ["s1", "s2"]


def _run_c1_round(round_num: int) -> tuple[list[PlanCommandStatus], ExecutionPlan, PlanEventLog]:
    """One retry-vs-cascade-skip race round (C1 invariant stress).

    Builds s1→s2→s3 with s1/s2 failed, races ``retry(s2)`` against
    ``skip(s1, cascade=True)`` on two barrier-synchronized threads, and
    returns (outcomes, plan, log) for invariant checks.
    """
    import threading

    plan = _make_plan(plan_id=f"plan-c1-{round_num}")
    _fail_step(plan, "s1")
    _fail_step(plan, "s2")
    handler, log = _make_handler(plan)

    start = threading.Barrier(2)
    outcomes: list[PlanCommandStatus] = []

    def retry_downstream() -> None:
        start.wait()
        outcomes.append(handler.apply(_cmd("c-retry", plan_id=plan.plan_id, step_id="s2")).status)

    def skip_root_cascade() -> None:
        start.wait()
        outcomes.append(
            handler.apply(
                _cmd(
                    "c-skip",
                    plan_id=plan.plan_id,
                    type=PlanCommandType.SKIP_STEP,
                    step_id="s1",
                    cascade=True,
                )
            ).status
        )

    threads = [
        threading.Thread(target=retry_downstream),
        threading.Thread(target=skip_root_cascade),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    # A future deadlock regression must fail the round, not hang the suite.
    assert all(not thread.is_alive() for thread in threads), "round deadlocked"
    return outcomes, plan, log


def test_concurrent_retry_and_cascade_skip_replay_converges() -> None:
    """C1 (20260831 adversarial review): a retry on a downstream step racing
    a cascading skip must never leave the event log's final per-step view
    diverged from the plan's real status.

    Timing argument: a command's mutation and its event emission are atomic
    under the handler lock, so a competing command can only mutate a step
    AFTER the first command's flush completes — a payload materialized under
    the lock can never be stale at append time, and the last
    step_transition per step always reflects the final status. Before the
    fix (events appended outside the lock) a gated interleaving made the
    stale payload land last and the replayed view diverge permanently; the
    divergence needed that forced window, so this test is a stress
    guardrail over the invariant, not a deterministic reproducer of the
    pre-fix defect."""
    for round_num in range(100):
        outcomes, plan, log = _run_c1_round(round_num)

        # Both commands were legal when issued; neither may deadlock or
        # crash — whatever the interleaving, at least the skip lands.
        assert PlanCommandStatus.ACCEPTED in outcomes
        # The replayed final view must agree with the plan's real state for
        # every step (the C1 divergence made s2's last transition stale).
        replayed = log.replay(plan.plan_id, since_seq=0).events
        last_status: dict[str, str] = {}
        for event in replayed:
            if event.type is PlanEventType.STEP_TRANSITION:
                last_status[event.payload["step_id"]] = event.payload["status"]
        for step in plan.steps:
            assert last_status.get(step.step_id) == step.status.value, (
                f"round {round_num}: replayed view for {step.step_id} is "
                f"{last_status.get(step.step_id)!r}, plan says {step.status.value!r}"
            )


def test_competing_thread_cannot_interleave_during_emission() -> None:
    """Deterministic pin for C1's two-thread variant: emission stays inside
    the handler lock, so a competing ``apply()`` started during the first
    append cannot complete until the outer flush finishes.

    If emission were moved back outside the lock while keeping ``_emitting``,
    the competitor would acquire the lock in the gap, land its events, and
    finish before the outer command's remaining appends — this test would
    see the competitor finish mid-flush and fail.
    """
    import threading
    import time

    plan = _make_plan()
    _fail_step(plan, "s1")
    _fail_step(plan, "s3")
    handler, log = _make_handler(plan)

    original_append = log.append
    competitor_started = threading.Event()
    competitor_finished = threading.Event()
    finished_mid_flush = False
    competitor_events: list = []
    thread_holder: list[threading.Thread] = []

    def competing() -> None:
        competitor_started.set()
        result = handler.apply(_cmd("c-comp", type=PlanCommandType.SKIP_STEP, step_id="s3"))
        competitor_events.extend(result.events)
        competitor_finished.set()

    append_count = 0

    def wrapping_append(*args, **kwargs):
        nonlocal append_count, finished_mid_flush
        if append_count == 0:
            thread = threading.Thread(target=competing)
            thread_holder.append(thread)
            thread.start()
            assert competitor_started.wait(timeout=2)
            # apply() finishes in well under 50ms when the lock is free.
            time.sleep(0.05)
            if competitor_finished.is_set():
                finished_mid_flush = True
        event = original_append(*args, **kwargs)
        append_count += 1
        return event

    log.append = wrapping_append  # type: ignore[method-assign]
    try:
        outer = handler.apply(_cmd("c-outer"))
    finally:
        log.append = original_append  # type: ignore[method-assign]

    assert thread_holder
    thread_holder[0].join(timeout=5)
    assert not thread_holder[0].is_alive(), "competing apply() deadlocked"

    assert outer.status == PlanCommandStatus.ACCEPTED
    assert not finished_mid_flush, (
        "competing apply() completed during outer emission — handler lock "
        "was not held across appends (C1 two-thread interleave is back)"
    )
    assert competitor_finished.is_set()
    assert competitor_events
    assert all(event.event_seq > outer.events[-1].event_seq for event in competitor_events)
