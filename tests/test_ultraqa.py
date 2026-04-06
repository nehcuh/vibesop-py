"""Tests for ultraqa pipeline."""

from vibesop.core.pipeline.ultraqa import (
    Bug,
    BugSeverity,
    BugStatus,
    UltraQAState,
)


def test_initial_state():
    state = UltraQAState(session_id="test-1")
    assert state.current_cycle == 0
    assert state.is_complete is False
    assert state.should_continue is True


def test_start_cycle():
    state = UltraQAState(session_id="test-2")
    cycle = state.start_cycle()
    assert cycle.cycle_number == 1
    assert state.current_cycle == 1


def test_complete_cycle():
    state = UltraQAState(session_id="test-3")
    cycle = state.start_cycle()
    state.complete_cycle(cycle)
    assert cycle.completed_at is not None


def test_should_stop_after_max_cycles():
    state = UltraQAState(session_id="test-4", max_cycles=2)
    state.start_cycle()
    state.start_cycle()
    assert state.should_continue is False


def test_should_stop_after_no_bugs():
    state = UltraQAState(session_id="test-5")
    c1 = state.start_cycle()
    state.complete_cycle(c1)
    c2 = state.start_cycle()
    state.complete_cycle(c2)
    # No bugs found in 2 cycles
    assert state.should_continue is False


def test_should_continue_with_bugs():
    state = UltraQAState(session_id="test-6")
    c1 = state.start_cycle()
    c1.bugs_found.append(Bug(bug_id="b1", severity=BugSeverity.HIGH, description="Bug"))
    state.complete_cycle(c1)
    assert state.should_continue is True


def test_total_counts():
    state = UltraQAState(session_id="test-7")
    c1 = state.start_cycle()
    c1.bugs_found.append(Bug(bug_id="b1", severity=BugSeverity.HIGH, description="Bug 1"))
    c1.bugs_found.append(Bug(bug_id="b2", severity=BugSeverity.LOW, description="Bug 2"))
    c1.bugs_fixed = 1
    state.complete_cycle(c1)

    assert state.total_bugs_found == 2
    assert state.total_bugs_fixed == 1


def test_to_dict():
    state = UltraQAState(session_id="test-8")
    d = state.to_dict()
    assert d["session_id"] == "test-8"
    assert d["cycle"] == 0
    assert d["bugs_found"] == 0
    assert d["status"] == "running"


def test_save_state(tmp_path):
    state = UltraQAState(session_id="test-9")
    filepath = state.save(tmp_path)
    assert filepath.exists()
    assert "ultraqa_test-9" in filepath.name


def test_bug_to_dict():
    bug = Bug(
        bug_id="b1",
        severity=BugSeverity.CRITICAL,
        description="Crash on load",
        root_cause="Null pointer",
        fix_applied="Added null check",
        status=BugStatus.FIXED,
    )
    d = bug.to_dict()
    assert d["severity"] == "critical"
    assert d["status"] == "fixed"
    assert d["root_cause"] == "Null pointer"
