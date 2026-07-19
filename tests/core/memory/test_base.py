"""Tests for memory base classes."""

from datetime import datetime

from vibesop.core.memory import Context, Conversation, Message, MessageRole


class TestMessageRole:
    """Test MessageRole enum."""

    def test_values(self):
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.TOOL.value == "tool"


class TestMessage:
    """Test Message dataclass."""

    def test_creation(self):
        msg = Message(role=MessageRole.USER, content="Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"
        assert msg.metadata == {}
        assert isinstance(msg.timestamp, datetime)

    def test_creation_with_metadata(self):
        msg = Message(role=MessageRole.ASSISTANT, content="Hi", metadata={"key": "val"})
        assert msg.metadata == {"key": "val"}

    def test_to_dict(self):
        dt = datetime(2026, 1, 1, 12, 0, 0)
        msg = Message(role=MessageRole.USER, content="Hello", timestamp=dt, metadata={"k": "v"})
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Hello"
        assert d["timestamp"] == "2026-01-01T12:00:00"
        assert d["metadata"] == {"k": "v"}

    def test_from_dict(self):
        d = {
            "role": "assistant",
            "content": "Hi",
            "timestamp": "2026-01-01T12:00:00",
            "metadata": {"k": "v"},
        }
        msg = Message.from_dict(d)
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "Hi"
        assert msg.metadata == {"k": "v"}

    def test_from_dict_defaults(self):
        d = {"role": "user", "content": "Hello", "timestamp": "2026-01-01T12:00:00"}
        msg = Message.from_dict(d)
        assert msg.metadata == {}


class TestConversation:
    """Test Conversation dataclass."""

    def test_creation_defaults(self):
        conv = Conversation(id="conv-1", title="Test")
        assert conv.messages == []
        assert conv.metadata == {}
        assert isinstance(conv.created_at, datetime)
        assert isinstance(conv.updated_at, datetime)

    def test_creation_with_messages(self):
        msg = Message(role=MessageRole.USER, content="Hello")
        conv = Conversation(id="conv-1", title="Test", messages=[msg])
        assert len(conv.messages) == 1
        assert conv.messages[0].content == "Hello"

    def test_add_message(self):
        conv = Conversation(id="conv-1", title="Test")
        # Pin updated_at into the past: on Windows the system clock granularity
        # (~15ms) can make a fresh `datetime.now()` compare equal, so deriving
        # `old_updated` from construction time is not a stable baseline.
        conv.updated_at = datetime(2020, 1, 1)
        old_updated = conv.updated_at
        msg = Message(role=MessageRole.USER, content="Hello")
        conv.add_message(msg)

        assert len(conv.messages) == 1
        assert conv.updated_at > old_updated

    def test_get_last_n_messages(self):
        conv = Conversation(id="conv-1", title="Test")
        conv.add_message(Message(role=MessageRole.USER, content="1"))
        conv.add_message(Message(role=MessageRole.USER, content="2"))
        conv.add_message(Message(role=MessageRole.USER, content="3"))

        last2 = conv.get_last_n_messages(2)
        assert len(last2) == 2
        assert last2[0].content == "2"
        assert last2[1].content == "3"

    def test_to_dict(self):
        dt = datetime(2026, 1, 1, 12, 0, 0)
        conv = Conversation(
            id="conv-1",
            title="Test",
            messages=[Message(role=MessageRole.USER, content="Hello", timestamp=dt)],
            created_at=dt,
            updated_at=dt,
            metadata={"k": "v"},
        )
        d = conv.to_dict()
        assert d["id"] == "conv-1"
        assert d["title"] == "Test"
        assert len(d["messages"]) == 1
        assert d["messages"][0]["content"] == "Hello"
        assert d["created_at"] == "2026-01-01T12:00:00"
        assert d["metadata"] == {"k": "v"}

    def test_from_dict(self):
        d = {
            "id": "conv-1",
            "title": "Test",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                    "timestamp": "2026-01-01T12:00:00",
                    "metadata": {},
                }
            ],
            "created_at": "2026-01-01T12:00:00",
            "updated_at": "2026-01-01T12:00:00",
            "metadata": {"k": "v"},
        }
        conv = Conversation.from_dict(d)
        assert conv.id == "conv-1"
        assert len(conv.messages) == 1
        assert conv.messages[0].role == MessageRole.USER
        assert conv.metadata == {"k": "v"}

    def test_from_dict_empty_messages(self):
        d = {
            "id": "conv-1",
            "title": "Test",
            "messages": [],
            "created_at": "2026-01-01T12:00:00",
            "updated_at": "2026-01-01T12:00:00",
            "metadata": {},
        }
        conv = Conversation.from_dict(d)
        assert conv.messages == []


class TestContext:
    """Test Context dataclass."""

    def test_creation_defaults(self):
        ctx = Context()
        assert ctx.conversation_id is None
        assert ctx.session_id is None
        assert ctx.working_dir == "."
        assert ctx.env == {}
        assert ctx.metadata == {}

    def test_creation_with_values(self):
        ctx = Context(
            conversation_id="conv-1",
            session_id="sess-1",
            working_dir="/tmp",
            env={"KEY": "VAL"},
            metadata={"k": "v"},
        )
        assert ctx.conversation_id == "conv-1"
        assert ctx.env == {"KEY": "VAL"}

    def test_to_dict(self):
        ctx = Context(
            conversation_id="c",
            session_id="s",
            working_dir="/tmp",
            env={"k": "v"},
            metadata={"m": 1},
        )
        d = ctx.to_dict()
        assert d["conversation_id"] == "c"
        assert d["session_id"] == "s"
        assert d["working_dir"] == "/tmp"
        assert d["env"] == {"k": "v"}
        assert d["metadata"] == {"m": 1}
