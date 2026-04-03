"""Transactional installation with rollback support.

This module provides transaction-based installation that can
be rolled back if any step fails, ensuring the system remains
in a consistent state.
"""

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable


@dataclass
class InstallationStep:
    """A single installation step.

    Attributes:
        name: Step name for identification
        execute: Function to execute the step
        rollback: Function to rollback the step
        completed: Whether the step completed successfully
        rollback_completed: Whether rollback was executed
    """

    name: str
    execute: Callable[[], Dict[str, Any]]
    rollback: Optional[Callable[[], Dict[str, Any]]]
    completed: bool = False
    rollback_completed: bool = False


@dataclass
class TransactionResult:
    """Result of a transaction.

    Attributes:
        success: Whether the transaction succeeded
        completed_steps: Names of steps that completed
        failed_at: Name of step that failed (if any)
        rollback_completed: Whether rollback was completed
        error: Error message if failed
        snapshot_id: ID of installation snapshot
    """

    success: bool
    completed_steps: List[str]
    failed_at: Optional[str]
    rollback_completed: bool
    error: Optional[str]
    snapshot_id: Optional[str] = None


class TransactionalInstaller:
    """Installer with transaction support and rollback capability.

    Installation happens in phases:
    1. Snapshot - Save current state
    2. Execute - Run installation steps
    3. Verify - Verify installation
    4. Commit - Finalize or rollback on failure

    Example:
        >>> installer = TransactionalInstaller()
        >>> installer.add_step("Download files", download_fn, rollback_fn)
        >>> installer.add_step("Install hooks", install_fn, rollback_fn)
        >>> result = installer.execute()
        >>> if not result.success:
        ...     # Automatic rollback occurred
        ...     print(f"Failed at: {result.failed_at}")
    """

    def __init__(
        self,
        snapshot_dir: Optional[Path] = None,
        auto_rollback: bool = True,
    ) -> None:
        """Initialize the transactional installer.

        Args:
            snapshot_dir: Directory for storing snapshots
            auto_rollback: Whether to automatically rollback on failure
        """
        self._snapshot_dir = snapshot_dir or Path.cwd() / ".vibe" / "snapshots"
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)

        self._auto_rollback = auto_rollback
        self._steps: List[InstallationStep] = []
        self._snapshot_id: Optional[str] = None

    def add_step(
        self,
        name: str,
        execute: Callable[[], Dict[str, Any]],
        rollback: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        """Add an installation step.

        Args:
            name: Step name for identification
            execute: Function to execute the step
            rollback: Function to rollback the step (optional)

        Example:
            >>> def download() -> dict:
            ...     # Download files
            ...     return {"success": True}
            >>>
            >>> def rollback_download() -> dict:
            ...     # Remove downloaded files
            ...     return {"success": True}
            >>>
            >>> installer.add_step("Download", download, rollback_download)
        """
        step = InstallationStep(
            name=name,
            execute=execute,
            rollback=rollback,
        )
        self._steps.append(step)

    def execute(self) -> TransactionResult:
        """Execute the installation transaction.

        Returns:
            TransactionResult with execution status

        The transaction will:
        1. Create a snapshot before starting
        2. Execute steps in order
        3. Rollback on failure if auto_rollback is enabled
        """
        completed_steps = []
        failed_at = None
        error = None
        rollback_completed = False

        # Create snapshot
        self._snapshot_id = self._create_snapshot()

        try:
            # Execute steps
            for step in self._steps:
                result = step.execute()

                if not result.get("success", False):
                    failed_at = step.name
                    error = result.get("error", "Step failed")
                    break

                step.completed = True
                completed_steps.append(step.name)

            # If all steps succeeded
            if not failed_at:
                return TransactionResult(
                    success=True,
                    completed_steps=completed_steps,
                    failed_at=None,
                    rollback_completed=False,
                    error=None,
                    snapshot_id=self._snapshot_id,
                )

            # Rollback on failure
            if self._auto_rollback:
                rollback_result = self._rollback(completed_steps)
                rollback_completed = rollback_result.get("success", False)

            return TransactionResult(
                success=False,
                completed_steps=completed_steps,
                failed_at=failed_at,
                rollback_completed=rollback_completed,
                error=error,
                snapshot_id=self._snapshot_id,
            )

        except Exception as e:
            error = str(e)
            if self._auto_rollback:
                rollback_result = self._rollback(completed_steps)
                rollback_completed = rollback_result.get("success", False)

            return TransactionResult(
                success=False,
                completed_steps=completed_steps,
                failed_at=failed_at,
                rollback_completed=rollback_completed,
                error=error,
                snapshot_id=self._snapshot_id,
            )

    def rollback(self) -> Dict[str, Any]:
        """Manually rollback the transaction.

        Returns:
            Result dictionary with rollback status
        """
        if not self._snapshot_id:
            return {"success": False, "error": "No snapshot to restore"}

        completed_steps = [s.name for s in self._steps if s.completed]
        return self._rollback(completed_steps)

    def _rollback(self, completed_steps: List[str]) -> Dict[str, Any]:
        """Internal rollback implementation.

        Args:
            completed_steps: List of step names to rollback

        Returns:
            Result dictionary
        """
        result = {
            "success": True,
            "errors": [],
        }

        # Rollback in reverse order
        for step in reversed(self._steps):
            if step.name in completed_steps and step.rollback:
                try:
                    rollback_result = step.rollback()
                    if not rollback_result.get("success", False):
                        result["success"] = False
                        result["errors"].append(
                            f"Rollback failed for {step.name}: "
                            f"{rollback_result.get('error', 'Unknown error')}"
                        )
                    else:
                        step.rollback_completed = True
                except Exception as e:
                    result["success"] = False
                    result["errors"].append(f"Rollback error for {step.name}: {e}")

        # Try to restore snapshot
        if self._snapshot_id:
            try:
                self._restore_snapshot(self._snapshot_id)
            except Exception as e:
                result["success"] = False
                result["errors"].append(f"Snapshot restore failed: {e}")

        return result

    def _create_snapshot(self) -> str:
        """Create a snapshot of current state.

        Returns:
            Snapshot ID
        """
        snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_path = self._snapshot_dir / snapshot_id
        snapshot_path.mkdir(exist_ok=True)

        # Save snapshot metadata
        metadata = {
            "snapshot_id": snapshot_id,
            "created_at": datetime.now().isoformat(),
            "steps": [s.name for s in self._steps],
        }

        metadata_path = snapshot_path / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return snapshot_id

    def _restore_snapshot(self, snapshot_id: str) -> None:
        """Restore from snapshot.

        Args:
            snapshot_id: ID of snapshot to restore

        Note:
            This is a base implementation. Subclasses should
            override to add snapshot-specific restoration logic.
        """
        snapshot_path = self._snapshot_dir / snapshot_id

        if not snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot {snapshot_id} not found")

        # Base implementation - just verify snapshot exists
        # Subclasses should override for actual restoration

    def cleanup_snapshot(self, snapshot_id: Optional[str] = None) -> None:
        """Clean up a snapshot.

        Args:
            snapshot_id: Snapshot ID to cleanup (uses current if None)
        """
        target_id = snapshot_id or self._snapshot_id
        if not target_id:
            return

        snapshot_path = self._snapshot_dir / target_id
        if snapshot_path.exists():
            shutil.rmtree(snapshot_path)


class FileTransactionalInstaller(TransactionalInstaller):
    """Transactional installer that tracks file changes.

    This installer monitors files created/modified during installation
    and can restore them on rollback.
    """

    def __init__(
        self,
        snapshot_dir: Optional[Path] = None,
        auto_rollback: bool = True,
        base_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the file transactional installer.

        Args:
            snapshot_dir: Directory for snapshots
            auto_rollback: Whether to auto-rollback on failure
            base_dir: Base directory to track (default: cwd)
        """
        super().__init__(snapshot_dir, auto_rollback)
        self._base_dir = base_dir or Path.cwd()
        self._tracked_files: Dict[str, bytes] = {}

    def track_file(self, path: Path) -> None:
        """Track a file before modification.

        Args:
            path: File path to track
        """
        path = Path(path)
        key = str(path.relative_to(self._base_dir))

        if path.exists() and key not in self._tracked_files:
            self._tracked_files[key] = path.read_bytes()

    def _create_snapshot(self) -> str:
        """Create snapshot with tracked files."""
        snapshot_id = super()._create_snapshot()
        snapshot_path = self._snapshot_dir / snapshot_id

        # Save tracked files
        files_dir = snapshot_path / "files"
        files_dir.mkdir(exist_ok=True)

        for key, content in self._tracked_files.items():
            file_path = files_dir / key
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

        # Save file list
        with open(files_dir / "files.json", "w", encoding="utf-8") as f:
            json.dump(list(self._tracked_files.keys()), f, indent=2)

        return snapshot_id

    def _restore_snapshot(self, snapshot_id: str) -> None:
        """Restore tracked files from snapshot."""
        snapshot_path = self._snapshot_dir / snapshot_id
        files_dir = snapshot_path / "files"
        files_list = files_dir / "files.json"

        if not files_list.exists():
            return

        with open(files_list, "r", encoding="utf-8") as f:
            tracked_files = json.load(f)

        # Restore each tracked file
        for key in tracked_files:
            snapshot_file = files_dir / key
            original_path = self._base_dir / key

            if snapshot_file.exists():
                original_path.parent.mkdir(parents=True, exist_ok=True)
                original_path.write_bytes(snapshot_file.read_bytes())


# Convenience functions
def execute_transaction(
    steps: List,
    auto_rollback: bool = True,
) -> TransactionResult:
    """Execute a transaction with given steps.

    Args:
        steps: List of (name, execute_fn, rollback_fn) tuples
        auto_rollback: Whether to auto-rollback on failure

    Returns:
        TransactionResult

    Example:
        >>> result = execute_transaction([
        ...     ("Download", download_fn, rollback_download_fn),
        ...     ("Install", install_fn, rollback_install_fn),
        ... ])
        >>> if result.success:
        ...     print("Installation successful!")
    """
    installer = TransactionalInstaller(auto_rollback=auto_rollback)

    for name, execute, rollback in steps:
        installer.add_step(name, execute, rollback)

    return installer.execute()
