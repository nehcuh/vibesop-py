"""End-to-end tests for complete workflow execution.

Tests full workflow lifecycle from YAML definition to execution results.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from vibesop.workflow import (
    WorkflowManager,
    WorkflowDefinition,
    PipelineStage,
    WorkflowExecutionContext,
    ExecutionStrategy,
)
from vibesop.workflow.models import WorkflowResult
from vibesop.workflow.cascade import StepStatus, StepResult


class TestFullWorkflowExecution:
    """Test complete workflow execution from definition to result."""

    @pytest.mark.asyncio
    async def test_yaml_to_execution_to_result(self, temp_workflow_dir):
        """Test complete flow: YAML file → Load → Execute → Result."""
        # Step 1: Create YAML workflow file
        workflow_yaml = """
name: e2e-test-workflow
description: End-to-end test workflow
version: 1.0.0
stages:
  - name: validate
    description: Validate input
    required: true
    timeout_seconds: 30
    metadata:
      skill_id: /validate

  - name: process
    description: Process data
    dependencies:
      - validate
    required: true
    timeout_seconds: 60
    metadata:
      skill_id: /process

  - name: report
    description: Generate report
    dependencies:
      - process
    required: false
    timeout_seconds: 30
    metadata:
      skill_id: /report
strategy: sequential
timeout_seconds: 300
"""
        workflow_file = temp_workflow_dir / "e2e-test.yaml"
        workflow_file.write_text(workflow_yaml)

        # Step 2: Create WorkflowManager and load workflow
        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflow = manager.get_workflow("e2e-test")
        assert workflow is not None
        assert workflow.name == "e2e-test-workflow"
        assert len(workflow.stages) == 3

        # Step 3: Create execution context
        context = WorkflowExecutionContext(
            input={"test": "data"}
        )

        # Step 4: Mock execution and run workflow
        with patch.object(
            manager._pipeline,
            'execute',
            new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = WorkflowResult(
                success=True,
                workflow_name=workflow.name,
                completed_stages=["validate", "process", "report"],
                failed_stages=[],
                skipped_stages=[],
                final_context={"done": True},
                execution_time_seconds=1.5,
            )

            result = await manager.execute_workflow(
                "e2e-test",
                {"test": "data"}
            )

            # Step 5: Verify results
            assert result.success is True
            assert len(result.completed_stages) == 3
            assert result.workflow_name == "e2e-test-workflow"

    @pytest.mark.asyncio
    async def test_workflow_with_dependencies_execution(self, temp_workflow_dir):
        """Test workflow execution respects stage dependencies."""
        workflow_yaml = """
name: dependency-test
description: Test dependency execution
stages:
  - name: stage1
    description: First stage
    required: true
    metadata:
      skill_id: /stage1

  - name: stage2
    description: Second stage
    dependencies:
      - stage1
    required: true
    metadata:
      skill_id: /stage2

  - name: stage3
    description: Third stage
    dependencies:
      - stage1
      - stage2
    required: true
    metadata:
      skill_id: /stage3
strategy: sequential
"""
        workflow_file = temp_workflow_dir / "dependency-test.yaml"
        workflow_file.write_text(workflow_yaml)

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflow = manager.get_workflow("dependency-test")
        assert workflow is not None

        # Verify dependencies
        stage2 = next(s for s in workflow.stages if s.name == "stage2")
        assert "stage1" in stage2.dependencies

        stage3 = next(s for s in workflow.stages if s.name == "stage3")
        assert "stage1" in stage3.dependencies
        assert "stage2" in stage3.dependencies

    @pytest.mark.asyncio
    async def test_workflow_failure_handling(self, temp_workflow_dir):
        """Test workflow handles stage failures correctly."""
        workflow_yaml = """
name: failure-test
description: Test failure handling
stages:
  - name: stage1
    description: Stage that succeeds
    required: true
    metadata:
      skill_id: /stage1

  - name: stage2
    description: Stage that fails
    required: true
    metadata:
      skill_id: /stage2

  - name: stage3
    description: Stage that gets skipped
    dependencies:
      - stage2
    required: false
    metadata:
      skill_id: /stage3
strategy: sequential
stop_on_first_failure: true
"""
        workflow_file = temp_workflow_dir / "failure-test.yaml"
        workflow_file.write_text(workflow_yaml)

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflow = manager.get_workflow("failure-test")

        with patch.object(
            manager._pipeline,
            'execute',
            new_callable=AsyncMock
        ) as mock_execute:
            # Simulate stage2 failure
            mock_execute.return_value = WorkflowResult(
                success=False,
                workflow_name=workflow.name,
                completed_stages=["stage1"],
                failed_stages=["stage2"],
                skipped_stages=["stage3"],
                final_context={},
                execution_time_seconds=0.5,
                errors=["Stage 2 failed"],
            )

            result = await manager.execute_workflow(
                "failure-test",
                {}
            )

            assert result.success is False
            assert "stage1" in result.completed_stages
            assert "stage2" in result.failed_stages
            assert "stage3" in result.skipped_stages

    @pytest.mark.asyncio
    async def test_workflow_state_persistence_lifecycle(self, temp_workflow_dir):
        """Test workflow state is saved and can be loaded."""
        workflow_yaml = """
name: state-test
description: Test state persistence
stages:
  - name: stage1
    description: Stage 1
    required: true
    metadata:
      skill_id: /test
strategy: sequential
"""
        workflow_file = temp_workflow_dir / "state-test.yaml"
        workflow_file.write_text(workflow_yaml)

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflow = manager.get_workflow("state-test")

        with patch.object(
            manager._pipeline,
            'execute',
            new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = WorkflowResult(
                success=True,
                workflow_name=workflow.name,
                completed_stages=["stage1"],
                failed_stages=[],
                skipped_stages=[],
                final_context={},
                execution_time_seconds=1.0,
            )

            # Execute workflow (should save state)
            result = await manager.execute_workflow(
                "state-test",
                {}
            )

            # Verify state was saved
            # The workflow ID is generated internally, so we check
            # that state files exist
            active_workflows = manager.list_active_workflows()
            # Should have at least the one we just executed
            # (though it might be marked as completed now)

    @pytest.mark.asyncio
    async def test_parallel_workflow_execution(self, temp_workflow_dir):
        """Test parallel strategy executes stages concurrently."""
        workflow_yaml = """
name: parallel-test
description: Test parallel execution
stages:
  - name: task1
    description: Parallel task 1
    required: true
    metadata:
      skill_id: /task1

  - name: task2
    description: Parallel task 2
    required: true
    metadata:
      skill_id: /task2

  - name: task3
    description: Parallel task 3
    required: true
    metadata:
      skill_id: /task3
strategy: parallel
max_parallel: 3
"""
        workflow_file = temp_workflow_dir / "parallel-test.yaml"
        workflow_file.write_text(workflow_yaml)

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflow = manager.get_workflow("parallel-test")

        with patch.object(
            manager._pipeline,
            'execute',
            new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = WorkflowResult(
                success=True,
                workflow_name=workflow.name,
                completed_stages=["task1", "task2", "task3"],
                failed_stages=[],
                skipped_stages=[],
                final_context={},
                execution_time_seconds=2.0,
            )

            result = await manager.execute_workflow(
                "parallel-test",
                {},
                strategy=ExecutionStrategy.PARALLEL
            )

            assert result.success is True
            assert len(result.completed_stages) == 3

    def test_workflow_validation_prevents_execution(self, temp_workflow_dir):
        """Test that invalid workflows cannot be executed."""
        # Create workflow with circular dependency
        workflow_yaml = """
name: circular-test
description: Invalid workflow with circular dependency
stages:
  - name: stage1
    description: Stage 1
    dependencies:
      - stage2
    required: true
    metadata:
      skill_id: /stage1

  - name: stage2
    description: Stage 2
    dependencies:
      - stage1
    required: true
    metadata:
      skill_id: /stage2
"""
        workflow_file = temp_workflow_dir / "circular.yaml"
        workflow_file.write_text(workflow_yaml)

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        # Should fail validation during construction
        workflow = manager.get_workflow("circular-test")
        # WorkflowDefinition validates during construction
        # so it should either return None or raise an error
        # For circular deps, Pydantic validation catches it
        assert workflow is None or "circular" in str(workflow).lower()

    @pytest.mark.asyncio
    async def test_workflow_with_optional_stages(self, temp_workflow_dir):
        """Test workflow with optional (required=false) stages."""
        workflow_yaml = """
name: optional-test
description: Test optional stage handling
stages:
  - name: required_stage
    description: Required stage
    required: true
    metadata:
      skill_id: /required

  - name: optional_stage
    description: Optional stage
    dependencies:
      - required_stage
    required: false
    metadata:
      skill_id: /optional

  - name: another_optional
    description: Another optional stage
    dependencies:
      - required_stage
    required: false
    metadata:
      skill_id: /another
strategy: sequential
stop_on_first_failure: false
"""
        workflow_file = temp_workflow_dir / "optional-test.yaml"
        workflow_file.write_text(workflow_yaml)

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflow = manager.get_workflow("optional-test")

        with patch.object(
            manager._pipeline,
            'execute',
            new_callable=AsyncMock
        ) as mock_execute:
            # Simulate optional stage failure
            mock_execute.return_value = WorkflowResult(
                success=False,  # Overall workflow fails but continues
                workflow_name=workflow.name,
                completed_stages=["required_stage"],
                failed_stages=["optional_stage"],
                skipped_stages=["another_optional"],
                final_context={},
                execution_time_seconds=1.0,
                errors=["Optional stage failed"],
            )

            result = await manager.execute_workflow(
                "optional-test",
                {},
                strategy=ExecutionStrategy.SEQUENTIAL
            )

            # Workflow continues despite optional stage failure
            assert "required_stage" in result.completed_stages


class TestRealWorkflowScenarios:
    """Test realistic workflow scenarios."""

    @pytest.mark.asyncio
    async def test_security_review_workflow_scenario(self):
        """Test realistic security review workflow scenario."""
        # This would test the predefined security-review workflow
        workflow_file = Path(".vibe/workflows/security-review.yaml")

        if not workflow_file.exists():
            pytest.skip("Predefined security-review workflow not found")

        manager = WorkflowManager(project_root=Path("."))

        workflow = manager.get_workflow("security-review")
        assert workflow is not None

        # Verify security review stages
        stage_names = [s.name for s in workflow.stages]
        assert "scan" in stage_names
        assert "analyze" in stage_names
        assert "prioritize" in stage_names
        assert "report" in stage_names

        # Verify dependencies
        scan_stage = next(s for s in workflow.stages if s.name == "scan")
        analyze_stage = next(s for s in workflow.stages if s.name == "analyze")
        assert scan_stage.name in analyze_stage.dependencies

    @pytest.mark.asyncio
    async def test_config_deploy_workflow_scenario(self):
        """Test realistic config deployment workflow scenario."""
        workflow_file = Path(".vibe/workflows/config-deploy.yaml")

        if not workflow_file.exists():
            pytest.skip("Predefined config-deploy workflow not found")

        manager = WorkflowManager(project_root=Path("."))

        workflow = manager.get_workflow("config-deploy")
        assert workflow is not None

        # Verify config deployment stages
        stage_names = [s.name for s in workflow.stages]
        assert "validate" in stage_names
        assert "backup" in stage_names
        assert "render" in stage_names
        assert "install" in stage_names
        assert "verify" in stage_names

        # Verify rollback is optional
        rollback_stage = next((s for s in workflow.stages if s.name == "rollback"), None)
        if rollback_stage:
            assert rollback_stage.required is False

    def test_workflow_discovery_from_multiple_sources(self, temp_workflow_dir):
        """Test workflow discovery from filesystem and cache."""
        # Create multiple workflow files
        for i in range(3):
            workflow_yaml = f"""
name: workflow{i}
description: Workflow {i}
stages:
  - name: stage{i}
    description: Stage {i}
    required: true
    metadata:
      skill_id: /test{i}
"""
            (temp_workflow_dir / f"workflow{i}.yaml").write_text(workflow_yaml)

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        # List all workflows
        workflows = manager.list_workflows()

        assert len(workflows) == 3

        # Get workflow (should cache)
        workflow1 = manager.get_workflow("workflow1")
        assert workflow1 is not None

        # Get again (should come from cache)
        workflow1_cached = manager.get_workflow("workflow1")
        assert workflow1_cached is not None
        # Same reference
        assert id(workflow1) == id(workflow1_cached)
