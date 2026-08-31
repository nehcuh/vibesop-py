"""Tests for StepRunner — execution bridge between plans and agents."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from vibesop.agent.step_runner import StepRunContext, StepRunner
from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    StepStatus,
    WorkflowPattern,
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
        plan = _make_plan(
            [
                ("gstack/review", "review code", "帮我 review 代码", None),
            ]
        )
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
        plan = _make_plan(
            [
                ("superpowers-architect", "analyze architecture", "分析项目架构", None),
                ("gstack/review", "review based on analysis", "审查代码", ["step-1"]),
                ("superpowers-optimize", "optimize based on review", "优化代码", ["step-2"]),
            ]
        )
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
        plan = _make_plan(
            [
                ("gstack/review", "review code", "review", None),
                ("gstack/qa", "qa test", "qa", None),
            ]
        )
        runner = StepRunner(plan, track_state=False)

        pending = runner.pending_steps()
        assert len(pending) == 2, "Both independent steps should be ready"

    def test_failed_dependency_blocks_downstream(self):
        plan = _make_plan(
            [
                ("superpowers-architect", "analyze", "分析", None),
                ("gstack/review", "review", "审查", ["step-1"]),
            ]
        )
        runner = StepRunner(plan, track_state=False)

        step1 = runner.pending_steps()[0]
        runner.mark_failed(step1, "LLM timeout")

        # Step 2 should NOT be ready because step 1 failed
        pending = runner.pending_steps()
        assert len(pending) == 0

    def test_skip_step(self):
        plan = _make_plan(
            [
                ("gstack/review", "review", "review", None),
            ]
        )
        runner = StepRunner(plan, track_state=False)
        step = runner.pending_steps()[0]
        runner.mark_skipped(step, "Not needed for this project")
        assert runner.completed_count == 1
        assert runner.is_complete


class TestStepContext:
    """Context accumulation from upstream steps."""

    def test_context_includes_dependency_outputs(self):
        plan = _make_plan(
            [
                ("superpowers-architect", "analyze", "分析架构", None),
                ("gstack/review", "review", "审查代码", ["step-1"]),
            ]
        )
        runner = StepRunner(plan, track_state=False)

        step1 = runner.pending_steps()[0]
        runner.mark_completed(step1, "Project uses hexagonal architecture")

        step2 = runner.pending_steps()[0]
        ctx = runner.get_context(step2)
        assert "step-1" in ctx.dependency_outputs
        assert "hexagonal architecture" in ctx.dependency_outputs["step-1"]

    def test_context_format_for_prompt(self):
        plan = _make_plan(
            [
                ("superpowers-architect", "analyze", "分析架构", None),
                ("gstack/review", "review", "审查代码", ["step-1"]),
            ]
        )
        runner = StepRunner(plan, track_state=False)

        step1 = runner.pending_steps()[0]
        runner.mark_completed(step1, "Project uses hexagonal architecture")

        step2 = runner.pending_steps()[0]
        ctx = runner.get_context(step2)
        prompt = ctx.format_for_prompt()
        assert "Previous Step Results" in prompt
        assert "hexagonal architecture" in prompt

    def test_context_empty_when_no_dependencies(self):
        plan = _make_plan(
            [
                ("gstack/review", "review", "review", None),
            ]
        )
        runner = StepRunner(plan, track_state=False)
        step = runner.pending_steps()[0]
        ctx = runner.get_context(step)
        assert len(ctx.dependency_outputs) == 0
        assert ctx.format_for_prompt() == ""

    def test_context_excludes_failed_dependencies(self):
        plan = _make_plan(
            [
                ("superpowers-architect", "analyze", "分析", None),
                ("gstack/review", "review", "审查", ["step-1"]),
            ]
        )
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
        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "do step 2", ["step-1"]),
                ("skill-c", "step 3", "do step 3", ["step-2"]),
            ]
        )
        runner = StepRunner(plan, track_state=False)

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
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
        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "do step 2", ["step-1"]),
                ("skill-c", "step 3", "do step 3", None),
            ]
        )
        runner = StepRunner(plan, track_state=False)

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
            if step.skill_id == "skill-b":
                raise RuntimeError("Intentional failure")
            return f"OK {step.skill_id}"

        errors_called: list[str] = []

        def on_error(step: ExecutionStep, error: Exception) -> bool:
            errors_called.append(step.skill_id)
            return True  # continue

        result = runner.execute_all(executor, on_step_error=on_error)
        assert result["completed"] == 2
        assert result["failed"] == 1
        assert len(errors_called) == 1
        assert errors_called[0] == "skill-b"

    def test_execute_all_fail_fast(self):
        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "do step 2", None),
            ]
        )
        runner = StepRunner(plan, track_state=False)

        call_order: list[str] = []

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
            call_order.append(step.skill_id)
            raise RuntimeError(f"Fail {step.skill_id}")

        result = runner.execute_all(executor, fail_fast=True)
        # fail_fast stops subsequent batches; in a parallel batch,
        # all tasks in the batch start together, so both may execute.
        # The key behavior is that no further batches run.
        assert result["failed"] >= 1, "fail_fast should record at least one failure"
        assert result["failed"] + result["skipped"] == runner.total_steps
        # Anchor metadata contract also holds on the fail-fast return path.
        assert result["plan_id"] == plan.plan_id
        assert all("step_id" in r for r in result["results"])

    def test_execute_all_result_carries_anchor_metadata(self):
        """Side-panel anchor contract (proposal §3.2 item 3): the result dict
        carries plan_id, and every per-step entry carries step_id."""
        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "do step 2", ["step-1"]),
            ]
        )
        runner = StepRunner(plan, track_state=False)

        result = runner.execute_all(lambda step, ctx: f"out-{step.step_id}")

        assert result["plan_id"] == plan.plan_id
        assert [r["step_id"] for r in result["results"]] == ["step-1", "step-2"]

    def test_execute_all_dynamic_result_carries_plan_id(self):
        """Dynamic (WorkflowEngine) return path also carries plan_id."""
        plan = _make_plan([("skill-a", "step 1", "do step 1", None)])
        plan.workflow_pattern = WorkflowPattern.LOOP_UNTIL_DRY
        runner = StepRunner(plan, track_state=False)

        result = runner.execute_all(lambda step, ctx: "done")

        assert result["plan_id"] == plan.plan_id
        assert result["dynamic"] is True

    def test_event_log_wired_through_engine(self):
        """P1-1 (20260831 review): StepRunner must forward its event_log into
        the WorkflowEngine — an integrator passing create_runner(event_log=...)
        or StepRunner(event_log=...) gets engine events without touching the
        engine directly."""
        from vibesop.core.orchestration import PlanEventLog, PlanEventType

        plan = _make_plan([("skill-a", "step 1", "do step 1", None)])
        plan.workflow_pattern = WorkflowPattern.LOOP_UNTIL_DRY
        log = PlanEventLog()
        runner = StepRunner(plan, track_state=False, event_log=log)

        runner.execute_all(lambda step, ctx: "done")

        events = log.replay(plan.plan_id, since_seq=0).events
        assert events, "engine events must land in the wired log"
        assert log.snapshot(plan.plan_id) is not None
        assert any(e.type == PlanEventType.PLAN_TERMINAL for e in events)

    def test_event_log_absent_engine_still_runs(self):
        """Default (no event_log) stays fully functional."""
        plan = _make_plan([("skill-a", "step 1", "do step 1", None)])
        plan.workflow_pattern = WorkflowPattern.LOOP_UNTIL_DRY
        runner = StepRunner(plan, track_state=False)

        result = runner.execute_all(lambda step, ctx: "done")

        assert result["dynamic"] is True
        assert result["failed"] == 0


class TestStatePersistence:
    """StepRunner integration with PlanTracker."""

    def test_persist_and_resume(self, tmp_path: Path):
        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "do step 2", ["step-1"]),
            ]
        )
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
        from vibesop.core.exceptions import PlanNotFoundError

        with pytest.raises(PlanNotFoundError, match="not found"):
            StepRunner.resume("nonexistent-plan-id", project_root=".")


class TestStepRunnerWithDeps:
    """Complex dependency scenarios."""

    def test_mixed_parallel_dependencies(self):
        plan = _make_plan(
            [
                ("skill-a", "step 1", "a", None),
                ("skill-b", "step 2", "b", None),
                ("skill-c", "step 3", "c depends on a+b", ["step-1", "step-2"]),
            ]
        )
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


class TestStepRunnerSquadMode:
    """Squad-oriented plan execution with role injection."""

    def test_execute_all_squad_injects_role_prompt_and_skills(self):
        plan = ExecutionPlan(
            plan_id=f"plan-{uuid.uuid4().hex[:8]}",
            original_query="squad test",
            workflow_pattern=WorkflowPattern.AGENT_SQUAD,
            execution_mode=ExecutionMode.SEQUENTIAL,
            steps=[
                ExecutionStep(
                    step_id="impl",
                    step_number=1,
                    skill_id="coding",
                    intent="implement",
                    input_query="implement",
                    assigned_role="implementer",
                    agent_squad_id="squad-1",
                    role_skills=["coding", "refactor"],
                ),
                ExecutionStep(
                    step_id="rev",
                    step_number=2,
                    skill_id="review",
                    intent="review",
                    input_query="review",
                    assigned_role="reviewer",
                    agent_squad_id="squad-1",
                    role_skills=["review", "code_review"],
                ),
            ],
        )
        runner = StepRunner(plan, track_state=False)

        calls: list[tuple[str, str, dict[str, Any]]] = []

        def executor(step: ExecutionStep, ctx: dict[str, Any]) -> str:
            calls.append((step.step_id, step.assigned_role or "", ctx))
            return f"output-{step.step_id}"

        result = runner.execute_all(executor, context={"base": "value"})

        assert result["completed"] == 2
        assert result["failed"] == 0
        assert runner.is_complete

        # Each role group receives its own enriched context
        impl_ctx = next(ctx for sid, _role, ctx in calls if sid == "impl")
        assert impl_ctx["role"] == "implementer"
        assert "Implementer" in impl_ctx["role_prompt"]
        assert impl_ctx["skill_isolation"]["allowed_skills"] == ["coding", "refactor"]
        assert impl_ctx["base"] == "value"

        rev_ctx = next(ctx for sid, _role, ctx in calls if sid == "rev")
        assert rev_ctx["role"] == "reviewer"
        assert "Reviewer" in rev_ctx["role_prompt"]
        assert rev_ctx["skill_isolation"]["allowed_skills"] == ["review", "code_review"]

    def test_execute_all_squad_member_failure_does_not_abort(self):
        """F-27: a single squad member failing must not abort the whole squad.

        Previously ``_execute_squad`` had no try/except: one member's exception
        propagated, result recording was skipped, and ``execute_all``
        unconditionally ``mark_completed`` every step — hiding the failure and
        leaving steps stuck in IN_PROGRESS.
        """
        plan = ExecutionPlan(
            plan_id=f"plan-{uuid.uuid4().hex[:8]}",
            original_query="squad failure test",
            workflow_pattern=WorkflowPattern.AGENT_SQUAD,
            execution_mode=ExecutionMode.SEQUENTIAL,
            steps=[
                ExecutionStep(
                    step_id="impl",
                    step_number=1,
                    skill_id="coding",
                    intent="implement",
                    input_query="implement",
                    assigned_role="implementer",
                    agent_squad_id="squad-1",
                    role_skills=["coding"],
                ),
                ExecutionStep(
                    step_id="rev",
                    step_number=2,
                    skill_id="review",
                    intent="review",
                    input_query="review",
                    assigned_role="reviewer",
                    agent_squad_id="squad-1",
                    role_skills=["review"],
                ),
                ExecutionStep(
                    step_id="qa",
                    step_number=3,
                    skill_id="qa",
                    intent="qa",
                    input_query="qa",
                    assigned_role="reviewer",
                    agent_squad_id="squad-1",
                    role_skills=["review"],
                ),
            ],
        )
        runner = StepRunner(plan, track_state=False)

        def executor(step: ExecutionStep, ctx: dict[str, Any]) -> str:
            if step.step_id == "rev":
                raise RuntimeError("review tool crashed")
            return f"ok-{step.step_id}"

        errors_notified: list[str] = []

        def on_error(step: ExecutionStep, error: Exception) -> bool:
            errors_notified.append(step.step_id)
            return True

        result = runner.execute_all(executor, context={}, on_step_error=on_error)

        # Squad not aborted: impl + qa complete, rev fails.
        assert result["completed"] == 2
        assert result["failed"] == 1

        by_id = {r["step_id"]: r for r in result["results"]}
        assert by_id["impl"]["status"] == "completed"
        assert by_id["rev"]["status"] == "failed"
        assert "review tool crashed" in by_id["rev"]["error"]
        assert by_id["qa"]["status"] == "completed"

        # The failed step was surfaced through on_step_error.
        assert errors_notified == ["rev"]

        # F-27 symptom: the failed step reached FAILED (not stuck IN_PROGRESS).
        rev_step = next(s for s in plan.steps if s.step_id == "rev")
        assert rev_step.status == StepStatus.FAILED

    def test_execute_all_squad_all_members_fail(self):
        """F-27: when every squad member fails, all are marked failed (completed=0)."""
        plan = ExecutionPlan(
            plan_id=f"plan-{uuid.uuid4().hex[:8]}",
            original_query="squad all-fail test",
            workflow_pattern=WorkflowPattern.AGENT_SQUAD,
            execution_mode=ExecutionMode.SEQUENTIAL,
            steps=[
                ExecutionStep(
                    step_id="a",
                    step_number=1,
                    skill_id="x",
                    intent="a",
                    input_query="a",
                    assigned_role="attacker",
                    agent_squad_id="s1",
                    role_skills=["x"],
                ),
                ExecutionStep(
                    step_id="b",
                    step_number=2,
                    skill_id="y",
                    intent="b",
                    input_query="b",
                    assigned_role="defender",
                    agent_squad_id="s1",
                    role_skills=["y"],
                ),
            ],
        )
        runner = StepRunner(plan, track_state=False)

        def executor(step: ExecutionStep, ctx: dict[str, Any]) -> str:
            raise RuntimeError(f"crash-{step.step_id}")

        result = runner.execute_all(executor)

        assert result["completed"] == 0
        assert result["failed"] == 2
        assert all(r["status"] == "failed" for r in result["results"])
        assert all(s.status == StepStatus.FAILED for s in plan.steps)
