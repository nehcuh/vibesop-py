"""Tests for autopilot pipeline."""

import tempfile
from pathlib import Path

from vibesop.core.pipeline.autopilot import (
    AutopilotPhase,
    AutopilotPipeline,
    AutopilotState,
)


def test_initial_state() -> None:
    state = AutopilotState(session_id="test-1")
    assert state.current_phase == AutopilotPhase.CLARIFY
    assert state.is_complete is False
    assert len(state.phases) == 6
    assert state.phases["clarify"].status == "pending"


def test_mark_phase_running() -> None:
    state = AutopilotState(session_id="test-2")
    state.mark_phase_running(AutopilotPhase.PLAN)
    assert state.current_phase == AutopilotPhase.PLAN
    assert state.phases["plan"].status == "running"


def test_mark_phase_completed() -> None:
    state = AutopilotState(session_id="test-3")
    state.mark_phase_running(AutopilotPhase.CLARIFY)
    state.mark_phase_completed(AutopilotPhase.CLARIFY, {"clarity": 0.8})
    assert state.phases["clarify"].status == "completed"
    assert state.phases["clarify"].detail["clarity"] == 0.8
    assert state.current_phase == AutopilotPhase.PLAN


def test_mark_phase_failed() -> None:
    state = AutopilotState(session_id="test-4")
    state.mark_phase_failed(AutopilotPhase.EXECUTE, "Build failed")
    assert state.phases["execute"].status == "failed"
    assert state.error == "Build failed"
    assert state.is_complete is True
    assert state.is_successful is False


def test_complete_session() -> None:
    state = AutopilotState(session_id="test-5")
    state.complete_session()
    assert state.is_complete is True


def test_to_dict() -> None:
    state = AutopilotState(session_id="test-6")
    d = state.to_dict()
    assert d["session_id"] == "test-6"
    assert d["current_phase"] == "clarify"
    assert len(d["phases"]) == 6


def test_save_state(tmp_path: Path) -> None:
    state = AutopilotState(session_id="test-7")
    filepath = state.save(tmp_path)
    assert filepath.exists()
    assert "autopilot_test-7" in filepath.name


def test_pipeline_start() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pipeline = AutopilotPipeline("test-8", state_dir=tmp)
        state = pipeline.start()
        assert state.current_phase == AutopilotPhase.CLARIFY
        assert state.phases["clarify"].status == "running"
