"""Orchestration callbacks for streaming execution progress.

Provides a protocol for consumers to receive real-time updates
during the orchestration pipeline: intent detection, decomposition,
plan building, and step execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan, ExecutionStep


class OrchestrationPhase(StrEnum):
    """Phases in the orchestration pipeline."""

    ROUTING = "routing"  # Single-skill routing (fast path)
    DETECTION = "detection"  # Multi-intent detection
    DECOMPOSITION = "decomposition"  # Task decomposition
    PLAN_BUILDING = "plan_building"  # Execution plan construction
    EXECUTION = "execution"  # Step execution (if applicable)
    COMPLETE = "complete"  # Orchestration finished


class ErrorPolicy(StrEnum):
    """How to handle errors during orchestration."""

    SKIP = "skip"  # Skip failed step, continue with others
    RETRY = "retry"  # Retry failed step (with backoff)
    ABORT = "abort"  # Stop entire orchestration


@dataclass
class PhaseInfo:
    """Information about the current orchestration phase."""

    phase: OrchestrationPhase
    message: str
    progress: float  # 0.0 to 1.0
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


@dataclass
class StepResult:
    """Result of a single step execution."""

    step: ExecutionStep
    success: bool
    output: str | None = None
    error: str | None = None
    duration_ms: float = 0.0


class OrchestrationCallbacks(Protocol):
    """Protocol for orchestration progress callbacks.

    Implement this protocol to receive real-time updates during
    the orchestration pipeline. All methods are optional — the
    default implementation is a no-op.

    Example:
        >>> class MyCallbacks:
        ...     def on_phase_start(self, info: PhaseInfo) -> None:
        ...         print(f"Starting: {info.message}")
        ...     def on_phase_complete(self, info: PhaseInfo) -> None:
        ...         print(f"Done: {info.message}")
    """

    def on_phase_start(self, info: PhaseInfo) -> None:
        """Called when a new phase begins."""
        ...

    def on_phase_complete(self, info: PhaseInfo) -> None:
        """Called when a phase completes successfully."""
        ...

    def on_phase_error(
        self,
        info: PhaseInfo,
        error: Exception,
        policy: ErrorPolicy,
    ) -> ErrorPolicy:
        """Called when a phase encounters an error.

        Returns the error policy to apply (may override default).
        """
        ...

    def on_plan_ready(self, plan: ExecutionPlan) -> None:
        """Called when the execution plan is fully built."""
        ...


class NoOpCallbacks:
    """Default no-op implementation of OrchestrationCallbacks."""

    def on_phase_start(self, info: PhaseInfo) -> None:
        pass

    def on_phase_complete(self, info: PhaseInfo) -> None:
        pass

    def on_phase_error(
        self,
        _info: PhaseInfo,
        _error: Exception,
        policy: ErrorPolicy,
    ) -> ErrorPolicy:
        return policy

    def on_plan_ready(self, plan: ExecutionPlan) -> None:
        pass
