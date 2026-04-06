"""Team monitor for tracking worker progress."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from vibesop.core.team.worker import WorkerState, WorkerStatus


@dataclass
class MonitorReport:
    """Current status of the team."""

    team_name: str
    total_workers: int
    completed: int
    failed: int
    working: int
    stalled: int
    idle: int
    worker_details: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_complete(self) -> bool:
        return self.completed + self.failed == self.total_workers

    @property
    def progress_pct(self) -> float:
        if self.total_workers == 0:
            return 0.0
        return (self.completed + self.failed) / self.total_workers * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_name": self.team_name,
            "total_workers": self.total_workers,
            "completed": self.completed,
            "failed": self.failed,
            "working": self.working,
            "stalled": self.stalled,
            "idle": self.idle,
            "progress_pct": round(self.progress_pct, 1),
            "is_complete": self.is_complete,
            "timestamp": self.timestamp,
            "worker_details": self.worker_details,
        }


class TeamMonitor:
    """Monitor team worker progress."""

    def __init__(self, team_dir: str | Path, team_name: str, stall_threshold_seconds: int = 300):
        self.team_dir = Path(team_dir)
        self.team_name = team_name
        self.stall_threshold_seconds = stall_threshold_seconds

    def get_report(self) -> MonitorReport:
        """Generate current team status report."""
        workers_dir = self.team_dir / "workers"
        if not workers_dir.exists():
            return MonitorReport(
                team_name=self.team_name,
                total_workers=0,
                completed=0,
                failed=0,
                working=0,
                stalled=0,
                idle=0,
            )

        workers = []
        completed = failed = working = stalled = idle = 0

        for worker_dir in workers_dir.iterdir():
            if not worker_dir.is_dir():
                continue
            state_file = worker_dir / "state.json"
            if not state_file.exists():
                continue

            with state_file.open("r") as f:
                state = WorkerState.from_dict(json.load(f))

            # Check for stalled workers
            if state.status == WorkerStatus.WORKING and state.started_at:
                started = datetime.fromisoformat(state.started_at)
                elapsed = (datetime.now() - started).total_seconds()
                if elapsed > self.stall_threshold_seconds:
                    state.status = WorkerStatus.STALLED

            workers.append(state.to_dict())

            if state.status == WorkerStatus.COMPLETED:
                completed += 1
            elif state.status == WorkerStatus.FAILED:
                failed += 1
            elif state.status == WorkerStatus.WORKING:
                working += 1
            elif state.status == WorkerStatus.STALLED:
                stalled += 1
            else:
                idle += 1

        return MonitorReport(
            team_name=self.team_name,
            total_workers=len(workers),
            completed=completed,
            failed=failed,
            working=working,
            stalled=stalled,
            idle=idle,
            worker_details=workers,
        )
