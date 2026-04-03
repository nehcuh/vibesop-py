"""
Workflow state management system.

This module provides persistent state storage and management
for workflow execution, enabling recovery and resume capabilities.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime
import json
import uuid

from pydantic import BaseModel, Field

from vibesop.workflow.models import (
    WorkflowDefinition,
    WorkflowResult,
    WorkflowExecutionContext,
)
from vibesop.workflow.exceptions import WorkflowError, WorkflowRecoveryError


class WorkflowState(BaseModel):
    """Persistent state for workflow execution.

    Attributes:
        workflow_id: Unique workflow execution identifier
        workflow_name: Name of the workflow
        workflow_version: Version of the workflow definition
        status: Current execution status
        current_stage: Currently executing stage
        stage_states: State of each stage
        context: Workflow execution context
        result: Final workflow result (if completed)
        started_at: Execution start time
        completed_at: Execution completion time (if completed)
        error: Error message if failed
        metadata: Additional metadata
    """

    workflow_id: str = Field(..., description="Unique workflow execution ID")
    workflow_name: str = Field(..., description="Workflow name")
    workflow_version: str = Field(default="1.0.0", description="Workflow version")
    status: str = Field(default="pending", description="Execution status")
    current_stage: Optional[str] = Field(default=None, description="Current stage")
    stage_states: Dict[str, str] = Field(
        default_factory=dict,
        description="State of each stage"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Workflow execution context"
    )
    result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Final workflow result"
    )
    started_at: datetime = Field(
        default_factory=datetime.now,
        description="Execution start time"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Execution completion time"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    @property
    def is_active(self) -> bool:
        """Check if workflow is currently active."""
        return self.status in ["pending", "running", "in_progress"]

    @property
    def is_completed(self) -> bool:
        """Check if workflow execution is completed."""
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        """Check if workflow execution has failed."""
        return self.status == "failed"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowState":
        """Create from dictionary."""
        return cls(**data)

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class WorkflowStateManager:
    """Manages workflow state persistence and recovery.

    Provides file-based state storage with JSON serialization,
    enabling workflow recovery and resume capabilities.

    Usage:
        >>> manager = WorkflowStateManager(state_dir=Path(".vibe/state/workflows"))
        >>> # Save state
        >>> manager.save_state("workflow-123", workflow, context)
        >>> # Load state
        >>> state = manager.load_state("workflow-123")
        >>> # List active workflows
        >>> active = manager.list_active_workflows()
        >>> # Resume workflow
        >>> result = manager.resume_workflow("workflow-123")
    """

    def __init__(
        self,
        state_dir: Path = Path(".vibe/state/workflows"),
        create_dir: bool = True
    ):
        """Initialize the state manager.

        Args:
            state_dir: Directory for state storage
            create_dir: Whether to create directory if it doesn't exist
        """
        self.state_dir = Path(state_dir)
        if create_dir:
            self.state_dir.mkdir(parents=True, exist_ok=True)

    def generate_workflow_id(self) -> str:
        """Generate a unique workflow ID.

        Returns:
            Unique workflow identifier
        """
        return f"workflow-{uuid.uuid4()}"

    def save_state(
        self,
        workflow_id: str,
        workflow: WorkflowDefinition,
        context: WorkflowExecutionContext,
        result: Optional[WorkflowResult] = None
    ) -> WorkflowState:
        """Save workflow execution state.

        Args:
            workflow_id: Workflow execution identifier
            workflow: Workflow definition
            context: Execution context
            result: Optional workflow result

        Returns:
            Saved workflow state
        """
        # Create or update state
        state = WorkflowState(
            workflow_id=workflow_id,
            workflow_name=workflow.name,
            workflow_version=workflow.version,
            status="running",
            current_stage=context.current_stage,
            stage_states={
                stage.name: stage.status.value
                for stage in workflow.stages
            },
            context=context.model_dump(),
            result=result.model_dump() if result else None,
        )

        # If result is provided, update status
        if result:
            if result.success:
                state.status = "completed"
            else:
                state.status = "failed"
                state.error = "; ".join(result.errors)

        # Save to file
        state_file = self.state_dir / f"{workflow_id}.json"
        self._atomic_write(state_file, state.to_dict())

        return state

    def load_state(self, workflow_id: str) -> Optional[WorkflowState]:
        """Load workflow execution state.

        Args:
            workflow_id: Workflow execution identifier

        Returns:
            WorkflowState if found, None otherwise
        """
        state_file = self.state_dir / f"{workflow_id}.json"

        if not state_file.exists():
            return None

        try:
            data = json.loads(state_file.read_text())
            return WorkflowState.from_dict(data)
        except Exception as e:
            raise WorkflowRecoveryError(
                f"Failed to load state for workflow '{workflow_id}': {e}",
                workflow_id=workflow_id
            )

    def update_stage_state(
        self,
        workflow_id: str,
        stage_name: str,
        stage_status: str
    ) -> None:
        """Update state for a specific stage.

        Args:
            workflow_id: Workflow execution identifier
            stage_name: Stage name
            stage_status: Stage status
        """
        state = self.load_state(workflow_id)
        if not state:
            raise WorkflowRecoveryError(
                f"Cannot update non-existent workflow '{workflow_id}'",
                workflow_id=workflow_id
            )

        state.stage_states[stage_name] = stage_status
        state.current_stage = stage_name

        # Save updated state
        state_file = self.state_dir / f"{workflow_id}.json"
        self._atomic_write(state_file, state.to_dict())

    def complete_workflow(
        self,
        workflow_id: str,
        result: WorkflowResult
    ) -> None:
        """Mark workflow as completed.

        Args:
            workflow_id: Workflow execution identifier
            result: Final workflow result
        """
        state = self.load_state(workflow_id)
        if not state:
            raise WorkflowRecoveryError(
                f"Cannot complete non-existent workflow '{workflow_id}'",
                workflow_id=workflow_id
            )

        state.status = "completed" if result.success else "failed"
        state.completed_at = datetime.now()
        state.result = result.model_dump()
        state.current_stage = None

        # Save final state
        state_file = self.state_dir / f"{workflow_id}.json"
        self._atomic_write(state_file, state.to_dict())

    def list_active_workflows(self) -> list[WorkflowState]:
        """List all active workflow executions.

        Returns:
            List of active workflow states
        """
        active_workflows = []

        for state_file in self.state_dir.glob("*.json"):
            try:
                data = json.loads(state_file.read_text())
                state = WorkflowState.from_dict(data)
                if state.is_active:
                    active_workflows.append(state)
            except Exception:
                # Skip invalid state files
                continue

        return active_workflows

    def list_all_workflows(self) -> list[WorkflowState]:
        """List all workflow executions.

        Returns:
            List of all workflow states
        """
        all_workflows = []

        for state_file in self.state_dir.glob("*.json"):
            try:
                data = json.loads(state_file.read_text())
                state = WorkflowState.from_dict(data)
                all_workflows.append(state)
            except Exception:
                # Skip invalid state files
                continue

        return all_workflows

    def delete_state(self, workflow_id: str) -> bool:
        """Delete workflow state.

        Args:
            workflow_id: Workflow execution identifier

        Returns:
            True if deleted, False if not found
        """
        state_file = self.state_dir / f"{workflow_id}.json"

        if state_file.exists():
            state_file.unlink()
            return True

        return False

    def cleanup_old_states(
        self,
        max_age_hours: int = 24
    ) -> int:
        """Clean up old workflow states.

        Args:
            max_age_hours: Remove states older than this

        Returns:
            Number of states removed
        """
        import time

        removed_count = 0
        cutoff_time = time.time() - (max_age_hours * 3600)

        for state_file in self.state_dir.glob("*.json"):
            try:
                # Check file modification time
                if state_file.stat().st_mtime < cutoff_time:
                    # Check if workflow is completed or failed
                    data = json.loads(state_file.read_text())
                    state = WorkflowState.from_dict(data)

                    if not state.is_active:
                        state_file.unlink()
                        removed_count += 1
            except Exception:
                # Skip invalid files
                continue

        return removed_count

    def _atomic_write(self, path: Path, content: Dict[str, Any]) -> None:
        """Atomically write content to file.

        Args:
            path: File path
            content: Content to write
        """
        import tempfile
        import os

        # Write to temporary file
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            os.write(fd, json.dumps(content, indent=2).encode("utf-8"))
            os.close(fd)

            # Atomic rename
            os.rename(tmp_path, path)
        except Exception:
            # Clean up temporary file
            try:
                os.close(fd)
            except Exception:
                pass
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise


__all__ = [
    "WorkflowState",
    "WorkflowStateManager",
]
