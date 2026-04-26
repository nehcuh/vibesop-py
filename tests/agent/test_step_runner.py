"""Tests for StepRunner — execution bridge between plans and agents."""

from __future__ import annotations

import uuid
import time
from pathlib import Path

import pytest

from vibesop.agent.step_runner import StepRunner, StepRunContext, PlanStepState
from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    StepStatus,
)


def _make_plan(
    steps_config: list[tuple[str, str, str, list[str] | None]],
    execution_mode: str = "sequential",
) -> ExecutionPlan:
    steps = []
    for i, (skill_id, intent, input_query, deps) in enumerate(steps_config, 1):
        steps.append(
            ExecutionStep(
                step_id=f"step-{i}",
                step_number=i,
                skill_id=skill_id,
                intent=intent,
                input_query=input_query,
                output_as=f"output_{i}",
                status=StepStatus.PENDING,
                dependencies=deps or [],
                can_parallel=len(deps or []) == 0,
            )
        )
    return ExecutionPlan(
        plan_id=f"plan-{uuid.uuid4().hex[:8]}",
        original_query="test query",
        steps=steps,
        detected_intents=[s.intent for s in steps],
        reasoning="test plan",
        created_at="2026-04-26T00:00:00Z",
        status=PlanStatus.PENDING,
        execution_mode=ExecutionMode(execution_mode),
    )


class TestStepRunnerBasic:
    """Basic StepRunner lifecycle: create, iterate, complete."""

    def test_empty_plan(self):
        plan = _make_plan([])
        runner = StepRunner(plan, track_state=False)
        assert runner.total_steps == 0
        assert runner.is_complete
        assert runner.pending_steps() == []

    def test_single_step_execution(self):
        plan = _make_plan([
            ("gstack/review", "review code", "帮我 review 代码", None),
        ])
        runner = StepRunner(plan, track_state=False)

        pending = runner.pending_steps()
        assert len(pending) == 1
        assert pending[0].skill_id == "gstack/review"

        step = pending[0]
        runner.start_step(step)
        assert step.status.value == "in_progress"

        runner.mark_completed(step, "Found 3 issues: ...")
        assert step.status.value == "completed"
        assert runner.completed_count == 1
        assert runner.is_complete

    def test_sequential_dependent_steps(self):
        plan = _make_plan([
            ("superpowers-architect", "analyze architecture", "分析项目架构", None),
            ("gstack/review", "review based on analysis", "审查代码", ["step-1"]),
            ("superpowers-optimize", "optimize based on review", "优化代码", ["step-2"]),
        ])
        runner = StepRunner(plan, track_state=False)

        # Step 1 should be ready
        pending = runner.pending_steps()
        assert len(pending) == 1
        assert pending[0].skill_id == "superpowers-architect"

        # Complete step 1
        runner.mark_completed(pending[0], "Architecture analysis result")
        runner._states[pending[0].step_id].completed = True
        runner._states[pending[0].step_id].output = "Architecture analysis result"

        # Now step 2 should be ready, step 3 still blocked
        pending = runner.pending_steps()
        assert len(pending) == 1
        assert pending[0].skill_id == "gstack/review"

        # Complete step 2
        runner.mark_completed(pending[0], "Code review result")

        # Now step 3 should be ready
        pending = runner.pending_steps()
        assert len(pending) == 1
        assert pending[0].skill_id == "superpowers-optimize"

        runner.mark_completed(pending[0], "Optimization complete")
        assert runner.is_complete

    def test_independent_steps_run_in_parallel(self):
        plan = _make_plan([
            ("gstack/review", "review code", "review", None),
            ("gstack/qa", "qa test", "qa", None),
        ])
        runner = StepRunner(plan, track_state=False)

        pending = runner.pending_steps()
        assert len(pending) == 2, "Both independent steps should be ready"

    def test_failed_dependency_blocks_downstream(self):
        plan = _make_plan([
            ("superpowers-architect", "analyze", "分析", None),
            ("gstack/review", "review", "审查", ["step-1"]),
        ])
        runner = StepRunner(plan, track_state=False)

        step1 = runner.pending_steps()[0]
        runner.mark_failed(step1, "LLM timeout")

        # Step 2 should NOT be ready because step 1 failed
        pending = runner.pending_steps()
        assert len(pending) == 0

    def test_skip_step(self):
        plan = _make_plan([
            ("gstack/review", "review", "review", None),
        ])
        runner = StepRunner(plan, track_state=False)
        step = runner.pending_steps()[0]
        runner.mark_skipped(step, "Not needed for this project")
        assert runner.completed_count == 1
        assert runner.is_complete


class TestStepContext:
    """Context accumulation from upstream steps."""

    def test_context_includes_dependency_outputs(self):
        plan = _make_plan([
            ("superpowers-architect", "analyze", "分析架构", None),
            ("gstack/review", "review", "审查代码", ["step-1"]),
        ])
        runner = StepRunner(plan, track_state=False)

        step1 = runner.pending_steps()[0]
        runner.mark_completed(step1, "Project uses hexagonal architecture")

        step2 = runner.pending_steps()[0]
        ctx = runner.get_context(step2)
        assert "step-1" in ctx.dependency_outputs
        assert "hexagonal architecture" in ctx.dependency_outputs["step-1"]

    def test_context_format_for_prompt(self):
        plan = _make_plan([
            ("superpowers-architect", "analyze", "分析架构", None),
            ("gstack/review", "review", "审查代码", ["step-1"]),
        ])
        runner = StepRunner(plan, track_state=False)

        step1 = runner.pending_steps()[0]
        runner.mark_completed(step1, "Project uses hexagonal architecture")

        step2 = runner.pending_steps()[0]
        ctx = runner.get_context(step2)
        prompt = ctx.format_for_prompt()
        assert "Previous Step Results" in prompt
        assert "hexagonal architecture" in prompt

    def test_context_empty_when_no_dependencies(self):
        plan = _make_plan([
            ("gstack/review", "review", "review", None),
        ])
        runner = StepRunner(plan, track_state=False)
        step = runner.pending_steps()[0]
        ctx = runner.get_context(step)
        assert len(ctx.dependency_outputs) == 0
        assert ctx.format_for_prompt() == ""

    def test_context_excludes_failed_dependencies(self):
        plan = _make_plan([
            ("superpowers-architect", "analyze", "分析", None),
            ("gstack/review", "review", "审查", ["step-1"]),
        ])
        runner = StepRunner(plan, track_state=False)
        step1 = runner.pending_steps()[0]
        runner.mark_failed(step1, "Error")

        # Step 2 is blocked, so get_context is not normally called
        # but if it were, failed deps should be excluded
        step2 = plan.steps[1]
        runner._states[step2.step_id].completed = False
        runner._states[step2.step_id].failed = False
        ctx = runner.get_context(step2)
        assert "step-1" not in ctx.dependency_outputs


class TestExecuteAll:
    """Full execute_all() integration."""

    def test_execute_all_sequential(self):
        plan = _make_plan([
            ("skill-a", "step 1", "do step 1", None),
            ("skill-b", "step 2", "do step 2", ["step-1"]),
            ("skill-c", "step 3", "do step 3", ["step-2"]),
        ])
        runner = StepRunner(plan, track_state=False)

        def executor(step, ctx):
            ctx_str = ctx.format_for_prompt()
            return f"Executed {step.skill_id} with ctx_len={len(ctx_str)}"

        result = runner.execute_all(executor)
        assert result["completed"] == 3
        assert result["failed"] == 0
        assert runner.is_complete

        for r in result["results"]:
            assert r["status"] == "completed"
            assert r["output"].startswith("Executed skill-")

    def test_execute_all_with_failure_non_fatal(self):
        plan = _make_plan([
            ("skill-a", "step 1", "do step 1", None),
            ("skill-b", "step 2", "do step 2", ["step-1"]),
            ("skill-c", "step 3", "do step 3", None),
        ])
        runner = StepRunner(plan, track_state=False)

        def executor(step, ctx):
            if step.skill_id == "skill-b":
                raise RuntimeError("Intentional failure")
            return f"OK {step.skill_id}"

        errors_called = []
        def on_error(step, error):
            errors_called.append(step.skill_id)
            return True  # continue

        result = runner.execute_all(executor, on_step_error=on_error)
        assert result["completed"] == 2
        assert result["failed"] == 1
        assert len(errors_called) == 1
        assert errors_called[0] == "skill-b"

    def test_execute_all_fail_fast(self):
        plan = _make_plan([
            ("skill-a", "step 1", "do step 1", None),
            ("skill-b", "step 2", "do step 2", None),
        ])
        runner = StepRunner(plan, track_state=False)

        call_order = []
        def executor(step, ctx):
            call_order.append(step.skill_id)
            raise RuntimeError(f"Fail {step.skill_id}")

        result = runner.execute_all(executor, fail_fast=True)
        # fail_fast stops subsequent batches; in a parallel batch,
        # all tasks in the batch start together, so both may execute.
        # The key behavior is that no further batches run.
        assert result["failed"] >= 1, "fail_fast should record at least one failure"
        assert result["failed"] + result["skipped"] == runner.total_steps


class TestStatePersistence:
    """StepRunner integration with PlanTracker."""

    def test_persist_and_resume(self, tmp_path: Path):
        plan = _make_plan([
            ("skill-a", "step 1", "do step 1", None),
            ("skill-b", "step 2", "do step 2", ["step-1"]),
        ])
        runner = StepRunner(plan, project_root=tmp_path, track_state=True)

        step1 = runner.pending_steps()[0]
        runner.mark_completed(step1, "Result of step 1")

        # Resume from the same plan ID
        runner2 = StepRunner.resume(plan.plan_id, project_root=tmp_path)
        pending = runner2.pending_steps()
        assert len(pending) == 1
        assert pending[0].skill_id == "skill-b"
        assert runner2.completed_count == 1

    def test_resume_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            StepRunner.resume("nonexistent-plan-id", project_root=".")


class TestStepRunnerWithDeps:
    """Complex dependency scenarios."""

    def test_mixed_parallel_dependencies(self):
        plan = _make_plan([
            ("skill-a", "step 1", "a", None),
            ("skill-b", "step 2", "b", None),
            ("skill-c", "step 3", "c depends on a+b", ["step-1", "step-2"]),
        ])
        runner = StepRunner(plan, track_state=False)

        pending = runner.pending_steps()
        assert len(pending) == 2, "Step 1 and 2 should both be ready"

        runner.mark_completed(pending[0], "a done")
        pending = runner.pending_steps()
        assert len(pending) == 1, "Only step 2 still pending (step 3 blocked)"

        runner.mark_completed(pending[0], "b done")
        pending = runner.pending_steps()
        assert len(pending) == 1
        assert pending[0].skill_id == "skill-c"

        ctx = runner.get_context(pending[0])
        assert len(ctx.dependency_outputs) == 2
        assert "step-1" in ctx.dependency_outputs
        assert "step-2" in ctx.dependency_outputs
