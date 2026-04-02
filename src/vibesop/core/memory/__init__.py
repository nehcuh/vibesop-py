"""VibeSOP Memory System.

This module provides conversation memory and context management:
- Message and Conversation data classes
- Persistent storage backend
- High-level memory management API

Usage:
    from vibesop.core.memory import MemoryManager, MessageRole

    manager = MemoryManager()
    conv = manager.create_conversation("My Session")
    manager.add_user_message(conv.id, "Hello")
    messages = manager.get_messages_for_llm(conv.id)
"""

from vibesop.core.memory.base import Context, Conversation, Message, MessageRole
from vibesop.core.memory.manager import MemoryManager
from vibesop.core.memory.storage import ConversationStorage

__all__ = [
    "Context",
    "Conversation",
    "ConversationStorage",
    "MemoryManager",
    "Message",
    "MessageRole",
]
