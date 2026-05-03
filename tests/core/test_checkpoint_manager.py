"""Tests for CheckpointManager.

Covers: create, restore, list, delete, clear_old, update.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from vibesop.core.checkpoint.base import CheckpointStatus
from vibesop.core.checkpoint.manager import CheckpointManager


class TestCheckpointManager:
    """Test CheckpointManager lifecycle operations."""

    def test_create_checkpoint_returns_data_with_id(self, tmp_path: Path) -> None:
        manager = CheckpointManager(storage_dir=str(tmp_path))
        cp = manager.create_checkpoint("Test", "A test checkpoint")

        assert cp.metadata.id
        assert len(cp.metadata.id) == 8
        assert cp.metadata.name == "Test"
        assert cp.metadata.description == "A test checkpoint"
        assert cp.metadata.status == CheckpointStatus.CREATED

    def test_restore_checkpoint_returns_checkpoint(self, tmp_path: Path) -> None:
        manager = CheckpointManager(storage_dir=str(tmp_path))
        created = manager.create_checkpoint("RestoreMe", "to be restored")

        restored = manager.restore_checkpoint(created.metadata.id)
        assert restored is not None
        assert restored.metadata.id == created.metadata.id
        assert restored.metadata.name == "RestoreMe"
        assert restored.metadata.status == CheckpointStatus.RESTORED

    def test_restore_checkpoint_not_found(self, tmp_path: Path) -> None:
        manager = CheckpointManager(storage_dir=str(tmp_path))
        assert manager.restore_checkpoint("nonexistent") is None

    def test_list_checkpoints_returns_list(self, tmp_path: Path) -> None:
        manager = CheckpointManager(storage_dir=str(tmp_path))
        manager.create_checkpoint("First", "desc1")
        manager.create_checkpoint("Second", "desc2")

        checkpoints = manager.list_checkpoints()
        assert isinstance(checkpoints, list)
        assert len(checkpoints) == 2
        names = {cp.name for cp in checkpoints}
        assert names == {"First", "Second"}

    def test_delete_checkpoint_removes_checkpoint(self, tmp_path: Path) -> None:
        manager = CheckpointManager(storage_dir=str(tmp_path))
        cp = manager.create_checkpoint("DeleteMe", "to be deleted")

        assert manager.delete_checkpoint(cp.metadata.id) is True
        assert manager.get_checkpoint(cp.metadata.id) is None
        assert manager.delete_checkpoint(cp.metadata.id) is False

    def test_clear_old_checkpoints_removes_aged_checkpoints(self, tmp_path: Path) -> None:
        manager = CheckpointManager(storage_dir=str(tmp_path), max_age_days=7)

        # Create a recent checkpoint
        recent = manager.create_checkpoint("Recent", "recent checkpoint")

        # Create an old checkpoint by backdating its metadata
        old = manager.create_checkpoint("Old", "old checkpoint")
        old.metadata.created_at = datetime.now() - timedelta(days=10)
        manager._storage.save(old)

        deleted = manager.clear_old_checkpoints(days=7)
        assert deleted == 1
        assert manager.get_checkpoint(old.metadata.id) is None
        assert manager.get_checkpoint(recent.metadata.id) is not None

    def test_update_checkpoint_updates_description(self, tmp_path: Path) -> None:
        manager = CheckpointManager(storage_dir=str(tmp_path))
        cp = manager.create_checkpoint("UpdateMe", "original desc")

        updated = manager.update_checkpoint(
            cp.metadata.id,
            description="updated desc",
        )
        assert updated is not None
        assert updated.metadata.description == "updated desc"
        assert updated.metadata.name == "UpdateMe"

        # Verify persistence
        loaded = manager.get_checkpoint(cp.metadata.id)
        assert loaded is not None
        assert loaded.metadata.description == "updated desc"

    def test_update_checkpoint_not_found(self, tmp_path: Path) -> None:
        manager = CheckpointManager(storage_dir=str(tmp_path))
        assert manager.update_checkpoint("nonexistent", description="x") is None
