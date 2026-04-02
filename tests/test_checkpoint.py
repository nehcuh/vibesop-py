"""Test checkpoint system."""

import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from vibesop.core.checkpoint import (
    CheckpointData,
    CheckpointManager,
    CheckpointMetadata,
    CheckpointStatus,
    CheckpointStorage,
)


class TestCheckpointMetadata:
    """Test CheckpointMetadata class."""

    def test_create_metadata(self) -> None:
        """Test creating checkpoint metadata."""
        metadata = CheckpointMetadata(
            id="test-123",
            name="Test Checkpoint",
            description="A test checkpoint",
            created_at=datetime.now(),
        )

        assert metadata.id == "test-123"
        assert metadata.name == "Test Checkpoint"
        assert metadata.status == CheckpointStatus.CREATED
        assert metadata.tags == []

    def test_metadata_to_dict(self) -> None:
        """Test converting metadata to dictionary."""
        metadata = CheckpointMetadata(
            id="test",
            name="Test",
            description="Test checkpoint",
            created_at=datetime.now(),
            tags=["test", "demo"],
        )

        data = metadata.to_dict()

        assert data["id"] == "test"
        assert data["name"] == "Test"
        assert data["tags"] == ["test", "demo"]


class TestCheckpointData:
    """Test CheckpointData class."""

    def test_create_data(self) -> None:
        """Test creating checkpoint data."""
        metadata = CheckpointMetadata(
            id="test",
            name="Test",
            description="Test",
            created_at=datetime.now(),
        )

        data = CheckpointData(
            metadata=metadata,
            conversation_id="conv-123",
        )

        assert data.metadata.id == "test"
        assert data.conversation_id == "conv-123"
        assert data.files == {}
        assert data.context == {}

    def test_data_to_dict(self) -> None:
        """Test converting data to dictionary."""
        metadata = CheckpointMetadata(
            id="test",
            name="Test",
            description="Test",
            created_at=datetime.now(),
        )

        data = CheckpointData(
            metadata=metadata,
            custom_data={"key": "value"},
        )

        dict_data = data.to_dict()

        assert dict_data["metadata"]["id"] == "test"
        assert dict_data["custom_data"]["key"] == "value"


class TestCheckpointStorage:
    """Test CheckpointStorage class."""

    def _create_storage(self) -> tuple[CheckpointStorage, Path]:
        """Helper to create storage with temp directory."""
        tmpdir = Path(tempfile.mkdtemp())
        storage = CheckpointStorage(storage_dir=tmpdir / "checkpoints")
        return storage, tmpdir

    def test_save_and_load(self) -> None:
        """Test saving and loading a checkpoint."""
        storage, tmpdir = self._create_storage()

        metadata = CheckpointMetadata(
            id="test-123",
            name="Test",
            description="Test checkpoint",
            created_at=datetime.now(),
        )

        data = CheckpointData(
            metadata=metadata,
            conversation_id="conv-123",
        )

        storage.save(data)
        loaded = storage.load("test-123")

        assert loaded is not None
        assert loaded.metadata.id == "test-123"
        assert loaded.conversation_id == "conv-123"

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_save_and_load_file(self) -> None:
        """Test saving and loading file snapshots."""
        storage, tmpdir = self._create_storage()

        # Save a file
        content = "Hello, world!"
        content_hash = storage.save_file("test-123", "test.txt", content)

        assert content_hash is not None

        # Load the file
        loaded_content = storage.load_file("test-123", "test.txt")

        assert loaded_content == content

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_load_nonexistent(self) -> None:
        """Test loading nonexistent checkpoint."""
        storage, tmpdir = self._create_storage()

        result = storage.load("nonexistent")

        assert result is None

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_delete(self) -> None:
        """Test deleting a checkpoint."""
        storage, tmpdir = self._create_storage()

        metadata = CheckpointMetadata(
            id="test",
            name="Test",
            description="Test",
            created_at=datetime.now(),
        )

        data = CheckpointData(metadata=metadata)
        storage.save(data)

        assert storage.exists("test")

        deleted = storage.delete("test")

        assert deleted is True
        assert not storage.exists("test")

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_list_all(self) -> None:
        """Test listing all checkpoints."""
        storage, tmpdir = self._create_storage()

        # Create multiple checkpoints
        for i in range(3):
            metadata = CheckpointMetadata(
                id=f"test-{i}",
                name=f"Checkpoint {i}",
                description=f"Test {i}",
                created_at=datetime.now(),
            )
            data = CheckpointData(metadata=metadata)
            storage.save(data)

        all_cps = storage.list_all()

        assert len(all_cps) == 3

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_exists(self) -> None:
        """Test checking if checkpoint exists."""
        storage, tmpdir = self._create_storage()

        assert not storage.exists("test")

        metadata = CheckpointMetadata(
            id="test",
            name="Test",
            description="Test",
            created_at=datetime.now(),
        )
        data = CheckpointData(metadata=metadata)
        storage.save(data)

        assert storage.exists("test")

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_get_size(self) -> None:
        """Test getting checkpoint size."""
        storage, tmpdir = self._create_storage()

        metadata = CheckpointMetadata(
            id="test",
            name="Test",
            description="Test",
            created_at=datetime.now(),
        )
        data = CheckpointData(metadata=metadata)
        storage.save(data)

        # Save a file
        storage.save_file("test", "test.txt", "content")

        size = storage.get_size("test")

        assert size > 0

        # Cleanup
        shutil.rmtree(tmpdir)


class TestCheckpointManager:
    """Test CheckpointManager class."""

    def _create_manager(self) -> tuple[CheckpointManager, Path]:
        """Helper to create manager with temp directory."""
        tmpdir = Path(tempfile.mkdtemp())
        manager = CheckpointManager(storage_dir=tmpdir / "checkpoints")
        return manager, tmpdir

    def test_create_checkpoint(self) -> None:
        """Test creating a checkpoint."""
        manager, tmpdir = self._create_manager()

        cp = manager.create_checkpoint(
            name="Work Session",
            description="Progress so far",
        )

        assert cp.metadata.id is not None
        assert cp.metadata.name == "Work Session"
        assert cp.metadata.status == CheckpointStatus.CREATED

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_restore_checkpoint(self) -> None:
        """Test restoring a checkpoint."""
        manager, tmpdir = self._create_manager()

        # Create checkpoint
        created = manager.create_checkpoint(
            name="Test",
            description="Test checkpoint",
        )

        # Restore it
        restored = manager.restore_checkpoint(created.metadata.id)

        assert restored is not None
        assert restored.metadata.name == "Test"
        assert restored.metadata.status == CheckpointStatus.RESTORED

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_restore_with_files(self) -> None:
        """Test restoring checkpoint with files."""
        manager, tmpdir = self._create_manager()

        # Create a test file
        work_dir = tmpdir / "work"
        work_dir.mkdir()
        test_file = work_dir / "test.txt"
        test_file.write_text("Hello, world!")

        # Create checkpoint with file snapshot
        cp = manager.create_checkpoint(
            name="Test",
            files=["test.txt"],
            context={"working_dir": str(work_dir)},
        )

        # Delete the original file
        test_file.unlink()

        # Restore checkpoint
        restored = manager.restore_checkpoint(
            cp.metadata.id,
            restore_files=True,
            working_dir=work_dir,
        )

        assert restored is not None

        # Check file was restored
        restored_file = work_dir / "test.txt"
        assert restored_file.exists()
        assert restored_file.read_text() == "Hello, world!"

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_delete_checkpoint(self) -> None:
        """Test deleting a checkpoint."""
        manager, tmpdir = self._create_manager()

        cp = manager.create_checkpoint(name="Test")

        deleted = manager.delete_checkpoint(cp.metadata.id)

        assert deleted is True
        assert manager.get_checkpoint(cp.metadata.id) is None

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_get_checkpoint(self) -> None:
        """Test getting a checkpoint."""
        manager, tmpdir = self._create_manager()

        created = manager.create_checkpoint(name="Test")
        loaded = manager.get_checkpoint(created.metadata.id)

        assert loaded is not None
        assert loaded.metadata.name == "Test"

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_list_checkpoints(self) -> None:
        """Test listing checkpoints."""
        manager, tmpdir = self._create_manager()

        manager.create_checkpoint("First")
        manager.create_checkpoint("Second")

        checkpoints = manager.list_checkpoints()

        assert len(checkpoints) == 2

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_list_checkpoints_with_tag(self) -> None:
        """Test listing checkpoints filtered by tag."""
        manager, tmpdir = self._create_manager()

        manager.create_checkpoint("First", tags=["important"])
        manager.create_checkpoint("Second", tags=["test"])

        important_cps = manager.list_checkpoints(tag="important")

        assert len(important_cps) == 1
        assert important_cps[0].name == "First"

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_search_checkpoints(self) -> None:
        """Test searching checkpoints."""
        manager, tmpdir = self._create_manager()

        manager.create_checkpoint("Python Development", "Work on Python code")
        manager.create_checkpoint("JavaScript Help", "Work on JavaScript")

        results = manager.search_checkpoints("Python")

        assert len(results) >= 1
        assert any("Python" in cp.name for cp in results)

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_clear_old_checkpoints(self) -> None:
        """Test clearing old checkpoints."""
        manager, tmpdir = self._create_manager()

        # Create a new checkpoint first (enforces limits on init)
        manager.create_checkpoint("New")

        # Now manually add an old checkpoint
        old_metadata = CheckpointMetadata(
            id="old",
            name="Old",
            description="Old checkpoint",
            created_at=datetime.now() - timedelta(days=100),
        )
        old_cp = CheckpointData(metadata=old_metadata)
        manager._storage.save(old_cp)

        # Clear old
        deleted = manager.clear_old_checkpoints(days=30)

        assert deleted >= 1

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_get_stats(self) -> None:
        """Test getting statistics."""
        manager, tmpdir = self._create_manager()

        manager.create_checkpoint("Test")

        stats = manager.get_stats()

        assert stats["total_checkpoints"] == 1
        assert "storage_dir" in stats

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_update_checkpoint(self) -> None:
        """Test updating checkpoint metadata."""
        manager, tmpdir = self._create_manager()

        cp = manager.create_checkpoint("Original Name", "Original desc")

        updated = manager.update_checkpoint(
            cp.metadata.id,
            name="Updated Name",
            description="Updated desc",
        )

        assert updated is not None
        assert updated.metadata.name == "Updated Name"
        assert updated.metadata.description == "Updated desc"

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_add_file_to_checkpoint(self) -> None:
        """Test adding a file to existing checkpoint."""
        manager, tmpdir = self._create_manager()

        work_dir = tmpdir / "work"
        work_dir.mkdir()
        test_file = work_dir / "test.txt"
        test_file.write_text("Content")

        # Create checkpoint without files
        cp = manager.create_checkpoint("Test")

        # Add file
        added = manager.add_file_to_checkpoint(
            cp.metadata.id,
            "test.txt",
            working_dir=work_dir,
        )

        assert added is True

        # Verify file is in checkpoint
        loaded = manager.get_checkpoint(cp.metadata.id)
        assert "test.txt" in loaded.files

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_max_checkpoints_limit(self) -> None:
        """Test max checkpoints limit enforcement."""
        tmpdir = Path(tempfile.mkdtemp())
        manager = CheckpointManager(
            storage_dir=tmpdir / "checkpoints",
            max_checkpoints=3,
        )

        # Create 5 checkpoints (max is 3)
        for i in range(5):
            manager.create_checkpoint(f"Checkpoint {i}")

        # Should only have 3 (newest ones)
        stats = manager.get_stats()
        assert stats["total_checkpoints"] == 3

        # Cleanup
        shutil.rmtree(tmpdir)
