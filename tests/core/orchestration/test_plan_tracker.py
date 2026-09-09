"""Tests for PlanTracker — persistent execution plan state management."""

from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

import pytest

from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    StepStatus,
)
from vibesop.core.orchestration.plan_tracker import PlanTracker


class TestPlanTracker:
    """Core plan persistence tests."""

    @pytest.fixture
    def tracker(self) -> PlanTracker:
        with tempfile.TemporaryDirectory() as tmp:
            yield PlanTracker(storage_dir=tmp)

    def _make_plan(self, steps: list[ExecutionStep] | None = None) -> ExecutionPlan:
        if steps is None:
            steps = [
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="review",
                    intent="code review",
                ),
            ]
        return ExecutionPlan(
            plan_id="plan-001",
            original_query="review my code",
            steps=steps,
            detected_intents=["code_review"],
            reasoning="Step 1: code_review → review (100%)",
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

    def test_create_and_get_plan(self, tracker: PlanTracker) -> None:
        plan = self._make_plan()
        tracker.create_plan(plan)

        retrieved = tracker.get_plan("plan-001")
        assert retrieved is not None
        assert retrieved.plan_id == "plan-001"
        assert len(retrieved.steps) == 1
        assert retrieved.steps[0].skill_id == "review"

    def test_get_plan_not_found(self, tracker: PlanTracker) -> None:
        assert tracker.get_plan("nonexistent") is None

    def test_list_plans(self, tracker: PlanTracker) -> None:
        for i in range(3):
            plan = ExecutionPlan(
                plan_id=f"plan-{i}",
                original_query=f"query {i}",
                steps=[ExecutionStep(step_id=f"s{i}", step_number=1, skill_id="review")],
                execution_mode=ExecutionMode.SEQUENTIAL,
            )
            tracker.create_plan(plan)

        plans = tracker.list_plans(limit=3)
        assert len(plans) == 3

    def test_list_plans_respects_limit(self, tracker: PlanTracker) -> None:
        for i in range(5):
            plan = ExecutionPlan(
                plan_id=f"plan-{i}",
                steps=[ExecutionStep(step_id=f"s{i}", step_number=1, skill_id="review")],
                execution_mode=ExecutionMode.SEQUENTIAL,
            )
            tracker.create_plan(plan)

        plans = tracker.list_plans(limit=2)
        assert len(plans) == 2

    def test_update_step_status(self, tracker: PlanTracker) -> None:
        plan = ExecutionPlan(
            plan_id="plan-002",
            steps=[
                ExecutionStep(step_id="a1", step_number=1, skill_id="review"),
                ExecutionStep(step_id="a2", step_number=2, skill_id="test"),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )
        tracker.create_plan(plan)

        tracker.update_step_status("plan-002", "a1", StepStatus.COMPLETED, "All good")
        tracker.update_step_status("plan-002", "a2", StepStatus.COMPLETED)

        updated = tracker.get_plan("plan-002")
        assert updated is not None
        assert updated.steps[0].status == StepStatus.COMPLETED
        assert updated.steps[0].result_summary == "All good"
        assert updated.steps[1].status == StepStatus.COMPLETED
        assert updated.status == PlanStatus.COMPLETED

    def test_get_active_plan(self, tracker: PlanTracker) -> None:
        completed = self._make_plan()
        completed.plan_id = "done"
        completed.status = PlanStatus.COMPLETED
        tracker.create_plan(completed)

        active = ExecutionPlan(
            plan_id="running",
            steps=[ExecutionStep(step_id="x1", step_number=1, skill_id="debug")],
            execution_mode=ExecutionMode.SEQUENTIAL,
            status=PlanStatus.ACTIVE,
        )
        tracker.create_plan(active)

        result = tracker.get_active_plan()
        assert result is not None
        assert result.plan_id == "running"

    def test_get_active_plan_none_when_all_complete(self, tracker: PlanTracker) -> None:
        plan = self._make_plan()
        plan.status = PlanStatus.COMPLETED
        tracker.create_plan(plan)
        assert tracker.get_active_plan() is None

    def test_jsonl_append_format(self, tracker: PlanTracker) -> None:
        plan = self._make_plan()
        tracker.create_plan(plan)

        jsonl_path = Path(tracker.storage_path)
        assert jsonl_path.exists(), "JSONL file must be created"

        lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        data = json.loads(lines[0])
        assert data["plan_id"] == "plan-001"
        assert "steps" in data
        assert "execution_mode" in data

    def test_tracker_handles_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tracker = PlanTracker(storage_dir=tmp)
            # File doesn't exist yet — should handle gracefully
            assert tracker.get_plan("anything") is None
            assert tracker.list_plans() == []
            assert tracker.get_active_plan() is None


class TestCorruptJsonlLineTolerance:
    """Uniform per-line semantics: bad lines are skipped, never crash the
    reader, and never mask an earlier valid version of the same plan."""

    @pytest.fixture
    def tracker(self) -> PlanTracker:
        with tempfile.TemporaryDirectory() as tmp:
            yield PlanTracker(storage_dir=tmp)

    def _make_plan(self, plan_id: str = "plan-001") -> ExecutionPlan:
        return ExecutionPlan(
            plan_id=plan_id,
            original_query="review my code",
            steps=[
                ExecutionStep(step_id="s1", step_number=1, skill_id="review"),
                ExecutionStep(step_id="s2", step_number=2, skill_id="test"),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

    def _append_raw(self, tracker: PlanTracker, text: str) -> None:
        with Path(tracker.storage_path).open("a", encoding="utf-8") as f:
            f.write(text + "\n")

    def test_truncated_json_does_not_hide_last_valid_version(self, tracker: PlanTracker) -> None:
        """Real payload: valid to_dict line + truncated copy of the same line.
        get_plan must return the last valid version, and get/list must agree."""
        plan = self._make_plan()
        tracker.create_plan(plan)
        serialized = json.dumps(plan.to_dict(), ensure_ascii=False)
        self._append_raw(tracker, serialized[: len(serialized) // 2])

        retrieved = tracker.get_plan("plan-001")
        assert retrieved is not None
        assert retrieved.plan_id == "plan-001"
        assert [p.plan_id for p in tracker.list_plans(limit=10)] == ["plan-001"]

    def test_legal_json_non_object_lines_are_skipped(self, tracker: PlanTracker) -> None:
        tracker.create_plan(self._make_plan())
        for junk in ("[1,2,3]", '"a string"', "42", "null", "true"):
            self._append_raw(tracker, junk)

        retrieved = tracker.get_plan("plan-001")
        assert retrieved is not None
        assert retrieved.plan_id == "plan-001"
        assert [p.plan_id for p in tracker.list_plans(limit=10)] == ["plan-001"]

    def test_corrupted_schema_does_not_overwrite_last_valid_version(
        self, tracker: PlanTracker
    ) -> None:
        """Schema-corrupted object appended AFTER a valid update must be
        skipped — the last valid version (with the step update) wins."""
        tracker.create_plan(self._make_plan())
        tracker.update_step_status("plan-001", "s1", StepStatus.COMPLETED, "done")

        self._append_raw(
            tracker,
            json.dumps({"plan_id": "plan-001", "steps": "not-a-list", "status": "completed"}),
        )
        self._append_raw(tracker, json.dumps({"plan_id": 123, "steps": []}))

        retrieved = tracker.get_plan("plan-001")
        assert retrieved is not None
        assert retrieved.steps[0].status == StepStatus.COMPLETED
        assert retrieved.steps[0].result_summary == "done"
        assert [p.plan_id for p in tracker.list_plans(limit=10)] == ["plan-001"]

    def test_corrupt_lines_do_not_abort_later_lines(self, tracker: PlanTracker) -> None:
        tracker.create_plan(self._make_plan("plan-A"))
        self._append_raw(tracker, json.dumps({"plan_id": "plan-A", "steps": "garbage"}))
        self._append_raw(tracker, '{"truncated')
        tracker.create_plan(self._make_plan("plan-B"))

        ids = [p.plan_id for p in tracker.list_plans(limit=10)]
        assert ids == ["plan-A", "plan-B"]
        assert tracker.get_plan("plan-B") is not None

    def test_load_plans_for_trace_skips_corrupt_lines(self, tracker: PlanTracker) -> None:
        """load_plans_for_trace uses the same per-line semantics."""
        from vibesop.core.orchestration.plan_tracker import load_plans_for_trace

        plan = self._make_plan("plan-t")
        plan.metadata["trace_id"] = "trace-1"
        tracker.create_plan(plan)
        serialized = json.dumps(plan.to_dict(), ensure_ascii=False)
        self._append_raw(tracker, serialized[: len(serialized) // 2])
        self._append_raw(tracker, "[1,2,3]")
        self._append_raw(tracker, json.dumps({"plan_id": "plan-t", "steps": "garbage"}))

        result = load_plans_for_trace("trace-1", storage_dir=Path(tracker.storage_path).parent)
        assert [p.plan_id for p in result] == ["plan-t"]

    def test_concurrent_updates_to_different_steps_both_persist(self, tracker: PlanTracker) -> None:
        """Two threads updating different steps of the same plan, released
        simultaneously by a barrier (no sleep-based timing bets). The
        exclusive-lock read-modify-write must preserve both updates."""
        tracker.create_plan(self._make_plan("plan-race"))
        barrier = threading.Barrier(3)

        def worker(step_id: str, summary: str) -> None:
            barrier.wait()
            tracker.update_step_status("plan-race", step_id, StepStatus.COMPLETED, summary)

        t1 = threading.Thread(target=worker, args=("s1", "first done"))
        t2 = threading.Thread(target=worker, args=("s2", "second done"))
        t1.start()
        t2.start()
        barrier.wait()
        t1.join(timeout=30)
        t2.join(timeout=30)
        assert not t1.is_alive() and not t2.is_alive()

        final = tracker.get_plan("plan-race")
        assert final is not None
        by_id = {s.step_id: s for s in final.steps}
        assert by_id["s1"].status == StepStatus.COMPLETED
        assert by_id["s1"].result_summary == "first done"
        assert by_id["s2"].status == StepStatus.COMPLETED
        assert by_id["s2"].result_summary == "second done"


@pytest.mark.parametrize("tail", [b'{"plan_id":', b"\xff", b"\xe4\xb8"])
def test_torn_tail_cannot_swallow_following_update(tmp_path, tail):
    from vibesop.core.orchestration.plan_tracker import load_plans_for_trace

    tracker = PlanTracker(tmp_path)
    plan = ExecutionPlan(
        plan_id="torn",
        original_query="test",
        steps=[ExecutionStep(step_id="s1", step_number=1, skill_id="test/skill")],
        metadata={"trace_id": "trace-torn"},
    )
    tracker.create_plan(plan)
    with tracker.storage_path.open("ab") as handle:
        handle.write(tail)
    tracker.update_step_status(plan.plan_id, "s1", StepStatus.COMPLETED, "verified update")
    by_id = tracker.get_plan(plan.plan_id)
    listed = tracker.list_plans()
    traced = load_plans_for_trace("trace-torn", tmp_path)
    assert by_id is not None
    for restored in [by_id, *listed, *traced]:
        assert restored.steps[0].status == StepStatus.COMPLETED
        assert restored.steps[0].result_summary == "verified update"
    assert len(listed) == len(traced) == 1


def test_read_only_store_can_be_read_but_updates_require_lock(tmp_path, monkeypatch):
    import vibesop.core.orchestration.plan_tracker as storage

    tracker = PlanTracker(tmp_path)
    plan = ExecutionPlan(
        plan_id="read-only",
        original_query="test",
        steps=[ExecutionStep(step_id="s1", step_number=1, skill_id="test/skill")],
        metadata={"trace_id": "read-only-trace"},
    )
    tracker.create_plan(plan)
    original = tracker.storage_path.read_bytes()

    def refuse_lock(*args, **kwargs):
        raise PermissionError("read-only mount")

    monkeypatch.setattr(storage, "cross_process_lock", refuse_lock)
    assert tracker.get_plan(plan.plan_id).plan_id == plan.plan_id
    assert len(tracker.list_plans()) == 1
    assert len(storage.load_plans_for_trace("read-only-trace", tmp_path)) == 1
    with pytest.raises(PermissionError):
        tracker.update_step_status(plan.plan_id, "s1", StepStatus.COMPLETED)
    assert tracker.storage_path.read_bytes() == original
