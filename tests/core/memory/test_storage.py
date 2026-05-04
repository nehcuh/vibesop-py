"""Tests for ConversationStorage."""

from datetime import datetime
from pathlib import Path

from vibesop.core.memory import Conversation, ConversationStorage, Message, MessageRole


class TestConversationStorage:
    """Test ConversationStorage lifecycle operations."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        assert storage.storage_dir == tmp_path
        assert storage.storage_dir.exists()

    def test_get_conversation_path(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        path = storage.get_conversation_path("conv-123")
        assert path == tmp_path / "conv-123.json"

    def _make_conversation(self, conv_id: str = "conv-01") -> Conversation:
        return Conversation(
            id=conv_id,
            title="Test Conversation",
            messages=[
                Message(role=MessageRole.USER, content="Hello"),
                Message(role=MessageRole.ASSISTANT, content="Hi there"),
            ],
            created_at=datetime(2026, 1, 1, 12, 0, 0),
            updated_at=datetime(2026, 1, 1, 12, 5, 0),
        )

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        conversation = self._make_conversation("conv-01")

        storage.save(conversation)
        loaded = storage.load("conv-01")

        assert loaded is not None
        assert loaded.id == "conv-01"
        assert loaded.title == "Test Conversation"
        assert len(loaded.messages) == 2
        assert loaded.messages[0].role == MessageRole.USER
        assert loaded.messages[0].content == "Hello"
        assert loaded.messages[1].role == MessageRole.ASSISTANT
        assert loaded.messages[1].content == "Hi there"

    def test_load_missing_conversation_returns_none(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        assert storage.load("missing") is None

    def test_load_corrupted_file_returns_none(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        path = storage.get_conversation_path("bad")
        path.write_text("not json")
        assert storage.load("bad") is None

    def test_delete_existing(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        conversation = self._make_conversation("conv-02")
        storage.save(conversation)

        assert storage.delete("conv-02") is True
        assert storage.load("conv-02") is None

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        assert storage.delete("missing") is False

    def test_exists(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        conversation = self._make_conversation("conv-03")
        storage.save(conversation)

        assert storage.exists("conv-03") is True
        assert storage.exists("missing") is False

    def test_list_all_sorts_by_updated_at_descending(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        conv1 = Conversation(
            id="older",
            title="Older",
            updated_at=datetime(2026, 1, 1, 10, 0, 0),
        )
        conv2 = Conversation(
            id="newer",
            title="Newer",
            updated_at=datetime(2026, 1, 1, 14, 0, 0),
        )
        storage.save(conv1)
        storage.save(conv2)

        results = storage.list_all()
        assert len(results) == 2
        assert results[0].id == "newer"
        assert results[1].id == "older"

    def test_list_all_skips_corrupted_files(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        bad_path = storage.get_conversation_path("bad")
        bad_path.write_text("not json")
        assert storage.list_all() == []

    def test_clear_all(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        storage.save(self._make_conversation("conv-a"))
        storage.save(self._make_conversation("conv-b"))

        deleted = storage.clear_all()
        assert deleted == 2
        assert storage.list_all() == []

    def test_empty_conversation_roundtrip(self, tmp_path: Path) -> None:
        storage = ConversationStorage(storage_dir=str(tmp_path))
        conversation = Conversation(id="empty", title="Empty")
        storage.save(conversation)

        loaded = storage.load("empty")
        assert loaded is not None
        assert loaded.messages == []
        assert loaded.metadata == {}
