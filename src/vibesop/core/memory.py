"""VibeSOP Memory System — conversation memory and context management.

Usage:
    from vibesop.core.memory import MemoryManager, MessageRole

    manager = MemoryManager()
    conv = manager.create_conversation("My Session")
    manager.add_user_message(conv.id, "Hello")
    messages = manager.get_messages_for_llm(conv.id)
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class MessageRole(Enum):
    """Role of a message in conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """A message in the conversation."""

    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Conversation:
    """A conversation session."""

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
        self.messages.append(message)
        self.updated_at = datetime.now()

    def get_last_n_messages(self, n: int) -> list[Message]:
        return self.messages[-n:]

    def to_dict(self) -> dict[str, Any]:
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
    """Execution context with memory."""

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
        return {
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "working_dir": self.working_dir,
            "env": self.env,
            "metadata": self.metadata,
        }


class ConversationStorage:
    """Storage backend for conversations — reads/writes JSON to disk."""

    def __init__(self, storage_dir: str | Path = ".vibe/memory") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def get_conversation_path(self, conversation_id: str) -> Path:
        return self.storage_dir / f"{conversation_id}.json"

    def save(self, conversation: Conversation) -> None:
        path = self.get_conversation_path(conversation.id)
        with path.open("w", encoding="utf-8") as f:
            json.dump(conversation.to_dict(), f, indent=2, ensure_ascii=False)

    def load(self, conversation_id: str) -> Conversation | None:
        path = self.get_conversation_path(conversation_id)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return Conversation.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def delete(self, conversation_id: str) -> bool:
        path = self.get_conversation_path(conversation_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def list_all(self) -> list[Conversation]:
        conversations = []
        for file_path in self.storage_dir.glob("*.json"):
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                conversations.append(Conversation.from_dict(data))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        conversations.sort(key=lambda c: c.updated_at, reverse=True)
        return conversations

    def exists(self, conversation_id: str) -> bool:
        return self.get_conversation_path(conversation_id).exists()

    def clear_all(self) -> int:
        count = 0
        for file_path in self.storage_dir.glob("*.json"):
            file_path.unlink()
            count += 1
        return count


class MemoryManager:
    """Manage conversation memory and context.

    Usage:
        manager = MemoryManager()
        conv = manager.create_conversation("My Session")
        manager.add_user_message(conv.id, "Hello")
        manager.add_assistant_message(conv.id, "Hi there!")
        conv = manager.get_conversation(conv.id)
        messages = manager.get_messages_for_llm(conv.id)
    """

    def __init__(
        self,
        storage_dir: str | Path = ".vibe/memory",
        max_conversations: int = 100,
    ) -> None:
        self._storage = ConversationStorage(storage_dir)
        self._max_conversations = max_conversations
        self._active_conversation_id: str | None = None

    def create_conversation(
        self,
        title: str = "",
        metadata: dict[str, object] | None = None,
    ) -> Conversation:
        self._enforce_limit()
        conv_id = str(uuid.uuid4())[:8]
        now = datetime.now()
        if not title:
            title = f"Conversation {now.strftime('%Y-%m-%d %H:%M')}"
        conversation = Conversation(
            id=conv_id,
            title=title,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        self._storage.save(conversation)
        self._active_conversation_id = conv_id
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self._storage.load(conversation_id)

    def get_or_create_conversation(
        self,
        conversation_id: str | None = None,
        title: str = "",
    ) -> Conversation:
        if conversation_id:
            conv = self._storage.load(conversation_id)
            if conv:
                return conv
        return self.create_conversation(title)

    def delete_conversation(self, conversation_id: str) -> bool:
        if self._active_conversation_id == conversation_id:
            self._active_conversation_id = None
        return self._storage.delete(conversation_id)

    def list_conversations(self, limit: int = 50) -> list[Conversation]:
        return self._storage.list_all()[:limit]

    def add_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message | None:
        conv = self._storage.load(conversation_id)
        if not conv:
            return None
        message = Message(role=role, content=content, metadata=metadata or {})
        conv.add_message(message)
        self._storage.save(conv)
        return message

    def add_user_message(
        self,
        conversation_id: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message | None:
        return self.add_message(conversation_id, MessageRole.USER, content, metadata)

    def add_assistant_message(
        self,
        conversation_id: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message | None:
        return self.add_message(conversation_id, MessageRole.ASSISTANT, content, metadata)

    def add_system_message(
        self,
        conversation_id: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message | None:
        return self.add_message(conversation_id, MessageRole.SYSTEM, content, metadata)

    def get_messages(
        self,
        conversation_id: str,
        limit: int = 100,
    ) -> list[Message]:
        conv = self._storage.load(conversation_id)
        if not conv:
            return []
        return conv.get_last_n_messages(limit)

    def get_messages_for_llm(
        self,
        conversation_id: str,
        include_system: bool = True,
        limit: int = 100,
    ) -> list[dict[str, str]]:
        messages = self.get_messages(conversation_id, limit)
        result = []
        for msg in messages:
            if not include_system and msg.role == MessageRole.SYSTEM:
                continue
            result.append({"role": msg.role.value, "content": msg.content})
        return result

    def get_recent_queries(
        self,
        conversation_id: str | None = None,
        limit: int = 5,
    ) -> list[str]:
        conv_id = conversation_id or self._active_conversation_id
        if not conv_id:
            return []
        conv = self._storage.load(conv_id)
        if not conv:
            return []
        queries = []
        for msg in conv.messages:
            if msg.role == MessageRole.USER:
                queries.append(msg.content)
        return queries[-limit:]

    def search_conversations(
        self,
        query: str,
        limit: int = 10,
    ) -> list[Conversation]:
        """Search conversations by semantic token overlap.

        Uses token-based similarity instead of naive substring matching
        to support CJK languages and multi-word intent matching.
        """
        from vibesop.core.matching.tokenizers import tokenize

        query_tokens = set(tokenize(query))
        if not query_tokens:
            return []

        scored_results: list[tuple[float, Conversation]] = []

        for conv in self._storage.list_all():
            scores: list[float] = []

            title_tokens = set(tokenize(conv.title))
            if title_tokens:
                intersection = query_tokens & title_tokens
                union = query_tokens | title_tokens
                scores.append(len(intersection) / len(union) if union else 0.0)

            best_msg_score = 0.0
            for msg in conv.messages:
                msg_tokens = set(tokenize(msg.content))
                if msg_tokens:
                    intersection = query_tokens & msg_tokens
                    union = query_tokens | msg_tokens
                    score = len(intersection) / len(union) if union else 0.0
                    best_msg_score = max(best_msg_score, score)
            if best_msg_score > 0:
                scores.append(best_msg_score)

            if scores:
                avg_score = sum(scores) / len(scores)
                if avg_score > 0.1:
                    scored_results.append((avg_score, conv))

        scored_results.sort(key=lambda x: x[0], reverse=True)
        return [conv for _score, conv in scored_results[:limit]]

    def get_active_conversation_id(self) -> str | None:
        return self._active_conversation_id

    def set_active_conversation(self, conversation_id: str) -> bool:
        if not self._storage.exists(conversation_id):
            return False
        self._active_conversation_id = conversation_id
        return True

    def clear_old_conversations(self, days: int = 30) -> int:
        cutoff = datetime.now() - timedelta(days=days)
        deleted = 0
        for conv in self._storage.list_all():
            if conv.updated_at < cutoff and self._storage.delete(conv.id):
                deleted += 1
        return deleted

    def get_stats(self) -> dict[str, object]:
        conversations = self._storage.list_all()
        total_messages = sum(len(conv.messages) for conv in conversations)
        return {
            "total_conversations": len(conversations),
            "total_messages": total_messages,
            "active_conversation": self._active_conversation_id,
            "storage_dir": str(self._storage.storage_dir),
        }

    def _enforce_limit(self) -> None:
        """Delete oldest conversations to stay under max_conversations."""
        conversations = self._storage.list_all()
        if len(conversations) >= self._max_conversations:
            for conv in conversations[: -(self._max_conversations - 1)]:
                self._storage.delete(conv.id)


__all__ = [
    "Context",
    "Conversation",
    "ConversationStorage",
    "MemoryManager",
    "Message",
    "MessageRole",
]
