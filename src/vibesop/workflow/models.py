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
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional stage metadata (e.g., skill_id)"
    )

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


class ExecutionStrategy(str, Enum):
    """Execution strategy for workflow."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"


class RetryPolicy(BaseModel):
    """Retry policy for failed stages.

    Attributes:
        max_attempts: Maximum number of retry attempts
        backoff_strategy: Strategy for backoff delay
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
    """

    max_attempts: int = Field(default=3, ge=1, description="Maximum retry attempts")
    backoff_strategy: Literal["exponential", "linear", "constant"] = Field(
        default="exponential",
        description="Backoff delay strategy"
    )
    base_delay: float = Field(default=1.0, ge=0, description="Base delay in seconds")
    max_delay: float = Field(default=60.0, ge=0, description="Maximum delay in seconds")


class RecoveryStrategy(BaseModel):
    """Recovery strategy for failed workflows.

    Attributes:
        checkpoint_on_failure: Create checkpoint on failure
        rollback_on_failure: Rollback to checkpoint on failure
        recovery_stages: Stages to execute for recovery
    """

    checkpoint_on_failure: bool = Field(
        default=True,
        description="Create checkpoint on failure"
    )
    rollback_on_failure: bool = Field(
        default=False,
        description="Rollback to checkpoint on failure"
    )
    recovery_stages: List[str] = Field(
        default_factory=list,
        description="Stages to execute for recovery"
    )


class WorkflowDefinition(BaseModel):
    """Complete workflow definition with validation.

    This is the primary user-facing model for defining workflows.
    It provides full type safety and validation while integrating
    seamlessly with the existing CascadeExecutor.

    Attributes:
        name: Workflow name
        description: Workflow description
        version: Workflow version
        stages: Workflow stages in execution order
        strategy: Default execution strategy
        timeout_seconds: Workflow timeout
        max_parallel: Max parallel stages (for parallel/pipeline)
        stop_on_first_failure: Stop workflow on first failure
        retry_policy: Retry policy for failed stages
        recovery_strategy: Recovery strategy for failures
        metadata: Additional metadata
    """

    name: str = Field(..., min_length=1, description="Workflow name")
    description: str = Field(..., description="Workflow description")
    version: str = Field(default="1.0.0", description="Workflow version")
    stages: List[PipelineStage] = Field(
        default_factory=list,
        description="Workflow stages in execution order"
    )
    strategy: Literal["sequential", "parallel", "pipeline"] = Field(
        default="sequential",
        description="Default execution strategy"
    )
    timeout_seconds: int = Field(
        default=300,
        ge=1,
        description="Workflow timeout"
    )
    max_parallel: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max parallel stages (for parallel/pipeline)"
    )
    stop_on_first_failure: bool = Field(
        default=True,
        description="Stop workflow on first failure"
    )
    retry_policy: RetryPolicy = Field(
        default_factory=RetryPolicy,
        description="Retry policy for failed stages"
    )
    recovery_strategy: RecoveryStrategy = Field(
        default_factory=RecoveryStrategy,
        description="Recovery strategy for failures"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    @field_validator('stages')
    @classmethod
    def validate_stages(
        cls,
        stages: List[PipelineStage]
    ) -> List[PipelineStage]:
        """Validate stages for circular dependencies."""
        if not stages:
            return stages

        # Build dependency graph
        dep_graph = {stage.name: stage.dependencies for stage in stages}
        stage_names = {stage.name for stage in stages}

        # Check for circular dependencies using topological sort
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(stage_name: str) -> bool:
            """Detect circular dependencies using DFS."""
            visited.add(stage_name)
            rec_stack.add(stage_name)

            for dep_id in dep_graph.get(stage_name, []):
                if dep_id not in stage_names:
                    raise ValueError(
                        f"Stage '{stage_name}' depends on non-existent stage '{dep_id}'"
                    )

                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    raise ValueError(
                        f"Circular dependency detected involving '{stage_name}' and '{dep_id}'"
                    )

            rec_stack.remove(stage_name)
            return False

        for stage_name in stage_names:
            if stage_name not in visited:
                has_cycle(stage_name)

        return stages

    @model_validator(mode='after')
    def validate_handlers(self) -> 'WorkflowDefinition':
        """Ensure all stages have handlers or skill references."""
        for stage in self.stages:
            has_handler = stage.handler is not None
            has_skill = 'skill_id' in stage.metadata

            if not has_handler and not has_skill:
                raise ValueError(
                    f"Stage '{stage.name}' must have either a handler or skill_id in metadata"
                )
        return self

    @model_validator(mode='after')
    def validate_strategy(self) -> 'WorkflowDefinition':
        """Validate execution strategy matches workflow requirements."""
        if self.strategy == "parallel" or self.strategy == "pipeline":
            if len(self.stages) < 2:
                raise ValueError(
                    f"Strategy '{self.strategy}' requires at least 2 stages"
                )
        return self


__all__ = [
    "StageStatus",
    "PipelineStage",
    "WorkflowResult",
    "WorkflowExecutionContext",
    "ExecutionStrategy",
    "RetryPolicy",
    "RecoveryStrategy",
    "WorkflowDefinition",
]
