"""Tests for ``vibesop.core.loop.models``.

Covers:
    - Field-level validation: kebab-case name, non-empty description,
      min_length=1 max_failures, cron syntax.
    - Cross-field validation: exactly one of skill_id / query / workflow_id.
    - State machine: ACTIVE → FAILING → DEAD transition, success reset,
      paused-stickiness, recent_runs cap at 20.
    - JSON round-trip via pydantic BaseModel (no hand-written serializer).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from vibesop.core.loop.models import (
    LoopRunRecord,
    LoopSpec,
    LoopState,
    LoopStatus,
    LoopTrigger,
)

# ──────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────


def _valid_spec_kwargs(**overrides):
    """Return a minimal valid spec kwargs dict, with optional overrides."""
    base = {
        "name": "ci-watcher",
        "description": "Watch CI failures and triage",
        "schedule": "*/30 * * * *",
        "skill_id": "systematic-debugging",
    }
    base.update(overrides)
    return base


def _make_run(loop_name: str = "ci-watcher", success: bool = True) -> LoopRunRecord:
    started = datetime.now(UTC)
    return LoopRunRecord(
        loop_name=loop_name,
        started_at=started,
        finished_at=started,
        success=success,
        output_summary="ok" if success else "",
        error="" if success else "boom",
        duration_s=0.1,
    )


# ──────────────────────────────────────────────────────────────────
# LoopSpec — happy paths
# ──────────────────────────────────────────────────────────────────


def test_spec_accepts_valid_minimal_definition():
    spec = LoopSpec(**_valid_spec_kwargs())
    assert spec.name == "ci-watcher"
    assert spec.trigger == LoopTrigger.CRON
    assert spec.max_failures == 3
    assert spec.created_at.tzinfo is not None  # tz-aware UTC


def test_spec_accepts_query_target_when_skill_id_absent():
    spec = LoopSpec(**_valid_spec_kwargs(skill_id="", query="check ci status"))
    assert spec.query == "check ci status"
    assert spec.skill_id == ""


def test_spec_accepts_workflow_id_target():
    spec = LoopSpec(
        **_valid_spec_kwargs(skill_id="", workflow_id="daily-digest"),
    )
    assert spec.workflow_id == "daily-digest"


# ──────────────────────────────────────────────────────────────────
# LoopSpec — name validation
# ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad_name",
    [
        "",  # empty
        "CI-Watcher",  # uppercase
        "ci_watcher",  # underscore
        "-leading",  # leading dash
        "trailing-",  # trailing dash
        "has space",  # whitespace
        "123",  # digits-only is allowed by pattern actually,
        # but the next case asserts a clearer rejection
    ],
)
def test_spec_rejects_invalid_name(bad_name):
    # Special-case: pure "123" matches the pattern, so exclude it here.
    if bad_name == "123":
        pytest.skip("digits-only name is valid under current pattern")
    with pytest.raises(ValidationError):
        LoopSpec(**_valid_spec_kwargs(name=bad_name))


def test_spec_rejects_empty_description():
    with pytest.raises(ValidationError):
        LoopSpec(**_valid_spec_kwargs(description=""))


def test_spec_rejects_max_failures_below_one():
    with pytest.raises(ValidationError):
        LoopSpec(**_valid_spec_kwargs(max_failures=0))


# ──────────────────────────────────────────────────────────────────
# LoopSpec — cron validation
# ──────────────────────────────────────────────────────────────────


def test_spec_rejects_cron_with_wrong_field_count():
    with pytest.raises(ValidationError):
        LoopSpec(**_valid_spec_kwargs(schedule="*/5 * * *"))  # 4 fields
    with pytest.raises(ValidationError):
        LoopSpec(**_valid_spec_kwargs(schedule="* * * * * *"))  # 6 fields


def test_spec_rejects_cron_with_out_of_range_value():
    with pytest.raises(ValidationError):
        LoopSpec(**_valid_spec_kwargs(schedule="60 * * * *"))  # minute > 59
    with pytest.raises(ValidationError):
        LoopSpec(**_valid_spec_kwargs(schedule="* 25 * * *"))  # hour > 23


def test_spec_accepts_typical_cron_expressions():
    for schedule in (
        "*/15 * * * *",  # every 15 min
        "0 9 * * 1-5",  # weekday 9am
        "30 22 * * *",  # daily 22:30
        "0 0 1 * *",  # monthly on the 1st
        "0 0 1 1 *",  # yearly on Jan 1
        "*/30 9-17 * * 1-5",  # every 30 min during business hours
    ):
        spec = LoopSpec(**_valid_spec_kwargs(schedule=schedule))
        assert spec.schedule == schedule


# ──────────────────────────────────────────────────────────────────
# LoopSpec — cross-field target validation
# ──────────────────────────────────────────────────────────────────


def test_spec_rejects_when_no_target_set():
    with pytest.raises(ValidationError):
        LoopSpec(**_valid_spec_kwargs(skill_id="", query="", workflow_id=""))


def test_spec_rejects_when_multiple_targets_set():
    with pytest.raises(ValidationError):
        LoopSpec(
            **_valid_spec_kwargs(
                skill_id="systematic-debugging",
                query="check ci",
            )
        )


# ──────────────────────────────────────────────────────────────────
# LoopSpec — JSON round-trip (BaseModel native)
# ──────────────────────────────────────────────────────────────────


def test_spec_round_trips_through_json():
    original = LoopSpec(**_valid_spec_kwargs())
    json_text = original.model_dump_json()
    restored = LoopSpec.model_validate_json(json_text)
    assert restored == original


# ──────────────────────────────────────────────────────────────────
# LoopState — record_run state machine
# ──────────────────────────────────────────────────────────────────


def test_state_starts_active():
    state = LoopState(spec=LoopSpec(**_valid_spec_kwargs()))
    assert state.status == LoopStatus.ACTIVE
    assert state.consecutive_failures == 0
    assert state.total_runs == 0
    assert state.recent_runs == []


def test_state_success_resets_failures_and_stays_active():
    state = LoopState(spec=LoopSpec(**_valid_spec_kwargs(max_failures=3)))
    # Prime with one failure to confirm reset actually clears the counter.
    state.record_run(_make_run(success=False))
    assert state.consecutive_failures == 1
    assert state.status == LoopStatus.FAILING

    state.record_run(_make_run(success=True))
    assert state.consecutive_failures == 0
    assert state.status == LoopStatus.ACTIVE
    assert state.total_runs == 2
    assert state.last_success_at is not None


def test_state_transitions_to_dead_at_max_failures():
    state = LoopState(spec=LoopSpec(**_valid_spec_kwargs(max_failures=3)))
    state.record_run(_make_run(success=False))
    assert state.status == LoopStatus.FAILING
    state.record_run(_make_run(success=False))
    assert state.status == LoopStatus.FAILING
    state.record_run(_make_run(success=False))
    assert state.status == LoopStatus.DEAD
    assert state.consecutive_failures == 3


def test_state_max_failures_one_flips_to_dead_immediately():
    state = LoopState(spec=LoopSpec(**_valid_spec_kwargs(max_failures=1)))
    state.record_run(_make_run(success=False))
    assert state.status == LoopStatus.DEAD


def test_state_paused_is_sticky_through_success():
    """A PAUSED loop stays paused even when a success is recorded.

    The executor should not tick paused loops, but defensively we guard
    so that a stray success doesn't silently reactivate one.
    """
    state = LoopState(spec=LoopSpec(**_valid_spec_kwargs()))
    state.status = LoopStatus.PAUSED
    state.record_run(_make_run(success=True))
    assert state.status == LoopStatus.PAUSED
    # total_runs still increments because record_run was called.
    assert state.total_runs == 1


def test_state_paused_is_sticky_through_failure():
    state = LoopState(spec=LoopSpec(**_valid_spec_kwargs(max_failures=2)))
    state.status = LoopStatus.PAUSED
    state.record_run(_make_run(success=False))
    assert state.status == LoopStatus.PAUSED
    assert state.consecutive_failures == 0


def test_state_caps_recent_runs_at_twenty():
    state = LoopState(spec=LoopSpec(**_valid_spec_kwargs()))
    for _ in range(25):
        state.record_run(_make_run())
    assert len(state.recent_runs) == 20
    assert state.total_runs == 25  # total_runs is uncapped


def test_state_round_trips_through_json():
    spec = LoopSpec(**_valid_spec_kwargs())
    state = LoopState(spec=spec)
    state.record_run(_make_run(success=True))
    state.record_run(_make_run(success=False))

    json_text = state.model_dump_json()
    restored = LoopState.model_validate_json(json_text)

    assert restored.spec == spec
    assert restored.total_runs == 2
    assert restored.consecutive_failures == 1
    assert len(restored.recent_runs) == 2
    assert restored.last_run_at is not None
