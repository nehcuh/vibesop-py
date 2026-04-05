"""Unit tests for WorkflowPipeline - Simplified version.

Tests the main workflow orchestration engine including:
- Workflow validation
- CascadeExecutor integration
- Result conversion
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch
from typing import Any

import pytest

from vibesop.workflow.models import (
    WorkflowDefinition,
    WorkflowExecutionContext,
)
from vibesop.workflow.pipeline import WorkflowPipeline
from vibesop.workflow.exceptions import WorkflowError
from vibesop.workflow.cascade import StepStatus, StepResult, ExecutionStrategy


class TestWorkflowPipeline:
    """Test WorkflowPipeline class."""

    def test_initialization(self, tmp_path: Path) -> None:
        """Test pipeline initialization."""
        pipeline = WorkflowPipeline(project_root=Path("."), state_dir=tmp_path / ".vibe" / "state")

        assert pipeline.project_root == Path(".").resolve()
        assert pipeline._executor is not None  # type: ignore[reportPrivateUsage]
        assert pipeline._skill_manager is None  # type: ignore[reportPrivateUsage]
        assert pipeline._router is None  # type: ignore[reportPrivateUsage]

    def test_initialization_with_dependencies(self, tmp_path: Path) -> None:
        """Test pipeline initialization with SkillManager and Router."""
        from unittest.mock import Mock

        mock_skill_manager = Mock()
        mock_router = Mock()

        pipeline = WorkflowPipeline(
            project_root=Path("."),
            skill_manager=mock_skill_manager,
            router=mock_router,
            state_dir=tmp_path / ".vibe" / "state",
        )

        assert pipeline._skill_manager is mock_skill_manager  # type: ignore[reportPrivateUsage]
        assert pipeline._router is mock_router  # type: ignore[reportPrivateUsage]

    @pytest.mark.asyncio
    async def test_execute_sequential_workflow(
        self, sample_workflow: WorkflowDefinition, sample_context: WorkflowExecutionContext
    ) -> None:
        """Test executing workflow with sequential strategy."""
        pipeline = WorkflowPipeline(project_root=Path("."))

        with patch.object(pipeline._executor, "execute", new_callable=AsyncMock) as mock_execute:  # type: ignore[reportPrivateUsage]
            mock_execute.return_value = {
                "stage1": StepResult(
                    step_id="stage1",
                    status=StepStatus.COMPLETED,
                    output={"step": 1},
                    duration_ms=100,
                    error=None,
                ),
                "stage2": StepResult(
                    step_id="stage2",
                    status=StepStatus.COMPLETED,
                    output={"step": 2},
                    duration_ms=100,
                    error=None,
                ),
                "stage3": StepResult(
                    step_id="stage3",
                    status=StepStatus.COMPLETED,
                    output={"step": 3},
                    duration_ms=100,
                    error=None,
                ),
            }

            result = await pipeline.execute(
                sample_workflow, sample_context, ExecutionStrategy.SEQUENTIAL
            )

            assert result.success is True
            assert len(result.completed_stages) == 3
            assert len(result.failed_stages) == 0
            assert result.workflow_name == "test-workflow"
            assert result.execution_time_seconds > 0

    def test_validate_workflow_success(self, sample_workflow: WorkflowDefinition) -> None:
        """Test workflow validation succeeds."""
        pipeline = WorkflowPipeline(project_root=Path("."))

        pipeline._validate_workflow(sample_workflow)  # type: ignore[reportPrivateUsage]

    def test_validate_workflow_empty_stages(self) -> None:
        """Test validation rejects workflow with no stages."""
        workflow = WorkflowDefinition(name="empty", description="Empty workflow", stages=[])

        pipeline = WorkflowPipeline(project_root=Path("."))

        with pytest.raises(WorkflowError, match="has no stages"):
            pipeline._validate_workflow(workflow)  # type: ignore[reportPrivateUsage]

    def test_to_cascade_config_conversion(
        self, sample_workflow: WorkflowDefinition, sample_context: WorkflowExecutionContext
    ) -> None:
        """Test conversion from WorkflowDefinition to WorkflowConfig."""
        pipeline = WorkflowPipeline(project_root=Path("."))

        config = pipeline._to_cascade_config(  # type: ignore[reportPrivateUsage]
            sample_workflow, sample_context, ExecutionStrategy.SEQUENTIAL
        )

        assert config.name == "test-workflow"
        assert config.description == "A test workflow"
        assert config.strategy == ExecutionStrategy.SEQUENTIAL
        assert len(config.steps) == len(sample_workflow.stages)

        for i, step in enumerate(config.steps):
            assert step.step_id == sample_workflow.stages[i].name
            assert step.description == sample_workflow.stages[i].description

    def test_to_workflow_result_success(
        self, sample_workflow: WorkflowDefinition, sample_context: WorkflowExecutionContext
    ) -> None:
        """Test conversion from CascadeExecutor results to WorkflowResult."""
        pipeline = WorkflowPipeline(project_root=Path("."))

        step_results = {
            "stage1": StepResult(
                step_id="stage1",
                status=StepStatus.COMPLETED,
                output={"data": "result1"},
                duration_ms=100,
                error=None,
            ),
            "stage2": StepResult(
                step_id="stage2",
                status=StepStatus.COMPLETED,
                output={"data": "result2"},
                duration_ms=100,
                error=None,
            ),
        }

        import time

        start_time = time.time() - 1.5

        result = pipeline._to_workflow_result(  # type: ignore[reportPrivateUsage]
            sample_workflow, step_results, sample_context, start_time
        )

        assert result.success is True
        assert len(result.completed_stages) == 2
        assert len(result.failed_stages) == 0
        assert result.execution_time_seconds >= 1.5
        assert result.completion_percentage == 100.0

    def test_to_workflow_result_mixed_status(
        self, sample_workflow: WorkflowDefinition, sample_context: WorkflowExecutionContext
    ) -> None:
        """Test result conversion with mixed stage statuses."""
        pipeline = WorkflowPipeline(project_root=Path("."))

        step_results = {
            "stage1": StepResult(
                step_id="stage1",
                status=StepStatus.COMPLETED,
                output={"data": "result1"},
                duration_ms=100,
                error=None,
            ),
            "stage2": StepResult(
                step_id="stage2",
                status=StepStatus.FAILED,
                output=None,
                duration_ms=50,
                error="Stage 2 error",
            ),
            "stage3": StepResult(
                step_id="stage3", status=StepStatus.SKIPPED, output=None, duration_ms=0, error=None
            ),
        }

        import time

        start_time = time.time() - 0.5

        result = pipeline._to_workflow_result(  # type: ignore[reportPrivateUsage]
            sample_workflow, step_results, sample_context, start_time
        )

        assert result.success is False
        assert len(result.completed_stages) == 1
        assert len(result.failed_stages) == 1
        assert len(result.skipped_stages) == 1
        assert any("Stage 2 error" in err for err in result.errors)

    def test_generate_workflow_id(self) -> None:
        """Test workflow ID generation."""
        pipeline = WorkflowPipeline(project_root=Path("."))

        id1 = pipeline._generate_workflow_id()  # type: ignore[reportPrivateUsage]
        id2 = pipeline._generate_workflow_id()  # type: ignore[reportPrivateUsage]

        assert id1.startswith("workflow-")
        assert id2.startswith("workflow-")
        assert id1 != id2


class TestPipelineExecutionStrategies:
    """Test different execution strategies."""

    @pytest.mark.asyncio
    async def test_sequential_strategy_execution(
        self, sample_workflow: WorkflowDefinition, sample_context: WorkflowExecutionContext
    ) -> None:
        """Test sequential execution strategy."""
        pipeline = WorkflowPipeline(project_root=Path("."))

        with patch.object(pipeline._executor, "execute", new_callable=AsyncMock) as mock_execute:  # type: ignore[reportPrivateUsage]
            mock_execute.return_value = {
                "stage1": StepResult(
                    step_id="stage1",
                    status=StepStatus.COMPLETED,
                    output={},
                    duration_ms=100,
                    error=None,
                ),
            }

            await pipeline.execute(sample_workflow, sample_context, ExecutionStrategy.SEQUENTIAL)

            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_parallel_strategy_execution(
        self, complex_workflow: WorkflowDefinition, sample_context: WorkflowExecutionContext
    ) -> None:
        """Test parallel execution strategy."""
        pipeline = WorkflowPipeline(project_root=Path("."))

        with patch.object(pipeline._executor, "execute", new_callable=AsyncMock) as mock_execute:  # type: ignore[reportPrivateUsage]
            mock_execute.return_value = {}

            await pipeline.execute(complex_workflow, sample_context, ExecutionStrategy.PARALLEL)

            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_strategy_execution(
        self, complex_workflow: WorkflowDefinition, sample_context: WorkflowExecutionContext
    ) -> None:
        """Test pipeline (adaptive) execution strategy."""
        pipeline = WorkflowPipeline(project_root=Path("."))

        with patch.object(pipeline._executor, "execute", new_callable=AsyncMock) as mock_execute:  # type: ignore[reportPrivateUsage]
            mock_execute.return_value = {}

            await pipeline.execute(complex_workflow, sample_context, ExecutionStrategy.PIPELINE)

            mock_execute.assert_called_once()


class TestPipelineErrorHandling:
    """Test error handling in pipeline."""

    @pytest.mark.asyncio
    async def test_executor_exception_handling(
        self, sample_workflow: WorkflowDefinition, sample_context: WorkflowExecutionContext
    ) -> None:
        """Test handling of exceptions from CascadeExecutor."""
        pipeline = WorkflowPipeline(project_root=Path("."))

        with patch.object(pipeline._executor, "execute", new_callable=AsyncMock) as mock_execute:  # type: ignore[reportPrivateUsage]
            mock_execute.side_effect = Exception("Executor error")

            with pytest.raises(WorkflowError, match="Workflow execution failed"):
                await pipeline.execute(
                    sample_workflow, sample_context, ExecutionStrategy.SEQUENTIAL
                )


class TestPipelineIntegration:
    """Test integration with other components."""

    def test_pipeline_skill_manager_integration(self, tmp_path: Path) -> None:
        """Test pipeline can use SkillManager for skill-based stages."""
        from unittest.mock import Mock

        mock_skill_manager = Mock()

        pipeline = WorkflowPipeline(
            project_root=Path("."),
            skill_manager=mock_skill_manager,
            state_dir=tmp_path / ".vibe" / "state",
        )

        assert pipeline._skill_manager is mock_skill_manager  # type: ignore[reportPrivateUsage]

    def test_pipeline_router_integration(self, tmp_path: Path) -> None:
        """Test pipeline can use SkillRouter for dynamic skill selection."""
        from unittest.mock import Mock

        mock_router = Mock()

        pipeline = WorkflowPipeline(
            project_root=Path("."), router=mock_router, state_dir=tmp_path / ".vibe" / "state"
        )

        assert pipeline._router is mock_router  # type: ignore[reportPrivateUsage]


class TestClosureBugFix:
    """Test that closure bug is fixed in pipeline.py."""

    @pytest.mark.asyncio
    async def test_multiple_stages_execute_correct_handlers(self, tmp_path: Path) -> None:
        """Test that each stage executes its own handler, not the last one."""
        from vibesop.workflow.models import (
            PipelineStage,
            WorkflowDefinition,
            WorkflowExecutionContext,
        )

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

        pipeline = WorkflowPipeline(project_root=tmp_path)
        await pipeline.execute(workflow, context)

        # Each stage should have executed its own handler
        assert results == {
            "stage-0": "stage-0",
            "stage-1": "stage-1",
            "stage-2": "stage-2",
        }
