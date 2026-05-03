"""Tests for checkpoint base classes."""

from datetime import datetime

import pytest

from vibesop.core.checkpoint.base import CheckpointData, CheckpointMetadata, CheckpointStatus


class TestCheckpointStatus:
    """Test CheckpointStatus enum."""

    def test_values(self):
        assert CheckpointStatus.CREATED.value == "created"
        assert CheckpointStatus.RESTORED.value == "restored"
        assert CheckpointStatus.EXPIRED.value == "expired"
        assert CheckpointStatus.CORRUPTED.value == "corrupted"


class TestCheckpointMetadata:
    """Test CheckpointMetadata dataclass."""

    def test_creation(self):
        meta = CheckpointMetadata(
            id="ckpt-01",
            name="Test",
            description="A test",
            created_at=datetime(2026, 1, 1, 12, 0, 0),
        )
        assert meta.id == "ckpt-01"
        assert meta.name == "Test"
        assert meta.status == CheckpointStatus.CREATED
        assert meta.tags == []
        assert meta.size == 0

    def test_creation_with_tags(self):
        meta = CheckpointMetadata(
            id="ckpt-02",
            name="Test",
            description="Test",
            created_at=datetime.now(),
            tags=["a", "b"],
            size=1024,
        )
        assert meta.tags == ["a", "b"]
        assert meta.size == 1024

    def test_to_dict(self):
        dt = datetime(2026, 1, 1, 12, 0, 0)
        meta = CheckpointMetadata(id="ckpt", name="N", description="D", created_at=dt, tags=["t"], size=100)
        d = meta.to_dict()
        assert d["id"] == "ckpt"
        assert d["name"] == "N"
        assert d["description"] == "D"
        assert d["created_at"] == "2026-01-01T12:00:00"
        assert d["status"] == "created"
        assert d["tags"] == ["t"]
        assert d["size"] == 100

    def test_from_dict(self):
        d = {
            "id": "ckpt",
            "name": "N",
            "description": "D",
            "created_at": "2026-01-01T12:00:00",
            "status": "restored",
            "tags": ["t"],
            "size": 200,
        }
        meta = CheckpointMetadata.from_dict(d)
        assert meta.id == "ckpt"
        assert meta.status == CheckpointStatus.RESTORED
        assert meta.tags == ["t"]
        assert meta.size == 200

    def test_from_dict_defaults(self):
        d = {"id": "ckpt", "name": "N", "description": "D", "created_at": "2026-01-01T12:00:00"}
        meta = CheckpointMetadata.from_dict(d)
        assert meta.status == CheckpointStatus.CREATED
        assert meta.tags == []
        assert meta.size == 0


class TestCheckpointData:
    """Test CheckpointData dataclass."""

    def _make_meta(self, ckpt_id: str = "ckpt") -> CheckpointMetadata:
        return CheckpointMetadata(
            id=ckpt_id,
            name="Test",
            description="Test",
            created_at=datetime(2026, 1, 1, 12, 0, 0),
        )

    def test_creation_defaults(self):
        data = CheckpointData(metadata=self._make_meta())
        assert data.conversation_id is None
        assert data.files == {}
        assert data.context == {}
        assert data.custom_data == {}

    def test_creation_with_data(self):
        data = CheckpointData(
            metadata=self._make_meta(),
            conversation_id="conv-1",
            files={"a.py": "hash1"},
            context={"key": "val"},
            custom_data={"extra": 42},
        )
        assert data.conversation_id == "conv-1"
        assert data.files == {"a.py": "hash1"}
        assert data.context == {"key": "val"}
        assert data.custom_data == {"extra": 42}

    def test_to_dict(self):
        data = CheckpointData(
            metadata=self._make_meta("ckpt-1"),
            conversation_id="conv-1",
            files={"a.py": "h1"},
            context={"k": "v"},
            custom_data={"x": 1},
        )
        d = data.to_dict()
        assert d["metadata"]["id"] == "ckpt-1"
        assert d["conversation_id"] == "conv-1"
        assert d["files"] == {"a.py": "h1"}
        assert d["context"] == {"k": "v"}
        assert d["custom_data"] == {"x": 1}

    def test_from_dict(self):
        d = {
            "metadata": {
                "id": "ckpt",
                "name": "N",
                "description": "D",
                "created_at": "2026-01-01T12:00:00",
                "status": "created",
                "tags": [],
                "size": 0,
            },
            "conversation_id": "conv-1",
            "files": {"a.py": "h1"},
            "context": {"k": "v"},
            "custom_data": {"x": 1},
        }
        data = CheckpointData.from_dict(d)
        assert data.metadata.id == "ckpt"
        assert data.conversation_id == "conv-1"
        assert data.files == {"a.py": "h1"}
        assert data.context == {"k": "v"}
        assert data.custom_data == {"x": 1}

    def test_from_dict_defaults(self):
        d = {
            "metadata": {
                "id": "ckpt",
                "name": "N",
                "description": "D",
                "created_at": "2026-01-01T12:00:00",
                "status": "created",
                "tags": [],
                "size": 0,
            }
        }
        data = CheckpointData.from_dict(d)
        assert data.conversation_id is None
        assert data.files == {}
        assert data.context == {}
        assert data.custom_data == {}
