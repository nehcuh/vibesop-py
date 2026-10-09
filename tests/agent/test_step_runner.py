"""Tests for StepRunner — execution bridge between plans and agents."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from vibesop.agent.step_runner import StepRunContext, StepRunner
from vibesop.core.models import (
    AgentSquad,
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

    def test_execute_all_parallel_acceptance_failure_marks_failed(self):
        """8.3.1 (A-2): the parallel batch path applies the same
        acceptance-failure predicate as the serial path — "blocked:" /
        "failed" outputs must never be marked completed. B3 adds the blocked
        breakdown: a blocked sentinel counts in BOTH failed and blocked
        (restored HEAD contract — failed ⊇ blocked)."""
        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "do step 2", None),
            ]
        )
        runner = StepRunner(plan, track_state=False, max_parallel=2)

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
            if step.skill_id == "skill-b":
                return "blocked: missing evidence"
            return f"OK {step.skill_id}"

        result = runner.execute_all(executor)
        assert result["completed"] == 1
        assert result["failed"] == 1
        assert result["blocked"] == 1
        # One success + one blocked (no real failure) → partial.
        assert result["final_status"] == "partial"
        # F2: the per-step entry keeps the legacy status value domain.
        by_id = {r["step_id"]: r for r in result["results"]}
        assert by_id["step-2"]["status"] == "failed"
        assert "blocked" in by_id["step-2"]["error"]
        # F1 four-face consistency: returned dict, runner state, StepStatus
        # and the StepOutcome all agree.
        assert runner.failed_count == 1
        assert not runner._states["step-2"].completed
        assert plan.steps[1].status == StepStatus.FAILED
        outcome = runner.last_plan_outcome
        assert outcome is not None
        assert outcome.failed == 1 and outcome.blocked == 1
        step_statuses = {s.step_id: s.status for s in outcome.steps}
        assert step_statuses["step-2"].value == "blocked"

    def test_execute_all_parallel_dict_blocked_detected(self):
        """B3 matrix (blocked sentinel, dict shape): {"status": "blocked"} is
        classified as blocked (and counted in failed per F1), not completed."""
        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "do step 2", None),
            ]
        )
        runner = StepRunner(plan, track_state=False, max_parallel=2)

        def executor(step: ExecutionStep, ctx: StepRunContext):
            if step.skill_id == "skill-b":
                return {"status": "blocked", "reason": "no evidence"}
            return f"OK {step.skill_id}"

        result = runner.execute_all(executor)
        assert result["completed"] == 1
        assert result["failed"] == 1
        assert result["blocked"] == 1
        by_id = {r["step_id"]: r for r in result["results"]}
        # F2: legacy entry status value domain (completed/failed).
        assert by_id["step-2"]["status"] == "failed"

    def test_execute_all_parallel_dict_failure_detected(self):
        """8.3.1 (A-2/K-1): dict-shaped failures are detected on the RAW
        result before stringification — the parallel path must reach the
        dict branch of the predicate."""
        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "do step 2", None),
            ]
        )
        runner = StepRunner(plan, track_state=False, max_parallel=2)

        def executor(step: ExecutionStep, ctx: StepRunContext):
            if step.skill_id == "skill-b":
                return {"status": "failed", "reason": "tests red"}
            return f"OK {step.skill_id}"

        result = runner.execute_all(executor)
        assert result["completed"] == 1
        assert result["failed"] == 1
        assert not runner._states["step-2"].completed

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
        # 8.3.1: only execution-ready plans are persisted/tracked (blocked
        # plans are refused at handoff before a StepRunner is constructed).
        plan.metadata["execution_ready"] = True
        runner = StepRunner(plan, project_root=tmp_path, track_state=True)

        step1 = runner.pending_steps()[0]
        runner.mark_completed(step1, "Result of step 1")

        # Resume from the same plan ID
        runner2 = StepRunner.resume(plan.plan_id, project_root=tmp_path)
        pending = runner2.pending_steps()
        assert len(pending) == 1
        assert pending[0].skill_id == "skill-b"
        assert runner2.completed_count == 1

    def test_blocked_plan_is_not_persisted(self, tmp_path: Path):
        # 8.3.1: an execution_ready=False plan must not enter the plan store.
        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
            ]
        )
        plan.metadata["execution_ready"] = False
        runner = StepRunner(plan, project_root=tmp_path, track_state=True)
        assert runner._tracker is None
        assert not (tmp_path / ".vibe" / "execution_plans.jsonl").exists()

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


class _RouterStub:
    """Router stand-in for PlanBuilder (same contract as the delivery-contract
    integration tests): sub-tasks carry pre-assigned skill_ids / squad plans
    are metadata-driven, so the routing branch is never entered. The loader
    backs SkillComposer's global skill discovery."""

    def __init__(self, skills: dict[str, list[str]] | None = None) -> None:
        self._skills = skills or {}

    def get_skill_loader(self) -> Any:
        router = self

        class _Loader:
            def discover_all(self, force_reload: bool = False) -> dict[str, Any]:
                return {
                    skill_id: type(
                        "Loaded",
                        (),
                        {
                            "metadata": type(
                                "Meta",
                                (),
                                {
                                    "name": skill_id,
                                    "description": f"{skill_id} skill",
                                    "intent": "",
                                    "tags": [],
                                    "capabilities": caps,
                                    "triggers": [],
                                },
                            )()
                        },
                    )()
                    for skill_id, caps in router._skills.items()
                }

        return _Loader()


def _build_fan_out_plan() -> ExecutionPlan:
    """D06 counterexample fixture: real PlanBuilder FAN_OUT — A∥B with no
    dependencies plus a synthesise step C depending on BOTH (production
    writer; no hand-built step shapes)."""
    from vibesop.core.orchestration.plan_builder import PlanBuilder
    from vibesop.core.orchestration.task_decomposer import SubTask

    builder = PlanBuilder(_RouterStub())
    return builder.build_plan(
        "run a and b then synthesise",
        [
            SubTask(intent="step A", query="do A", skill_id="skill-a"),
            SubTask(intent="step B", query="do B", skill_id="skill-b"),
        ],
        workflow_pattern=WorkflowPattern.FAN_OUT,
    )


def _build_loop_until_dry_plan() -> ExecutionPlan:
    """D07 counterexample fixture: real PlanBuilder LOOP_UNTIL_DRY plan."""
    from vibesop.core.orchestration.plan_builder import PlanBuilder
    from vibesop.core.orchestration.task_decomposer import SubTask

    builder = PlanBuilder(_RouterStub())
    plan = builder.build_plan(
        "loop until dry",
        [SubTask(intent="analysis", query="analyze", skill_id="skill-a")],
        workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY,
    )
    plan.dry_threshold = 1
    plan.max_reorchestration_rounds = 1
    return plan


def _build_squad_plan(
    pattern: WorkflowPattern,
    *,
    roles: list[str],
    protocol: str,
    skills: dict[str, list[str]],
) -> ExecutionPlan:
    """D08 counterexample fixture: real PlanBuilder squad plan — steps carry
    agent_squad_id and metadata carries agent_squad (both from production
    writers: PlanBuilder._build_squad_steps / AgentSquad.to_dict)."""
    from vibesop.core.models import IntentAnalysis
    from vibesop.core.orchestration.plan_builder import PlanBuilder
    from vibesop.core.orchestration.task_decomposer import SubTask

    builder = PlanBuilder(_RouterStub(skills))
    analysis = IntentAnalysis(
        complexity="multi_agent",
        facets=["test"],
        squad_needed=True,
        suggested_roles=roles,
        collaboration_protocol=protocol,
        per_agent_skills=dict(skills),
        confidence=0.9,
    )
    return builder.build_plan(
        "squad query",
        [SubTask(intent="placeholder", query="placeholder")],
        workflow_pattern=pattern,
        metadata={"intent_analysis": analysis},
    )


def _role_of(step: Any) -> str:
    """Role accessor for the ExecutionStep objects public executors receive
    (assigned_role); still tolerates engine-internal SquadStep shapes."""
    return getattr(step, "assigned_role", None) or getattr(step, "role_id", "") or ""


class _HardRejectLLM:
    """LLM whose review verdict is always a hard reject (blocked: no evidence)."""

    def __init__(self, issues: str = "no evidence") -> None:
        self._issues = issues

    def call(self, prompt: str, **kwargs: Any) -> Any:
        body = (
            '{"passed": false, "issues": ["'
            + self._issues
            + '"], "score": 1.0, "requires_revision": false, '
            + '"revision_feedback": "blocked: '
            + self._issues
            + '"}'
        )
        return type("Response", (), {"content": body})()


class TestExecuteAllCounterexamples:
    """D06/D07 counterexamples through the public StepRunner entry."""

    def test_d06_fail_fast_all_success_batch_runs_downstream_steps(self):
        """D06: fail_fast=True with an all-success parallel batch must NOT
        swallow downstream dependent steps — the old unconditional break
        left the synthesise step pending (completed=2/3)."""
        plan = _build_fan_out_plan()
        assert len(plan.steps) == 3
        synthesise = plan.steps[-1]
        assert len(synthesise.dependencies) == 2, "FAN_OUT synthesise depends on both A and B"

        runner = StepRunner(plan, track_state=False, max_parallel=2)
        executed: list[str] = []

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
            executed.append(step.step_id)
            return f"OK {step.step_id}"

        result = runner.execute_all(executor, fail_fast=True)

        assert synthesise.step_id in executed, "downstream synthesise step must run"
        assert result["completed"] == 3
        assert result["failed"] == 0
        assert result["final_status"] == "completed"

    def test_d06_fail_fast_still_aborts_on_real_failure(self):
        """D06 guard: the same fix must not weaken fail_fast — a real failure
        in the batch still stops downstream steps."""
        plan = _build_fan_out_plan()
        runner = StepRunner(plan, track_state=False, max_parallel=2)

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
            if step.step_id == plan.steps[0].step_id:
                raise RuntimeError("A exploded")
            return f"OK {step.step_id}"

        result = runner.execute_all(executor, fail_fast=True)

        assert result["failed"] == 1
        assert result["completed"] <= 1
        # Downstream synthesise depends on the failed step → never dispatched.
        synthesise = plan.steps[-1]
        assert synthesise.status == StepStatus.SKIPPED
        assert result["skipped"] >= 1

    def test_d07_dynamic_exception_reports_real_counters_and_final_status(self):
        """D07: a LOOP_UNTIL_DRY executor exception must surface as failed>=1
        and deliver the engine's final_status — the old bridge hardcoded
        failed=0 and dropped final_status entirely."""
        plan = _build_loop_until_dry_plan()
        runner = StepRunner(plan, track_state=False)

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
            raise RuntimeError("analysis blew up")

        result = runner.execute_all(executor)

        assert result["dynamic"] is True
        assert result["failed"] >= 1
        assert result["final_status"] == "failed"
        assert result["plan_id"] == plan.plan_id
        # Underlying engine state agrees with the public counters.
        assert plan.status == PlanStatus.FAILED
        # Legacy results dict shape preserved: keyed by step identity, not a list.
        assert isinstance(result["results"], dict)
        failed_values = [v for v in result["results"].values() if isinstance(v, dict)]
        assert any("error" in v for v in failed_values)

    def test_d07_dynamic_success_delivers_completed_final_status(self):
        """D07 matrix (OK cell, dynamic entry): all-success dynamic run
        reports real counters and final_status=completed."""
        plan = _build_loop_until_dry_plan()
        runner = StepRunner(plan, track_state=False)

        result = runner.execute_all(lambda step, ctx: "dry")

        assert result["failed"] == 0
        assert result["completed"] >= 1
        assert result["final_status"] in ("completed", "terminated_early")
        assert isinstance(result["results"], dict)


class TestStepRunnerSquadMode:
    """Squad-oriented plan execution through the public runner (D08).

    Squad patterns are dynamic: they delegate to WorkflowEngine.run_async
    (handoff/review/revision gates). The simplified alphabetical-role branch
    that bypassed those gates is gone.
    """

    def test_squad_plan_requires_engine_metadata(self):
        """A squad-pattern plan without agent_squad metadata is refused by the
        engine with a clear error instead of being silently 'completed' by a
        simplified branch."""
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
                    role_skills=["coding"],
                ),
            ],
        )
        runner = StepRunner(plan, track_state=False)

        with pytest.raises(ValueError, match="squad metadata"):
            runner.execute_all(lambda step, ctx: "out")

    def test_squad_runs_in_collaboration_order_not_alphabetical(self):
        """D08: execution follows the squad's collaboration order. With
        suggested roles [tester, architect] the alphabetical order would be
        architect-first — the old branch sorted roles alphabetically."""
        plan = _build_squad_plan(
            WorkflowPattern.AGENT_SQUAD,
            roles=["tester", "architect"],
            protocol="sequential",
            skills={"tester": ["testing"], "architect": ["design"]},
        )
        squad = AgentSquad(**plan.metadata["agent_squad"])
        assert squad.execution_order != sorted(squad.execution_order), (
            "fixture must discriminate collaboration order from alphabetical"
        )

        runner = StepRunner(plan, track_state=False)
        call_order: list[str] = []

        def executor(step: ExecutionStep, ctx: dict[str, Any]) -> dict[str, Any]:
            call_order.append(step.step_id)
            return {"step_id": step.step_id, "role_id": _role_of(step), "content": "out"}

        result = runner.execute_all(executor, context={"base": "value"})

        assert call_order == squad.execution_order
        assert result["completed"] == 2
        assert result["failed"] == 0
        assert result["blocked"] == 0
        assert result["final_status"] == "completed"
        # Squad lane keeps the legacy result keys (additive-only evolution).
        assert result["plan_id"] == plan.plan_id
        assert result["pattern"] == WorkflowPattern.AGENT_SQUAD.value
        assert all("step_id" in r for r in result["results"])

    def test_squad_handoff_context_reaches_downstream_role(self):
        """D08: the engine's handoff payload is present in the downstream
        role's context (the old simplified branch never built one)."""
        plan = _build_squad_plan(
            WorkflowPattern.RED_TEAM,
            roles=["implementer", "red_team"],
            protocol="red_team",
            skills={"implementer": ["coding"], "red_team": ["security-audit"]},
        )
        runner = StepRunner(plan, track_state=False)
        contexts: dict[str, dict[str, Any]] = {}

        def executor(step: ExecutionStep, ctx: dict[str, Any]) -> dict[str, Any]:
            contexts[_role_of(step)] = ctx
            return {
                "step_id": step.step_id,
                "role_id": _role_of(step),
                "content": f"work-by-{_role_of(step)}",
            }

        result = runner.execute_all(executor)

        red_team_ctx = contexts.get("red_team", {})
        assert red_team_ctx.get("handoff"), "red_team must receive a handoff payload"
        assert "work-by-implementer" in str(red_team_ctx["handoff"])
        assert result["final_status"] == "completed"

    def test_squad_context_restores_role_prompt_and_skill_isolation(self):
        """F5 (F27 contract): the unified engine path must deliver the same
        role context keys as the old _execute_squad branch — a rendered
        role_prompt and skill_isolation.allowed_skills for the role's real
        SquadStep skills — alongside the new handoff key. The deleted
        role-injection test is restored here against the public runner."""
        from vibesop.core.orchestration.role_templates import render_role_prompt

        plan = _build_squad_plan(
            WorkflowPattern.RED_TEAM,
            roles=["implementer", "red_team"],
            protocol="red_team",
            skills={"implementer": ["coding"], "red_team": ["security-audit"]},
        )
        squad = AgentSquad(**plan.metadata["agent_squad"])
        expected_skills = {s.role_id: list(s.skill_ids) for s in squad.steps}
        runner = StepRunner(plan, track_state=False)
        contexts: dict[str, dict[str, Any]] = {}

        def executor(step: ExecutionStep, ctx: dict[str, Any]) -> dict[str, Any]:
            contexts[_role_of(step)] = ctx
            return {
                "step_id": step.step_id,
                "role_id": _role_of(step),
                "content": f"work-by-{_role_of(step)}",
            }

        result = runner.execute_all(executor)

        for role, ctx in contexts.items():
            assert ctx.get("role_prompt"), f"{role} must receive a rendered role prompt"
            assert ctx["role_prompt"] == render_role_prompt(role, expected_skills[role])
            assert ctx.get("skill_isolation", {}).get("allowed_skills") == expected_skills[role]
        # New keys from the unified engine path coexist with the restored ones.
        assert contexts["red_team"].get("handoff"), "handoff must still be delivered"
        assert result["final_status"] == "completed"

    def test_squad_review_gate_error_surfaces_not_accepted(self):
        """F4: a required review gate that errors (no LLM configured) is
        neither a hard reject nor an acceptance — the run completed (engine
        run-completed contract) but the public result must say review_status
        'error', and the adapter must expose it. Execution success
        (all_succeeded) must not mask the missing acceptance."""
        from vibesop.agent.execution_protocol import (
            PlanExecutionResult,
            StepResultStatus,
        )

        plan = _build_squad_plan(
            WorkflowPattern.AGENT_SQUAD,
            roles=["implementer", "reviewer"],
            protocol="review_gate",
            skills={"implementer": ["coding"], "reviewer": ["review"]},
        )
        runner = StepRunner(plan, track_state=False)  # no llm_client → review gate errors

        def executor(step: ExecutionStep, ctx: dict[str, Any]) -> dict[str, Any]:
            return {"step_id": step.step_id, "role_id": _role_of(step), "content": "work"}

        result = runner.execute_all(executor)

        # Execution itself succeeded — every member produced work.
        assert result["completed"] == len(plan.steps)
        assert result["failed"] == 0
        assert result["blocked"] == 0
        assert result["final_status"] == "completed"
        # But acceptance is explicitly unknown: the review gate never ran.
        assert result["review_status"] == "error"
        assert plan.status == PlanStatus.COMPLETED, "run-completed contract restored (F3)"
        # A degraded gate verdict is delivered for inspection but is not a
        # genuine hard reject.
        assert any(not v["passed"] for v in result["verdicts"])
        # The adapter exposes the acceptance dimension explicitly.
        adapted = PlanExecutionResult.from_step_runner_dict(result, plan)
        assert adapted.review_status == "error"
        assert adapted.all_succeeded, "execution success is truthful..."
        assert all(r.status is StepResultStatus.SUCCESS for r in adapted.results)
        # ...and must never be read as review acceptance.
        assert adapted.review_status != "accepted"

    @pytest.mark.parametrize(
        "pattern",
        [WorkflowPattern.RED_TEAM, WorkflowPattern.DEBATE],
    )
    def test_squad_blocked_verdict_surfaces_blocked_not_completed(self, pattern):
        """D08: when the review gate hard-rejects (reviewer reports
        'blocked: no evidence'), the public result must carry blocked>=1 and
        final_status='blocked' — never completed. Steps keep their real
        per-step statuses and verdicts remain inspectable."""
        if pattern == WorkflowPattern.RED_TEAM:
            roles = ["implementer", "red_team"]
            protocol = "red_team"
            skills = {"implementer": ["coding"], "red_team": ["security-audit"]}
        else:
            roles = ["debater", "reviewer"]
            protocol = "debate"
            skills = {"debater": ["analysis"], "reviewer": ["review"]}

        plan = _build_squad_plan(pattern, roles=roles, protocol=protocol, skills=skills)
        runner = StepRunner(
            plan, track_state=False, llm_client=_HardRejectLLM(issues="no evidence")
        )

        def executor(step: ExecutionStep, ctx: dict[str, Any]) -> dict[str, Any]:
            return {
                "step_id": step.step_id,
                "role_id": _role_of(step),
                "content": "blocked: no evidence",
            }

        result = runner.execute_all(executor)

        assert result["blocked"] >= 1, f"blocked verdict must surface, got {result}"
        assert result["failed"] >= result["blocked"], "failed must include blocked steps (F1)"
        assert result["completed"] < len(plan.steps), "blocked work must not count as completed"
        assert result["final_status"] == "blocked"
        assert result["review_status"] == "rejected"
        by_id = {r["step_id"]: r for r in result["results"]}
        # F2: per-step entries keep the legacy status value domain; blocked
        # granularity is carried by the blocked counter / StepOutcome / adapter.
        assert all(r["status"] in ("completed", "failed", "skipped") for r in by_id.values())
        blocked_entries = [r for r in by_id.values() if r["error"] and "blocked" in r["error"]]
        assert blocked_entries, "blocked steps must carry the blocked reason"
        # Engine run-completed contract restored (F3): the plan ran to
        # completion; acceptance is expressed via review_status/blocked.
        assert plan.status == PlanStatus.COMPLETED
        # Verdicts remain inspectable on the public result (additive key).
        assert result["verdicts"], "review verdicts must be delivered"
        assert any(not v["passed"] for v in result["verdicts"])
        # Handoff evidence was delivered to the reviewing role.
        assert any("no evidence" in str(v.get("issues")) for v in result["verdicts"])
        # StepOutcome + adapter agree with the dict counters (F1).
        outcome = runner.last_plan_outcome
        assert outcome is not None
        assert outcome.blocked == result["blocked"]
        assert outcome.failed == result["failed"]
        assert any(s.status.value == "blocked" for s in outcome.steps)
        from vibesop.agent.execution_protocol import (
            PlanExecutionResult,
            StepResultStatus,
        )

        adapted = PlanExecutionResult.from_step_runner_dict(result, plan)
        assert adapted.review_status == "rejected"
        assert any(r.status is StepResultStatus.BLOCKED for r in adapted.results)

    def test_squad_member_crash_fails_run_honestly(self):
        """B3 matrix (exception cell, squad entry): a member crash propagates
        through the engine as a run failure — the plan is FAILED, never
        presented as completed with the member silently dropped."""
        plan = _build_squad_plan(
            WorkflowPattern.AGENT_SQUAD,
            roles=["implementer", "reviewer"],
            protocol="review_gate",
            skills={"implementer": ["coding"], "reviewer": ["review"]},
        )
        runner = StepRunner(plan, track_state=False)

        def executor(step: ExecutionStep, ctx: dict[str, Any]) -> dict[str, Any]:
            if _role_of(step) == "implementer":
                raise RuntimeError("member crashed")
            return {"step_id": step.step_id, "role_id": _role_of(step), "content": "x"}

        with pytest.raises(RuntimeError, match="member crashed"):
            runner.execute_all(executor)

        assert plan.status == PlanStatus.FAILED


class TestSquadPublicExecutorContract:
    """R1 regression (third-pass audit): the public step_executor must receive
    the plan's own ExecutionStep — with the original skill_id / input_query and
    every other original field verbatim — even though the WorkflowEngine runs
    its internal SquadStep objects for squad patterns. The engine's enriched
    context (role_prompt, skill_isolation, handoff, verdicts) must still be
    delivered alongside.

    The plans come from the real PlanBuilder + real SkillLoader against temp
    SKILL.md files (no hand-built squad contracts, no stub loaders); the
    executor only uses the documented public step attributes.
    """

    @staticmethod
    def _build_real_squad_plan(tmp_path: Path) -> ExecutionPlan:
        from unittest.mock import patch

        from vibesop.core.models import IntentAnalysis
        from vibesop.core.orchestration.plan_builder import PlanBuilder
        from vibesop.core.orchestration.task_decomposer import SubTask
        from vibesop.core.skills.config_manager import SkillConfigManager
        from vibesop.core.skills.loader import SkillLoader

        for skill_id, capability in (("implskill", "coding"), ("revskill", "review")):
            skill_file = tmp_path / "skills" / skill_id / "SKILL.md"
            skill_file.parent.mkdir(parents=True, exist_ok=True)
            skill_file.write_text(
                f"---\nid: {skill_id}\nname: {skill_id}\ndescription: Dummy {skill_id}\n"
                f"capabilities: [{capability}]\n---\n# dummy\n"
            )
        loader = SkillLoader(
            tmp_path,
            search_paths=[tmp_path / "skills"],
            enable_external=False,
            strict_search_paths=True,
        )

        class _Router:
            def get_skill_loader(self) -> Any:
                return loader

        with patch.object(SkillConfigManager, "SKILL_CONFIG_FILE", tmp_path / "auto-config.yaml"):
            analysis = IntentAnalysis(
                complexity="multi_agent",
                facets=["test"],
                squad_needed=True,
                suggested_roles=["implementer", "reviewer"],
                collaboration_protocol="sequential",
                per_agent_skills={"implementer": ["implskill"], "reviewer": ["revskill"]},
                confidence=0.9,
            )
            return PlanBuilder(_Router()).build_plan(
                "implement and review",
                [SubTask(intent="run", query="run it", skill_id="implskill")],
                workflow_pattern=WorkflowPattern.AGENT_SQUAD,
                metadata={"intent_analysis": analysis},
            )

    @pytest.mark.parametrize("field", ["skill_id", "input_query"])
    def test_public_executor_reads_original_step_fields(self, tmp_path: Path, field: str):
        """A legal public executor that reads ``step.<field>`` on every squad
        callback must see the plan's own ExecutionStep values — not an
        AttributeError from an internal SquadStep, not a guessed skill, not a
        squad-instruction string standing in for the original query."""
        plan = self._build_real_squad_plan(tmp_path)
        plan_steps = {s.step_id: s for s in plan.steps}
        assert len(plan_steps) == 2
        seen: list[ExecutionStep] = []

        def executor(step: ExecutionStep, ctx: dict[str, Any]) -> str:
            seen.append(step)
            value = getattr(step, field)  # public contract: no compat shim needed
            # Engine-enriched context is still delivered alongside the step.
            assert ctx.get("role_prompt"), "role_prompt must reach the public executor"
            assert ctx.get("skill_isolation", {}).get("allowed_skills"), (
                "skill_isolation must reach the public executor"
            )
            return f"done {value}"

        runner = StepRunner(plan, project_root=tmp_path, track_state=False)
        result = runner.execute_all(executor)

        assert result["completed"] == 2
        assert result["failed"] == 0
        assert result["final_status"] == "completed"
        assert len(seen) == 2
        for step in seen:
            # The exact original plan step object — identity, not a copy,
            # wrapper, or engine-internal type.
            assert type(step) is ExecutionStep
            assert step is plan_steps[step.step_id]
            assert getattr(step, field) == getattr(plan_steps[step.step_id], field)
        assert {s.skill_id for s in seen} == {"implskill", "revskill"}

    def test_public_executor_receives_original_step_identity(self, tmp_path: Path):
        """Both public fields stay verbatim on the delivered step: skill_id
        keeps the producer's real skill and input_query keeps the producer's
        original query (never the SquadStep instruction payload)."""
        plan = self._build_real_squad_plan(tmp_path)
        plan_steps = {s.step_id: s for s in plan.steps}

        def executor(step: ExecutionStep, ctx: dict[str, Any]) -> str:
            original = plan_steps[step.step_id]
            assert step is original, "executor must receive the original plan step"
            assert step.skill_id == original.skill_id
            assert step.input_query == original.input_query
            return "ok"

        runner = StepRunner(plan, project_root=tmp_path, track_state=False)
        result = runner.execute_all(executor)

        assert result["completed"] == 2
        assert result["failed"] == 0
        assert result["review_status"] == "accepted"


class TestTrackerGate:
    """8.3.1-P1-3: state persistence is gated on the execution_ready verdict,
    and a missing verdict (never annotated) must be loudly diagnosable."""

    def test_ready_plan_creates_tracker(self, tmp_path):
        plan = _make_plan([("a/b", "intent", "do it", None)])
        plan.metadata["execution_ready"] = True
        runner = StepRunner(plan, project_root=tmp_path)
        assert runner._tracker is not None
        assert (tmp_path / ".vibe" / "execution_plans.jsonl").exists()

    def test_blocked_plan_skips_tracker(self, tmp_path, caplog):
        import logging

        plan = _make_plan([("a/b", "intent", "do it", None)])
        plan.metadata["execution_ready"] = False
        with caplog.at_level(logging.INFO, logger="vibesop.agent.step_runner"):
            runner = StepRunner(plan, project_root=tmp_path)
        assert runner._tracker is None
        assert not (tmp_path / ".vibe" / "execution_plans.jsonl").exists()
        assert any("blocked" in rec.message for rec in caplog.records)

    def test_unannotated_plan_skips_tracker_with_warning(self, tmp_path, caplog):
        import logging

        plan = _make_plan([("a/b", "intent", "do it", None)])
        with caplog.at_level(logging.WARNING, logger="vibesop.agent.step_runner"):
            runner = StepRunner(plan, project_root=tmp_path)
        assert runner._tracker is None
        assert any("execution_ready" in rec.message for rec in caplog.records)


class TestStaticLaneOutcomeMatrix:
    """B3 matrix for the static (serial/parallel) public entry:
    OK / exception / failed sentinel / dependency failure / cancel."""

    def test_matrix_dependency_failure_marks_downstream_skipped(self):
        """Dependency failure: the failed step is failed, the dependent step
        is explicitly skipped (never runs on empty upstream output), and the
        shared aggregation accounts for every step."""
        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "depends on a", ["step-1"]),
                ("skill-c", "step 3", "independent", None),
            ]
        )
        runner = StepRunner(plan, track_state=False)

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
            if step.step_id == "step-1":
                raise RuntimeError("step 1 exploded")
            return f"OK {step.skill_id}"

        result = runner.execute_all(executor)

        assert result["failed"] == 1
        assert result["completed"] == 1  # only skill-c ran successfully
        assert result["skipped"] == 1  # step-2's dependency failed
        assert result["final_status"] == "partial"
        by_id = {r["step_id"]: r for r in result["results"]}
        assert by_id["step-1"]["status"] == "failed"
        assert plan.steps[1].status == StepStatus.SKIPPED
        assert plan.steps[1].step_id not in by_id or by_id["step-2"].get("status") in (
            "skipped",
            "failed",
        )

    def test_matrix_serial_blocked_sentinel_counts_blocked(self):
        """Blocked sentinel in the serial branch counts in BOTH failed and
        blocked (F1 restored contract) — and every public face agrees:
        returned dict, runner property, StepStatus, StepOutcome, adapter."""
        from vibesop.agent.execution_protocol import (
            PlanExecutionResult,
            StepResultStatus,
        )

        plan = _make_plan([("skill-a", "step 1", "do step 1", None)])
        runner = StepRunner(plan, track_state=False)

        result = runner.execute_all(lambda step, ctx: "blocked: need human approval")

        assert result["blocked"] == 1
        assert result["failed"] == 1
        assert result["completed"] == 0
        assert result["final_status"] == "blocked"
        # F2: entry status keeps the legacy value domain.
        assert result["results"][0]["status"] == "failed"
        # Four-face consistency (F1).
        assert runner.failed_count == 1
        assert plan.steps[0].status == StepStatus.FAILED
        outcome = runner.last_plan_outcome
        assert outcome is not None
        assert outcome.failed == 1 and outcome.blocked == 1
        assert outcome.steps[0].status.value == "blocked"
        adapted = PlanExecutionResult.from_step_runner_dict(result, plan)
        assert adapted.results[0].status is StepResultStatus.BLOCKED
        assert adapted.review_status == "not_required"

    def test_matrix_cancel_propagates(self):
        """Cancel cell: asyncio.CancelledError is a BaseException — it must
        propagate out of execute_all, never be swallowed as a step failure."""
        import asyncio

        plan = _make_plan([("skill-a", "step 1", "do step 1", None)])
        runner = StepRunner(plan, track_state=False)

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            runner.execute_all(executor)

        # Cancel propagates without cleanup — the step is left in_progress,
        # which is exactly why callers must treat cancellation as a run
        # abort, not a per-step failure.
        assert plan.steps[0].status == StepStatus.IN_PROGRESS

    def test_matrix_empty_plan_is_completed(self):
        """OK cell edge: an empty plan completes with zero counters."""
        plan = _make_plan([])
        runner = StepRunner(plan, track_state=False)

        result = runner.execute_all(lambda step, ctx: "unused")

        assert result["completed"] == 0
        assert result["failed"] == 0
        assert result["skipped"] == 0
        assert result["blocked"] == 0
        assert result["final_status"] == "completed"

    def test_matrix_abort_marks_only_dependency_blocked_steps_skipped(self):
        """F6: after a fail_fast abort, only steps that can NEVER run — a
        transitive dependency failed or was skipped — are marked skipped.
        This is the authorized narrowing of the first-version sweep that
        marked every undispatched step skipped."""
        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "depends on a", ["step-1"]),
                ("skill-c", "step 3", "depends on b", ["step-2"]),
            ]
        )
        runner = StepRunner(plan, track_state=False)

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
            raise RuntimeError(f"Fail {step.step_id}")

        result = runner.execute_all(executor, fail_fast=True)

        assert result["failed"] == 1
        # Both downstream steps are transitively unrunnable → skipped,
        # never dispatched.
        assert result["skipped"] == 2
        assert plan.steps[1].status == StepStatus.SKIPPED
        assert plan.steps[2].status == StepStatus.SKIPPED
        # Every plan step accounted for by the shared aggregation.
        assert (
            result["completed"] + result["failed"] + result["skipped"] + result["blocked"]
            == runner.total_steps
        )

    def test_matrix_cancel_leaves_undispatched_steps_pending_for_resume(self):
        """F6 resume contract: cancellation aborts the run BEFORE the
        terminal dependency-skip scan — the scan must never claim steps
        that were not dispatched. The undispatched dependent step stays
        PENDING (not SKIPPED), the runner is not complete, and the step
        remains recoverable through pending_steps()-driven resume."""
        import asyncio

        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "depends on a", ["step-1"]),
            ]
        )
        runner = StepRunner(plan, track_state=False)

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            runner.execute_all(executor)

        # The cancel cell propagates without cleanup — step-2 was never
        # dispatched and must NOT be marked skipped by any terminal scan.
        assert plan.steps[1].status == StepStatus.PENDING
        assert not runner._states["step-2"].completed
        assert not runner.is_complete
        # Resume surface intact: a consumer that records the cancelled step
        # and re-drives pending steps still finds step-2 undispatched.
        runner.mark_failed(plan.steps[0], "cancelled by caller")
        assert plan.steps[1].status == StepStatus.PENDING
        assert not runner.is_complete


class TestExecutionProtocolAdapter:
    """B3: StepResult/PlanExecutionResult is the public face over the legacy
    execute_all dicts — one thin adapter, no third vocabulary."""

    def test_adapter_static_lane(self):
        from vibesop.agent.execution_protocol import (
            PlanExecutionResult,
            StepResultStatus,
        )

        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "do step 2", ["step-1"]),
            ]
        )
        runner = StepRunner(plan, track_state=False)
        result = runner.execute_all(lambda step, ctx: f"out-{step.step_id}")

        adapted = PlanExecutionResult.from_step_runner_dict(result, plan)

        assert adapted.plan_id == plan.plan_id
        assert [r.step_id for r in adapted.results] == ["step-1", "step-2"]
        assert all(r.status is StepResultStatus.SUCCESS for r in adapted.results)
        assert adapted.all_succeeded
        assert {r.skill_id for r in adapted.results} == {"skill-a", "skill-b"}

    def test_adapter_dynamic_lane_preserves_dict_shape(self):
        """The dynamic lane's legacy results dict (keyed by step identity)
        passes through the runner unchanged and adapts entry-by-entry."""
        from vibesop.agent.execution_protocol import (
            PlanExecutionResult,
            StepResultStatus,
        )

        plan = _build_loop_until_dry_plan()
        runner = StepRunner(plan, track_state=False)
        result = runner.execute_all(lambda step, ctx: "dry")

        assert isinstance(result["results"], dict)
        adapted = PlanExecutionResult.from_step_runner_dict(result, plan)

        assert adapted.plan_id == plan.plan_id
        assert all(r.status is StepResultStatus.SUCCESS for r in adapted.results)

    def test_adapter_blocked_and_failed_entries(self):
        from vibesop.agent.execution_protocol import (
            PlanExecutionResult,
            StepResultStatus,
        )

        plan = _make_plan(
            [
                ("skill-a", "step 1", "do step 1", None),
                ("skill-b", "step 2", "do step 2", None),
                ("skill-c", "step 3", "do step 3", None),
            ]
        )
        runner = StepRunner(plan, track_state=False, max_parallel=3)

        def executor(step: ExecutionStep, ctx: StepRunContext) -> str:
            return {
                "step-1": "all good",
                "step-2": "blocked: no evidence",
                "step-3": "failed: tests red",
            }[step.step_id]

        result = runner.execute_all(executor)
        adapted = PlanExecutionResult.from_step_runner_dict(result, plan)
        by_id = {r.step_id: r.status for r in adapted.results}

        assert by_id == {
            "step-1": StepResultStatus.SUCCESS,
            "step-2": StepResultStatus.BLOCKED,
            "step-3": StepResultStatus.FAILED,
        }
        assert not adapted.all_succeeded
        assert adapted.success_count == 1
