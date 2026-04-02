"""Storage for checkpoint system."""

import hashlib
import json
from pathlib import Path

from vibesop.core.checkpoint.base import CheckpointData, CheckpointMetadata


class CheckpointStorage:
    """Storage backend for checkpoints.

    Handles reading and writing checkpoints to disk.
    """

    def __init__(
        self,
        storage_dir: str | Path = ".vibe/checkpoints",
    ) -> None:
        """Initialize the storage backend.

        Args:
            storage_dir: Directory to store checkpoint data
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectories
        self.meta_dir = self.storage_dir / "meta"
        self.meta_dir.mkdir(exist_ok=True)
        self.data_dir = self.storage_dir / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.files_dir = self.storage_dir / "files"
        self.files_dir.mkdir(exist_ok=True)

    def get_meta_path(self, checkpoint_id: str) -> Path:
        """Get the metadata file path for a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Path to metadata file
        """
        return self.meta_dir / f"{checkpoint_id}.json"

    def get_data_path(self, checkpoint_id: str) -> Path:
        """Get the data file path for a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Path to data file
        """
        return self.data_dir / f"{checkpoint_id}.json"

    def get_file_path(self, checkpoint_id: str, file_path: str) -> Path:
        """Get the stored file path for a checkpointed file.

        Args:
            checkpoint_id: Checkpoint ID
            file_path: Original file path

        Returns:
            Path to stored file
        """
        # Create a safe filename from the file path
        safe_name = file_path.replace("/", "_").replace("\\", "_")
        return self.files_dir / f"{checkpoint_id}_{safe_name}"

    def save(self, checkpoint: CheckpointData) -> None:
        """Save a checkpoint to disk.

        Args:
            checkpoint: Checkpoint data to save
        """
        # Save metadata
        meta_path = self.get_meta_path(checkpoint.metadata.id)
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(checkpoint.metadata.to_dict(), f, indent=2)

        # Save data (without metadata, already saved separately)
        data_path = self.get_data_path(checkpoint.metadata.id)
        data_to_save = {
            "conversation_id": checkpoint.conversation_id,
            "files": checkpoint.files,
            "context": checkpoint.context,
            "custom_data": checkpoint.custom_data,
        }
        with data_path.open("w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=2)

    def load(self, checkpoint_id: str) -> CheckpointData | None:
        """Load a checkpoint from disk.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            CheckpointData or None if not found
        """
        # Load metadata
        meta_path = self.get_meta_path(checkpoint_id)
        if not meta_path.exists():
            return None

        try:
            with meta_path.open("r", encoding="utf-8") as f:
                metadata = CheckpointMetadata.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

        # Load data
        data_path = self.get_data_path(checkpoint_id)
        if not data_path.exists():
            return CheckpointData(metadata=metadata)

        try:
            with data_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError):
            return CheckpointData(metadata=metadata)

        return CheckpointData(
            metadata=metadata,
            conversation_id=data.get("conversation_id"),
            files=data.get("files", {}),
            context=data.get("context", {}),
            custom_data=data.get("custom_data", {}),
        )

    def delete(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint from disk.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            True if deleted, False if not found
        """
        deleted = False

        # Delete metadata
        meta_path = self.get_meta_path(checkpoint_id)
        if meta_path.exists():
            meta_path.unlink()
            deleted = True

        # Delete data
        data_path = self.get_data_path(checkpoint_id)
        if data_path.exists():
            data_path.unlink()

        # Delete associated files
        for file_path in self.files_dir.glob(f"{checkpoint_id}_*"):
            file_path.unlink()

        return deleted

    def list_all(self) -> list[CheckpointMetadata]:
        """List all stored checkpoints.

        Returns:
            List of checkpoint metadata
        """
        checkpoints = []

        for meta_path in self.meta_dir.glob("*.json"):
            try:
                with meta_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                checkpoints.append(CheckpointMetadata.from_dict(data))
            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip corrupted files
                continue

        # Sort by created_at, most recent first
        checkpoints.sort(key=lambda c: c.created_at, reverse=True)
        return checkpoints

    def exists(self, checkpoint_id: str) -> bool:
        """Check if a checkpoint exists.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            True if checkpoint exists
        """
        return self.get_meta_path(checkpoint_id).exists()

    def save_file(
        self,
        checkpoint_id: str,
        file_path: str,
        content: str,
    ) -> str:
        """Save a file snapshot for a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID
            file_path: Original file path
            content: File content

        Returns:
            Content hash
        """
        stored_path = self.get_file_path(checkpoint_id, file_path)

        with stored_path.open("w", encoding="utf-8") as f:
            f.write(content)

        # Calculate hash
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return content_hash

    def load_file(
        self,
        checkpoint_id: str,
        file_path: str,
    ) -> str | None:
        """Load a file snapshot from a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID
            file_path: Original file path

        Returns:
            File content or None if not found
        """
        stored_path = self.get_file_path(checkpoint_id, file_path)

        if not stored_path.exists():
            return None

        with stored_path.open("r", encoding="utf-8") as f:
            return f.read()

    def clear_all(self) -> int:
        """Clear all stored checkpoints.

        Returns:
            Number of checkpoints deleted
        """
        count = 0

        for meta_path in self.meta_dir.glob("*.json"):
            checkpoint_id = meta_path.stem
            if self.delete(checkpoint_id):
                count += 1

        return count

    def get_size(self, checkpoint_id: str) -> int:
        """Get the total size of a checkpoint in bytes.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Size in bytes
        """
        total_size = 0

        # Metadata file
        meta_path = self.get_meta_path(checkpoint_id)
        if meta_path.exists():
            total_size += meta_path.stat().st_size

        # Data file
        data_path = self.get_data_path(checkpoint_id)
        if data_path.exists():
            total_size += data_path.stat().st_size

        # Associated files
        for file_path in self.files_dir.glob(f"{checkpoint_id}_*"):
            total_size += file_path.stat().st_size

        return total_size
