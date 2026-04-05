"""Pydantic state models for all VibeSOP modes."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StateEntry(BaseModel):
    """Base state entry for any mode."""

    mode: str = Field(..., min_length=1, description="Mode name")
    scope: str = Field(..., min_length=1, description="Scope identifier")
    active: bool = Field(default=True, description="Whether state is active")
    current_phase: str = Field(default="initializing", description="Current phase")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    data: dict[str, Any] = Field(default_factory=dict, description="Mode-specific state data")

    def update(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = datetime.now()


class RalphState(StateEntry):
    mode: str = Field(default="ralph")
    iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=10, ge=1)
    context_snapshot_path: str | None = None
    linked_ultrawork: bool = False
    linked_ecomode: bool = False


class TeamState(StateEntry):
    mode: str = Field(default="team")
    team_name: str = Field(default="", min_length=1)
    worker_count: int = Field(default=0, ge=0)
    pending_tasks: int = Field(default=0, ge=0)
    completed_tasks: int = Field(default=0, ge=0)
    failed_tasks: int = Field(default=0, ge=0)


class InterviewState(StateEntry):
    mode: str = Field(default="deep-interview")
    profile: str = Field(default="standard")
    threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    current_ambiguity: float = Field(default=1.0, ge=0.0, le=1.0)
    round_number: int = Field(default=0, ge=0)
    max_rounds: int = Field(default=12, ge=1)


class SessionState(StateEntry):
    mode: str = Field(default="session")
    session_id: str = Field(default="", min_length=1)
    active_modes: list[str] = Field(default_factory=list)


STATE_MODELS: dict[str, type[StateEntry]] = {
    "ralph": RalphState,
    "team": TeamState,
    "deep-interview": InterviewState,
    "session": SessionState,
}
