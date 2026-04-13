"""Checkpoint manager for saving and restoring work state."""

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from vibesop.core.checkpoint.base import (
    CheckpointData,
    CheckpointMetadata,
    CheckpointStatus,
)
from vibesop.core.checkpoint.storage import CheckpointStorage


class CheckpointManager:
    """Manage work state checkpoints.

    Usage:
        manager = CheckpointManager()

        # Create a checkpoint
        cp = manager.create_checkpoint("My Work", "Current progress")

        # Restore a checkpoint
        restored = manager.restore_checkpoint(cp.id)

        # List checkpoints
        checkpoints = manager.list_checkpoints()
    """

    def __init__(
        self,
        storage_dir: str | Path = ".vibe/checkpoints",
        max_checkpoints: int = 50,
        max_age_days: int = 90,
    ) -> None:
        """Initialize the checkpoint manager.

        Args:
            storage_dir: Directory for checkpoint storage
            max_checkpoints: Maximum checkpoints to keep
            max_age_days: Maximum age in days before auto-cleanup
        """
        self._storage = CheckpointStorage(storage_dir)
        self._max_checkpoints = max_checkpoints
        self._max_age_days = max_age_days

    def create_checkpoint(
        self,
        name: str,
        description: str = "",
        conversation_id: str | None = None,
        files: list[str] | None = None,
        context: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> CheckpointData:
        """Create a new checkpoint.

        Args:
            name: Checkpoint name
            description: Checkpoint description
            conversation_id: Optional associated conversation ID
            files: Optional list of file paths to snapshot
            context: Optional execution context
            tags: Optional tags for categorization

        Returns:
            Created checkpoint data
        """
        # Enforce limits
        self._enforce_limits()

        # Create checkpoint ID
        cp_id = str(uuid.uuid4())[:8]
        now = datetime.now()

        # Snapshot files if specified
        files_dict: dict[str, str] = {}
        if files:
            working_dir = Path(context.get("working_dir", ".") if context else ".")
            for file_path in files:
                full_path = working_dir / file_path
                if full_path.exists():
                    try:
                        content = full_path.read_text(encoding="utf-8")
                        content_hash = self._storage.save_file(cp_id, file_path, content)
                        files_dict[file_path] = content_hash
                    except (OSError, UnicodeDecodeError):
                        # Skip files that can't be read
                        pass

        # Create metadata
        metadata = CheckpointMetadata(
            id=cp_id,
            name=name,
            description=description,
            created_at=now,
            status=CheckpointStatus.CREATED,
            tags=tags or [],
        )

        # Create checkpoint data
        checkpoint = CheckpointData(
            metadata=metadata,
            conversation_id=conversation_id,
            files=files_dict,
            context=context or {},
        )

        # Update size
        checkpoint.metadata.size = self._storage.get_size(cp_id)

        # Save to storage
        self._storage.save(checkpoint)

        return checkpoint

    def restore_checkpoint(
        self,
        checkpoint_id: str,
        restore_files: bool = False,
        working_dir: str | Path = ".",
    ) -> CheckpointData | None:
        """Restore a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID
            restore_files: Whether to restore file snapshots
            working_dir: Working directory for file restoration

        Returns:
            Restored checkpoint data or None if not found
        """
        checkpoint = self._storage.load(checkpoint_id)
        if not checkpoint:
            return None

        # Restore files if requested
        if restore_files and checkpoint.files:
            working_path = Path(working_dir)
            for file_path, _ in checkpoint.files.items():
                content = self._storage.load_file(checkpoint_id, file_path)
                if content is not None:
                    full_path = working_path / file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")

        # Update status
        checkpoint.metadata.status = CheckpointStatus.RESTORED
        self._storage.save(checkpoint)

        return checkpoint

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            True if deleted
        """
        return self._storage.delete(checkpoint_id)

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointData | None:
        """Get a checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Checkpoint data or None if not found
        """
        return self._storage.load(checkpoint_id)

    def list_checkpoints(
        self,
        tag: str | None = None,
        limit: int = 50,
    ) -> list[CheckpointMetadata]:
        """List all checkpoints.

        Args:
            tag: Optional tag filter
            limit: Maximum number to return

        Returns:
            List of checkpoint metadata
        """
        all_checkpoints = self._storage.list_all()

        # Filter by tag
        if tag:
            all_checkpoints = [cp for cp in all_checkpoints if tag in (cp.tags or [])]

        return all_checkpoints[:limit]

    def search_checkpoints(
        self,
        query: str,
        limit: int = 10,
    ) -> list[CheckpointMetadata]:
        """Search checkpoints by name or description.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching checkpoints
        """
        query_lower = query.lower()
        results = []

        for cp in self._storage.list_all():
            if query_lower in cp.name.lower() or query_lower in cp.description.lower():
                results.append(cp)
                if len(results) >= limit:
                    break

        return results

    def clear_old_checkpoints(self, days: int | None = None) -> int:
        """Clear checkpoints older than specified days.

        Args:
            days: Days threshold (defaults to max_age_days)

        Returns:
            Number of checkpoints deleted
        """
        if days is None:
            days = self._max_age_days

        cutoff = datetime.now() - timedelta(days=days)
        deleted = 0

        for cp in self._storage.list_all():
            if cp.created_at < cutoff and self._storage.delete(cp.id):
                deleted += 1

        return deleted

    def get_stats(self) -> dict[str, Any]:
        """Get checkpoint statistics.

        Returns:
            Dictionary with statistics
        """
        checkpoints = self._storage.list_all()

        total_size = sum(self._storage.get_size(cp.id) for cp in checkpoints)

        # Count by status
        by_status: dict[str, int] = {}
        for cp in checkpoints:
            status = cp.status.value
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total_checkpoints": len(checkpoints),
            "total_size_bytes": total_size,
            "by_status": by_status,
            "storage_dir": str(self._storage.storage_dir),
        }

    def _enforce_limits(self) -> None:
        """Enforce maximum checkpoints limit.

        Deletes oldest checkpoints to make room for new ones.
        Ensures that after creating a new checkpoint, total will be <= max.
        """
        checkpoints = self._storage.list_all()

        # We need to delete enough so that after adding the new one,
        # we're at max_checkpoints. So we keep max-1 and delete the rest.
        if len(checkpoints) >= self._max_checkpoints:
            # Delete oldest checkpoints (keep newest max-1)
            for cp in checkpoints[: -(self._max_checkpoints - 1)]:
                self._storage.delete(cp.id)

    def update_checkpoint(
        self,
        checkpoint_id: str,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> CheckpointData | None:
        """Update checkpoint metadata.

        Args:
            checkpoint_id: Checkpoint ID
            name: New name (None to keep existing)
            description: New description (None to keep existing)
            tags: New tags (None to keep existing)

        Returns:
            Updated checkpoint or None if not found
        """
        checkpoint = self._storage.load(checkpoint_id)
        if not checkpoint:
            return None

        if name is not None:
            checkpoint.metadata.name = name
        if description is not None:
            checkpoint.metadata.description = description
        if tags is not None:
            checkpoint.metadata.tags = tags

        self._storage.save(checkpoint)
        return checkpoint

    def add_file_to_checkpoint(
        self,
        checkpoint_id: str,
        file_path: str,
        working_dir: str | Path = ".",
    ) -> bool:
        """Add a file snapshot to an existing checkpoint.

        Args:
            checkpoint_id: Checkpoint ID
            file_path: Path to file (relative to working_dir)
            working_dir: Working directory

        Returns:
            True if file was added
        """
        checkpoint = self._storage.load(checkpoint_id)
        if checkpoint is None:
            return False

        full_path = Path(working_dir) / file_path
        if not full_path.exists():
            return False

        try:
            content = full_path.read_text(encoding="utf-8")
            content_hash = self._storage.save_file(checkpoint_id, file_path, content)
            checkpoint.files[file_path] = content_hash
            self._storage.save(checkpoint)
            return True
        except (OSError, UnicodeDecodeError):
            return False
