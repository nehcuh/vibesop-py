"""Test memory system."""

import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from vibesop.core.memory import (
    Context,
    Conversation,
    ConversationStorage,
    MemoryManager,
    Message,
    MessageRole,
)


class TestMessage:
    """Test Message class."""

    def test_create_message(self) -> None:
        """Test creating a message."""
        msg = Message(
            role=MessageRole.USER,
            content="Hello",
        )

        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"
        assert msg.metadata == {}

    def test_message_to_dict(self) -> None:
        """Test converting message to dictionary."""
        msg = Message(
            role=MessageRole.ASSISTANT,
            content="Hi there!",
            metadata={"source": "test"},
        )

        data = msg.to_dict()

        assert data["role"] == "assistant"
        assert data["content"] == "Hi there!"
        assert data["metadata"]["source"] == "test"

    def test_message_from_dict(self) -> None:
        """Test creating message from dictionary."""
        data = {
            "role": "user",
            "content": "Test",
            "timestamp": datetime.now().isoformat(),
            "metadata": {},
        }

        msg = Message.from_dict(data)

        assert msg.role == MessageRole.USER
        assert msg.content == "Test"


class TestConversation:
    """Test Conversation class."""

    def test_create_conversation(self) -> None:
        """Test creating a conversation."""
        conv = Conversation(
            id="test-123",
            title="Test Conversation",
        )

        assert conv.id == "test-123"
        assert conv.title == "Test Conversation"
        assert len(conv.messages) == 0

    def test_add_message(self) -> None:
        """Test adding a message to conversation."""
        conv = Conversation(
            id="test-123",
            title="Test",
        )

        msg = Message(role=MessageRole.USER, content="Hello")
        conv.add_message(msg)

        assert len(conv.messages) == 1
        assert conv.messages[0] == msg

    def test_get_last_n_messages(self) -> None:
        """Test getting last n messages."""
        conv = Conversation(id="test", title="Test")

        for i in range(10):
            conv.add_message(Message(role=MessageRole.USER, content=f"Message {i}"))

        last_3 = conv.get_last_n_messages(3)

        assert len(last_3) == 3
        assert last_3[0].content == "Message 7"
        assert last_3[2].content == "Message 9"

    def test_conversation_to_dict(self) -> None:
        """Test converting conversation to dictionary."""
        conv = Conversation(
            id="test",
            title="Test",
        )
        conv.add_message(Message(role=MessageRole.USER, content="Hello"))

        data = conv.to_dict()

        assert data["id"] == "test"
        assert data["title"] == "Test"
        assert len(data["messages"]) == 1


class TestContext:
    """Test Context class."""

    def test_create_context(self) -> None:
        """Test creating a context."""
        ctx = Context(
            conversation_id="conv-123",
            working_dir="/tmp",
        )

        assert ctx.conversation_id == "conv-123"
        assert ctx.working_dir == "/tmp"
        assert ctx.env == {}
        assert ctx.metadata == {}

    def test_context_with_env(self) -> None:
        """Test context with environment variables."""
        ctx = Context(
            env={"TEST": "value"},
        )

        assert ctx.env == {"TEST": "value"}


class TestConversationStorage:
    """Test ConversationStorage class."""

    def _create_storage(self) -> tuple[ConversationStorage, Path]:
        """Helper to create storage with temp directory."""
        tmpdir = Path(tempfile.mkdtemp())
        storage = ConversationStorage(storage_dir=tmpdir / "memory")
        return storage, tmpdir

    def test_save_and_load(self) -> None:
        """Test saving and loading a conversation."""
        storage, tmpdir = self._create_storage()

        conv = Conversation(
            id="test-123",
            title="Test",
        )
        conv.add_message(Message(role=MessageRole.USER, content="Hello"))

        storage.save(conv)
        loaded = storage.load("test-123")

        assert loaded is not None
        assert loaded.id == "test-123"
        assert loaded.title == "Test"
        assert len(loaded.messages) == 1

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_load_nonexistent(self) -> None:
        """Test loading nonexistent conversation."""
        storage, tmpdir = self._create_storage()

        result = storage.load("nonexistent")

        assert result is None

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_delete(self) -> None:
        """Test deleting a conversation."""
        storage, tmpdir = self._create_storage()

        conv = Conversation(id="test", title="Test")
        storage.save(conv)

        assert storage.exists("test")

        deleted = storage.delete("test")

        assert deleted is True
        assert not storage.exists("test")

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_delete_nonexistent(self) -> None:
        """Test deleting nonexistent conversation."""
        storage, tmpdir = self._create_storage()

        deleted = storage.delete("nonexistent")

        assert deleted is False

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_list_all(self) -> None:
        """Test listing all conversations."""
        storage, tmpdir = self._create_storage()

        # Create multiple conversations
        for i in range(3):
            conv = Conversation(
                id=f"test-{i}",
                title=f"Conversation {i}",
            )
            storage.save(conv)

        all_convs = storage.list_all()

        assert len(all_convs) == 3

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_exists(self) -> None:
        """Test checking if conversation exists."""
        storage, tmpdir = self._create_storage()

        assert not storage.exists("test")

        conv = Conversation(id="test", title="Test")
        storage.save(conv)

        assert storage.exists("test")

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_clear_all(self) -> None:
        """Test clearing all conversations."""
        storage, tmpdir = self._create_storage()

        # Create some conversations
        for i in range(3):
            conv = Conversation(id=f"test-{i}", title=f"Test {i}")
            storage.save(conv)

        count = storage.clear_all()

        assert count == 3
        assert len(storage.list_all()) == 0

        # Cleanup
        shutil.rmtree(tmpdir)


class TestMemoryManager:
    """Test MemoryManager class."""

    def _create_manager(self) -> tuple[MemoryManager, Path]:
        """Helper to create manager with temp directory."""
        tmpdir = Path(tempfile.mkdtemp())
        manager = MemoryManager(storage_dir=tmpdir / "memory")
        return manager, tmpdir

    def test_create_conversation(self) -> None:
        """Test creating a conversation."""
        manager, tmpdir = self._create_manager()

        conv = manager.create_conversation("My Session")

        assert conv.id is not None
        assert conv.title == "My Session"
        assert manager.get_active_conversation_id() == conv.id

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_create_conversation_default_title(self) -> None:
        """Test creating conversation with default title."""
        manager, tmpdir = self._create_manager()

        conv = manager.create_conversation()

        assert conv.title != ""

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_get_conversation(self) -> None:
        """Test getting a conversation."""
        manager, tmpdir = self._create_manager()

        created = manager.create_conversation("Test")
        loaded = manager.get_conversation(created.id)

        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.title == "Test"

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_get_or_create_conversation(self) -> None:
        """Test get or create conversation."""
        manager, tmpdir = self._create_manager()

        # Create new
        conv1 = manager.get_or_create_conversation(None, "New")
        assert conv1.id is not None

        # Get existing
        conv2 = manager.get_or_create_conversation(conv1.id)
        assert conv2.id == conv1.id

        # Create new for invalid ID
        conv3 = manager.get_or_create_conversation("invalid", "Another")
        assert conv3.id != conv1.id

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_delete_conversation(self) -> None:
        """Test deleting a conversation."""
        manager, tmpdir = self._create_manager()

        conv = manager.create_conversation()
        conv_id = conv.id

        deleted = manager.delete_conversation(conv_id)

        assert deleted is True
        assert manager.get_conversation(conv_id) is None

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_add_user_message(self) -> None:
        """Test adding a user message."""
        manager, tmpdir = self._create_manager()

        conv = manager.create_conversation()

        msg = manager.add_user_message(conv.id, "Hello")

        assert msg is not None
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"

        # Verify it was saved
        loaded = manager.get_conversation(conv.id)
        assert len(loaded.messages) == 1

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_add_assistant_message(self) -> None:
        """Test adding an assistant message."""
        manager, tmpdir = self._create_manager()

        conv = manager.create_conversation()

        msg = manager.add_assistant_message(conv.id, "Hi!")

        assert msg is not None
        assert msg.role == MessageRole.ASSISTANT

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_add_system_message(self) -> None:
        """Test adding a system message."""
        manager, tmpdir = self._create_manager()

        conv = manager.create_conversation()

        msg = manager.add_system_message(conv.id, "You are helpful.")

        assert msg is not None
        assert msg.role == MessageRole.SYSTEM

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_get_messages(self) -> None:
        """Test getting messages."""
        manager, tmpdir = self._create_manager()

        conv = manager.create_conversation()

        manager.add_user_message(conv.id, "First")
        manager.add_assistant_message(conv.id, "Second")
        manager.add_user_message(conv.id, "Third")

        messages = manager.get_messages(conv.id)

        assert len(messages) == 3
        assert messages[0].content == "First"
        assert messages[2].content == "Third"

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_get_messages_with_limit(self) -> None:
        """Test getting messages with limit."""
        manager, tmpdir = self._create_manager()

        conv = manager.create_conversation()

        for i in range(10):
            manager.add_user_message(conv.id, f"Message {i}")

        messages = manager.get_messages(conv.id, limit=3)

        assert len(messages) == 3
        assert messages[0].content == "Message 7"

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_get_messages_for_llm(self) -> None:
        """Test getting messages formatted for LLM."""
        manager, tmpdir = self._create_manager()

        conv = manager.create_conversation()

        manager.add_user_message(conv.id, "Hello")
        manager.add_assistant_message(conv.id, "Hi")

        messages = manager.get_messages_for_llm(conv.id)

        assert len(messages) == 2
        assert messages[0] == {"role": "user", "content": "Hello"}
        assert messages[1] == {"role": "assistant", "content": "Hi"}

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_get_messages_for_llm_exclude_system(self) -> None:
        """Test excluding system messages from LLM format."""
        manager, tmpdir = self._create_manager()

        conv = manager.create_conversation()

        manager.add_system_message(conv.id, "System prompt")
        manager.add_user_message(conv.id, "Hello")

        messages = manager.get_messages_for_llm(conv.id, include_system=False)

        assert len(messages) == 1
        assert messages[0]["role"] == "user"

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_list_conversations(self) -> None:
        """Test listing conversations."""
        manager, tmpdir = self._create_manager()

        manager.create_conversation("First")
        manager.create_conversation("Second")

        conversations = manager.list_conversations()

        assert len(conversations) == 2

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_set_active_conversation(self) -> None:
        """Test setting active conversation."""
        manager, tmpdir = self._create_manager()

        conv1 = manager.create_conversation("First")
        conv2_id = "different-id"

        # Set to existing
        result = manager.set_active_conversation(conv1.id)
        assert result is True

        # Set to non-existing
        result = manager.set_active_conversation(conv2_id)
        assert result is False

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_search_conversations(self) -> None:
        """Test searching conversations."""
        manager, tmpdir = self._create_manager()

        conv1 = manager.create_conversation("Python Development")
        manager.add_user_message(conv1.id, "How to write Python code?")

        conv2 = manager.create_conversation("JavaScript Help")
        manager.add_user_message(conv2.id, "How to write JavaScript?")

        results = manager.search_conversations("Python")

        assert len(results) >= 1
        # Check that at least one result has "Python" in title or messages
        found = False
        for c in results:
            if "Python" in c.title.lower():
                found = True
                break
            for m in c.messages:
                if "python" in m.content.lower():
                    found = True
                    break
            if found:
                break
        assert found

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_clear_old_conversations(self) -> None:
        """Test clearing old conversations."""
        manager, tmpdir = self._create_manager()

        # Manually create an old conversation
        old_conv = Conversation(
            id="old",
            title="Old",
            created_at=datetime.now() - timedelta(days=100),
            updated_at=datetime.now() - timedelta(days=100),
        )
        manager._storage.save(old_conv)

        # Create new conversation
        manager.create_conversation("New")

        # Clear old
        deleted = manager.clear_old_conversations(days=30)

        assert deleted >= 1

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_get_stats(self) -> None:
        """Test getting statistics."""
        manager, tmpdir = self._create_manager()

        manager.create_conversation("Test")
        manager.add_user_message(manager.get_active_conversation_id(), "Hello")

        stats = manager.get_stats()

        assert stats["total_conversations"] == 1
        assert stats["total_messages"] == 1
        assert "storage_dir" in stats

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_max_conversations_limit(self) -> None:
        """Test max conversations limit enforcement."""
        tmpdir = Path(tempfile.mkdtemp())

        # Ensure clean storage directory
        storage_dir = tmpdir / "memory"
        storage_dir.mkdir(parents=True, exist_ok=True)

        manager = MemoryManager(
            storage_dir=storage_dir,
            max_conversations=3,
        )

        # Create 5 conversations (max is 3)
        for i in range(5):
            manager.create_conversation(f"Conversation {i}")

        # Should only have 3 (newest ones)
        stats = manager.get_stats()
        # Since we delete old ones before creating new ones,
        # we should have exactly max_conversations
        assert stats["total_conversations"] == 3

        # Cleanup
        shutil.rmtree(tmpdir)
