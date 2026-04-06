"""Ultrawork — Tier-aware parallel execution engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class TaskTier(str, Enum):
    LOW = "low"
    STANDARD = "standard"
    THOROUGH = "thorough"


@dataclass
class UltraworkTask:
    """A single task for ultrawork."""

    task_id: str
    description: str
    tier: TaskTier = TaskTier.STANDARD
    result: dict[str, Any] | None = None
    error: str | None = None
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "tier": self.tier.value,
            "result": self.result,
            "error": self.error,
            "status": self.status,
        }


@dataclass
class UltraworkResult:
    """Result of an ultrawork session."""

    session_id: str
    tasks: list[UltraworkTask] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None

    @property
    def total(self) -> int:
        return len(self.tasks)

    @property
    def completed(self) -> int:
        return sum(1 for t in self.tasks if t.status == "completed")

    @property
    def failed(self) -> int:
        return sum(1 for t in self.tasks if t.status == "failed")

    @property
    def success(self) -> bool:
        return self.failed == 0

    @property
    def tier_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {"low": 0, "standard": 0, "thorough": 0}
        for t in self.tasks:
            counts[t.tier.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "total_tasks": self.total,
            "tiers": self.tier_counts,
            "completed": self.completed,
            "failed": self.failed,
            "success": self.success,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    def save(self, output_dir: str | Path) -> Path:
        """Save result to file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"ultrawork_{self.session_id}.json"
        with filepath.open("w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return filepath


class UltraworkEngine:
    """Ultrawork execution engine."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.result = UltraworkResult(session_id=session_id)

    def add_task(self, task_id: str, description: str, tier: TaskTier = TaskTier.STANDARD) -> None:
        """Add a task to the session."""
        self.result.tasks.append(
            UltraworkTask(
                task_id=task_id,
                description=description,
                tier=tier,
            )
        )

    def complete_task(self, task_id: str, result: dict[str, Any]) -> None:
        """Mark a task as completed."""
        for task in self.result.tasks:
            if task.task_id == task_id:
                task.status = "completed"
                task.result = result
                break

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        for task in self.result.tasks:
            if task.task_id == task_id:
                task.status = "failed"
                task.error = error
                break

    def finalize(self) -> UltraworkResult:
        """Finalize the session."""
        self.result.completed_at = datetime.now().isoformat()
        return self.result
