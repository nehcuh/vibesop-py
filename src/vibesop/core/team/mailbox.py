"""File-based mailbox system for team communication."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Message:
    """A message in the team mailbox."""

    sender: str
    recipient: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        return cls(**data)


class Mailbox:
    """File-based mailbox for worker communication."""

    def __init__(self, mailbox_dir: str | Path):
        self.mailbox_dir = Path(mailbox_dir)
        self.mailbox_dir.mkdir(parents=True, exist_ok=True)

    def send(self, message: Message) -> Path:
        """Send a message to a worker's mailbox."""
        msg_file = self.mailbox_dir / f"{message.recipient}.json"
        with msg_file.open("w") as f:
            json.dump(message.to_dict(), f, indent=2)
        return msg_file

    def receive(self, recipient: str) -> Message | None:
        """Receive a message from a worker's mailbox."""
        msg_file = self.mailbox_dir / f"{recipient}.json"
        if not msg_file.exists():
            return None
        with msg_file.open("r") as f:
            return Message.from_dict(json.load(f))

    def clear(self, recipient: str) -> bool:
        """Clear a worker's mailbox."""
        msg_file = self.mailbox_dir / f"{recipient}.json"
        if msg_file.exists():
            msg_file.unlink()
            return True
        return False

    def list_pending(self) -> list[str]:
        """List workers with pending messages."""
        return [f.stem for f in self.mailbox_dir.glob("*.json")]
