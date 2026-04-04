"""Shared fixtures for workflow tests.

This module provides pytest fixtures for testing the v2.0 workflow system,
including sample workflows, stages, and test contexts.
"""

import pytest
import asyncio
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from vibesop.workflow.models import (
    WorkflowDefinition,
    PipelineStage,
    WorkflowExecutionContext,
    ExecutionStrategy,
    RetryPolicy,
    RecoveryStrategy,
    StageStatus,
)
from vibesop.workflow.pipeline import WorkflowPipeline
from vibesop.workflow.manager import WorkflowManager
from vibesop.workflow.state import WorkflowStateManager, WorkflowState


@pytest.fixture
def sample_stage():
    """Create a sample pipeline stage."""
    return PipelineStage(
        name="test-stage",
        description="A test stage",
        handler=lambda ctx: {"result": "success"},
        required=True,
        timeout_seconds=30,
        retry_count=2,
        metadata={"skill_id": "/test/skill"}
    )


@pytest.fixture
def sample_stages():
    """Create multiple sample stages with dependencies."""
    return [
        PipelineStage(
            name="stage1",
            description="First stage",
            handler=lambda ctx: {"step": 1},
            required=True,
            timeout_seconds=30,
        ),
        PipelineStage(
            name="stage2",
            description="Second stage",
            handler=lambda ctx: {"step": 2},
            dependencies=["stage1"],
            required=True,
            timeout_seconds=30,
        ),
        PipelineStage(
            name="stage3",
            description="Third stage",
            handler=lambda ctx: {"step": 3},
            dependencies=["stage1", "stage2"],
            required=False,
            timeout_seconds=30,
        ),
    ]


@pytest.fixture
def sample_workflow(sample_stages):
    """Create a sample workflow definition."""
    return WorkflowDefinition(
        name="test-workflow",
        description="A test workflow",
        version="1.0.0",
        stages=sample_stages,
        strategy="sequential",
        timeout_seconds=300,
        max_parallel=3,
        stop_on_first_failure=True,
    )


@pytest.fixture
def sample_context():
    """Create a sample workflow execution context."""
    return WorkflowExecutionContext(
        input={"test": "data"},
        metadata={"test_run": True}
    )


@pytest.fixture
def temp_workflow_dir(tmp_path):
    """Create a temporary directory for workflow files."""
    workflow_dir = tmp_path / ".vibe" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    return workflow_dir


@pytest.fixture
def workflow_manager(temp_workflow_dir):
    """Create a WorkflowManager instance with temp directory."""
    return WorkflowManager(
        project_root=Path("."),
        workflow_dir=temp_workflow_dir
    )


@pytest.fixture
def workflow_pipeline(tmp_path):
    """Create a WorkflowPipeline instance with temp state directory."""
    return WorkflowPipeline(
        project_root=Path("."),
        state_dir=tmp_path / ".vibe" / "state" / "workflows"
    )


@pytest.fixture
def state_manager(tmp_path):
    """Create a WorkflowStateManager instance with temp directory."""
    state_dir = tmp_path / ".vibe" / "state" / "workflows"
    return WorkflowStateManager(state_dir=state_dir)


@pytest.fixture
def sample_workflow_state():
    """Create a sample workflow state."""
    return WorkflowState(
        workflow_id="test-workflow-123",
        workflow_name="test-workflow",
        workflow_version="1.0.0",
        status="running",
        current_stage="stage1",
        stage_states={
            "stage1": "in_progress",
            "stage2": "pending",
            "stage3": "pending"
        },
        context={"input": "test"},
        started_at=datetime.now(),
    )


@pytest.fixture
def complex_workflow():
    """Create a complex workflow with multiple stages and dependencies."""
    stages = [
        PipelineStage(
            name="validate",
            description="Validate input",
            handler=lambda ctx: {"valid": True},
            required=True,
        ),
        PipelineStage(
            name="process_a",
            description="Process A",
            dependencies=["validate"],
            handler=lambda ctx: {"a": True},
            required=True,
        ),
        PipelineStage(
            name="process_b",
            description="Process B",
            dependencies=["validate"],
            handler=lambda ctx: {"b": True},
            required=True,
        ),
        PipelineStage(
            name="merge",
            description="Merge results",
            dependencies=["process_a", "process_b"],
            handler=lambda ctx: {"merged": True},
            required=True,
        ),
        PipelineStage(
            name="report",
            description="Generate report",
            dependencies=["merge"],
            handler=lambda ctx: {"report": True},
            required=False,
        ),
    ]

    return WorkflowDefinition(
        name="complex-workflow",
        description="A complex workflow with parallel stages",
        stages=stages,
        strategy="parallel",
        max_parallel=2,
    )


@pytest.fixture
def circular_dependency_workflow():
    """Create a workflow with circular dependencies for testing validation."""
    stages = [
        PipelineStage(
            name="stage1",
            description="Stage 1",
            dependencies=["stage2"],  # Circular!
            handler=lambda ctx: {},
        ),
        PipelineStage(
            name="stage2",
            description="Stage 2",
            dependencies=["stage1"],  # Circular!
            handler=lambda ctx: {},
        ),
    ]

    return WorkflowDefinition(
        name="circular-workflow",
        description="Workflow with circular dependencies",
        stages=stages,
    )


@pytest.fixture
def workflow_yaml_content():
    """Sample workflow YAML content for file-based tests."""
    return """
name: test-workflow
description: A test workflow from YAML
version: 1.0.0
stages:
  - name: validate
    description: Validate input
    required: true
    timeout_seconds: 30
    metadata:
      skill_id: /validate/input

  - name: process
    description: Process data
    dependencies:
      - validate
    required: true
    timeout_seconds: 60
    metadata:
      skill_id: /process/data

  - name: report
    description: Generate report
    dependencies:
      - process
    required: false
    timeout_seconds: 30
    metadata:
      skill_id: /report/generate
strategy: sequential
timeout_seconds: 300
max_parallel: 3
stop_on_first_failure: true
"""


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_workflow_runner():
    """Helper fixture for running async workflow tests."""
    async def run_workflow(
        workflow: WorkflowDefinition,
        context: WorkflowExecutionContext,
        strategy: ExecutionStrategy = ExecutionStrategy.SEQUENTIAL
    ):
        pipeline = WorkflowPipeline(project_root=Path("."))
        return await pipeline.execute(workflow, context, strategy)

    return run_workflow


# Test data generators
def generate_test_stages(count: int, with_dependencies: bool = False) -> list[PipelineStage]:
    """Generate test stages for parameterized testing.

    Args:
        count: Number of stages to generate
        with_dependencies: Whether to add dependencies between stages

    Returns:
        List of PipelineStage objects
    """
    stages = []
    for i in range(count):
        deps = [f"stage{i}"] if i > 0 and with_dependencies else []
        stage = PipelineStage(
            name=f"stage{i+1}",
            description=f"Test stage {i+1}",
            dependencies=deps,
            handler=lambda ctx, idx=i: {"stage": idx + 1},
            required=True,
        )
        stages.append(stage)
    return stages


def create_test_workflow(
    name: str,
    stage_count: int = 3,
    strategy: str = "sequential",
    with_dependencies: bool = False
) -> WorkflowDefinition:
    """Create a test workflow with specified parameters.

    Args:
        name: Workflow name
        stage_count: Number of stages
        strategy: Execution strategy
        with_dependencies: Whether stages have dependencies

    Returns:
        WorkflowDefinition object
    """
    stages = generate_test_stages(stage_count, with_dependencies)

    return WorkflowDefinition(
        name=name,
        description=f"Test workflow: {name}",
        stages=stages,
        strategy=strategy,
        timeout_seconds=300,
    )
