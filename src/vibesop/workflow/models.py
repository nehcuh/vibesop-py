"""
Workflow data models.

This module defines the core data models for the workflow orchestration system,
using Pydantic v2 for runtime validation and type safety.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal, Callable, Any, Dict, List, Optional
from enum import Enum
from datetime import datetime


class StageStatus(str, Enum):
    """Status of a pipeline stage."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStage(BaseModel):
    """
    A single stage in a workflow pipeline.

    Attributes:
        name: Unique stage identifier
        description: Human-readable description
        status: Current stage status
        dependencies: List of stage names that must complete first
        handler: Optional callable that executes the stage logic
        required: Whether this stage must succeed for workflow to continue
        timeout_seconds: Optional timeout for stage execution
        retry_count: Number of times to retry on failure
    """

    name: str = Field(..., min_length=1, description="Unique stage identifier")
    description: str = Field(..., description="Human-readable description")
    status: StageStatus = Field(default=StageStatus.PENDING, description="Current stage status")
    dependencies: List[str] = Field(default_factory=list, description="Required stage names")
    handler: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = Field(
        default=None,
        description="Stage execution handler"
    )
    required: bool = Field(default=True, description="Whether stage must succeed")
    timeout_seconds: Optional[int] = Field(
        default=None,
        ge=1,
        description="Stage execution timeout"
    )
    retry_count: int = Field(default=0, ge=0, description="Retry attempts on failure")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure stage name is valid."""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError("Stage name must contain only alphanumeric characters, hyphens, and underscores")
        return v

    @model_validator(mode='after')
    def validate_dependencies(self) -> 'PipelineStage':
        """Ensure dependencies don't create circular references."""
        # This will be validated at the pipeline level
        return self

    class Config:
        frozen = True  # Make stages immutable for thread safety


class WorkflowResult(BaseModel):
    """
    Result of workflow execution.

    Attributes:
        success: Whether workflow completed successfully
        workflow_name: Name of the executed workflow
        completed_stages: List of completed stage names
        failed_stages: List of failed stage names
        skipped_stages: List of skipped stage names
        final_context: Context after workflow execution
        execution_time_seconds: Total execution time
        errors: List of error messages
        metadata: Additional workflow metadata
    """

    success: bool = Field(..., description="Workflow completion status")
    workflow_name: str = Field(..., description="Executed workflow name")
    completed_stages: List[str] = Field(default_factory=list, description="Completed stages")
    failed_stages: List[str] = Field(default_factory=list, description="Failed stages")
    skipped_stages: List[str] = Field(default_factory=list, description="Skipped stages")
    final_context: Dict[str, Any] = Field(default_factory=dict, description="Final execution context")
    execution_time_seconds: float = Field(..., ge=0, description="Execution time in seconds")
    errors: List[str] = Field(default_factory=list, description="Error messages")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @property
    def total_stages(self) -> int:
        """Total number of stages in workflow."""
        return len(self.completed_stages) + len(self.failed_stages) + len(self.skipped_stages)

    @property
    def completion_percentage(self) -> float:
        """Percentage of stages completed."""
        if self.total_stages == 0:
            return 0.0
        return (len(self.completed_stages) / self.total_stages) * 100

    def get_stage_result(self, stage_name: str) -> Optional[Dict[str, Any]]:
        """Get result for a specific stage."""
        return self.final_context.get(f"__stage_result__{stage_name}")


class WorkflowExecutionContext(BaseModel):
    """
    Context passed through workflow execution.

    Attributes:
        input: Initial input to workflow
        current_stage: Currently executing stage
        stage_results: Results from completed stages
        metadata: Additional metadata
        created_at: Context creation timestamp
        updated_at: Last update timestamp
    """

    input: Dict[str, Any] = Field(default_factory=dict, description="Initial workflow input")
    current_stage: Optional[str] = Field(default=None, description="Current stage name")
    stage_results: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Results from completed stages"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")

    def update_stage_result(self, stage_name: str, result: Dict[str, Any]) -> None:
        """Update result for a completed stage."""
        self.stage_results[stage_name] = result
        self.updated_at = datetime.now()

    def get_stage_result(self, stage_name: str) -> Optional[Dict[str, Any]]:
        """Get result for a specific stage."""
        return self.stage_results.get(stage_name)


__all__ = [
    "StageStatus",
    "PipelineStage",
    "WorkflowResult",
    "WorkflowExecutionContext",
]
