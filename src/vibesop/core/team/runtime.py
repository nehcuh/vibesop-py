"""Team runtime — asyncio-based multi-agent execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from vibesop.core.state.manager import StateManager
from vibesop.core.team.mailbox import Mailbox, Message
from vibesop.core.team.monitor import MonitorReport, TeamMonitor
from vibesop.core.team.worker import WorkerState, WorkerStatus


@dataclass
class TeamConfig:
    """Configuration for a team run."""

    team_name: str
    tasks: list[dict[str, Any]]
    state_dir: str = ".vibe/state/team"
    context_snapshot_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_name": self.team_name,
            "task_count": len(self.tasks),
            "context_snapshot_path": self.context_snapshot_path,
        }


@dataclass
class TeamResult:
    """Result of a team run."""

    team_name: str
    completed: int
    failed: int
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_name": self.team_name,
            "completed": self.completed,
            "failed": self.failed,
            "success": self.success,
            "duration_seconds": round(self.duration_seconds, 2),
            "results": self.results,
            "errors": self.errors,
        }


class TeamRuntime:
    """Team runtime manager."""

    def __init__(self, state_manager: StateManager | None = None):
        self.state_manager = state_manager or StateManager()

    def create_team(self, config: TeamConfig) -> Path:
        """Create team directory structure."""
        team_dir = Path(config.state_dir) / config.team_name
        team_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (team_dir / "mailbox").mkdir(exist_ok=True)
        (team_dir / "workers").mkdir(exist_ok=True)

        # Save config
        config_file = team_dir / "config.json"
        with config_file.open("w") as f:
            json.dump(config.to_dict(), f, indent=2)

        # Initialize workers
        for i, task in enumerate(config.tasks):
            worker_id = f"worker-{i + 1}"
            worker_state = WorkerState(worker_id=worker_id)
            worker_state.mark_working(task.get("description", f"Task {i + 1}"))
            worker_state.save(team_dir / "workers")

            # Send task to mailbox
            mailbox = Mailbox(team_dir / "mailbox")
            mailbox.send(
                Message(
                    sender="coordinator",
                    recipient=worker_id,
                    content=json.dumps(task),
                )
            )

        # Save team state
        self.state_manager.write(
            "team",
            config.team_name,
            {
                "team_name": config.team_name,
                "task_count": len(config.tasks),
                "status": "running",
                "created_at": datetime.now().isoformat(),
            },
        )

        return team_dir

    def get_status(self, team_name: str, state_dir: str = ".vibe/state/team") -> MonitorReport:
        """Get current team status."""
        team_dir = Path(state_dir) / team_name
        monitor = TeamMonitor(team_dir, team_name)
        return monitor.get_report()

    def complete_team(self, team_name: str, result: TeamResult) -> None:
        """Mark team run as complete."""
        self.state_manager.write(
            "team",
            team_name,
            {
                "team_name": team_name,
                "status": "completed" if result.success else "failed",
                "completed": result.completed,
                "failed": result.failed,
                "duration_seconds": result.duration_seconds,
                "completed_at": datetime.now().isoformat(),
            },
        )
