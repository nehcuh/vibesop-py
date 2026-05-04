"""Tests for MemoryManager."""

import pytest

from vibesop.core.memory import Conversation, MemoryManager, MessageRole


@pytest.fixture
def manager(tmp_path):
    """Provide a MemoryManager with a temp storage dir."""
    return MemoryManager(storage_dir=tmp_path)


class TestCreateConversation:
    def test_returns_conversation_with_id(self, manager):
        conv = manager.create_conversation("Test Chat")
        assert isinstance(conv, Conversation)
        assert conv.id
        assert len(conv.id) == 8
        assert conv.title == "Test Chat"

    def test_generates_default_title_when_empty(self, manager):
        conv = manager.create_conversation()
        assert conv.title.startswith("Conversation ")


class TestAddMessages:
    def test_add_user_message(self, manager):
        conv = manager.create_conversation()
        msg = manager.add_user_message(conv.id, "Hello")
        assert msg is not None
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"

    def test_add_assistant_message(self, manager):
        conv = manager.create_conversation()
        msg = manager.add_assistant_message(conv.id, "Hi there")
        assert msg is not None
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "Hi there"

    def test_add_message_to_missing_conversation_returns_none(self, manager):
        assert manager.add_user_message("missing-id", "Hello") is None
        assert manager.add_assistant_message("missing-id", "Hi") is None


class TestGetConversation:
    def test_get_conversation_returns_conversation(self, manager):
        conv = manager.create_conversation("My Chat")
        manager.add_user_message(conv.id, "Hello")

        fetched = manager.get_conversation(conv.id)
        assert fetched is not None
        assert fetched.id == conv.id
        assert fetched.title == "My Chat"
        assert len(fetched.messages) == 1

    def test_get_conversation_missing_returns_none(self, manager):
        assert manager.get_conversation("no-such-id") is None


class TestGetMessagesForLlm:
    def test_returns_formatted_messages(self, manager):
        conv = manager.create_conversation()
        manager.add_user_message(conv.id, "Hello")
        manager.add_assistant_message(conv.id, "Hi")

        messages = manager.get_messages_for_llm(conv.id)
        assert messages == [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

    def test_excludes_system_when_requested(self, manager):
        conv = manager.create_conversation()
        manager.add_system_message(conv.id, "Be helpful")
        manager.add_user_message(conv.id, "Hello")

        messages = manager.get_messages_for_llm(conv.id, include_system=False)
        assert messages == [{"role": "user", "content": "Hello"}]

    def test_missing_conversation_returns_empty_list(self, manager):
        assert manager.get_messages_for_llm("missing") == []


class TestActiveConversation:
    def test_get_active_after_create(self, manager):
        conv = manager.create_conversation()
        assert manager.get_active_conversation_id() == conv.id

    def test_set_active_conversation(self, manager):
        conv1 = manager.create_conversation()
        conv2 = manager.create_conversation()
        assert manager.get_active_conversation_id() == conv2.id

        result = manager.set_active_conversation(conv1.id)
        assert result is True
        assert manager.get_active_conversation_id() == conv1.id

    def test_set_active_missing_returns_false(self, manager):
        assert manager.set_active_conversation("missing") is False


class TestListConversations:
    def test_list_conversations(self, manager):
        conv1 = manager.create_conversation("First")
        conv2 = manager.create_conversation("Second")

        convs = manager.list_conversations()
        ids = {c.id for c in convs}
        assert ids == {conv1.id, conv2.id}

    def test_list_conversations_respects_limit(self, manager):
        for i in range(5):
            manager.create_conversation(f"Conv {i}")
        assert len(manager.list_conversations(limit=2)) == 2


class TestDeleteConversation:
    def test_delete_conversation_removes_it(self, manager):
        conv = manager.create_conversation()
        assert manager.get_conversation(conv.id) is not None

        result = manager.delete_conversation(conv.id)
        assert result is True
        assert manager.get_conversation(conv.id) is None

    def test_delete_clears_active_conversation(self, manager):
        conv = manager.create_conversation()
        assert manager.get_active_conversation_id() == conv.id

        manager.delete_conversation(conv.id)
        assert manager.get_active_conversation_id() is None

    def test_delete_missing_returns_false(self, manager):
        assert manager.delete_conversation("missing") is False
