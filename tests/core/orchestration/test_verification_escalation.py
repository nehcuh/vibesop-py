"""Phase 2: ESCALATE activation + failure classification in decide_action.

Roadmap 2.1/2.2 — the failed path now classifies before deciding:
- same error signature twice → ESCALATE (retrying yields nothing new)
- PERMANENT (incl. evidence-free, the classifier's conservative default)
  → TERMINATE
- transient first occurrence below threshold and inside the retry budget
  → RETRY (this is what makes escalation_threshold reachable at all)
- consecutive failures >= escalation_threshold → ESCALATE (backstop)
- max_retries bounds the failed path too (shared bounded-retry budget)
"""

from __future__ import annotations

from vibesop.core.models import ExecutionStep
from vibesop.core.orchestration.verification_loop import (
    VerificationLoop,
    VerificationLoopAction,
    VerificationLoopConfig,
)


def _step() -> ExecutionStep:
    return ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )


def test_transient_failure_first_occurrence_retries() -> None:
    loop = VerificationLoop()
    action = loop.decide_action(_step(), {"status": "failed", "reasoning": "connection timed out"})

    assert action == VerificationLoopAction.RETRY
    state = loop.get_state("test-1")
    assert state.consecutive_failures == 1
    assert state.retry_count == 1
    assert state.last_failure_category == "transient"


def test_permanent_failure_terminates_without_retry() -> None:
    loop = VerificationLoop()
    action = loop.decide_action(_step(), {"status": "failed", "reasoning": "invalid api key"})

    assert action == VerificationLoopAction.TERMINATE
    state = loop.get_state("test-1")
    assert state.last_failure_category == "permanent"
    assert state.retry_count == 0


def test_evidence_free_failure_terminates() -> None:
    """No reasoning/issues → classifier's conservative default PERMANENT → TERMINATE.

    This is exactly the pre-Phase-2 behaviour for evidence-free failures
    (test_verification_phase2.py::test_verification_loop_decide_action_failed).
    """
    loop = VerificationLoop()
    action = loop.decide_action(_step(), {"status": "failed", "confidence": 0.3})

    assert action == VerificationLoopAction.TERMINATE


def test_same_signature_twice_escalates() -> None:
    loop = VerificationLoop()
    payload = {"status": "failed", "reasoning": "rate limit exceeded"}

    first = loop.decide_action(_step(), payload)
    second = loop.decide_action(_step(), payload)

    assert first == VerificationLoopAction.RETRY
    assert second == VerificationLoopAction.ESCALATE


def test_digit_variations_share_signature() -> None:
    """Counts/IDs vary between occurrences of the same error; digits are stripped."""
    loop = VerificationLoop()
    first = loop.decide_action(_step(), {"status": "failed", "reasoning": "timeout after 30s"})
    second = loop.decide_action(_step(), {"status": "failed", "reasoning": "timeout after 45s"})

    assert first == VerificationLoopAction.RETRY
    assert second == VerificationLoopAction.ESCALATE


def test_distinct_signatures_escalate_at_threshold() -> None:
    """Backstop: different transient errors still escalate once consecutive
    failures reach escalation_threshold (default 2)."""
    loop = VerificationLoop()
    first = loop.decide_action(_step(), {"status": "failed", "reasoning": "connection reset by peer"})
    second = loop.decide_action(_step(), {"status": "failed", "reasoning": "service unavailable"})

    assert first == VerificationLoopAction.RETRY
    assert second == VerificationLoopAction.ESCALATE


def test_threshold_three_permits_second_retry() -> None:
    loop = VerificationLoop(VerificationLoopConfig(escalation_threshold=3))
    first = loop.decide_action(_step(), {"status": "failed", "reasoning": "connection reset by peer"})
    second = loop.decide_action(_step(), {"status": "failed", "reasoning": "rate limit hit"})
    third = loop.decide_action(_step(), {"status": "failed", "reasoning": "temporary dns failure"})

    assert first == VerificationLoopAction.RETRY
    assert second == VerificationLoopAction.RETRY
    assert third == VerificationLoopAction.ESCALATE
    assert loop.get_state("test-1").consecutive_failures == 3


def test_max_retries_bounds_failed_path() -> None:
    loop = VerificationLoop(VerificationLoopConfig(max_retries=1, escalation_threshold=99))
    first = loop.decide_action(_step(), {"status": "failed", "reasoning": "connection reset by peer"})
    second = loop.decide_action(_step(), {"status": "failed", "reasoning": "rate limit hit"})

    assert first == VerificationLoopAction.RETRY
    assert second == VerificationLoopAction.ESCALATE


def test_issue_descriptions_feed_classification() -> None:
    loop = VerificationLoop()
    action = loop.decide_action(
        _step(),
        {
            "status": "failed",
            "issues": [{"severity": "high", "category": "infra", "description": "rate limit exceeded"}],
        },
    )

    assert action == VerificationLoopAction.RETRY


def test_state_records_signature_and_category() -> None:
    loop = VerificationLoop()
    loop.decide_action(_step(), {"status": "failed", "reasoning": "connection timed out"})

    state = loop.get_state("test-1")
    assert len(state.failure_signatures) == 1
    assert state.last_failure_category == "transient"


def test_passed_resets_consecutive_failures() -> None:
    loop = VerificationLoop()
    step = _step()
    loop.decide_action(step, {"status": "failed", "reasoning": "connection timed out"})
    loop.decide_action(step, {"status": "passed"})

    assert loop.get_state("test-1").consecutive_failures == 0
