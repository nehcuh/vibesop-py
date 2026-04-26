"""Tests for Agent Execution Protocol."""

from __future__ import annotations

from vibesop.agent.execution_protocol import (
    ExecutionProtocol,
    PlanExecutionResult,
    StepResult,
    StepResultStatus,
)
from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    StepStatus,
)


class TestExecutionProtocol:
    def test_plan_to_instructions_includes_all_steps(self):
        plan = ExecutionPlan(
            plan_id="test-001",
            original_query="分析架构然后写测试",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="superpowers-architect",
                    intent="架构分析",
                    input_query="分析项目架构",
                    output_as="step_1_result",
                    status=StepStatus.PENDING,
                ),
                ExecutionStep(
                    step_id="s2",
                    step_number=2,
                    skill_id="superpowers-tdd",
                    intent="测试生成",
                    input_query="生成单元测试",
                    output_as="step_2_result",
                    status=StepStatus.PENDING,
                ),
            ],
            detected_intents=["架构分析", "测试生成"],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )
        instructions = ExecutionProtocol.plan_to_agent_instructions(plan)
        assert "superpowers-architect" in instructions
        assert "superpowers-tdd" in instructions
        assert "SEQUENTIAL" in instructions.upper() or "sequential" in instructions

    def test_plan_to_json_serializable(self):
        import json

        plan = ExecutionPlan(
            plan_id="test-002",
            original_query="review code",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="gstack-review",
                    intent="代码审查",
                    input_query="review the code",
                    output_as="step_1_result",
                    status=StepStatus.PENDING,
                )
            ],
            detected_intents=["代码审查"],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )
        data = ExecutionProtocol.plan_to_json(plan)
        json_str = json.dumps(data)
        assert "test-002" in json_str
        assert "gstack-review" in json_str

    def test_validate_results_matches_all_steps(self):
        plan = ExecutionPlan(
            plan_id="test-003",
            original_query="test",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="skill-a",
                    intent="task a",
                    input_query="do a",
                    output_as="a",
                    status=StepStatus.PENDING,
                ),
                ExecutionStep(
                    step_id="s2",
                    step_number=2,
                    skill_id="skill-b",
                    intent="task b",
                    input_query="do b",
                    output_as="b",
                    status=StepStatus.PENDING,
                ),
            ],
            detected_intents=["a", "b"],
            execution_mode=ExecutionMode.PARALLEL,
        )
        results = PlanExecutionResult(
            plan_id="test-003",
            results=[
                StepResult(
                    step_id="s1",
                    skill_id="skill-a",
                    status=StepResultStatus.SUCCESS,
                ),
                StepResult(
                    step_id="s2",
                    skill_id="skill-b",
                    status=StepResultStatus.SUCCESS,
                ),
            ],
        )
        assert ExecutionProtocol.validate_results(plan, results)

    def test_validate_results_detects_missing_steps(self):
        plan = ExecutionPlan(
            plan_id="test-004",
            original_query="test",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="skill-a",
                    intent="task a",
                    input_query="do a",
                    output_as="a",
                    status=StepStatus.PENDING,
                ),
            ],
            detected_intents=["a"],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )
        results = PlanExecutionResult(plan_id="test-004", results=[])
        assert not ExecutionProtocol.validate_results(plan, results)

    def test_plan_execution_result_success_count(self):
        results = PlanExecutionResult(
            plan_id="test",
            results=[
                StepResult(step_id="s1", skill_id="a", status=StepResultStatus.SUCCESS),
                StepResult(step_id="s2", skill_id="b", status=StepResultStatus.FAILED),
                StepResult(step_id="s3", skill_id="c", status=StepResultStatus.SUCCESS),
            ],
        )
        assert results.success_count == 2
        assert not results.all_succeeded

    def test_plan_execution_result_all_succeeded(self):
        results = PlanExecutionResult(
            plan_id="test",
            results=[
                StepResult(step_id="s1", skill_id="a", status=StepResultStatus.SUCCESS),
                StepResult(step_id="s2", skill_id="b", status=StepResultStatus.SUCCESS),
            ],
        )
        assert results.all_succeeded
