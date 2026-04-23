"""Tests for PlanExecutor."""

from __future__ import annotations

import pytest

from vibesop.agent.runtime.plan_executor import PlanExecutor
from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    StepStatus,
)


class TestPlanExecutor:
    """Test execution plan guide generation."""

    def test_build_guide_basic(self) -> None:
        executor = PlanExecutor()
        plan = ExecutionPlan(
            plan_id="plan-1",
            original_query="analyze architecture",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="superpowers-architect",
                    intent="Analyze architecture",
                    input_query="Analyze the architecture",
                    output_as="analysis",
                ),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
            status=PlanStatus.PENDING,
        )

        guide = executor.build_guide(plan)

        assert "执行计划" in guide.prompt
        assert "superpowers-architect" in guide.prompt
        assert "步骤 1 完成" in guide.step_markers
        assert len(guide.step_markers) == 1

    def test_build_guide_parallel_steps(self) -> None:
        executor = PlanExecutor()
        plan = ExecutionPlan(
            plan_id="plan-2",
            original_query="test frontend and backend",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="test-frontend",
                    intent="Test frontend",
                    input_query="Test frontend",
                    output_as="frontend_result",
                    can_parallel=True,
                ),
                ExecutionStep(
                    step_id="s2",
                    step_number=2,
                    skill_id="test-backend",
                    intent="Test backend",
                    input_query="Test backend",
                    output_as="backend_result",
                    can_parallel=True,
                ),
            ],
            execution_mode=ExecutionMode.PARALLEL,
            status=PlanStatus.PENDING,
        )

        guide = executor.build_guide(plan)

        assert "并行" in guide.prompt
        assert "test-frontend" in guide.prompt
        assert "test-backend" in guide.prompt
        # Both steps in same parallel group → one marker for the group
        assert len(guide.step_markers) == 1
        assert "并行组 1" in guide.step_markers[0]

    def test_build_guide_sequential_with_deps(self) -> None:
        executor = PlanExecutor()
        plan = ExecutionPlan(
            plan_id="plan-3",
            original_query="analyze and optimize",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="superpowers-architect",
                    intent="Analyze",
                    input_query="Analyze",
                    output_as="analysis",
                ),
                ExecutionStep(
                    step_id="s2",
                    step_number=2,
                    skill_id="superpowers-optimize",
                    intent="Optimize",
                    input_query="Optimize",
                    output_as="optimization",
                    dependencies=["s1"],
                ),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
            status=PlanStatus.PENDING,
        )

        guide = executor.build_guide(plan)

        assert "依赖" in guide.prompt
        assert "analysis" in guide.prompt
        assert "optimization" in guide.prompt
        assert len(guide.step_markers) == 2

    def test_step_transition_prompt(self) -> None:
        executor = PlanExecutor()
        plan = ExecutionPlan(
            plan_id="plan-4",
            original_query="step test",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="skill-a",
                    intent="Step A",
                    input_query="Do A",
                    status=StepStatus.COMPLETED,
                ),
                ExecutionStep(
                    step_id="s2",
                    step_number=2,
                    skill_id="skill-b",
                    intent="Step B",
                    input_query="Do B",
                    status=StepStatus.PENDING,
                ),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

        transition = executor.build_step_transition_prompt(plan, 1)

        assert "步骤 1 已完成" in transition
        assert "skill-b" in transition
        assert "步骤 2" in transition

    def test_step_transition_all_done(self) -> None:
        executor = PlanExecutor()
        plan = ExecutionPlan(
            plan_id="plan-5",
            original_query="done",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="skill-a",
                    intent="Step A",
                    input_query="Do A",
                    status=StepStatus.COMPLETED,
                ),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

        transition = executor.build_step_transition_prompt(plan, 1)

        assert "所有步骤已完成" in transition
        assert "汇总结果" in transition

    def test_progress_summary(self) -> None:
        executor = PlanExecutor()
        plan = ExecutionPlan(
            plan_id="plan-6",
            original_query="progress test",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="skill-a",
                    intent="A",
                    input_query="A",
                    status=StepStatus.COMPLETED,
                ),
                ExecutionStep(
                    step_id="s2",
                    step_number=2,
                    skill_id="skill-b",
                    intent="B",
                    input_query="B",
                    status=StepStatus.IN_PROGRESS,
                ),
                ExecutionStep(
                    step_id="s3",
                    step_number=3,
                    skill_id="skill-c",
                    intent="C",
                    input_query="C",
                    status=StepStatus.PENDING,
                ),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

        summary = executor.build_progress_summary(plan)

        assert "1/3 完成" in summary
        assert "✅" in summary
        assert "🔄" in summary
        assert "⏳" in summary
        assert "skill-a" in summary
        assert "skill-b" in summary
        assert "skill-c" in summary

    def test_execution_rules_in_prompt(self) -> None:
        executor = PlanExecutor()
        plan = ExecutionPlan(
            plan_id="plan-7",
            original_query="rules test",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="test-skill",
                    intent="Test",
                    input_query="Test",
                ),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

        guide = executor.build_guide(plan)

        assert "每步必须读取 SKILL.md" in guide.prompt
        assert "严格按顺序" in guide.prompt
        assert "明确报告" in guide.prompt
        assert "失败处理" in guide.prompt
