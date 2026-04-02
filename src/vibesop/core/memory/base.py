"""Base classes for memory system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MessageRole(Enum):
    """Role of a message in conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """A message in the conversation.

    Attributes:
        role: Message role
        content: Message content
        timestamp: When the message was created
        metadata: Additional message data
    """

    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Create from dictionary.

        Args:
            data: Dictionary data

        Returns:
            Message instance
        """
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Conversation:
    """A conversation session.

    Attributes:
        id: Unique conversation ID
        title: Conversation title
        messages: List of messages
        created_at: When conversation was created
        updated_at: When conversation was last updated
        metadata: Additional conversation data
    """

    id: str
    title: str
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}

    def add_message(self, message: Message) -> None:
        """Add a message to the conversation.

        Args:
            message: Message to add
        """
        self.messages.append(message)
        self.updated_at = datetime.now()

    def get_last_n_messages(self, n: int) -> list[Message]:
        """Get the last n messages.

        Args:
            n: Number of messages to get

        Returns:
            List of messages
        """
        return self.messages[-n:]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "id": self.id,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Conversation":
        """Create from dictionary.

        Args:
            data: Dictionary data

        Returns:
            Conversation instance
        """
        return cls(
            id=data["id"],
            title=data["title"],
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Context:
    """Execution context with memory.

    Attributes:
        conversation_id: Current conversation ID
        session_id: Current session ID
        working_dir: Working directory
        env: Environment variables
        metadata: Additional context data
    """

    conversation_id: str | None = None
    session_id: str | None = None
    working_dir: str = "."
    env: dict[str, str] | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.env is None:
            self.env = {}
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "working_dir": self.working_dir,
            "env": self.env,
            "metadata": self.metadata,
        }
