"""Tests for cascade execution system."""

import asyncio
import tempfile
from pathlib import Path

from vibesop.workflow import (
    CascadeExecutor,
    WorkflowStep,
    WorkflowConfig,
    StepStatus,
    ExecutionStrategy,
)


class TestStepStatus:
    """Test StepStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.SKIPPED.value == "skipped"


class TestExecutionStrategy:
    """Test ExecutionStrategy enum."""

    def test_strategy_values(self) -> None:
        """Test strategy enum values."""
        assert ExecutionStrategy.SEQUENTIAL.value == "sequential"
        assert ExecutionStrategy.PARALLEL.value == "parallel"
        assert ExecutionStrategy.PIPELINE.value == "pipeline"


class TestWorkflowStep:
    """Test WorkflowStep dataclass."""

    def test_create_step(self) -> None:
        """Test creating a workflow step."""

        async def dummy_handler():
            return {"result": "success"}

        step = WorkflowStep(
            step_id="step1",
            name="First Step",
            description="Initial step",
            handler=dummy_handler,
            dependencies=[],
            timeout_seconds=60,
        )

        assert step.step_id == "step1"
        assert step.name == "First Step"


class TestCascadeExecutor:
    """Test CascadeExecutor functionality."""

    def test_create_executor(self) -> None:
        """Test creating executor."""
        executor = CascadeExecutor()
        assert executor is not None

    def test_execute_sequential(self) -> None:
        """Test sequential execution."""

        async def handler1():
            return {"step": 1}

        async def handler2():
            return {"step": 2}

        step1 = WorkflowStep(
            step_id="step1",
            name="Step 1",
            description="",
            handler=handler1,
        )

        step2 = WorkflowStep(
            step_id="step2",
            name="Step 2",
            description="",
            handler=handler2,
            dependencies=["step1"],
        )

        config = WorkflowConfig(
            workflow_id="test_wf",
            name="Test Workflow",
            description="Test",
            steps=[step1, step2],
            strategy=ExecutionStrategy.SEQUENTIAL,
        )

        executor = CascadeExecutor()
        results = asyncio.run(executor.execute(config))

        assert len(results) == 2
        assert results["step1"].status == StepStatus.COMPLETED
        assert results["step2"].status == StepStatus.COMPLETED

    def test_execute_with_disabled_step(self) -> None:
        """Test execution with disabled step."""

        async def handler():
            return {"result": "success"}

        step = WorkflowStep(
            step_id="step1",
            name="Step 1",
            description="",
            handler=handler,
            enabled=False,
        )

        config = WorkflowConfig(
            workflow_id="test_wf",
            name="Test",
            description="Test",
            steps=[step],
        )

        executor = CascadeExecutor()
        results = asyncio.run(executor.execute(config))

        # Step should be skipped
        assert len(results) == 0

    def test_execute_with_failure(self) -> None:
        """Test execution with step failure."""

        async def failing_handler():
            raise ValueError("Step failed")

        step = WorkflowStep(
            step_id="step1",
            name="Failing Step",
            description="",
            handler=failing_handler,
        )

        config = WorkflowConfig(
            workflow_id="test_wf",
            name="Test",
            description="Test",
            steps=[step],
            stop_on_first_failure=True,
        )

        executor = CascadeExecutor()
        results = asyncio.run(executor.execute(config))

        assert results["step1"].status == StepStatus.FAILED
        assert "Step failed" in (results["step1"].error or "")

    def test_execute_parallel(self) -> None:
        """Test parallel execution."""

        async def handler1():
            await asyncio.sleep(0.01)
            return {"step": 1}

        async def handler2():
            await asyncio.sleep(0.01)
            return {"step": 2}

        step1 = WorkflowStep(
            step_id="step1",
            name="Step 1",
            description="",
            handler=handler1,
        )

        step2 = WorkflowStep(
            step_id="step2",
            name="Step 2",
            description="",
            handler=handler2,
        )

        config = WorkflowConfig(
            workflow_id="test_wf",
            name="Test",
            description="Test",
            steps=[step1, step2],
            strategy=ExecutionStrategy.PARALLEL,
        )

        executor = CascadeExecutor()
        results = asyncio.run(executor.execute(config))

        assert len(results) == 2
        assert results["step1"].status == StepStatus.COMPLETED
        assert results["step2"].status == StepStatus.COMPLETED

    def test_get_execution_summary(self) -> None:
        """Test getting execution summary."""

        async def handler():
            return {"result": "success"}

        step = WorkflowStep(
            step_id="step1",
            name="Step 1",
            description="",
            handler=handler,
        )

        config = WorkflowConfig(
            workflow_id="test_wf",
            name="Test",
            description="Test",
            steps=[step],
        )

        executor = CascadeExecutor()
        asyncio.run(executor.execute(config))

        summary = executor.get_execution_summary()

        assert summary["total_steps"] == 1
        assert summary["completed"] == 1
        assert summary["failed"] == 0

    def test_export_execution_log(self) -> None:
        """Test exporting execution log."""

        async def handler():
            return {"result": "success"}

        step = WorkflowStep(
            step_id="step1",
            name="Step 1",
            description="",
            handler=handler,
        )

        config = WorkflowConfig(
            workflow_id="test_wf",
            name="Test",
            description="Test",
            steps=[step],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "execution_log.json"

            executor = CascadeExecutor()
            asyncio.run(executor.execute(config))
            result = executor.export_execution_log(output_path)

            assert result["success"]
            assert output_path.exists()
