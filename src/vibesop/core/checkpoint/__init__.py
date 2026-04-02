"""VibeSOP Checkpoint System.

This module provides work state checkpointing:
- Checkpoint data classes and metadata
- Persistent storage backend
- High-level checkpoint management API

Usage:
    from vibesop.core.checkpoint import CheckpointManager

    manager = CheckpointManager()
    cp = manager.create_checkpoint("Work Session 1", "Progress so far")
    restored = manager.restore_checkpoint(cp.id, restore_files=True)
"""

from vibesop.core.checkpoint.base import CheckpointData, CheckpointMetadata, CheckpointStatus
from vibesop.core.checkpoint.manager import CheckpointManager
from vibesop.core.checkpoint.storage import CheckpointStorage

__all__ = [
    "CheckpointData",
    "CheckpointManager",
    "CheckpointMetadata",
    "CheckpointStatus",
    "CheckpointStorage",
]
