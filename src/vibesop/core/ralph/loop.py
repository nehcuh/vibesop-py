"""Main ralph persistent completion loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vibesop.core.ralph.deslop import SlopReport, scan_files
from vibesop.core.ralph.verifier import (
    VerificationResult,
    VerificationTier,
    determine_tier,
    run_verification,
)
from vibesop.core.state.manager import StateManager


@dataclass
class RalphIteration:
    """State for a single ralph iteration."""

    iteration: int
    phase: str  # review, delegate, verify, deslop, reverify
    verification: VerificationResult | None = None
    deslop_report: list[SlopReport] | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class RalphLoopState:
    """Complete state for ralph loop."""

    max_iterations: int = 10
    current_iteration: int = 0
    context_snapshot_path: str | None = None
    iterations: list[RalphIteration] = field(default_factory=list)
    approved: bool = False
    rejected: bool = False

    @property
    def is_complete(self) -> bool:
        return self.approved or self.rejected or self.current_iteration >= self.max_iterations

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_iterations": self.max_iterations,
            "current_iteration": self.current_iteration,
            "context_snapshot_path": self.context_snapshot_path,
            "approved": self.approved,
            "rejected": self.rejected,
            "is_complete": self.is_complete,
        }


class RalphLoop:
    """Ralph persistent completion loop manager."""

    def __init__(
        self,
        max_iterations: int = 10,
        state_manager: StateManager | None = None,
        project_root: str = ".",
    ):
        self.max_iterations = max_iterations
        self.state_manager = state_manager or StateManager()
        self.project_root = project_root
        self.loop_state = RalphLoopState(max_iterations=max_iterations)

    def start(self, context_snapshot_path: str | None = None) -> RalphLoopState:
        """Start the ralph loop."""
        self.loop_state.context_snapshot_path = context_snapshot_path
        self._save_state()
        return self.loop_state

    def next_iteration(self) -> RalphIteration:
        """Advance to next iteration."""
        self.loop_state.current_iteration += 1
        iteration = RalphIteration(
            iteration=self.loop_state.current_iteration,
            phase="review",
        )
        self.loop_state.iterations.append(iteration)
        self._save_state()
        return iteration

    def run_verification_step(self, lines_changed: int) -> VerificationResult:
        """Run verification at the appropriate tier."""
        tier = determine_tier(lines_changed)
        result = run_verification(tier, self.project_root)

        if self.loop_state.iterations:
            self.loop_state.iterations[-1].verification = result
            self.loop_state.iterations[-1].phase = "verify"

        self._save_state()
        return result

    def run_deslop_step(self, changed_files: list[str]) -> list[SlopReport]:
        """Run deslop pass on changed files."""
        reports = scan_files(changed_files)

        if self.loop_state.iterations:
            self.loop_state.iterations[-1].deslop_report = reports
            self.loop_state.iterations[-1].phase = "deslop"

        self._save_state()
        return reports

    def approve(self) -> None:
        """Mark loop as approved."""
        self.loop_state.approved = True
        self._save_state()

    def reject(self, reason: str) -> None:
        """Mark loop as rejected with reason."""
        self.loop_state.rejected = True
        if self.loop_state.iterations:
            self.loop_state.iterations[-1].errors.append(reason)
        self._save_state()

    def _save_state(self) -> None:
        """Persist state to .vibe/state/ralph/."""
        self.state_manager.write("ralph", "default", self.loop_state.to_dict())
