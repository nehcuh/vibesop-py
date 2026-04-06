"""Worker protocol for team runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class WorkerStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    STALLED = "stalled"


@dataclass
class WorkerState:
    """State of a single worker."""

    worker_id: str
    status: WorkerStatus = WorkerStatus.IDLE
    task: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    progress_updates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "status": self.status.value,
            "task": self.task,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "progress_updates": self.progress_updates,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkerState:
        data["status"] = WorkerStatus(data["status"])
        return cls(**data)

    def save(self, workers_dir: str | Path) -> Path:
        """Save worker state to file."""
        worker_dir = Path(workers_dir) / self.worker_id
        worker_dir.mkdir(parents=True, exist_ok=True)
        state_file = worker_dir / "state.json"
        with state_file.open("w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return state_file

    def save_result(self, workers_dir: str | Path) -> Path:
        """Save worker result."""
        worker_dir = Path(workers_dir) / self.worker_id
        worker_dir.mkdir(parents=True, exist_ok=True)
        result_file = worker_dir / "result.json"
        with result_file.open("w") as f:
            json.dump(self.result or {}, f, indent=2)
        return result_file

    def mark_working(self, task: str) -> None:
        self.status = WorkerStatus.WORKING
        self.task = task
        self.started_at = datetime.now().isoformat()

    def mark_completed(self, result: dict[str, Any]) -> None:
        self.status = WorkerStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now().isoformat()

    def mark_failed(self, error: str) -> None:
        self.status = WorkerStatus.FAILED
        self.error = error
        self.completed_at = datetime.now().isoformat()

    def add_progress(self, message: str) -> None:
        self.progress_updates.append(
            {
                "timestamp": datetime.now().isoformat(),
                "message": message,
            }
        )


class Worker:
    """Worker agent for team runtime."""

    def __init__(self, worker_id: str, workers_dir: str | Path):
        self.worker_id = worker_id
        self.workers_dir = Path(workers_dir)
        self.state = WorkerState(worker_id=worker_id)

    def load_state(self) -> None:
        """Load worker state from file."""
        state_file = self.workers_dir / self.worker_id / "state.json"
        if state_file.exists():
            with state_file.open("r") as f:
                self.state = WorkerState.from_dict(json.load(f))

    def save_state(self) -> Path:
        """Save worker state to file."""
        return self.state.save(self.workers_dir)
