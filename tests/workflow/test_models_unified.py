"""Tests for unified workflow models and closure bug fix."""

import pytest
from vibesop.workflow.models import (
    StageStatus,
    ExecutionStrategy,
    PipelineStage,
    StepResult,
    ExecutionResult,
    WorkflowDefinition,
    WorkflowExecutionContext,
)


class TestUnifiedModels:
    """Test that models are unified (no duplicate definitions)."""

    def test_stage_status_enum(self) -> None:
        """Test StageStatus enum values."""
        assert StageStatus.PENDING == "pending"
        assert StageStatus.COMPLETED == "completed"
        assert StageStatus.FAILED == "failed"
        assert StageStatus.IN_PROGRESS == "in_progress"
        assert StageStatus.SKIPPED == "skipped"

    def test_execution_strategy_enum(self) -> None:
        """Test ExecutionStrategy enum values."""
        assert ExecutionStrategy.SEQUENTIAL == "sequential"
        assert ExecutionStrategy.PARALLEL == "parallel"
        assert ExecutionStrategy.PIPELINE == "pipeline"

    def test_pipeline_stage_is_pydantic(self) -> None:
        """Test PipelineStage is a Pydantic model with validation."""
        stage = PipelineStage(
            name="test-stage",
            description="Test stage",
        )
        assert stage.name == "test-stage"
        assert stage.status == StageStatus.PENDING
        assert stage.required is True

    def test_step_result_model(self) -> None:
        """Test StepResult model."""
        result = StepResult(
            step_id="step-1",
            status=StageStatus.COMPLETED,
            output={"data": "test"},
        )
        assert result.step_id == "step-1"
        assert result.status == StageStatus.COMPLETED
        assert result.output == {"data": "test"}
        assert result.error is None
        assert result.duration_ms == 0

    def test_execution_result_model(self) -> None:
        """Test ExecutionResult model."""
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


class TestClosureBugFix:
    """Test that closure bug is fixed in pipeline.py."""

    @pytest.mark.asyncio
    async def test_multiple_stages_execute_correct_handlers(self) -> None:
        """Test that each stage executes its own handler, not the last one."""
        from vibesop.workflow.pipeline import WorkflowPipeline
        from pathlib import Path
        import tempfile

        results: dict[str, str] = {}

        def make_handler(stage_name: str):
            def handler(ctx: dict) -> dict:
                results[stage_name] = stage_name
                return {"result": stage_name}

            return handler

        stages = [
            PipelineStage(
                name=f"stage-{i}",
                description=f"Stage {i}",
                handler=make_handler(f"stage-{i}"),
            )
            for i in range(3)
        ]

        workflow = WorkflowDefinition(
            name="test-closure",
            description="Test closure bug fix",
            stages=stages,
            strategy="sequential",
        )
        context = WorkflowExecutionContext(input={})

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = WorkflowPipeline(project_root=Path(tmpdir))
            await pipeline.execute(workflow, context)

        # Each stage should have executed its own handler
        assert results == {
            "stage-0": "stage-0",
            "stage-1": "stage-1",
            "stage-2": "stage-2",
        }
