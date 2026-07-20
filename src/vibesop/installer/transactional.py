"""Transactional installation with rollback support."""

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class InstallationStep:
    name: str
    execute: Callable[[], dict[str, Any]]
    rollback: Callable[[], dict[str, Any]] | None
    completed: bool = False
    rollback_completed: bool = False


@dataclass
class TransactionResult:
    success: bool
    completed_steps: list[str]
    failed_at: str | None
    rollback_completed: bool
    error: str | None
    snapshot_id: str | None = None


class TransactionalInstaller:
    """Installer with transaction support and automatic rollback."""

    def __init__(
        self,
        snapshot_dir: Path | None = None,
        auto_rollback: bool = True,
    ) -> None:
        self._snapshot_dir = snapshot_dir or Path.cwd() / ".vibe" / "snapshots"
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._auto_rollback = auto_rollback
        self._steps: list[InstallationStep] = []
        self._snapshot_id: str | None = None

    def add_step(
        self,
        name: str,
        execute: Callable[[], dict[str, Any]],
        rollback: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._steps.append(InstallationStep(name=name, execute=execute, rollback=rollback))

    def execute(self) -> TransactionResult:
        completed_steps: list[str] = []
        failed_at: str | None = None
        error: str | None = None

        self._snapshot_id = self._create_snapshot()

        try:
            for step in self._steps:
                result = step.execute()
                if not result.get("success", False):
                    failed_at = step.name
                    error = result.get("error", "Step failed")
                    break
                step.completed = True
                completed_steps.append(step.name)

        except Exception as e:
            error = str(e)

        rollback_completed = False
        if (failed_at or error) and self._auto_rollback:
            rb = self._rollback(completed_steps)
            rollback_completed = rb.get("success", False)

        return TransactionResult(
            success=not failed_at and not error,
            completed_steps=completed_steps,
            failed_at=failed_at,
            rollback_completed=rollback_completed,
            error=error,
            snapshot_id=self._snapshot_id,
        )

    def rollback(self) -> dict[str, Any]:
        if not self._snapshot_id:
            return {"success": False, "error": "No snapshot to restore"}
        return self._rollback([s.name for s in self._steps if s.completed])

    def _rollback(self, completed_steps: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = {"success": True, "errors": []}

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

        if self._snapshot_id:
            try:
                self._restore_snapshot(self._snapshot_id)
            except Exception as e:
                result["success"] = False
                result["errors"].append(f"Snapshot restore failed: {e}")

        return result

    def _create_snapshot(self) -> str:
        snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_path = self._snapshot_dir / snapshot_id
        snapshot_path.mkdir(exist_ok=True)

        metadata = {
            "snapshot_id": snapshot_id,
            "created_at": datetime.now().isoformat(),
            "steps": [s.name for s in self._steps],
        }

        with (snapshot_path / "metadata.json").open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return snapshot_id

    def _restore_snapshot(self, snapshot_id: str) -> None:
        """Restore files from a snapshot (must be overridden by subclasses)."""
        raise NotImplementedError(
            "Subclasses must implement _restore_snapshot. "
            "Use FileTransactionalInstaller for file-based snapshots."
        )

    def cleanup_snapshot(self, snapshot_id: str | None = None) -> None:
        target_id = snapshot_id or self._snapshot_id
        if not target_id:
            return
        snapshot_path = self._snapshot_dir / target_id
        if snapshot_path.exists():
            shutil.rmtree(snapshot_path)

    def cleanup_old_snapshots(self, days: int = 7) -> dict[str, int]:
        if not self._snapshot_dir.exists():
            return {"kept": 0, "removed": 0}

        cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = cutoff.replace(day=cutoff.day - days)

        kept = 0
        removed = 0

        for entry in self._snapshot_dir.iterdir():
            if not entry.is_dir():
                continue
            try:
                snapshot_date = datetime.strptime(entry.name, "%Y%m%d_%H%M%S")
                if snapshot_date < cutoff:
                    shutil.rmtree(entry)
                    removed += 1
                else:
                    kept += 1
            except ValueError:
                kept += 1

        return {"kept": kept, "removed": removed}


class FileTransactionalInstaller(TransactionalInstaller):
    """Transactional installer that tracks and restores file changes."""

    def __init__(
        self,
        snapshot_dir: Path | None = None,
        auto_rollback: bool = True,
        base_dir: Path | None = None,
    ) -> None:
        super().__init__(snapshot_dir, auto_rollback)
        self._base_dir = base_dir or Path.cwd()
        self._tracked_files: dict[str, bytes] = {}

    def track_file(self, path: Path) -> None:
        path = Path(path)
        key = str(path.relative_to(self._base_dir))
        if path.exists() and key not in self._tracked_files:
            self._tracked_files[key] = path.read_bytes()

    def _create_snapshot(self) -> str:
        snapshot_id = super()._create_snapshot()
        snapshot_path = self._snapshot_dir / snapshot_id

        files_dir = snapshot_path / "files"
        files_dir.mkdir(exist_ok=True)

        for key, content in self._tracked_files.items():
            file_path = files_dir / key
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

        with (files_dir / "files.json").open("w", encoding="utf-8") as f:
            json.dump(list(self._tracked_files.keys()), f, indent=2)

        return snapshot_id

    def _restore_snapshot(self, snapshot_id: str) -> None:
        snapshot_path = self._snapshot_dir / snapshot_id
        files_dir = snapshot_path / "files"
        files_list = files_dir / "files.json"

        if not files_list.exists():
            return

        with files_list.open(encoding="utf-8") as f:
            tracked_files = json.load(f)

        for key in tracked_files:
            snapshot_file = files_dir / key
            original_path = self._base_dir / key

            if snapshot_file.exists():
                original_path.parent.mkdir(parents=True, exist_ok=True)
                original_path.write_bytes(snapshot_file.read_bytes())


def execute_transaction(
    steps: list[tuple[str, Callable[[], dict[str, Any]], Callable[[], dict[str, Any]] | None]],
    auto_rollback: bool = True,
) -> TransactionResult:
    """Execute a transaction with given steps."""
    installer = TransactionalInstaller(auto_rollback=auto_rollback)
    for name, execute, rollback in steps:
        installer.add_step(name, execute, rollback)
    return installer.execute()
