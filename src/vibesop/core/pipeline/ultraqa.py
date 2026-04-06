"""UltraQA — Autonomous QA cycling with architect diagnosis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class BugSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    COSMETIC = "cosmetic"


class BugStatus(StrEnum):
    FOUND = "found"
    DIAGNOSED = "diagnosed"
    FIXED = "fixed"
    WONTFIX = "wontfix"


@dataclass
class Bug:
    """A bug found during QA."""

    bug_id: str
    severity: BugSeverity
    description: str
    reproduction_steps: list[str] = field(default_factory=list)
    root_cause: str | None = None
    fix_applied: str | None = None
    status: BugStatus = BugStatus.FOUND
    found_in_cycle: int = 0
    fixed_in_cycle: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bug_id": self.bug_id,
            "severity": self.severity.value,
            "description": self.description,
            "reproduction_steps": self.reproduction_steps,
            "root_cause": self.root_cause,
            "fix_applied": self.fix_applied,
            "status": self.status.value,
            "found_in_cycle": self.found_in_cycle,
            "fixed_in_cycle": self.fixed_in_cycle,
        }


@dataclass
class QACycle:
    """A single QA cycle."""

    cycle_number: int
    bugs_found: list[Bug] = field(default_factory=list)
    bugs_fixed: int = 0
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None

    @property
    def total_bugs(self) -> int:
        return len(self.bugs_found)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_number": self.cycle_number,
            "bugs_found": self.total_bugs,
            "bugs_fixed": self.bugs_fixed,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "bugs": [b.to_dict() for b in self.bugs_found],
        }


@dataclass
class UltraQAState:
    """Complete state of a QA session."""

    session_id: str
    cycles: list[QACycle] = field(default_factory=list)
    max_cycles: int = 5
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None

    @property
    def current_cycle(self) -> int:
        return len(self.cycles)

    @property
    def total_bugs_found(self) -> int:
        return sum(c.total_bugs for c in self.cycles)

    @property
    def total_bugs_fixed(self) -> int:
        return sum(c.bugs_fixed for c in self.cycles)

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    @property
    def should_continue(self) -> bool:
        if self.is_complete:
            return False
        if self.current_cycle >= self.max_cycles:
            return False
        # Stop if no new bugs in last 2 cycles
        if self.current_cycle >= 2:
            last_two = self.cycles[-2:]
            if all(c.total_bugs == 0 for c in last_two):
                return False
        return True

    def start_cycle(self) -> QACycle:
        """Start a new QA cycle."""
        cycle = QACycle(cycle_number=self.current_cycle + 1)
        self.cycles.append(cycle)
        return cycle

    def complete_cycle(self, cycle: QACycle) -> None:
        """Complete the current cycle."""
        cycle.completed_at = datetime.now().isoformat()

    def complete_session(self) -> None:
        """Mark session as complete."""
        self.completed_at = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "cycle": self.current_cycle,
            "max_cycles": self.max_cycles,
            "bugs_found": self.total_bugs_found,
            "bugs_fixed": self.total_bugs_fixed,
            "bugs_remaining": self.total_bugs_found - self.total_bugs_fixed,
            "status": "completed" if self.is_complete else "running",
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "should_continue": self.should_continue,
            "cycles": [c.to_dict() for c in self.cycles],
        }

    def save(self, output_dir: str | Path) -> Path:
        """Save state to file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"ultraqa_{self.session_id}.json"
        with filepath.open("w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return filepath


class UltraQAPipeline:
    """UltraQA pipeline manager."""

    def __init__(
        self,
        session_id: str,
        max_cycles: int = 5,
        state_dir: str = ".vibe/state/sessions",
    ):
        self.session_id = session_id
        self.state_dir = Path(state_dir) / session_id
        self.state = UltraQAState(session_id=session_id, max_cycles=max_cycles)

    def start(self) -> UltraQAState:
        """Start the QA session."""
        self._save()
        return self.state

    def next_cycle(self) -> QACycle:
        """Start the next QA cycle."""
        cycle = self.state.start_cycle()
        self._save()
        return cycle

    def complete_cycle(self, cycle: QACycle) -> UltraQAState:
        """Complete the current cycle."""
        self.state.complete_cycle(cycle)
        self._save()
        return self.state

    def complete(self) -> UltraQAState:
        """Mark session as complete."""
        self.state.complete_session()
        self._save()
        return self.state

    def should_continue(self) -> bool:
        """Check if QA should continue."""
        return self.state.should_continue

    def _save(self) -> None:
        """Persist state to file."""
        self.state.save(self.state_dir)
