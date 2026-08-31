"""Tests for the control-plane command contract (commands.py).

Covers retry/skip validation, idempotency, in-flight rejection, skip
dependency semantics, event payloads, and the complete_command lifecycle
(design background: docs/archive/chrome-sidepanel-task-plan-panel.md §2.6/§3.2).
"""

from __future__ import annotations

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

    no_step = handler.apply(_cmd("c-2", step_id="nope"))
    assert no_step.status == PlanCommandStatus.REJECTED_INVALID_STATE


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
    deadlock on the handler lock. Events are emitted outside the lock."""
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
        # Skip a *different* failed step from inside the callback (the
        # in-flight gate blocks same-step commands by design).
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

    assert outer_status == [PlanCommandStatus.ACCEPTED]
    assert nested_results, "subscriber callback never ran"
    assert nested_results[0] == PlanCommandStatus.ACCEPTED


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
