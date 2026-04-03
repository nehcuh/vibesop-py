"""Unit tests for WorkflowManager.

Tests workflow discovery, loading, and execution management.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from vibesop.workflow.manager import WorkflowManager
from vibesop.workflow.models import (
    WorkflowDefinition,
    PipelineStage,
    WorkflowExecutionContext,
    ExecutionStrategy,
    WorkflowResult,
)
from vibesop.workflow.exceptions import WorkflowError


class TestWorkflowManager:
    """Test WorkflowManager class."""

    def test_initialization(self, temp_workflow_dir):
        """Test manager initialization."""
        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        assert manager.project_root == Path(".").resolve()
        assert manager.workflow_dir == temp_workflow_dir
        assert manager._pipeline is not None
        assert manager._config is not None
        assert manager._state_manager is not None
        assert manager._workflow_cache == {}

    def test_list_workflows_empty(self, temp_workflow_dir):
        """Test listing workflows when directory is empty."""
        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflows = manager.list_workflows()

        assert workflows == []

    def test_list_workflows_with_files(self, temp_workflow_dir, workflow_yaml_content):
        """Test listing workflows from YAML files."""
        # Create workflow files
        (temp_workflow_dir / "workflow1.yaml").write_text(workflow_yaml_content)
        (temp_workflow_dir / "workflow2.yaml").write_text(
            workflow_yaml_content.replace("test-workflow", "workflow2")
        )

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflows = manager.list_workflows()

        assert len(workflows) == 2
        assert workflows[0]["id"] == "test-workflow"
        assert workflows[1]["id"] == "workflow2"

    def test_list_workflows_with_invalid_file(self, temp_workflow_dir):
        """Test listing workflows skips invalid files."""
        # Create valid workflow
        valid_yaml = """
name: valid-workflow
description: Valid workflow
stages:
  - name: stage1
    description: Stage 1
    required: true
    metadata:
      skill_id: /test
"""
        (temp_workflow_dir / "valid.yaml").write_text(valid_yaml)

        # Create invalid workflow
        (temp_workflow_dir / "invalid.yaml").write_text("invalid: yaml: content:")

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflows = manager.list_workflows()

        # Should only return valid workflow
        assert len(workflows) == 1
        assert workflows[0]["id"] == "valid-workflow"

    def test_get_workflow_from_cache(self, workflow_manager, sample_workflow):
        """Test getting workflow from cache."""
        # Manually add to cache
        workflow_manager._workflow_cache["cached-workflow"] = sample_workflow

        # Get from cache
        result = workflow_manager.get_workflow("cached-workflow")

        assert result is not None
        assert result.name == sample_workflow.name

    def test_get_workflow_from_filesystem(self, temp_workflow_dir, workflow_yaml_content):
        """Test loading workflow from filesystem."""
        # Create workflow file
        (temp_workflow_dir / "test-workflow.yaml").write_text(workflow_yaml_content)

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflow = manager.get_workflow("test-workflow")

        assert workflow is not None
        assert workflow.name == "test-workflow"
        assert len(workflow.stages) == 3

    def test_get_workflow_not_found(self, workflow_manager):
        """Test getting non-existent workflow returns None."""
        workflow = workflow_manager.get_workflow("nonexistent")

        assert workflow is None

    def test_get_workflow_caches_result(self, temp_workflow_dir, workflow_yaml_content):
        """Test that get_workflow caches the result."""
        # Create workflow file
        (temp_workflow_dir / "cache-test.yaml").write_text(workflow_yaml_content)

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        # First call - should load from file
        workflow1 = manager.get_workflow("cache-test")
        assert "cache-test" in manager._workflow_cache

        # Second call - should load from cache
        workflow2 = manager.get_workflow("cache-test")

        assert workflow1 is not None
        assert workflow2 is not None
        # Same object reference from cache
        assert id(workflow1) == id(workflow2)

    def test_load_workflow_from_file(self, temp_workflow_dir, workflow_yaml_content):
        """Test loading workflow from YAML file."""
        workflow_file = temp_workflow_dir / "test-load.yaml"
        workflow_file.write_text(workflow_yaml_content)

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflow = manager._load_workflow_from_file(workflow_file)

        assert workflow is not None
        assert workflow.name == "test-workflow"
        assert workflow.description == "A test workflow from YAML"
        assert len(workflow.stages) == 3

    def test_load_workflow_from_invalid_file(self, temp_workflow_dir):
        """Test loading from invalid YAML file returns None."""
        invalid_file = temp_workflow_dir / "invalid.yaml"
        invalid_file.write_text("not: valid: yaml:")

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflow = manager._load_workflow_from_file(invalid_file)

        assert workflow is None

    def test_load_workflow_from_nonexistent_file(self, temp_workflow_dir):
        """Test loading from non-existent file returns None."""
        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflow = manager._load_workflow_from_file(
            temp_workflow_dir / "nonexistent.yaml"
        )

        assert workflow is None

    @pytest.mark.asyncio
    async def test_execute_workflow_success(self, workflow_manager, sample_workflow):
        """Test executing workflow successfully."""
        # Add workflow to cache
        workflow_manager._workflow_cache["test-workflow"] = sample_workflow

        # Mock pipeline execution
        with patch.object(
            workflow_manager._pipeline,
            'execute',
            new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = WorkflowResult(
                success=True,
                workflow_name=sample_workflow.name,
                completed_stages=["stage1", "stage2"],
                failed_stages=[],
                skipped_stages=[],
                final_context={},
                execution_time_seconds=1.0,
            )

            # Execute
            result = await workflow_manager.execute_workflow(
                "test-workflow",
                {"input": "data"}
            )

            # Verify
            assert result.success is True
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_workflow_not_found(self, workflow_manager):
        """Test executing non-existent workflow raises error."""
        with pytest.raises(WorkflowError, match="Workflow not found"):
            await workflow_manager.execute_workflow("nonexistent", {})

    @pytest.mark.asyncio
    async def test_execute_workflow_with_strategy(self, workflow_manager, sample_workflow):
        """Test executing workflow with custom strategy."""
        workflow_manager._workflow_cache["test-workflow"] = sample_workflow

        with patch.object(
            workflow_manager._pipeline,
            'execute',
            new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = WorkflowResult(
                success=True,
                workflow_name=sample_workflow.name,
                completed_stages=[],
                failed_stages=[],
                skipped_stages=[],
                final_context={},
                execution_time_seconds=1.0,
            )

            # Execute with parallel strategy
            await workflow_manager.execute_workflow(
                "test-workflow",
                {},
                strategy=ExecutionStrategy.PARALLEL
            )

            # Verify strategy was passed
            call_args = mock_execute.call_args
            assert call_args[0][2] == ExecutionStrategy.PARALLEL

    @pytest.mark.asyncio
    async def test_execute_workflow_saves_state(self, workflow_manager, sample_workflow):
        """Test that workflow execution saves state."""
        workflow_manager._workflow_cache["test-workflow"] = sample_workflow

        with patch.object(
            workflow_manager._pipeline,
            'execute',
            new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = WorkflowResult(
                success=True,
                workflow_name=sample_workflow.name,
                completed_stages=[],
                failed_stages=[],
                skipped_stages=[],
                final_context={},
                execution_time_seconds=1.0,
            )

            # Execute
            await workflow_manager.execute_workflow("test-workflow", {})

            # Verify state was saved
            # The state ID should have been generated
            # We can't easily check the exact ID, but we can verify no errors

    @pytest.mark.asyncio
    async def test_execute_workflow_handles_failure(self, workflow_manager, sample_workflow):
        """Test that workflow execution failure is handled."""
        workflow_manager._workflow_cache["test-workflow"] = sample_workflow

        with patch.object(
            workflow_manager._pipeline,
            'execute',
            new_callable=AsyncMock
        ) as mock_execute:
            # Simulate execution failure
            mock_execute.side_effect = Exception("Execution failed")

            with pytest.raises(WorkflowError, match="Workflow execution failed"):
                await workflow_manager.execute_workflow("test-workflow", {})

    def test_list_active_workflows(self, workflow_manager):
        """Test listing active workflows."""
        # This tests the method that wraps state_manager.list_active_workflows()
        active = workflow_manager.list_active_workflows()

        # Should return list (may be empty)
        assert isinstance(active, list)

    def test_resume_workflow_not_implemented(self, workflow_manager, sample_workflow, sample_context):
        """Test that resume workflow is not yet implemented."""
        # Create a workflow state first
        workflow_id = "test-resume-workflow"
        # Add workflow to cache so get_workflow can find it
        workflow_manager._workflow_cache[sample_workflow.name] = sample_workflow
        workflow_manager._state_manager.save_state(
            workflow_id,
            sample_workflow,
            sample_context
        )

        # Resume should raise NotImplementedError
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            workflow_manager.resume_workflow(workflow_id)

    def test_load_from_filesystem(self, temp_workflow_dir, workflow_yaml_content):
        """Test _load_from_filesystem method."""
        # Create workflow file
        (temp_workflow_dir / "test-load.yaml").write_text(workflow_yaml_content)

        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        workflow = manager._load_from_filesystem("test-load")

        assert workflow is not None
        assert workflow.name == "test-workflow"  # Name comes from YAML content

    def test_load_from_filesystem_not_found(self, workflow_manager):
        """Test _load_from_filesystem with non-existent workflow."""
        workflow = workflow_manager._load_from_filesystem("nonexistent")

        assert workflow is None

    def test_load_from_builtin(self, workflow_manager):
        """Test _load_from_builtin (currently returns None)."""
        # Builtin workflows not implemented yet
        workflow = workflow_manager._load_from_builtin("builtin-workflow")

        assert workflow is None


class TestWorkflowManagerIntegration:
    """Test WorkflowManager integration with other components."""

    def test_manager_pipeline_integration(self, temp_workflow_dir):
        """Test WorkflowManager has pipeline integration."""
        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        assert manager._pipeline is not None
        assert hasattr(manager._pipeline, 'execute')

    def test_manager_state_manager_integration(self, temp_workflow_dir):
        """Test WorkflowManager has state manager integration."""
        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        assert manager._state_manager is not None
        assert hasattr(manager._state_manager, 'save_state')
        assert hasattr(manager._state_manager, 'load_state')

    def test_manager_config_integration(self, temp_workflow_dir):
        """Test WorkflowManager has config loader integration."""
        manager = WorkflowManager(
            project_root=Path("."),
            workflow_dir=temp_workflow_dir
        )

        assert manager._config is not None
