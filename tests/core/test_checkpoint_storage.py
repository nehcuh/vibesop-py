"""Tests for CheckpointStorage.

Covers: save, load, delete, list, exists, save_file, load_file, clear_all, get_size.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from vibesop.core.checkpoint.base import CheckpointData, CheckpointMetadata, CheckpointStatus
from vibesop.core.checkpoint.storage import CheckpointStorage


class TestCheckpointStorage:
    """Test CheckpointStorage lifecycle operations."""

    def test_init_creates_directories(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        assert storage.storage_dir == tmp_path
        assert storage.meta_dir.exists()
        assert storage.data_dir.exists()
        assert storage.files_dir.exists()

    def test_get_meta_path(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        path = storage.get_meta_path("abc123")
        assert path == tmp_path / "meta" / "abc123.json"

    def test_get_data_path(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        path = storage.get_data_path("abc123")
        assert path == tmp_path / "data" / "abc123.json"

    def test_get_file_path(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        path = storage.get_file_path("abc123", "src/main.py")
        assert path == tmp_path / "files" / "abc123_src_main.py"

    def test_get_file_path_windows_backslash(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        path = storage.get_file_path("abc123", "src\\main.py")
        assert path == tmp_path / "files" / "abc123_src_main.py"

    def _make_checkpoint(self, checkpoint_id: str = "ckpt-01") -> CheckpointData:
        metadata = CheckpointMetadata(
            id=checkpoint_id,
            name="Test Checkpoint",
            description="A test checkpoint",
            created_at=datetime(2026, 1, 1, 12, 0, 0),
            status=CheckpointStatus.CREATED,
            tags=["test"],
            size=0,
        )
        return CheckpointData(
            metadata=metadata,
            conversation_id="conv-123",
            files={"a.py": "hash1"},
            context={"key": "value"},
            custom_data={"extra": 42},
        )

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        checkpoint = self._make_checkpoint("ckpt-01")

        storage.save(checkpoint)
        loaded = storage.load("ckpt-01")

        assert loaded is not None
        assert loaded.metadata.id == "ckpt-01"
        assert loaded.metadata.name == "Test Checkpoint"
        assert loaded.metadata.description == "A test checkpoint"
        assert loaded.metadata.status == CheckpointStatus.CREATED
        assert loaded.metadata.tags == ["test"]
        assert loaded.conversation_id == "conv-123"
        assert loaded.files == {"a.py": "hash1"}
        assert loaded.context == {"key": "value"}
        assert loaded.custom_data == {"extra": 42}

    def test_load_missing_checkpoint_returns_none(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        assert storage.load("missing") is None

    def test_load_corrupted_metadata_returns_none(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        meta_path = storage.get_meta_path("bad")
        meta_path.write_text("not json")
        assert storage.load("bad") is None

    def test_load_missing_data_file_returns_metadata_only(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        checkpoint = self._make_checkpoint("ckpt-02")
        storage.save(checkpoint)
        # Delete data file but keep metadata
        storage.get_data_path("ckpt-02").unlink()

        loaded = storage.load("ckpt-02")
        assert loaded is not None
        assert loaded.metadata.id == "ckpt-02"
        assert loaded.conversation_id is None
        assert loaded.files == {}
        assert loaded.context == {}
        assert loaded.custom_data == {}

    def test_load_corrupted_data_file_returns_metadata_only(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        checkpoint = self._make_checkpoint("ckpt-03")
        storage.save(checkpoint)
        storage.get_data_path("ckpt-03").write_text("not json")

        loaded = storage.load("ckpt-03")
        assert loaded is not None
        assert loaded.metadata.id == "ckpt-03"
        assert loaded.conversation_id is None
        assert loaded.files == {}
        assert loaded.context == {}
        assert loaded.custom_data == {}

    def test_delete_existing_checkpoint(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        checkpoint = self._make_checkpoint("ckpt-04")
        storage.save(checkpoint)

        assert storage.delete("ckpt-04") is True
        assert storage.load("ckpt-04") is None

    def test_delete_nonexistent_checkpoint(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        assert storage.delete("missing") is False

    def test_delete_removes_associated_files(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        checkpoint = self._make_checkpoint("ckpt-05")
        storage.save(checkpoint)
        storage.save_file("ckpt-05", "src/main.py", "print('hello')")

        file_path = storage.get_file_path("ckpt-05", "src/main.py")
        assert file_path.exists()

        storage.delete("ckpt-05")
        assert not file_path.exists()

    def test_exists(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        checkpoint = self._make_checkpoint("ckpt-06")
        storage.save(checkpoint)

        assert storage.exists("ckpt-06") is True
        assert storage.exists("missing") is False

    def test_list_all_sorts_by_created_at_descending(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        cp1 = CheckpointData(
            metadata=CheckpointMetadata(
                id="older",
                name="Older",
                description="older",
                created_at=datetime(2026, 1, 1, 10, 0, 0),
            )
        )
        cp2 = CheckpointData(
            metadata=CheckpointMetadata(
                id="newer",
                name="Newer",
                description="newer",
                created_at=datetime(2026, 1, 1, 14, 0, 0),
            )
        )
        storage.save(cp1)
        storage.save(cp2)

        results = storage.list_all()
        assert len(results) == 2
        assert results[0].id == "newer"
        assert results[1].id == "older"

    def test_list_all_skips_corrupted_files(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        bad_meta = storage.get_meta_path("bad")
        bad_meta.write_text("not json")
        assert storage.list_all() == []

    def test_save_file_and_load_file(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        content = "print('hello world')"
        content_hash = storage.save_file("ckpt-07", "src/app.py", content)

        assert isinstance(content_hash, str)
        assert len(content_hash) == 64  # SHA-256 hex

        loaded = storage.load_file("ckpt-07", "src/app.py")
        assert loaded == content

    def test_load_file_missing_returns_none(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        assert storage.load_file("missing", "src/app.py") is None

    def test_clear_all(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        storage.save(self._make_checkpoint("ckpt-a"))
        storage.save(self._make_checkpoint("ckpt-b"))

        deleted = storage.clear_all()
        assert deleted == 2
        assert storage.load("ckpt-a") is None
        assert storage.load("ckpt-b") is None
        assert storage.list_all() == []

    def test_get_size(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        checkpoint = self._make_checkpoint("ckpt-size")
        storage.save(checkpoint)
        storage.save_file("ckpt-size", "file.txt", "hello")

        size = storage.get_size("ckpt-size")
        assert size > 0
        # Meta + data + file should all contribute
        assert size == (
            storage.get_meta_path("ckpt-size").stat().st_size
            + storage.get_data_path("ckpt-size").stat().st_size
            + storage.get_file_path("ckpt-size", "file.txt").stat().st_size
        )

    def test_get_size_missing_checkpoint(self, tmp_path: Path) -> None:
        storage = CheckpointStorage(storage_dir=str(tmp_path))
        assert storage.get_size("missing") == 0
