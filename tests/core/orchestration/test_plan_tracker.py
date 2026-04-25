"""Tests for PlanTracker — persistent execution plan state management."""

from __future__ import annotations

import json
import tempfile
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

        lines = jsonl_path.read_text().strip().split("\n")
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
