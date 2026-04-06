"""Tests for unified state management."""

import pytest

from vibesop.core.state.manager import StateManager


@pytest.fixture
def state_manager(tmp_path):
    return StateManager(state_root=tmp_path / "state")


def test_write_and_read_state(state_manager):
    state_manager.write(
        "ralph",
        "test-scope",
        {
            "iteration": 1,
            "current_phase": "executing",
        },
    )

    state = state_manager.read("ralph", "test-scope")
    assert state is not None
    assert state["mode"] == "ralph"
    assert state["scope"] == "test-scope"
    assert state["active"] is True
    assert state["iteration"] == 1
    assert state["current_phase"] == "executing"
    assert "created_at" in state
    assert "updated_at" in state


def test_read_nonexistent_state(state_manager):
    state = state_manager.read("ralph", "nonexistent")
    assert state is None


def test_clear_state(state_manager):
    state_manager.write("ralph", "test-scope", {"iteration": 1})
    result = state_manager.clear("ralph", "test-scope")
    assert result is True

    state = state_manager.read("ralph", "test-scope")
    assert state["active"] is False


def test_clear_nonexistent_state(state_manager):
    result = state_manager.clear("ralph", "nonexistent")
    assert result is False


def test_list_active_states(state_manager):
    state_manager.write("ralph", "scope1", {"iteration": 1})
    state_manager.write("team", "scope2", {"worker_count": 3})
    state_manager.clear("ralph", "scope1")

    active = state_manager.list_active_states()
    assert len(active) == 1
    assert active[0]["mode"] == "team"
    assert active[0]["scope"] == "scope2"


def test_list_active_states_empty(state_manager):
    active = state_manager.list_active_states()
    assert active == []


def test_state_file_created(state_manager, tmp_path):
    path = state_manager.write("ralph", "test", {"data": "value"})
    assert path.exists()
    assert path.name == "state.json"
    assert "ralph" in str(path)
    assert "test" in str(path)


def test_atomic_write_on_error(state_manager):
    """Write should use atomic rename to prevent corruption."""
    state_manager.write("ralph", "test", {"data": "value"})
    state_file = state_manager.get_state_path("ralph", "test")
    assert state_file.exists()
    assert not state_file.with_suffix(".tmp").exists()


def test_merge_with_existing_state(state_manager):
    """Write should merge with existing state, not overwrite."""
    state_manager.write("ralph", "test", {"iteration": 1, "phase": "start"})
    state_manager.write("ralph", "test", {"iteration": 2})

    state = state_manager.read("ralph", "test")
    assert state["iteration"] == 2
    assert state["phase"] == "start"  # Preserved from previous write


def test_corrupted_state_returns_none(state_manager):
    """Read should return None for corrupted JSON."""
    state_dir = state_manager.state_root / "ralph" / "corrupt"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("not valid json")

    state = state_manager.read("ralph", "corrupt")
    assert state is None
