"""Phase 1 default-deny: is_verified_success + three-tier classification.

The success side of the shared predicate vocabulary: only positive acceptance
evidence ("passed" / "passed:" / dict status in {passed, completed, success})
is verified success. Everything else — prose, empty, None, evidence-free
dicts — must classify as UNVERIFIED, never SUCCESS and never a failure.
"""

from __future__ import annotations

import pytest

from vibesop.agent.step_runner import StepOutcomeStatus, _classify_output
from vibesop.core.orchestration.verification_loop import is_verified_success


@pytest.mark.parametrize(
    "output",
    [
        "passed",
        "PASSED",
        "passed: all checks green",
        {"status": "passed"},
        {"status": "completed"},
        {"status": "SUCCESS"},
        {"status": "success", "evidence": ["t1", "t2"]},
    ],
)
def test_positive_evidence_is_verified_success(output) -> None:
    assert is_verified_success(output) is True
    assert _classify_output(output) is StepOutcomeStatus.SUCCESS


@pytest.mark.parametrize(
    "output",
    [
        None,
        "",
        "   ",
        {},
        {"result": "failed tests: 0"},  # no status key
        {"status": ""},
        # Prose is not a failure (B-8) and not verified success (Phase 1).
        "Failed to find X, skipping",
        "Blocked IPs table migrated",
        "Here is the architecture document you asked for.",
        "OK",
        "ok evidence",
    ],
)
def test_no_evidence_output_is_neither_failure_nor_success(output) -> None:
    assert is_verified_success(output) is False
    assert _classify_output(output) is StepOutcomeStatus.UNVERIFIED


@pytest.mark.parametrize(
    "output",
    [
        "blocked",
        "blocked: missing evidence",
        "failed",
        "failed: tests red",
        {"status": "failed"},
        {"status": "error"},
        {"error": "boom"},
    ],
)
def test_failure_sentinels_still_classify_as_failures(output) -> None:
    # Sentinel side frozen (8.3.1 B-8): failure vocabulary unchanged.
    assert is_verified_success(output) is False
    assert _classify_output(output) in (StepOutcomeStatus.BLOCKED, StepOutcomeStatus.FAILED)
