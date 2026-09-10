"""A rejected or missing verdict must never authorize downstream execution."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from vibesop.core.models import ExecutionPlan, ExecutionStep, WorkflowPattern
from vibesop.core.orchestration.verification_loop import (
    VerificationLoop,
    VerificationLoopAction,
    execute_plan_with_verification,
)
from vibesop.core.orchestration.verifier import (
    VerificationResult,
    VerificationStatus,
    VerificationStrictness,
    VerifierAgent,
)


def _plan():
    return ExecutionPlan(
        plan_id="guarded",
        workflow_pattern=WorkflowPattern.ADVERSARIAL,
        steps=[
            ExecutionStep(step_id="build", step_number=1, skill_id="build"),
            ExecutionStep(
                step_id="deliver", step_number=2, skill_id="deliver", dependencies=["build"]
            ),
        ],
    )


def test_missing_verdict_is_not_a_pass():
    payload = VerificationResult(status=VerificationStatus.PASSED).to_dict()
    payload.pop("status")
    loop = VerificationLoop()
    assert loop.decide_action(_plan().steps[0], payload) == VerificationLoopAction.ESCALATE
    assert loop.get_state("build").last_status == "error"


@pytest.mark.parametrize("status", [None, "approved", "", 123])
@pytest.mark.parametrize("strictness", list(VerificationStrictness))
def test_invalid_llm_verdict_cannot_be_upgraded_to_pass(status, strictness):
    payload = VerificationResult(status=VerificationStatus.PASSED).to_dict()
    if status is None:
        payload.pop("status")
    else:
        payload["status"] = status
    llm = SimpleNamespace(call=Mock(return_value=SimpleNamespace(content=json.dumps(payload))))
    result = VerifierAgent(llm, strictness=strictness).verify("Build", _plan().steps[0], "artifact")
    assert result.status == VerificationStatus.ERROR
    assert result.confidence == 0.0


@pytest.mark.parametrize("status", [VerificationStatus.FAILED, VerificationStatus.ERROR])
def test_rejected_verdict_stops_downstream_execution(status):
    executor = Mock(return_value="artifact")
    verdict = VerificationResult(status=status, reasoning="Not accepted")
    verifier = SimpleNamespace(verify=Mock(return_value=verdict))
    result = execute_plan_with_verification(_plan(), executor, verifier)
    assert [call.args[0].step_id for call in executor.call_args_list] == ["build"]
    assert "error" in result["results"]["build"]
    assert result["results"]["build"]["verification_result"] == verdict.to_dict()
    assert "deliver" not in result["results"]


@pytest.mark.parametrize("on_retry", [False, True])
def test_executor_failure_stops_dependent_steps(on_retry):
    effects = (
        ["artifact", RuntimeError("build failed")] if on_retry else [RuntimeError("build failed")]
    )
    executor = Mock(side_effect=effects)
    verifier = SimpleNamespace(
        verify=Mock(return_value=VerificationResult(status=VerificationStatus.NEEDS_REVISION))
    )
    result = execute_plan_with_verification(_plan(), executor, verifier)
    assert all(call.args[0].step_id == "build" for call in executor.call_args_list)
    assert result["results"]["build"]["error"] == "build failed"
    assert "deliver" not in result["results"]


def test_explicit_pass_continues_to_dependent_step():
    executor = Mock(return_value="artifact")
    verifier = SimpleNamespace(
        verify=Mock(return_value=VerificationResult(status=VerificationStatus.PASSED))
    )
    result = execute_plan_with_verification(_plan(), executor, verifier)
    assert [call.args[0].step_id for call in executor.call_args_list] == ["build", "deliver"]
    assert result["results"] == {"build": "artifact", "deliver": "artifact"}


def test_quarantine_blocked_or_failed_is_not_pass() -> None:
    from vibesop.core.models import TrustLevel

    loop = VerificationLoop()
    step = ExecutionStep(
        step_id="verify",
        step_number=2,
        skill_id="builtin/verify-result",
        trust_level=TrustLevel.QUARANTINE,
        is_verification_step=True,
    )
    assert loop.verify_step(step, "blocked") is False
    assert loop.verify_step(step, "failed") is False
    assert loop.verify_step(step, "blocked: missing test evidence") is False
    assert loop.verify_step(step, "ok evidence") is True


def test_verification_step_is_executed() -> None:
    plan = ExecutionPlan(
        plan_id="with-verify",
        workflow_pattern=WorkflowPattern.ADVERSARIAL,
        steps=[
            ExecutionStep(step_id="build", step_number=1, skill_id="build"),
            ExecutionStep(
                step_id="verify",
                step_number=2,
                skill_id="builtin/verify-result",
                dependencies=["build"],
                is_verification_step=True,
            ),
        ],
    )
    executor = Mock(return_value="passed")
    verifier = SimpleNamespace(
        verify=Mock(return_value=VerificationResult(status=VerificationStatus.PASSED))
    )
    result = execute_plan_with_verification(plan, executor, verifier)
    assert [call.args[0].step_id for call in executor.call_args_list] == ["build", "verify"]
    assert "verify" in result["results"]
