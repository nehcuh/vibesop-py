"""Unit tests for workflow models.

Tests Pydantic v2 model validation, field validators,
and model validators for workflow definitions.
"""

import pytest
from pydantic import ValidationError
from datetime import datetime

from vibesop.workflow.models import (
    StageStatus,
    PipelineStage,
    WorkflowResult,
    WorkflowExecutionContext,
    ExecutionStrategy,
    RetryPolicy,
    RecoveryStrategy,
    WorkflowDefinition,
    StepResult,
    ExecutionResult,
)


class TestStageStatus:
    """Test StageStatus enum."""

    def test_stage_status_values(self):
        """Test StageStatus enum values."""
        assert StageStatus.PENDING == "pending"
        assert StageStatus.IN_PROGRESS == "in_progress"
        assert StageStatus.COMPLETED == "completed"
        assert StageStatus.FAILED == "failed"
        assert StageStatus.SKIPPED == "skipped"


class TestPipelineStage:
    """Test PipelineStage model."""

    def test_create_minimal_stage(self):
        """Test creating a stage with minimal fields."""
        stage = PipelineStage(name="test-stage", description="Test description")

        assert stage.name == "test-stage"
        assert stage.description == "Test description"
        assert stage.status == StageStatus.PENDING
        assert stage.dependencies == []
        assert stage.handler is None
        assert stage.required is True
        assert stage.timeout_seconds is None
        assert stage.retry_count == 0
        assert stage.metadata == {}

    def test_create_full_stage(self):
        """Test creating a stage with all fields."""
        handler = lambda ctx: {"result": "success"}

        stage = PipelineStage(
            name="full-stage",
            description="Full stage description",
            status=StageStatus.IN_PROGRESS,
            dependencies=["stage1", "stage2"],
            handler=handler,
            required=False,
            timeout_seconds=60,
            retry_count=3,
            metadata={"skill_id": "/test/skill", "category": "test"},
        )

        assert stage.name == "full-stage"
        assert stage.description == "Full stage description"
        assert stage.status == StageStatus.IN_PROGRESS
        assert stage.dependencies == ["stage1", "stage2"]
        assert stage.handler is not None
        assert stage.required is False
        assert stage.timeout_seconds == 60
        assert stage.retry_count == 3
        assert stage.metadata["skill_id"] == "/test/skill"

    def test_stage_name_validation_valid(self):
        """Test stage name validation with valid names."""
        valid_names = [
            "simple",
            "with-hyphen",
            "with_underscore",
            "CamelCase",
            "123numbers",
        ]

        for name in valid_names:
            stage = PipelineStage(name=name, description="Valid name")
            assert stage.name == name

    def test_stage_name_validation_invalid(self):
        """Test stage name validation rejects invalid names."""
        invalid_names = [
            "with space",
            "with.dot",
            "with/slash",
            "with@symbol",
            "",
        ]

        for name in invalid_names:
            with pytest.raises(ValidationError):
                PipelineStage(name=name, description="Invalid name")

    def test_stage_immutable(self):
        """Test that PipelineStage is immutable (frozen)."""
        stage = PipelineStage(name="test", description="Test")

        with pytest.raises(Exception):  # TypeError or ValidationError
            stage.name = "new-name"


class TestWorkflowExecutionContext:
    """Test WorkflowExecutionContext model."""

    def test_create_context(self):
        """Test creating execution context."""
        context = WorkflowExecutionContext(
            input={"data": "test"}, current_stage="stage1", metadata={"test": True}
        )

        assert context.input == {"data": "test"}
        assert context.current_stage == "stage1"
        assert context.stage_results == {}
        assert context.metadata == {"test": True}
        assert isinstance(context.created_at, datetime)
        assert isinstance(context.updated_at, datetime)

    def test_update_stage_result(self):
        """Test updating stage result."""
        context = WorkflowExecutionContext()

        context.update_stage_result("stage1", {"output": "result1"})
        context.update_stage_result("stage2", {"output": "result2"})

        assert context.stage_results["stage1"] == {"output": "result1"}
        assert context.stage_results["stage2"] == {"output": "result2"}
        # Verify updated_at timestamp is updated
        assert context.updated_at > context.created_at

    def test_get_stage_result(self):
        """Test getting stage result."""
        context = WorkflowExecutionContext()
        context.update_stage_result("stage1", {"output": "result1"})

        result = context.get_stage_result("stage1")
        assert result == {"output": "result1"}

        missing = context.get_stage_result("stage2")
        assert missing is None


class TestWorkflowResult:
    """Test WorkflowResult model."""

    def test_create_successful_result(self):
        """Test creating successful workflow result."""
        result = WorkflowResult(
            success=True,
            workflow_name="test-workflow",
            completed_stages=["stage1", "stage2"],
            failed_stages=[],
            skipped_stages=[],
            final_context={"output": "done"},
            execution_time_seconds=1.5,
        )

        assert result.success is True
        assert result.workflow_name == "test-workflow"
        assert len(result.completed_stages) == 2
        assert result.total_stages == 2
        assert result.completion_percentage == 100.0

    def test_create_failed_result(self):
        """Test creating failed workflow result."""
        result = WorkflowResult(
            success=False,
            workflow_name="test-workflow",
            completed_stages=["stage1"],
            failed_stages=["stage2"],
            skipped_stages=["stage3"],
            final_context={},
            execution_time_seconds=0.5,
            errors=["Stage 2 failed"],
        )

        assert result.success is False
        assert result.total_stages == 3
        assert result.completion_percentage == pytest.approx(33.33, rel=1e-2)
        assert result.errors == ["Stage 2 failed"]

    def test_get_stage_result(self):
        """Test getting specific stage result from workflow result."""
        result = WorkflowResult(
            success=True,
            workflow_name="test",
            completed_stages=["stage1"],
            failed_stages=[],
            skipped_stages=[],
            final_context={
                "__stage_result__stage1": {"output": "result1"},
                "__stage_result__stage2": {"output": "result2"},
            },
            execution_time_seconds=1.0,
        )

        stage1_result = result.get_stage_result("stage1")
        assert stage1_result == {"output": "result1"}

        stage2_result = result.get_stage_result("stage2")
        assert stage2_result == {"output": "result2"}


class TestRetryPolicy:
    """Test RetryPolicy model."""

    def test_default_policy(self):
        """Test creating default retry policy."""
        policy = RetryPolicy()

        assert policy.max_attempts == 3
        assert policy.backoff_strategy == "exponential"
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0

    def test_custom_policy(self):
        """Test creating custom retry policy."""
        policy = RetryPolicy(
            max_attempts=5, backoff_strategy="linear", base_delay=2.0, max_delay=30.0
        )

        assert policy.max_attempts == 5
        assert policy.backoff_strategy == "linear"
        assert policy.base_delay == 2.0
        assert policy.max_delay == 30.0

    def test_invalid_backoff_strategy(self):
        """Test validation rejects invalid backoff strategy."""
        with pytest.raises(ValidationError):
            RetryPolicy(backoff_strategy="invalid")

    def test_negative_delay_validation(self):
        """Test validation rejects negative delays."""
        with pytest.raises(ValidationError):
            RetryPolicy(base_delay=-1.0)

        with pytest.raises(ValidationError):
            RetryPolicy(max_delay=-10.0)


class TestRecoveryStrategy:
    """Test RecoveryStrategy model."""

    def test_default_strategy(self):
        """Test creating default recovery strategy."""
        strategy = RecoveryStrategy()

        assert strategy.checkpoint_on_failure is True
        assert strategy.rollback_on_failure is False
        assert strategy.recovery_stages == []

    def test_custom_strategy(self):
        """Test creating custom recovery strategy."""
        strategy = RecoveryStrategy(
            checkpoint_on_failure=False,
            rollback_on_failure=True,
            recovery_stages=["cleanup", "notify"],
        )

        assert strategy.checkpoint_on_failure is False
        assert strategy.rollback_on_failure is True
        assert strategy.recovery_stages == ["cleanup", "notify"]


class TestWorkflowDefinition:
    """Test WorkflowDefinition model."""

    def test_create_minimal_workflow(self, sample_stage):
        """Test creating minimal workflow definition."""
        workflow = WorkflowDefinition(
            name="test-workflow", description="Test workflow", stages=[sample_stage]
        )

        assert workflow.name == "test-workflow"
        assert workflow.description == "Test workflow"
        assert workflow.version == "1.0.0"
        assert len(workflow.stages) == 1
        assert workflow.strategy == "sequential"
        assert workflow.timeout_seconds == 300
        assert workflow.max_parallel == 3
        assert workflow.stop_on_first_failure is True

    def test_create_full_workflow(self, sample_stages):
        """Test creating workflow with all fields."""
        retry_policy = RetryPolicy(max_attempts=5)
        recovery_strategy = RecoveryStrategy(
            checkpoint_on_failure=True, recovery_stages=["cleanup"]
        )

        workflow = WorkflowDefinition(
            name="full-workflow",
            description="Full workflow test",
            version="2.0.0",
            stages=sample_stages,
            strategy="parallel",
            timeout_seconds=600,
            max_parallel=5,
            stop_on_first_failure=False,
            retry_policy=retry_policy,
            recovery_strategy=recovery_strategy,
            metadata={"environment": "test"},
        )

        assert workflow.name == "full-workflow"
        assert workflow.version == "2.0.0"
        assert workflow.strategy == "parallel"
        assert workflow.max_parallel == 5
        assert workflow.stop_on_first_failure is False
        assert workflow.retry_policy.max_attempts == 5
        assert workflow.recovery_strategy.recovery_stages == ["cleanup"]
        assert workflow.metadata["environment"] == "test"

    def test_validate_empty_stages(self):
        """Test that empty stages list is allowed."""
        workflow = WorkflowDefinition(
            name="empty-workflow", description="Workflow with no stages", stages=[]
        )

        assert len(workflow.stages) == 0

    def test_validate_duplicate_stage_names(self):
        """Test that duplicate stage names are rejected."""
        stages = [
            PipelineStage(name="duplicate", description="First"),
            PipelineStage(name="duplicate", description="Second"),
        ]

        with pytest.raises(ValidationError):
            WorkflowDefinition(name="test", description="Test", stages=stages)

    def test_validate_missing_dependency(self):
        """Test that missing dependencies are rejected."""
        stages = [
            PipelineStage(name="stage1", description="Stage 1"),
            PipelineStage(
                name="stage2",
                description="Stage 2",
                dependencies=["missing-stage"],  # Doesn't exist
            ),
        ]

        with pytest.raises(ValidationError, match="depends on non-existent stage"):
            WorkflowDefinition(name="test", description="Test", stages=stages)

    def test_validate_circular_dependencies(self):
        """Test that circular dependencies are rejected."""
        stages = [
            PipelineStage(name="stage1", description="Stage 1", dependencies=["stage2"]),
            PipelineStage(name="stage2", description="Stage 2", dependencies=["stage1"]),
        ]

        with pytest.raises(ValidationError, match="Circular dependency"):
            WorkflowDefinition(name="test", description="Test", stages=stages)

    def test_validate_complex_circular_dependencies(self):
        """Test detection of complex circular dependencies."""
        stages = [
            PipelineStage(name="a", description="A", dependencies=["c"]),
            PipelineStage(name="b", description="B", dependencies=["a"]),
            PipelineStage(name="c", description="C", dependencies=["b"]),
        ]

        with pytest.raises(ValidationError, match="Circular dependency"):
            WorkflowDefinition(name="test", description="Test", stages=stages)

    def test_validate_handlers_require_skill_or_handler(self):
        """Test that stages must have handler or skill_id."""
        # Stage with neither handler nor skill_id
        stages = [
            PipelineStage(name="stage1", description="Stage 1"),
        ]

        with pytest.raises(ValidationError, match="must have either a handler or skill_id"):
            WorkflowDefinition(name="test", description="Test", stages=stages)

    def test_validate_handler_passes(self):
        """Test that stage with handler passes validation."""
        stages = [
            PipelineStage(name="stage1", description="Stage 1", handler=lambda ctx: {}),
        ]

        workflow = WorkflowDefinition(name="test", description="Test", stages=stages)

        assert len(workflow.stages) == 1

    def test_validate_skill_id_passes(self):
        """Test that stage with skill_id in metadata passes validation."""
        stages = [
            PipelineStage(
                name="stage1", description="Stage 1", metadata={"skill_id": "/test/skill"}
            ),
        ]

        workflow = WorkflowDefinition(name="test", description="Test", stages=stages)

        assert len(workflow.stages) == 1

    def test_validate_strategy_requires_multiple_stages(self):
        """Test that parallel/pipeline strategies require at least 2 stages."""
        single_stage = [
            PipelineStage(name="stage1", description="Stage 1", handler=lambda ctx: {}),
        ]

        with pytest.raises(ValidationError, match="requires at least 2 stages"):
            WorkflowDefinition(
                name="test", description="Test", stages=single_stage, strategy="parallel"
            )

        with pytest.raises(ValidationError, match="requires at least 2 stages"):
            WorkflowDefinition(
                name="test", description="Test", stages=single_stage, strategy="pipeline"
            )

    def test_validate_invalid_strategy(self):
        """Test that invalid strategy is rejected."""
        with pytest.raises(ValidationError):
            WorkflowDefinition(
                name="test", description="Test", stages=[], strategy="invalid-strategy"
            )

    def test_validate_max_parallel_bounds(self):
        """Test that max_parallel is within bounds."""
        with pytest.raises(ValidationError):
            WorkflowDefinition(name="test", description="Test", stages=[], max_parallel=0)

        with pytest.raises(ValidationError):
            WorkflowDefinition(
                name="test",
                description="Test",
                stages=[],
                max_parallel=11,  # Max is 10
            )

    def test_validate_timeout_bounds(self):
        """Test that timeout_seconds is positive."""
        with pytest.raises(ValidationError):
            WorkflowDefinition(name="test", description="Test", stages=[], timeout_seconds=0)


class TestStepResult:
    """Test StepResult model."""

    def test_create_step_result(self):
        """Test creating StepResult with minimal fields."""
        result = StepResult(
            step_id="step-1",
            status=StageStatus.COMPLETED,
        )
        assert result.step_id == "step-1"
        assert result.status == StageStatus.COMPLETED
        assert result.output is None
        assert result.error is None
        assert result.duration_ms == 0

    def test_create_full_step_result(self):
        """Test creating StepResult with all fields."""
        result = StepResult(
            step_id="step-1",
            status=StageStatus.COMPLETED,
            output={"data": "test"},
            error=None,
            duration_ms=100,
        )
        assert result.step_id == "step-1"
        assert result.status == StageStatus.COMPLETED
        assert result.output == {"data": "test"}
        assert result.error is None
        assert result.duration_ms == 100


class TestExecutionResult:
    """Test ExecutionResult model."""

    def test_create_execution_result(self):
        """Test creating ExecutionResult."""
        result = ExecutionResult(
            success=True,
            step_results={
                "step-1": StepResult(
                    step_id="step-1",
                    status=StageStatus.COMPLETED,
                    output={"result": "done"},
                    duration_ms=100,
                )
            },
        )
        assert result.success is True
        assert "step-1" in result.step_results
        assert result.step_results["step-1"].status == StageStatus.COMPLETED

    def test_execution_result_with_errors(self):
        """Test ExecutionResult with failed steps."""
        result = ExecutionResult(
            success=False,
            step_results={
                "step-1": StepResult(
                    step_id="step-1",
                    status=StageStatus.FAILED,
                    error="Something went wrong",
                    duration_ms=50,
                )
            },
        )
        assert result.success is False
        assert result.step_results["step-1"].error == "Something went wrong"
