"""Autopilot — Full autonomous lifecycle pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class AutopilotPhase(StrEnum):
    CLARIFY = "clarify"
    PLAN = "plan"
    GATE = "gate"
    EXECUTE = "execute"
    VERIFY = "verify"
    SHIP = "ship"


@dataclass
class PhaseStatus:
    """Status of a single phase."""

    status: str = "pending"
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, **self.detail}


@dataclass
class AutopilotState:
    """Complete state of an autopilot session."""

    session_id: str
    current_phase: AutopilotPhase = AutopilotPhase.CLARIFY
    phases: dict[str, PhaseStatus] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.phases:
            for phase in AutopilotPhase:
                self.phases[phase.value] = PhaseStatus()

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    @property
    def is_successful(self) -> bool:
        if not self.is_complete:
            return False
        return all(p.status in ("completed", "skipped") for p in self.phases.values())

    def mark_phase_running(self, phase: AutopilotPhase) -> None:
        self.current_phase = phase
        self.phases[phase.value].status = "running"

    def mark_phase_completed(
        self, phase: AutopilotPhase, detail: dict[str, Any] | None = None
    ) -> None:
        self.phases[phase.value].status = "completed"
        if detail:
            self.phases[phase.value].detail.update(detail)
        phases = list(AutopilotPhase)
        idx = phases.index(phase)
        if idx + 1 < len(phases):
            self.current_phase = phases[idx + 1]

    def mark_phase_failed(self, phase: AutopilotPhase, error: str) -> None:
        self.phases[phase.value].status = "failed"
        self.phases[phase.value].detail["error"] = error
        self.error = error
        self.completed_at = datetime.now().isoformat()

    def complete_session(self) -> None:
        """Mark the entire session as complete."""
        self.completed_at = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "current_phase": self.current_phase.value,
            "phases": {k: v.to_dict() for k, v in self.phases.items()},
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "is_complete": self.is_complete,
            "is_successful": self.is_successful,
            "error": self.error,
        }

    def save(self, output_dir: str | Path) -> Path:
        """Save state to file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"autopilot_{self.session_id}.json"
        with filepath.open("w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return filepath


class AutopilotPipeline:
    """Autopilot pipeline manager."""

    def __init__(self, session_id: str, state_dir: str = ".vibe/state/sessions") -> None:
        self.session_id = session_id
        self.state_dir = Path(state_dir) / session_id
        self.state = AutopilotState(session_id=session_id)

    def start(self) -> AutopilotState:
        """Start the autopilot session."""
        self.state.mark_phase_running(AutopilotPhase.CLARIFY)
        self._save()
        return self.state

    def advance_phase(
        self, phase: AutopilotPhase, detail: dict[str, Any] | None = None
    ) -> AutopilotState:
        """Mark current phase complete and advance to next."""
        self.state.mark_phase_completed(phase, detail)
        self._save()
        return self.state

    def fail(self, phase: AutopilotPhase, error: str) -> AutopilotState:
        """Mark session as failed."""
        self.state.mark_phase_failed(phase, error)
        self._save()
        return self.state

    def complete(self) -> AutopilotState:
        """Mark session as successfully complete."""
        self.state.complete_session()
        self._save()
        return self.state

    def _save(self) -> None:
        """Persist state to file."""
        self.state.save(self.state_dir)
