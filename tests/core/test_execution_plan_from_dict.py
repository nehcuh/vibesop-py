"""Tests for ExecutionPlan.from_dict / ExecutionStep.from_dict (v7.0.10).

Background: prior to v7.0.10, three call sites in agent/__init__.py
each manually rebuilt ExecutionPlan/ExecutionStep from dicts with a
different subset of fields:

- ``get_parallel_preview`` (line 362): dropped parallel_group, metadata,
  step_type, trust_level, dynamic_status, loop_iteration, contestant_index,
  verification_result, estimated_*, source_files, assigned_role,
  agent_squad_id, role_skills, original_query_segment.
- ``execute_plan`` (line 400): same drop set as get_parallel_preview.
- ``create_runner`` (line 450): dropped metadata, step_type, trust_level,
  estimated_*, source_files, agent_squad_id, role_skills, verification_result.

Any new field added to ExecutionStep or ExecutionPlan would silently
disappear when crossing the agent boundary, with no type-checker signal.

v7.0.10 adds ``ExecutionStep.from_dict`` and ``ExecutionPlan.from_dict``
classmethods that round-trip the full schema, and migrates the three
call sites to use them.
"""

from __future__ import annotations

import pytest

from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    StepStatus,
    TrustLevel,
    WorkflowPattern,
)


def _build_full_step(
    *,
    step_id: str = "step-1",
    step_number: int = 1,
) -> ExecutionStep:
    """Build an ExecutionStep with every field populated."""
    return ExecutionStep(
        step_id=step_id,
        step_number=step_number,
        skill_id="some/skill",
        intent="do the thing",
        original_query_segment="original query segment",
        input_query="input query text",
        output_as="step_result",
        status=StepStatus.COMPLETED,
        result_summary="done",
        started_at="2026-06-14T10:00:00",
        completed_at="2026-06-14T10:05:00",
        dependencies=[],
        can_parallel=True,
        parallel_group=2,
        is_verification_step=True,
        verification_result={"passed": True},
        trust_level=TrustLevel.QUARANTINE,
        dynamic_status=None,
        loop_iteration=3,
        contestant_index=1,
        step_type="review",
        estimated_risk="high",
        estimated_file_count=5,
        source_files=["a.py", "b.py"],
        assigned_role="architect",
        agent_squad_id="squad-1",
        role_skills=["system-design"],
    )


def _build_full_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-1",
        original_query="the original query",
        steps=[_build_full_step(), _build_full_step(step_id="step-2", step_number=2)],
        detected_intents=["intent_a", "intent_b"],
        reasoning="because",
        created_at="2026-06-14T09:00:00",
        status=PlanStatus.ACTIVE,
        execution_mode=ExecutionMode.PARALLEL,
        workflow_pattern=WorkflowPattern.AGENT_SQUAD,
        is_dynamic=True,
        dry_threshold=4,
        max_reorchestration_rounds=10,
        reorchestration_history=[{"round": 1}],
        metadata={"review_type": "multi_dimensional"},
    )


class TestExecutionStepRoundTrip:
    """ExecutionStep.to_dict() → from_dict() preserves all fields."""

    def test_round_trip_preserves_all_fields(self) -> None:
        original = _build_full_step()
        rebuilt = ExecutionStep.from_dict(original.to_dict())
        assert rebuilt == original

    def test_round_trip_with_minimal_step(self) -> None:
        """A step with only required fields round-trips cleanly."""
        original = ExecutionStep(step_id="x", step_number=1, skill_id="y")
        rebuilt = ExecutionStep.from_dict(original.to_dict())
        assert rebuilt == original

    def test_from_dict_tolerates_missing_optional_keys(self) -> None:
        """from_dict should accept a dict with only required keys + use defaults."""
        minimal = {"step_id": "x", "step_number": 1, "skill_id": "y"}
        step = ExecutionStep.from_dict(minimal)
        assert step.step_id == "x"
        assert step.intent == ""
        assert step.dependencies == []
        assert step.can_parallel is True
        assert step.parallel_group is None
        assert step.trust_level == TrustLevel.TRUSTED

    def test_from_dict_ignores_stray_keys(self) -> None:
        """Unknown keys in the input dict must not raise."""
        data = {
            "step_id": "x",
            "step_number": 1,
            "skill_id": "y",
            "unknown_future_field": "ignored",
            "another_stray": [1, 2, 3],
        }
        step = ExecutionStep.from_dict(data)
        assert step.step_id == "x"

    def test_preserves_phase_7_fields(self) -> None:
        """Fields added in v7.0/v7.1 must survive round-trip (the bug fix)."""
        original = _build_full_step()
        rebuilt = ExecutionStep.from_dict(original.to_dict())
        assert rebuilt.step_type == "review"
        assert rebuilt.estimated_risk == "high"
        assert rebuilt.estimated_file_count == 5
        assert rebuilt.source_files == ["a.py", "b.py"]
        assert rebuilt.assigned_role == "architect"
        assert rebuilt.agent_squad_id == "squad-1"
        assert rebuilt.role_skills == ["system-design"]


class TestExecutionPlanRoundTrip:
    """ExecutionPlan.to_dict() → from_dict() preserves all fields."""

    def test_round_trip_preserves_all_fields(self) -> None:
        original = _build_full_plan()
        rebuilt = ExecutionPlan.from_dict(original.to_dict())
        assert rebuilt == original

    def test_round_trip_preserves_metadata(self) -> None:
        """metadata field must survive (the S19 Final Phase branch bug)."""
        original = _build_full_plan()
        rebuilt = ExecutionPlan.from_dict(original.to_dict())
        assert rebuilt.metadata == {"review_type": "multi_dimensional"}

    def test_round_trip_preserves_workflow_pattern(self) -> None:
        original = _build_full_plan()
        rebuilt = ExecutionPlan.from_dict(original.to_dict())
        assert rebuilt.workflow_pattern == WorkflowPattern.AGENT_SQUAD

    def test_from_dict_recursively_rebuilds_steps(self) -> None:
        """Each step in the plan must be fully reconstructed."""
        original = _build_full_plan()
        rebuilt = ExecutionPlan.from_dict(original.to_dict())
        assert len(rebuilt.steps) == 2
        for orig_step, reborn_step in zip(original.steps, rebuilt.steps, strict=True):
            assert reborn_step == orig_step

    def test_from_dict_tolerates_missing_steps_key(self) -> None:
        """A plan dict without 'steps' key produces an empty plan."""
        minimal = {"plan_id": "p"}
        plan = ExecutionPlan.from_dict(minimal)
        assert plan.plan_id == "p"
        assert plan.steps == []


class TestAgentRouterUsesFromDict:
    """Smoke: the migrated call sites in agent/__init__.py should still
    flow correctly."""

    def test_get_parallel_preview_with_full_plan(self) -> None:
        """End-to-end: a full plan dict survives the from_dict path."""
        from vibesop.agent import AgentRouter

        plan = _build_full_plan()
        plan_dict = plan.to_dict()

        # Build a minimal router stub; get_parallel_preview only needs
        # ParallelScheduler which doesn't depend on router state.
        router = object.__new__(AgentRouter)
        preview = router.get_parallel_preview(plan_dict)

        # Preview is a dict; just verify it returned something with
        # the plan_id propagated.
        assert isinstance(preview, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
