"""8.3.1 (B-8): is_acceptance_failure sentinel matching, not prose prefixes."""

from __future__ import annotations

import pytest

from vibesop.core.orchestration.verification_loop import is_acceptance_failure


@pytest.mark.parametrize(
    "output",
    [
        "blocked",
        "BLOCKED",
        "blocked: missing evidence",
        "failed",
        "failed: tests red",
        {"status": "blocked"},
        {"status": "failed"},
        {"status": "error"},
        {"error": "boom"},
    ],
)
def test_failure_shapes_detected(output) -> None:
    assert is_acceptance_failure(output) is True


@pytest.mark.parametrize(
    "output",
    [
        None,
        "",
        "passed",
        "OK",
        # 8.3.1 tightening: prose that merely starts with the words is success.
        "Failed to find X, skipping",
        "Blocked IPs table migrated",
        "blocked-ips migration done",
        {"status": "passed"},
        {"status": "completed"},
        {"result": "failed tests: 0"},
        "failed_tests: 0",
    ],
)
def test_success_shapes_not_failure(output) -> None:
    assert is_acceptance_failure(output) is False
