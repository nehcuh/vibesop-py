"""Tests for the plan execution event contract (core/orchestration/events.py).

Covers PlanEventLog semantics (seq allocation, replay window, ring eviction,
subscriber isolation) and WorkflowEngine emission (step transitions,
plan mutations, terminal status) per the observer-UI event contract
(design background: docs/archive/chrome-sidepanel-task-plan-panel.md §3.2).
"""

from __future__ import annotations

import threading

import pytest

from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    StepStatus,
    WorkflowPattern,
)
from vibesop.core.orchestration.events import (
    PlanEventLog,
    PlanEventType,
    plan_snapshot_projection,
)
from vibesop.core.orchestration.workflow_engine import (
    DynamicExecutionResult,
    WorkflowEngine,
)


def _make_plan(
    plan_id: str = "plan-events",
    pattern: WorkflowPattern = WorkflowPattern.SEQUENTIAL,
    num_steps: int = 2,
    **kwargs,
) -> ExecutionPlan:
    """Build a minimal plan with ``num_steps`` pending steps."""
    return ExecutionPlan(
        plan_id=plan_id,
        original_query="event test",
        steps=[
            ExecutionStep(
                step_id=f"s{i + 1}",
                step_number=i + 1,
                skill_id="test",
                intent=f"Task {i + 1}",
                output_as=f"s{i + 1}_result",
            )
            for i in range(num_steps)
        ],
        workflow_pattern=pattern,
        execution_mode=ExecutionMode.SEQUENTIAL,
        **kwargs,
    )


class _ScriptedLLM:
    """Mock LLM returning scripted reorchestration decisions in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def call(self, prompt, **kwargs):
        if self._responses:
            return self._responses.pop(0)
        return '{"decision": "continue", "confidence": 0.5, "reasoning": "default"}'


# --- PlanEventLog unit tests ---


def test_event_seq_monotonic_per_plan() -> None:
    log = PlanEventLog()
    e1 = log.append("p1", PlanEventType.STEP_TRANSITION, {"step_id": "a"})
    e2 = log.append("p1", PlanEventType.STEP_TRANSITION, {"step_id": "a"})
    assert (e1.event_seq, e2.event_seq) == (1, 2)
    assert e1.type == PlanEventType.STEP_TRANSITION
    assert e1.at  # ISO8601 UTC timestamp present
    d = e1.to_dict()
    assert d["type"] == "step_transition" and d["event_seq"] == 1


def test_event_seq_independent_across_plans() -> None:
    log = PlanEventLog()
    log.append("p1", PlanEventType.STEP_TRANSITION, {})
    log.append("p1", PlanEventType.STEP_TRANSITION, {})
    other = log.append("p2", PlanEventType.STEP_TRANSITION, {})
    assert other.event_seq == 1
    assert log.latest_seq("p1") == 2
    assert log.latest_seq("unknown") == 0


def test_replay_within_window_returns_incremental_events() -> None:
    log = PlanEventLog()
    for i in range(4):
        log.append("p1", PlanEventType.STEP_TRANSITION, {"i": i})

    result = log.replay("p1", since_seq=2)

    assert result.needs_snapshot is False
    assert result.snapshot is None
    assert [e.event_seq for e in result.events] == [3, 4]


def test_replay_stale_cursor_returns_snapshot() -> None:
    log = PlanEventLog(window_size=3)
    plan = _make_plan(plan_id="p1")
    log.update_plan(plan)
    for i in range(5):
        log.append("p1", PlanEventType.STEP_TRANSITION, {"i": i})

    result = log.replay("p1", since_seq=1)  # seq 2 was evicted

    assert result.needs_snapshot is True
    assert result.events == []
    assert result.snapshot is not None
    assert result.snapshot.type == PlanEventType.PLAN_SNAPSHOT
    assert result.snapshot.event_seq == 5  # latest allocated seq = new cursor
    assert result.snapshot.payload["plan"]["plan_id"] == "p1"


def test_replay_unknown_plan_is_empty() -> None:
    log = PlanEventLog()
    result = log.replay("nope", since_seq=0)
    assert result.events == [] and result.snapshot is None
    assert result.needs_snapshot is False


def test_ring_window_evicts_oldest_events() -> None:
    log = PlanEventLog(window_size=3)
    for i in range(5):
        log.append("p1", PlanEventType.STEP_TRANSITION, {"i": i})

    result = log.replay("p1", since_seq=2)

    assert [e.event_seq for e in result.events] == [3, 4, 5]
    assert [e.payload["i"] for e in result.events] == [2, 3, 4]


def test_subscriber_notification_and_unsubscribe() -> None:
    log = PlanEventLog()
    received: list[int] = []
    log.subscribe("p1", lambda e: received.append(e.event_seq))

    log.append("p1", PlanEventType.STEP_TRANSITION, {})
    assert received == [1]

    callback = lambda e: received.append(e.event_seq)  # noqa: E731
    log.subscribe("p1", callback)
    log.unsubscribe("p1", callback)
    log.append("p1", PlanEventType.STEP_TRANSITION, {})
    assert received == [1, 2]


def test_subscriber_exception_does_not_propagate() -> None:
    log = PlanEventLog()
    received: list[int] = []

    def broken(event) -> None:
        raise RuntimeError("subscriber exploded")

    log.subscribe("p1", broken)
    log.subscribe("p1", lambda e: received.append(e.event_seq))

    event = log.append("p1", PlanEventType.PLAN_TERMINAL, {})

    assert event.event_seq == 1
    assert received == [1]  # later subscribers still notified


def test_snapshot_projection_excludes_output_text() -> None:
    plan = _make_plan(plan_id="p1", num_steps=1)
    plan.steps[0].result_summary = "full output text that must not leak"

    projection = plan_snapshot_projection(plan)

    assert projection["plan_id"] == "p1"
    assert projection["status"] == "pending"
    assert projection["workflow_pattern"] == "sequential"
    step = projection["steps"][0]
    assert set(step) == {
        "step_id",
        "step_number",
        "intent",
        "status",
        "dynamic_status",
        "loop_iteration",
        "started_at",
        "completed_at",
        "dependencies",
        "parallel_group",
    }
    assert "result_summary" not in step


# --- WorkflowEngine emission tests ---


def test_engine_emits_full_event_sequence_for_sequential_plan() -> None:
    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)
    plan = _make_plan()

    result = engine.run(plan, lambda step: f"out-{step.step_id}")

    assert isinstance(result, DynamicExecutionResult)
    replay = log.replay(plan.plan_id, since_seq=0)
    events = replay.events
    assert [e.event_seq for e in events] == list(range(1, len(events) + 1))

    assert events[0].type == PlanEventType.PLAN_SNAPSHOT
    assert events[0].payload["plan"]["status"] == "active"

    transitions = [e for e in events if e.type == PlanEventType.STEP_TRANSITION]
    assert [(e.payload["step_id"], e.payload["status"]) for e in transitions] == [
        ("s1", "in_progress"),
        ("s1", "completed"),
        ("s2", "in_progress"),
        ("s2", "completed"),
    ]
    # Sequential fallback never sets dynamic_status — key must be omitted.
    assert all("dynamic_status" not in e.payload for e in transitions)

    terminal = events[-1]
    assert terminal.type == PlanEventType.PLAN_TERMINAL
    assert terminal.payload == {
        "final_status": "completed",
        "total_steps_executed": 2,
        "reorchestration_rounds": 0,
    }


def test_engine_terminal_status_failed_and_partial() -> None:
    def fail_all(step):
        raise RuntimeError(f"boom-{step.step_id}")

    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)
    plan = _make_plan(plan_id="p-fail", num_steps=1)
    engine.run(plan, fail_all)
    terminal = log.replay("p-fail", since_seq=0).events[-1]
    assert terminal.payload["final_status"] == "failed"
    failed_transition = log.replay("p-fail", since_seq=0).events[-2]
    assert failed_transition.payload["status"] == "failed"
    assert failed_transition.payload["error"] == "boom-s1"
    # Unified terminal vocabulary: plan.status is not stamped COMPLETED on
    # a failed run (FC2 from the 20260831 three-lane review).
    assert plan.status == PlanStatus.FAILED

    log2 = PlanEventLog()
    engine2 = WorkflowEngine(event_log=log2)
    plan2 = _make_plan(plan_id="p-partial")

    def fail_second(step):
        if step.step_id == "s2":
            raise RuntimeError("second failed")
        return "ok"

    engine2.run(plan2, fail_second)
    terminal2 = log2.replay("p-partial", since_seq=0).events[-1]
    assert terminal2.payload["final_status"] == "partial"
    assert terminal2.payload["total_steps_executed"] == 1
    assert plan2.status == PlanStatus.PARTIAL


def test_engine_without_event_log_is_unchanged() -> None:
    """Regression: event_log=None keeps existing behavior (zero-overhead no-op)."""
    engine = WorkflowEngine()  # no event log
    assert engine._events is None

    plan = _make_plan(plan_id="p-noop", pattern=WorkflowPattern.LOOP_UNTIL_DRY)
    result = engine.run(plan, lambda step: "done")

    assert isinstance(result, DynamicExecutionResult)
    assert result.total_steps_executed == 2
    assert result.final_status == "completed"


def test_engine_emits_loop_back_mutation_and_rewind_transition() -> None:
    log = PlanEventLog()
    llm = _ScriptedLLM(
        [
            '{"decision": "loop_back", "confidence": 0.9, '
            '"reasoning": "redo", "loop_target_step_id": "s1"}'
        ]
    )
    engine = WorkflowEngine(llm_client=llm, event_log=log)
    plan = _make_plan(
        plan_id="p-loop",
        pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        num_steps=1,
        detected_intents=["intent-a", "intent-b"],  # goals-met fast path never fires
        dry_threshold=1,  # default "continue" after the script ends closes the loop
        max_reorchestration_rounds=5,
    )

    engine.run(plan, lambda step: "out")

    events = log.replay("p-loop", since_seq=0).events
    mutations = [e for e in events if e.type == PlanEventType.PLAN_MUTATED]
    assert len(mutations) == 1
    assert mutations[0].payload["decision"] == "loop_back"
    assert mutations[0].payload["loop_back_step_id"] == "s1"

    rewinds = [
        e
        for e in events
        if e.type == PlanEventType.STEP_TRANSITION and e.payload["status"] == "pending"
    ]
    assert len(rewinds) == 1
    assert rewinds[0].payload["dynamic_status"] == "looping"
    assert rewinds[0].payload["loop_iteration"] == 1


def test_engine_emits_append_steps_mutation() -> None:
    log = PlanEventLog()
    llm = _ScriptedLLM(
        [
            '{"decision": "append_steps", "confidence": 0.9, "reasoning": "new work", '
            '"new_sub_tasks": [{"intent": "Fix X", "query": "fix the X"}]}'
        ]
    )
    engine = WorkflowEngine(llm_client=llm, event_log=log)
    plan = _make_plan(
        plan_id="p-append",
        pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        num_steps=1,
        detected_intents=["uncovered-intent"],
        dry_threshold=1,
        max_reorchestration_rounds=5,
    )

    result = engine.run(plan, lambda step: "out")

    assert result.total_steps_executed == 2  # original + appended
    mutations = [
        e
        for e in log.replay("p-append", since_seq=0).events
        if e.type == PlanEventType.PLAN_MUTATED
    ]
    assert len(mutations) == 1
    payload = mutations[0].payload
    assert payload["decision"] == "append_steps"
    assert len(payload["added_steps"]) == 1
    added = payload["added_steps"][0]
    assert added["intent"] == "Fix X"
    assert added["step_number"] == 2
    assert set(added) == {"step_id", "step_number", "intent"}


def test_engine_emits_escalate_mutation() -> None:
    log = PlanEventLog()
    llm = _ScriptedLLM(
        [
            '{"decision": "escalate", "confidence": 0.9, "reasoning": "stuck", '
            '"escalation_message": "Need a human decision"}'
        ]
    )
    engine = WorkflowEngine(llm_client=llm, event_log=log)
    plan = _make_plan(
        plan_id="p-escalate",
        pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        num_steps=2,
        detected_intents=["uncovered-intent"],
        dry_threshold=5,
        max_reorchestration_rounds=5,
    )

    engine.run(plan, lambda step: "out")

    mutations = [
        e
        for e in log.replay("p-escalate", since_seq=0).events
        if e.type == PlanEventType.PLAN_MUTATED
    ]
    assert len(mutations) == 1
    assert mutations[0].payload["decision"] == "escalate"
    assert mutations[0].payload["escalation_message"] == "Need a human decision"


def test_engine_terminate_early_maps_terminal_status() -> None:
    """Degraded (no-LLM) goals-met path emits terminated_early, and the
    terminal vocabulary is unified: event, result object, and plan.status
    all say terminated_early."""
    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)  # no LLM → degraded path
    plan = _make_plan(
        plan_id="p-early",
        pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        num_steps=2,
        detected_intents=["Task 1"],  # covered once s1 completes
        dry_threshold=5,
    )

    result = engine.run(plan, lambda step: "out")

    events = log.replay("p-early", since_seq=0).events
    mutations = [e for e in events if e.type == PlanEventType.PLAN_MUTATED]
    assert len(mutations) == 1
    assert mutations[0].payload["decision"] == "terminate_early"
    assert mutations[0].payload["remaining_step_ids"] == ["s2"]

    terminal = events[-1]
    assert terminal.type == PlanEventType.PLAN_TERMINAL
    assert terminal.payload["final_status"] == "terminated_early"
    assert terminal.payload["total_steps_executed"] == 1
    assert result.final_status == "terminated_early"
    assert plan.status == PlanStatus.TERMINATED_EARLY


def test_engine_prompt_chain_success_emits_terminal(tmp_path) -> None:
    """FC6 (20260831 review): PROMPT_CHAIN success must close the stream its
    snapshot opened — a consumer waiting on plan_terminal would otherwise
    hang on a completed plan."""
    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log, prompt_chain_output_dir=str(tmp_path / "prompts"))
    plan = _make_plan(plan_id="p-chain", pattern=WorkflowPattern.PROMPT_CHAIN)

    result = engine.run(plan, lambda step: "out")

    events = log.replay("p-chain", since_seq=0).events
    assert events, "prompt chain must emit at least snapshot + terminal"
    terminal = events[-1]
    assert terminal.type == PlanEventType.PLAN_TERMINAL
    assert terminal.payload["final_status"] == "completed"
    assert terminal.payload["total_steps_executed"] == 0
    # The result model keeps its own domain discriminator; the plan object
    # agrees with the event vocabulary.
    assert result.final_status == "prompts_generated"
    assert plan.status == PlanStatus.COMPLETED


@pytest.mark.asyncio
async def test_run_async_misuse_closes_stream_with_failed_terminal() -> None:
    """A-F1 (20260831 review): the non-squad ValueError fires after the
    snapshot opened the stream — it must close with a failed terminal."""
    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)
    plan = _make_plan(plan_id="p-misuse", pattern=WorkflowPattern.SEQUENTIAL)

    with pytest.raises(ValueError, match="not a squad pattern"):
        await engine.run_async(plan)

    events = log.replay("p-misuse", since_seq=0).events
    assert [e.type for e in events] == [
        PlanEventType.PLAN_SNAPSHOT,
        PlanEventType.PLAN_TERMINAL,
    ]
    assert events[-1].payload["final_status"] == "failed"
    assert "not a squad pattern" in events[-1].payload["error"]
    assert plan.status == PlanStatus.FAILED


@pytest.mark.asyncio
async def test_run_async_cancellation_closes_stream() -> None:
    """A6 (20260831 review, kimi+grok independently found): asyncio
    cancellation is BaseException — the guard must still close the stream,
    then re-raise so the cancellation propagates unchanged."""
    import asyncio

    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)
    plan = _make_plan(plan_id="p-cancel", pattern=WorkflowPattern.AGENT_SQUAD)

    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError()

    engine._run_agent_squad = cancelled  # type: ignore[method-assign]
    with pytest.raises(asyncio.CancelledError):
        await engine.run_async(plan)

    events = log.replay("p-cancel", since_seq=0).events
    assert events[-1].type == PlanEventType.PLAN_TERMINAL
    assert events[-1].payload["final_status"] == "failed"
    # CancelledError() has an empty str — the guard falls back to the class
    # name so the error payload is never blank.
    assert events[-1].payload["error"] == "CancelledError"
    assert plan.status == PlanStatus.FAILED


def test_run_guarded_keyboard_interrupt_closes_stream() -> None:
    """A6 sync lane: ^C closes the stream, then propagates."""
    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)
    plan = _make_plan(plan_id="p-ki", pattern=WorkflowPattern.SEQUENTIAL)

    def interrupter(step):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        engine.run(plan, interrupter)

    events = log.replay("p-ki", since_seq=0).events
    assert events[-1].type == PlanEventType.PLAN_TERMINAL
    assert events[-1].payload["final_status"] == "failed"
    assert events[-1].payload["error"] == "KeyboardInterrupt"
    assert plan.status == PlanStatus.FAILED


def test_engine_snapshot_reflects_latest_plan_state() -> None:
    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)
    plan = _make_plan(plan_id="p-snap")

    engine.run(plan, lambda step: "out")

    snapshot = log.snapshot("p-snap")
    assert snapshot is not None
    assert snapshot.payload["plan"]["status"] == "completed"
    assert all(s["status"] == StepStatus.COMPLETED.value for s in snapshot.payload["plan"]["steps"])
    assert log.snapshot("unknown-plan") is None


# --- Concurrency, edge cases, and lifecycle ---


def test_concurrent_appends_allocate_gapless_seqs() -> None:
    """Single-writer seq allocation under threads: exactly 1..N, no dup/gap."""
    log = PlanEventLog()

    def produce() -> None:
        for _ in range(50):
            log.append("p1", PlanEventType.STEP_TRANSITION, {})

    threads = [threading.Thread(target=produce) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    events = log.replay("p1", since_seq=0).events
    assert [e.event_seq for e in events] == list(range(1, 201))


def test_replay_since_seq_at_latest_returns_empty() -> None:
    log = PlanEventLog()
    log.append("p1", PlanEventType.STEP_TRANSITION, {})
    log.append("p1", PlanEventType.STEP_TRANSITION, {})

    result = log.replay("p1", since_seq=2)

    assert result.events == []
    assert result.needs_snapshot is False


def test_replay_stale_without_plan_ref_flags_history_lost() -> None:
    """FC7 (20260831 review): a stale cursor with no registered plan
    reference can produce neither deltas nor a snapshot — say so explicitly
    instead of the contradictory needs_snapshot=True + snapshot=None."""
    log = PlanEventLog(window_size=2)
    for i in range(5):
        log.append("p1", PlanEventType.STEP_TRANSITION, {"i": i})

    result = log.replay("p1", since_seq=1)

    assert result.history_lost is True
    assert result.needs_snapshot is False
    assert result.snapshot is None
    assert result.events == []


def test_registered_plan_with_zero_events_replay_and_snapshot() -> None:
    log = PlanEventLog()
    log.update_plan(_make_plan(plan_id="p1"))

    replay = log.replay("p1", since_seq=0)
    assert replay.events == []
    assert replay.needs_snapshot is False

    snapshot = log.snapshot("p1")
    assert snapshot is not None
    assert snapshot.event_seq == 0
    assert snapshot.type == PlanEventType.PLAN_SNAPSHOT


def test_drop_plan_clears_all_state() -> None:
    log = PlanEventLog()
    received: list[int] = []
    log.subscribe("p1", lambda e: received.append(e.event_seq))
    log.update_plan(_make_plan(plan_id="p1"))
    log.append("p1", PlanEventType.STEP_TRANSITION, {})

    log.drop_plan("p1")

    assert log.latest_seq("p1") == 0
    assert log.replay("p1", since_seq=0).events == []
    assert log.snapshot("p1") is None
    # Subscribers were dropped too: a fresh append does not notify them.
    log.append("p1", PlanEventType.STEP_TRANSITION, {})
    assert received == [1]
    log.drop_plan("unknown")  # silently ignored


def test_event_to_dict_carries_schema_version_and_is_json_ready() -> None:
    import json

    log = PlanEventLog()
    event = log.append("p1", PlanEventType.PLAN_TERMINAL, {"final_status": "completed"})

    data = event.to_dict()
    assert data["schema_version"] == 1
    assert data["type"] == "plan_terminal"
    json.dumps(data)  # must not raise


# --- Crash / escalate / verification-step / squad terminal coverage ---


def test_engine_crash_emits_failed_terminal_then_reraises() -> None:
    """An unexpected crash mid-run closes the stream with a failed terminal;
    the original exception propagates unchanged."""
    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)
    plan = _make_plan(plan_id="p-crash")

    def boom(_plan, _executor):
        raise RuntimeError("engine exploded")

    engine._run_sequential = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="engine exploded"):
        engine.run(plan, lambda step: "x")

    events = log.replay("p-crash", since_seq=0).events
    terminal = events[-1]
    assert terminal.type == PlanEventType.PLAN_TERMINAL
    assert terminal.payload["final_status"] == "failed"
    assert terminal.payload["error"] == "engine exploded"
    # The plan object agrees with the event stream (no stuck ACTIVE).
    assert plan.status == PlanStatus.FAILED


def test_engine_escalate_terminal_is_terminated_early_with_message() -> None:
    """Escalation must not surface as 'completed': the terminal event maps to
    terminated_early and carries the escalation message."""
    log = PlanEventLog()
    llm = _ScriptedLLM(
        [
            '{"decision": "escalate", "confidence": 0.9, "reasoning": "stuck", '
            '"escalation_message": "Need a human decision"}'
        ]
    )
    engine = WorkflowEngine(llm_client=llm, event_log=log)
    plan = _make_plan(
        plan_id="p-esc-term",
        pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        num_steps=2,
        detected_intents=["uncovered-intent"],
        dry_threshold=5,
        max_reorchestration_rounds=5,
    )

    engine.run(plan, lambda step: "out")

    terminal = log.replay("p-esc-term", since_seq=0).events[-1]
    assert terminal.type == PlanEventType.PLAN_TERMINAL
    assert terminal.payload["final_status"] == "terminated_early"
    assert terminal.payload["escalation_message"] == "Need a human decision"
    assert plan.status == PlanStatus.TERMINATED_EARLY


def test_verification_step_emits_skipped_transition() -> None:
    """Verification steps are not executed in the loop; they surface as an
    explicit skipped transition instead of staying pending forever."""
    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)
    plan = _make_plan(
        plan_id="p-verify",
        pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        num_steps=1,
        # Uncovered intent + high dry threshold so the loop reaches step 2
        # instead of terminating early after step 1.
        detected_intents=["uncovered-intent"],
        dry_threshold=5,
    )
    plan.steps.append(
        ExecutionStep(
            step_id="verify",
            step_number=2,
            skill_id="t",
            intent="Verify",
            is_verification_step=True,
        )
    )

    engine.run(plan, lambda step: "out")

    verify_step = plan.steps[1]
    assert verify_step.status == StepStatus.SKIPPED
    transitions = [
        e
        for e in log.replay("p-verify", since_seq=0).events
        if e.type == PlanEventType.STEP_TRANSITION and e.payload["step_id"] == "verify"
    ]
    assert len(transitions) == 1
    assert transitions[0].payload["status"] == "skipped"


def _make_squad_plan(plan_id: str) -> ExecutionPlan:
    """Minimal squad plan (same shape as test_workflow_engine's)."""
    from vibesop.core.models import AgentRole, AgentSquad, SquadStep

    squad = AgentSquad(
        squad_id="squad-ev",
        roles=[
            AgentRole(role_id="implementer", name="实现者", required_skills=["coding"]),
            AgentRole(role_id="reviewer", name="审查者", required_skills=["review"]),
        ],
        steps=[
            SquadStep(step_id="impl", role_id="implementer", skill_ids=["coding"]),
            SquadStep(step_id="rev", role_id="reviewer", skill_ids=["review"], input_from=["impl"]),
        ],
        collaboration_protocol="review_gate",
        lead_role="reviewer",
        max_rounds=2,
        execution_order=["impl", "rev"],
    )
    return ExecutionPlan(
        plan_id=plan_id,
        original_query="implement and review",
        workflow_pattern=WorkflowPattern.AGENT_SQUAD,
        metadata={"agent_squad": squad.to_dict()},
    )


@pytest.mark.asyncio
async def test_squad_run_emits_plan_terminal() -> None:
    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)
    plan = _make_squad_plan("p-squad")

    async def executor(step, context):
        return {"step_id": step.step_id, "role_id": step.role_id, "content": "x"}

    await engine.run_async(plan, executor=executor)

    events = log.replay("p-squad", since_seq=0).events
    assert events[0].type == PlanEventType.PLAN_SNAPSHOT
    terminal = events[-1]
    assert terminal.type == PlanEventType.PLAN_TERMINAL
    assert terminal.payload["final_status"] == "completed"
    assert terminal.payload["total_steps_executed"] == 2
    assert terminal.payload["reorchestration_rounds"] == 1


@pytest.mark.asyncio
async def test_squad_crash_emits_failed_terminal() -> None:
    log = PlanEventLog()
    engine = WorkflowEngine(event_log=log)
    plan = _make_squad_plan("p-squad-crash")

    async def executor(step, context):
        raise RuntimeError("member crashed")

    with pytest.raises(RuntimeError, match="member crashed"):
        await engine.run_async(plan, executor=executor)

    terminal = log.replay("p-squad-crash", since_seq=0).events[-1]
    assert terminal.type == PlanEventType.PLAN_TERMINAL
    assert terminal.payload["final_status"] == "failed"
    assert terminal.payload["error"] == "member crashed"
    assert plan.status == PlanStatus.FAILED


def test_contract_types_exported_from_package() -> None:
    """The v8.3 event/command contract types are importable from the
    orchestration package — integrators must not reach into submodules."""
    import vibesop.core.orchestration as orch

    for name in (
        "PlanEvent",
        "PlanEventLog",
        "PlanEventType",
        "ReplayResult",
        "PlanCommand",
        "PlanCommandHandler",
        "PlanCommandResult",
        "PlanCommandStatus",
        "PlanCommandType",
    ):
        assert hasattr(orch, name), f"{name} missing from vibesop.core.orchestration"
        assert name in orch.__all__
