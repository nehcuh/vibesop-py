"""Persistent storage for conversations."""

import json
from pathlib import Path

from vibesop.core.memory.base import Conversation


class ConversationStorage:
    """Storage backend for conversations.

    Handles reading and writing conversations to disk.
    """

    def __init__(self, storage_dir: str | Path = ".vibe/memory") -> None:
        """Initialize the storage backend.

        Args:
            storage_dir: Directory to store conversation files
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def get_conversation_path(self, conversation_id: str) -> Path:
        """Get the file path for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Path to conversation file
        """
        return self.storage_dir / f"{conversation_id}.json"

    def save(self, conversation: Conversation) -> None:
        """Save a conversation to disk.

        Args:
            conversation: Conversation to save
        """
        path = self.get_conversation_path(conversation.id)

        with path.open("w", encoding="utf-8") as f:
            json.dump(conversation.to_dict(), f, indent=2, ensure_ascii=False)

    def load(self, conversation_id: str) -> Conversation | None:
        """Load a conversation from disk.

        Args:
            conversation_id: Conversation ID

        Returns:
            Conversation or None if not found
        """
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
        """Delete a conversation from disk.

        Args:
            conversation_id: Conversation ID

        Returns:
            True if deleted, False if not found
        """
        path = self.get_conversation_path(conversation_id)

        if not path.exists():
            return False

        path.unlink()
        return True

    def list_all(self) -> list[Conversation]:
        """List all stored conversations.

        Returns:
            List of conversations
        """
        conversations = []

        for file_path in self.storage_dir.glob("*.json"):
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                conversations.append(Conversation.from_dict(data))
            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip corrupted files
                continue

        # Sort by updated_at, most recent first
        conversations.sort(key=lambda c: c.updated_at, reverse=True)
        return conversations

    def exists(self, conversation_id: str) -> bool:
        """Check if a conversation exists.

        Args:
            conversation_id: Conversation ID

        Returns:
            True if conversation exists
        """
        return self.get_conversation_path(conversation_id).exists()

    def clear_all(self) -> int:
        """Clear all stored conversations.

        Returns:
            Number of conversations deleted
        """
        count = 0
        for file_path in self.storage_dir.glob("*.json"):
            file_path.unlink()
            count += 1
        return count
