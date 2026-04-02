"""Memory manager for conversation tracking."""

import uuid
from datetime import datetime, timedelta
from pathlib import Path

from vibesop.core.memory.base import Conversation, Message, MessageRole
from vibesop.core.memory.storage import ConversationStorage


class MemoryManager:
    """Manage conversation memory and context.

    Usage:
        manager = MemoryManager()

        # Start a new conversation
        conv = manager.create_conversation("My Session")

        # Add messages
        manager.add_user_message(conv.id, "Hello")
        manager.add_assistant_message(conv.id, "Hi there!")

        # Get conversation
        conv = manager.get_conversation(conv.id)

        # Get context for LLM
        messages = manager.get_messages_for_llm(conv.id)
    """

    def __init__(
        self,
        storage_dir: str | Path = ".vibe/memory",
        max_conversations: int = 100,
    ) -> None:
        """Initialize the memory manager.

        Args:
            storage_dir: Directory for conversation storage
            max_conversations: Maximum conversations to keep
        """
        self._storage = ConversationStorage(storage_dir)
        self._max_conversations = max_conversations

        # Current active conversation
        self._active_conversation_id: str | None = None

    def create_conversation(
        self,
        title: str = "",
        metadata: dict[str, object] | None = None,
    ) -> Conversation:
        """Create a new conversation.

        Args:
            title: Conversation title
            metadata: Optional metadata

        Returns:
            New conversation
        """
        # Enforce max conversations limit
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
        """Get a conversation by ID.

        Args:
            conversation_id: Conversation ID

        Returns:
            Conversation or None if not found
        """
        return self._storage.load(conversation_id)

    def get_or_create_conversation(
        self,
        conversation_id: str | None = None,
        title: str = "",
    ) -> Conversation:
        """Get existing conversation or create new one.

        Args:
            conversation_id: Existing conversation ID (None to create new)
            title: Title for new conversation

        Returns:
            Conversation
        """
        if conversation_id:
            conv = self._storage.load(conversation_id)
            if conv:
                return conv

        return self.create_conversation(title)

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            True if deleted
        """
        if self._active_conversation_id == conversation_id:
            self._active_conversation_id = None

        return self._storage.delete(conversation_id)

    def list_conversations(
        self,
        limit: int = 50,
    ) -> list[Conversation]:
        """List all conversations.

        Args:
            limit: Maximum number to return

        Returns:
            List of conversations
        """
        all_convs = self._storage.list_all()
        return all_convs[:limit]

    def add_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message | None:
        """Add a message to a conversation.

        Args:
            conversation_id: Conversation ID
            role: Message role
            content: Message content
            metadata: Optional metadata

        Returns:
            Added message or None if conversation not found
        """
        conv = self._storage.load(conversation_id)
        if not conv:
            return None

        message = Message(
            role=role,
            content=content,
            metadata=metadata or {},
        )

        conv.add_message(message)
        self._storage.save(conv)

        return message

    def add_user_message(
        self,
        conversation_id: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message | None:
        """Add a user message.

        Args:
            conversation_id: Conversation ID
            content: Message content
            metadata: Optional metadata

        Returns:
            Added message or None if conversation not found
        """
        return self.add_message(conversation_id, MessageRole.USER, content, metadata)

    def add_assistant_message(
        self,
        conversation_id: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message | None:
        """Add an assistant message.

        Args:
            conversation_id: Conversation ID
            content: Message content
            metadata: Optional metadata

        Returns:
            Added message or None if conversation not found
        """
        return self.add_message(conversation_id, MessageRole.ASSISTANT, content, metadata)

    def add_system_message(
        self,
        conversation_id: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message | None:
        """Add a system message.

        Args:
            conversation_id: Conversation ID
            content: Message content
            metadata: Optional metadata

        Returns:
            Added message or None if conversation not found
        """
        return self.add_message(conversation_id, MessageRole.SYSTEM, content, metadata)

    def get_messages(
        self,
        conversation_id: str,
        limit: int = 100,
    ) -> list[Message]:
        """Get messages from a conversation.

        Args:
            conversation_id: Conversation ID
            limit: Maximum messages to return

        Returns:
            List of messages
        """
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
        """Get messages formatted for LLM API.

        Args:
            conversation_id: Conversation ID
            include_system: Whether to include system messages
            limit: Maximum messages to return

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        messages = self.get_messages(conversation_id, limit)

        result = []
        for msg in messages:
            if not include_system and msg.role == MessageRole.SYSTEM:
                continue
            result.append({"role": msg.role.value, "content": msg.content})

        return result

    def search_conversations(
        self,
        query: str,
        limit: int = 10,
    ) -> list[Conversation]:
        """Search conversations by content.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching conversations
        """
        query_lower = query.lower()
        results = []

        for conv in self._storage.list_all():
            # Search in title
            if query_lower in conv.title.lower():
                results.append(conv)
                continue

            # Search in messages
            for msg in conv.messages:
                if query_lower in msg.content.lower():
                    results.append(conv)
                    break

            if len(results) >= limit:
                break

        return results

    def get_active_conversation_id(self) -> str | None:
        """Get the active conversation ID.

        Returns:
            Active conversation ID or None
        """
        return self._active_conversation_id

    def set_active_conversation(self, conversation_id: str) -> bool:
        """Set the active conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            True if conversation exists
        """
        if not self._storage.exists(conversation_id):
            return False

        self._active_conversation_id = conversation_id
        return True

    def clear_old_conversations(self, days: int = 30) -> int:
        """Clear conversations older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of conversations deleted
        """
        cutoff = datetime.now() - timedelta(days=days)
        deleted = 0

        for conv in self._storage.list_all():
            if conv.updated_at < cutoff and self._storage.delete(conv.id):
                deleted += 1

        return deleted

    def get_stats(self) -> dict[str, object]:
        """Get memory statistics.

        Returns:
            Dictionary with statistics
        """
        conversations = self._storage.list_all()

        total_messages = sum(len(conv.messages) for conv in conversations)

        return {
            "total_conversations": len(conversations),
            "total_messages": total_messages,
            "active_conversation": self._active_conversation_id,
            "storage_dir": str(self._storage.storage_dir),
        }

    def _enforce_limit(self) -> None:
        """Enforce maximum conversations limit.

        Deletes oldest conversations to make room for new ones.
        Ensures that after creating a new conversation, total will be <= max.
        """
        conversations = self._storage.list_all()

        # We need to delete enough so that after adding the new one,
        # we're at max_conversations. So we keep max-1 and delete the rest.
        if len(conversations) >= self._max_conversations:
            # Delete oldest conversations (keep newest max-1)
            for conv in conversations[: -(self._max_conversations - 1)]:
                self._storage.delete(conv.id)
