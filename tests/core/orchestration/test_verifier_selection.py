"""Contract tests for adversarial verifier selection in PlanBuilder.

Spec A: verifier_skill_id is a keyword-only parameter of build_plan defaulting
to builtin/verify-result; for ADVERSARIAL plans explicit invalid values
(blank, non-string including None, fallback-llm) raise ValueError instead of
silently falling back; other patterns ignore the parameter entirely; the
verification step depends on all original steps and carries type / expected
output / requirements with itemized-evidence acceptance rules.
"""

from __future__ import annotations

import pytest

from vibesop.core.models import (
    ExecutionMode,
    StepStatus,
    TrustLevel,
    WorkflowPattern,
)
from vibesop.core.orchestration.plan_builder import (
    DEFAULT_VERIFIER_SKILL_ID,
    PlanBuilder,
)
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


def _build(
    pattern: WorkflowPattern,
    verifier_skill_id: object = "unset",
    sub_tasks: list[SubTask] | None = None,
) -> object:
    builder = PlanBuilder(FakeRouter())
    # Only None falls back to the default tasks; an explicit [] stays empty.
    tasks = (
        [
            # Intents chosen so _classify_step_type is deterministic:
            # "分析" → analysis, "测试" → review
            SubTask(intent="分析崩溃日志", query="分析崩溃日志", task_type="debug"),
            SubTask(intent="运行测试", query="运行全部测试", task_type="test"),
        ]
        if sub_tasks is None
        else sub_tasks
    )
    kwargs: dict = {"workflow_pattern": pattern}
    if verifier_skill_id != "unset":
        kwargs["verifier_skill_id"] = verifier_skill_id
    return builder.build_plan("原始需求: 修复并发死锁", tasks, **kwargs)


def _verify_step(plan) -> object:
    return plan.steps[-1]


class TestDefaultVerifier:
    def test_default_is_builtin_verify_result(self):
        plan = _build(WorkflowPattern.ADVERSARIAL)
        verify = _verify_step(plan)
        assert verify.skill_id == DEFAULT_VERIFIER_SKILL_ID
        assert verify.skill_id == "builtin/verify-result"

    def test_default_is_distinguishable_from_explicit_invalid(self):
        # Omitted parameter -> default, no exception
        plan = _build(WorkflowPattern.ADVERSARIAL)
        assert _verify_step(plan).skill_id == "builtin/verify-result"
        # Explicit None is a non-string -> ValueError, never a silent fallback
        with pytest.raises(ValueError):
            _build(WorkflowPattern.ADVERSARIAL, verifier_skill_id=None)


class TestExplicitVerifier:
    def test_explicit_skill_id_is_used(self):
        plan = _build(WorkflowPattern.ADVERSARIAL, verifier_skill_id="omx/verify")
        assert _verify_step(plan).skill_id == "omx/verify"

    def test_explicit_skill_id_with_surrounding_whitespace_is_used(self):
        plan = _build(WorkflowPattern.ADVERSARIAL, verifier_skill_id="  omx/verify  ")
        assert _verify_step(plan).skill_id == "omx/verify"


class TestInvalidVerifierRejected:
    @pytest.mark.parametrize(
        "bad_value",
        ["", "   ", "\t\n", "fallback-llm", " fallback-llm ", None, 123, 0, ["x/y"], object()],
    )
    def test_invalid_values_raise_value_error(self, bad_value):
        with pytest.raises(ValueError):
            _build(WorkflowPattern.ADVERSARIAL, verifier_skill_id=bad_value)

    def test_invalid_rejected_even_when_steps_empty(self):
        # ADVERSARIAL validation applies regardless of step count; sub_tasks
        # is a real empty list here (only None triggers the default tasks).
        with pytest.raises(ValueError):
            _build(WorkflowPattern.ADVERSARIAL, verifier_skill_id="", sub_tasks=[])

    def test_adversarial_empty_steps_yields_no_verify_step(self):
        plan = _build(WorkflowPattern.ADVERSARIAL, sub_tasks=[])
        assert plan.steps == []

    @pytest.mark.parametrize("bad_value", ["fallback-llm", "", None])
    def test_invalid_ignored_for_non_adversarial_patterns(self, bad_value):
        # Validation applies only to ADVERSARIAL; other patterns ignore the
        # parameter entirely, even when the explicit value is invalid.
        baseline = _build(WorkflowPattern.PARALLEL)
        with_verifier = _build(WorkflowPattern.PARALLEL, verifier_skill_id=bad_value)
        assert len(with_verifier.steps) == len(baseline.steps)
        assert [s.skill_id for s in with_verifier.steps] == [s.skill_id for s in baseline.steps]
        assert [s.input_query for s in with_verifier.steps] == [
            s.input_query for s in baseline.steps
        ]


class TestKeywordOnlySignature:
    def test_verifier_skill_id_is_keyword_only(self):
        builder = PlanBuilder(FakeRouter())
        tasks = [SubTask(intent="分析崩溃日志", query="分析崩溃日志")]
        with pytest.raises(TypeError):
            builder.build_plan("原始需求", tasks, WorkflowPattern.ADVERSARIAL, None, "omx/verify")


class TestOtherPatternsUnchanged:
    @pytest.mark.parametrize(
        "pattern",
        [
            WorkflowPattern.SEQUENTIAL,
            WorkflowPattern.PARALLEL,
            WorkflowPattern.FAN_OUT,
            WorkflowPattern.LOOP_UNTIL_DRY,
            WorkflowPattern.TOURNAMENT,
        ],
    )
    def test_explicit_verifier_has_no_effect_on_other_patterns(self, pattern):
        baseline = _build(pattern)
        with_verifier = _build(pattern, verifier_skill_id="omx/verify")

        assert len(with_verifier.steps) == len(baseline.steps)
        for got, want in zip(with_verifier.steps, baseline.steps, strict=True):
            assert got.skill_id == want.skill_id
            assert got.intent == want.intent
            assert got.input_query == want.input_query
            assert got.can_parallel == want.can_parallel
            assert got.is_verification_step == want.is_verification_step
            assert got.trust_level == want.trust_level
            assert len(got.dependencies) == len(want.dependencies)

    def test_execution_mode_unchanged_by_verifier_param(self):
        baseline = _build(WorkflowPattern.SEQUENTIAL)
        with_verifier = _build(WorkflowPattern.SEQUENTIAL, verifier_skill_id="omx/verify")
        assert with_verifier.execution_mode == baseline.execution_mode


class TestVerificationStepContract:
    def test_verify_step_real_to_dict_serialization(self):
        plan = _build(WorkflowPattern.ADVERSARIAL)
        serialized = _verify_step(plan).to_dict()

        assert serialized["is_verification_step"] is True
        assert serialized["trust_level"] == TrustLevel.QUARANTINE.value
        assert serialized["status"] == StepStatus.PENDING.value
        assert serialized["skill_id"] == "builtin/verify-result"
        assert serialized["dependencies"] == [s.step_id for s in plan.steps[:-1]]

    def test_verify_step_contract_fields(self):
        plan = _build(WorkflowPattern.ADVERSARIAL)
        verify = _verify_step(plan)

        assert verify.is_verification_step is True
        assert verify.trust_level == TrustLevel.QUARANTINE
        assert verify.status == StepStatus.PENDING
        assert verify.original_query_segment == "原始需求: 修复并发死锁"
        assert verify.output_as == "verification_result"
        assert verify.can_parallel is False
        assert verify.step_number == len(plan.steps)
        assert verify.confidence >= 0.6

    def test_verify_step_depends_on_all_original_steps(self):
        plan = _build(WorkflowPattern.ADVERSARIAL)
        verify = _verify_step(plan)
        original_ids = [s.step_id for s in plan.steps[:-1]]
        assert verify.dependencies == original_ids
        # Multi-step: the first step is also a dependency, not just the last
        assert plan.steps[0].step_id in verify.dependencies

    def test_input_query_provides_original_request_and_step_contract(self):
        plan = _build(WorkflowPattern.ADVERSARIAL)
        verify = _verify_step(plan)
        query = verify.input_query

        # Original request preserved
        assert "原始需求: 修复并发死锁" in query
        # Each step: type, expected output, requirement (intent)
        for step in plan.steps[:-1]:
            assert step.intent in query
            assert step.output_as in query
            assert step.skill_id in query
        assert "analysis" in query  # classified step_type of first sub-task
        assert "review" in query  # classified step_type of second sub-task

    def test_input_query_requires_itemized_evidence_and_no_default_pass(self):
        plan = _build(WorkflowPattern.ADVERSARIAL)
        query = _verify_step(plan).input_query

        assert "证据" in query
        assert "不得以代理自述代替证据" in query
        assert "blocked" in query
        assert "failed" in query
        assert "passed" in query
        assert "不得默认通过" in query
        assert "不得运行未获授权的部署" in query
        assert "不得修改实现" in query

    def test_adversarial_still_forces_sequential_mode(self):
        plan = _build(WorkflowPattern.ADVERSARIAL, verifier_skill_id="omx/verify")
        assert plan.execution_mode == ExecutionMode.SEQUENTIAL


class TestStaticCallCompatibility:
    def test_static_apply_adversarial_keeps_positional_signature(self):
        from vibesop.core.models import ExecutionStep

        step = ExecutionStep(
            step_id="s1", step_number=1, skill_id="x/y", intent="do it", output_as="s1_out"
        )
        steps = [step]

        # Two-positional-arg call (existing orchestrator.py:407 usage)
        out = PlanBuilder._apply_adversarial(steps, "原始需求")
        assert out[-1].skill_id == "builtin/verify-result"
        assert out[-1].dependencies == ["s1"]

        # Third positional arg still works
        steps2 = [step.model_copy(deep=True)]
        out2 = PlanBuilder._apply_adversarial(steps2, "原始需求", "omx/verify")
        assert out2[-1].skill_id == "omx/verify"

        # Explicit None is a non-string and is rejected, not treated as default
        steps3 = [step.model_copy(deep=True)]
        with pytest.raises(ValueError):
            PlanBuilder._apply_adversarial(steps3, "原始需求", None)
