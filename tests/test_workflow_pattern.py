"""Tests for WorkflowPattern-aware plan generation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from vibesop.core.models import ExecutionMode, ExecutionPlan, WorkflowPattern
from vibesop.core.orchestration.plan_builder import PlanBuilder
from vibesop.core.orchestration.task_decomposer import SubTask


class FakeRouter:
    """Minimal fake router for PlanBuilder tests."""

    def __init__(self, skill_id="test/skill"):
        self._skill_id = skill_id

    def _single_skill_route(self, query, candidates=None, context=None):
        from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute

        result = RoutingResult()
        result.primary = SkillRoute(
            skill_id=self._skill_id,
            confidence=0.9,
            layer=RoutingLayer.KEYWORD,
        )
        return result


class TestPlanBuilderPatternAware:
    """PlanBuilder pattern-aware execution plan tests."""

    def _make_builder(self, skill_id="test/skill"):
        router = FakeRouter(skill_id=skill_id)
        return PlanBuilder(router)

    def test_sequential_pattern_default(self):
        builder = self._make_builder()
        sub_tasks = [
            SubTask(intent="step 1", query="do step 1"),
            SubTask(intent="step 2", query="do step 2"),
        ]
        # Default pattern (SEQUENTIAL) preserves keyword-detected mode.
        # "test query" has no sequential keywords but multiple tasks → PARALLEL.
        plan = builder.build_plan("test query", sub_tasks)

        assert plan.workflow_pattern == WorkflowPattern.SEQUENTIAL
        # Default pattern preserves keyword detection: parallel for multi-task
        assert plan.execution_mode == ExecutionMode.PARALLEL
        assert len(plan.steps) == 2

    def test_parallel_pattern_clears_dependencies(self):
        builder = self._make_builder()
        sub_tasks = [
            SubTask(intent="task A", query="do A"),
            SubTask(intent="task B", query="do B"),
        ]
        plan = builder.build_plan(
            "test query", sub_tasks, workflow_pattern=WorkflowPattern.PARALLEL
        )

        assert plan.workflow_pattern == WorkflowPattern.PARALLEL
        assert plan.execution_mode == ExecutionMode.PARALLEL
        # All steps should have no dependencies and can_parallel=True
        for step in plan.steps:
            assert step.dependencies == []
            assert step.can_parallel is True

    def test_fan_out_adds_synthesise_step(self):
        builder = self._make_builder()
        sub_tasks = [
            SubTask(intent="find bugs", query="find bugs"),
            SubTask(intent="check performance", query="check performance"),
        ]
        plan = builder.build_plan(
            "test query", sub_tasks, workflow_pattern=WorkflowPattern.FAN_OUT
        )

        assert plan.workflow_pattern == WorkflowPattern.FAN_OUT
        assert len(plan.steps) == 3  # 2 sub-tasks + 1 synthesise step
        # First two steps: no deps, parallel
        assert plan.steps[0].dependencies == []
        assert plan.steps[1].dependencies == []
        # Synthesise step depends on both
        synth = plan.steps[2]
        assert synth.skill_id == "builtin/slash-orchestrate"
        assert synth.intent == "综合所有并行步骤的结果"
        assert set(synth.dependencies) == {plan.steps[0].step_id, plan.steps[1].step_id}

    def test_fan_out_single_task_no_synthesise(self):
        builder = self._make_builder()
        sub_tasks = [SubTask(intent="only task", query="do one thing")]
        plan = builder.build_plan(
            "test query", sub_tasks, workflow_pattern=WorkflowPattern.FAN_OUT
        )

        # Single task: no synthesise step added
        assert len(plan.steps) == 1

    def test_adversarial_adds_verify_step(self):
        builder = self._make_builder()
        sub_tasks = [
            SubTask(intent="fix bug", query="fix the bug"),
        ]
        plan = builder.build_plan(
            "test query", sub_tasks, workflow_pattern=WorkflowPattern.ADVERSARIAL
        )

        assert plan.workflow_pattern == WorkflowPattern.ADVERSARIAL
        assert len(plan.steps) == 2  # 1 sub-task + 1 verify step
        verify = plan.steps[1]
        assert verify.skill_id == "gstack/investigate"
        assert verify.intent == "独立验证执行结果"
        assert verify.dependencies == [plan.steps[0].step_id]

    def test_adversarial_empty_steps(self):
        builder = self._make_builder()
        plan = builder.build_plan(
            "test query", [], workflow_pattern=WorkflowPattern.ADVERSARIAL
        )

        assert len(plan.steps) == 0

    def test_execution_mode_override(self):
        builder = self._make_builder()
        sub_tasks = [
            SubTask(intent="task A", query="do A"),
        ]
        # Even with "parallel" keywords in query, adversarial pattern forces sequential
        plan = builder.build_plan(
            "do A and also do B", sub_tasks, workflow_pattern=WorkflowPattern.ADVERSARIAL
        )
        assert plan.execution_mode == ExecutionMode.SEQUENTIAL


class TestWorkflowPatternEnum:
    """WorkflowPattern enum validation tests."""

    def test_valid_patterns(self):
        assert WorkflowPattern("sequential") == WorkflowPattern.SEQUENTIAL
        assert WorkflowPattern("parallel") == WorkflowPattern.PARALLEL
        assert WorkflowPattern("fan_out") == WorkflowPattern.FAN_OUT
        assert WorkflowPattern("adversarial") == WorkflowPattern.ADVERSARIAL

    def test_invalid_pattern_raises(self):
        with pytest.raises(ValueError):
            WorkflowPattern("invalid")

    def test_pattern_values(self):
        values = {p.value for p in WorkflowPattern}
        assert values == {"sequential", "parallel", "fan_out", "adversarial"}
