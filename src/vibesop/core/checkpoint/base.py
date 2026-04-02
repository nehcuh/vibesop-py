"""Base classes for checkpoint system."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class CheckpointStatus(Enum):
    """Status of a checkpoint."""

    CREATED = "created"
    RESTORED = "restored"
    EXPIRED = "expired"
    CORRUPTED = "corrupted"


@dataclass
class CheckpointMetadata:
    """Metadata for a checkpoint.

    Attributes:
        id: Unique checkpoint ID
        name: Human-readable name
        description: Checkpoint description
        created_at: When checkpoint was created
        status: Current status
        tags: List of tags
        size: Size in bytes
    """

    id: str
    name: str
    description: str
    created_at: datetime
    status: CheckpointStatus = CheckpointStatus.CREATED
    tags: list[str] | None = None
    size: int = 0

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "tags": self.tags,
            "size": self.size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointMetadata":
        """Create from dictionary.

        Args:
            data: Dictionary data

        Returns:
            CheckpointMetadata instance
        """
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            created_at=datetime.fromisoformat(data["created_at"]),
            status=CheckpointStatus(data.get("status", "created")),
            tags=data.get("tags", []),
            size=data.get("size", 0),
        )


@dataclass
class CheckpointData:
    """Data stored in a checkpoint.

    Attributes:
        metadata: Checkpoint metadata
        conversation_id: Associated conversation ID
        files: Snapshot of file states
        context: Execution context
        custom_data: Additional custom data
    """

    metadata: CheckpointMetadata
    conversation_id: str | None = None
    files: dict[str, str] | None = None  # path -> content hash
    context: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.files is None:
            self.files = {}
        if self.context is None:
            self.context = {}
        if self.custom_data is None:
            self.custom_data = {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "metadata": self.metadata.to_dict(),
            "conversation_id": self.conversation_id,
            "files": self.files,
            "context": self.context,
            "custom_data": self.custom_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointData":
        """Create from dictionary.

        Args:
            data: Dictionary data

        Returns:
            CheckpointData instance
        """
        return cls(
            metadata=CheckpointMetadata.from_dict(data["metadata"]),
            conversation_id=data.get("conversation_id"),
            files=data.get("files", {}),
            context=data.get("context", {}),
            custom_data=data.get("custom_data", {}),
        )
