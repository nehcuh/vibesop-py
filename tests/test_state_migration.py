"""Tests for state migration from legacy .vibe/ structure."""

import json

import pytest

from vibesop.core.state.migration import migrate_legacy_state


@pytest.fixture
def vibe_root(tmp_path):
    """Create a .vibe/ directory with legacy data."""
    vibe = tmp_path / ".vibe"
    vibe.mkdir()

    memory_dir = vibe / "memory"
    memory_dir.mkdir()
    (memory_dir / "session-1.json").write_text(
        json.dumps(
            {
                "last_query": "debug this",
                "last_skill": "systematic-debugging",
            }
        )
    )
    (memory_dir / "session-2.json").write_text(
        json.dumps(
            {
                "last_query": "ship it",
                "last_skill": "gstack/ship",
            }
        )
    )

    return vibe


def test_migrate_creates_new_directories(vibe_root):
    migrate_legacy_state(vibe_root)
    assert (vibe_root / "interviews").exists()
    assert (vibe_root / "plans").exists()
    assert (vibe_root / "specs").exists()
    assert (vibe_root / "context").exists()
    assert (vibe_root / "state").exists()


def test_migrate_migrates_memory_files(vibe_root):
    report = migrate_legacy_state(vibe_root)
    assert report["migrated"] == 2
    assert report["errors"] == 0

    state_file_1 = vibe_root / "state" / "sessions" / "session-1" / "state.json"
    state_file_2 = vibe_root / "state" / "sessions" / "session-2" / "state.json"
    assert state_file_1.exists()
    assert state_file_2.exists()

    data = json.loads(state_file_1.read_text())
    assert data["last_query"] == "debug this"
    assert data["source"] == "migrated_from_memory"


def test_migrate_dry_run(vibe_root):
    report = migrate_legacy_state(vibe_root, dry_run=True)
    assert report["migrated"] == 2
    assert not (vibe_root / "interviews").exists()


def test_migrate_no_vibe_directory(tmp_path):
    report = migrate_legacy_state(tmp_path / "nonexistent")
    assert "No .vibe/" in report["details"][0]
    assert report["migrated"] == 0


def test_migrate_empty_memory_dir(vibe_root):
    """Migration should handle empty memory directory."""
    vibe = vibe_root
    memory_dir = vibe / "memory"
    for f in memory_dir.glob("*.json"):
        f.unlink()

    report = migrate_legacy_state(vibe)
    assert report["migrated"] == 0
    assert report["errors"] == 0


def test_migrate_corrupted_memory_file(vibe_root):
    """Migration should handle corrupted JSON in memory files."""
    (vibe_root / "memory" / "corrupt.json").write_text("not valid json")

    report = migrate_legacy_state(vibe_root)
    assert report["migrated"] == 2
    assert report["errors"] == 1
    assert any("Error migrating" in d for d in report["details"])
