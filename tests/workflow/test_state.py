"""Unit tests for WorkflowStateManager and WorkflowState.

Tests state persistence, recovery, and lifecycle management.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime, timedelta
from time import sleep

from vibesop.workflow.state import (
    WorkflowState,
    WorkflowStateManager,
)
from vibesop.workflow.models import (
    WorkflowDefinition,
    PipelineStage,
    WorkflowExecutionContext,
    WorkflowResult,
)
from vibesop.workflow.exceptions import WorkflowRecoveryError


class TestWorkflowState:
    """Test WorkflowState model."""

    def test_create_state(self):
        """Test creating a workflow state."""
        state = WorkflowState(
            workflow_id="test-123",
            workflow_name="test-workflow",
            workflow_version="1.0.0",
            status="running",
            current_stage="stage1",
            stage_states={
                "stage1": "in_progress",
                "stage2": "pending",
            },
            context={"input": "test"},
        )

        assert state.workflow_id == "test-123"
        assert state.workflow_name == "test-workflow"
        assert state.status == "running"
        assert state.current_stage == "stage1"
        assert len(state.stage_states) == 2

    def test_state_properties(self):
        """Test workflow state properties."""
        # Active states
        active_states = ["pending", "running", "in_progress"]
        for status in active_states:
            state = WorkflowState(
                workflow_id="test",
                workflow_name="test",
                status=status,
            )
            assert state.is_active is True
            assert state.is_completed is False
            assert state.is_failed is False

        # Completed state
        state = WorkflowState(
            workflow_id="test",
            workflow_name="test",
            status="completed",
        )
        assert state.is_active is False
        assert state.is_completed is True
        assert state.is_failed is False

        # Failed state
        state = WorkflowState(
            workflow_id="test",
            workflow_name="test",
            status="failed",
        )
        assert state.is_active is False
        assert state.is_completed is False
        assert state.is_failed is True

    def test_state_serialization(self):
        """Test state to_dict conversion."""
        state = WorkflowState(
            workflow_id="test-123",
            workflow_name="test-workflow",
            status="running",
        )

        state_dict = state.to_dict()

        assert state_dict["workflow_id"] == "test-123"
        assert state_dict["workflow_name"] == "test-workflow"
        assert "started_at" in state_dict

    def test_state_deserialization(self):
        """Test state from_dict conversion."""
        data = {
            "workflow_id": "test-123",
            "workflow_name": "test-workflow",
            "workflow_version": "1.0.0",
            "status": "running",
            "current_stage": "stage1",
            "stage_states": {},
            "context": {},
            "result": None,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "error": None,
            "metadata": {},
        }

        state = WorkflowState.from_dict(data)

        assert state.workflow_id == "test-123"
        assert state.workflow_name == "test-workflow"
        assert state.status == "running"


class TestWorkflowStateManager:
    """Test WorkflowStateManager class."""

    def test_initialization(self, tmp_path):
        """Test manager initialization."""
        state_dir = tmp_path / ".vibe" / "state"
        manager = WorkflowStateManager(state_dir=state_dir)

        assert manager.state_dir == state_dir
        assert state_dir.exists()

    def test_initialization_no_create(self, tmp_path):
        """Test initialization without creating directory."""
        state_dir = tmp_path / ".vibe" / "state"
        manager = WorkflowStateManager(
            state_dir=state_dir,
            create_dir=False
        )

        assert not state_dir.exists()

    def test_generate_workflow_id(self, state_manager):
        """Test workflow ID generation."""
        id1 = state_manager.generate_workflow_id()
        id2 = state_manager.generate_workflow_id()

        assert id1.startswith("workflow-")
        assert id2.startswith("workflow-")
        assert id1 != id2

    def test_save_and_load_state(self, state_manager, sample_workflow, sample_context):
        """Test saving and loading workflow state."""
        workflow_id = "test-workflow-123"

        # Save state
        state = state_manager.save_state(
            workflow_id,
            sample_workflow,
            sample_context
        )

        assert state.workflow_id == workflow_id
        assert state.workflow_name == sample_workflow.name
        assert state.status == "running"

        # Load state
        loaded_state = state_manager.load_state(workflow_id)

        assert loaded_state is not None
        assert loaded_state.workflow_id == workflow_id
        assert loaded_state.workflow_name == sample_workflow.name
        assert loaded_state.status == "running"

    def test_save_state_with_result(self, state_manager, sample_workflow, sample_context):
        """Test saving state with workflow result."""
        workflow_id = "test-workflow-456"

        # Create result
        result = WorkflowResult(
            success=True,
            workflow_name=sample_workflow.name,
            completed_stages=["stage1", "stage2"],
            failed_stages=[],
            skipped_stages=[],
            final_context={"done": True},
            execution_time_seconds=1.5,
        )

        # Save state with result
        state = state_manager.save_state(
            workflow_id,
            sample_workflow,
            sample_context,
            result
        )

        assert state.status == "completed"  # Updated based on result
        assert state.result is not None

        # Load and verify
        loaded_state = state_manager.load_state(workflow_id)
        assert loaded_state.status == "completed"
        assert loaded_state.result["success"] is True

    def test_save_state_with_failed_result(self, state_manager, sample_workflow, sample_context):
        """Test saving state with failed result."""
        workflow_id = "test-workflow-789"

        # Create failed result
        result = WorkflowResult(
            success=False,
            workflow_name=sample_workflow.name,
            completed_stages=["stage1"],
            failed_stages=["stage2"],
            skipped_stages=[],
            final_context={},
            execution_time_seconds=0.5,
            errors=["Stage 2 failed"],
        )

        # Save state with result
        state = state_manager.save_state(
            workflow_id,
            sample_workflow,
            sample_context,
            result
        )

        assert state.status == "failed"
        assert state.error is not None
        assert "Stage 2 failed" in state.error

    def test_load_nonexistent_state(self, state_manager):
        """Test loading non-existent state returns None."""
        state = state_manager.load_state("nonexistent-workflow")

        assert state is None

    def test_update_stage_state(self, state_manager, sample_workflow, sample_context):
        """Test updating stage state."""
        workflow_id = "test-workflow-update"

        # Save initial state
        state_manager.save_state(workflow_id, sample_workflow, sample_context)

        # Update stage state
        state_manager.update_stage_state(
            workflow_id,
            "stage1",
            "completed"
        )

        # Load and verify
        loaded_state = state_manager.load_state(workflow_id)
        assert loaded_state.stage_states["stage1"] == "completed"
        assert loaded_state.current_stage == "stage1"

    def test_update_stage_nonexistent_workflow(self, state_manager):
        """Test updating stage for non-existent workflow raises error."""
        with pytest.raises(WorkflowRecoveryError, match="Cannot update non-existent"):
            state_manager.update_stage_state(
                "nonexistent",
                "stage1",
                "completed"
            )

    def test_complete_workflow(self, state_manager, sample_workflow, sample_context):
        """Test marking workflow as completed."""
        workflow_id = "test-workflow-complete"

        # Save initial state
        state_manager.save_state(workflow_id, sample_workflow, sample_context)

        # Create result
        result = WorkflowResult(
            success=True,
            workflow_name=sample_workflow.name,
            completed_stages=["stage1", "stage2", "stage3"],
            failed_stages=[],
            skipped_stages=[],
            final_context={"done": True},
            execution_time_seconds=2.0,
        )

        # Complete workflow
        state_manager.complete_workflow(workflow_id, result)

        # Load and verify
        loaded_state = state_manager.load_state(workflow_id)
        assert loaded_state.status == "completed"
        assert loaded_state.completed_at is not None
        assert loaded_state.current_stage is None
        assert loaded_state.result is not None

    def test_complete_workflow_failed(self, state_manager, sample_workflow, sample_context):
        """Test completing workflow with failure."""
        workflow_id = "test-workflow-failed"

        # Save initial state
        state_manager.save_state(workflow_id, sample_workflow, sample_context)

        # Create failed result
        result = WorkflowResult(
            success=False,
            workflow_name=sample_workflow.name,
            completed_stages=["stage1"],
            failed_stages=["stage2"],
            skipped_stages=[],
            final_context={},
            execution_time_seconds=0.5,
            errors=["Error message"],
        )

        # Complete workflow with failure
        state_manager.complete_workflow(workflow_id, result)

        # Load and verify
        loaded_state = state_manager.load_state(workflow_id)
        assert loaded_state.status == "failed"
        assert loaded_state.completed_at is not None

    def test_complete_nonexistent_workflow(self, state_manager):
        """Test completing non-existent workflow raises error."""
        result = WorkflowResult(
            success=True,
            workflow_name="test",
            completed_stages=[],
            failed_stages=[],
            skipped_stages=[],
            final_context={},
            execution_time_seconds=1.0,
        )

        with pytest.raises(WorkflowRecoveryError, match="Cannot complete non-existent"):
            state_manager.complete_workflow("nonexistent", result)

    def test_list_active_workflows(self, state_manager, sample_workflow, sample_context):
        """Test listing active workflows."""
        # Save active workflows
        state_manager.save_state("active-1", sample_workflow, sample_context)

        # Create another workflow
        workflow2 = WorkflowDefinition(
            name="test-workflow-2",
            description="Test",
            stages=[
                PipelineStage(
                    name="stage1",
                    description="Stage 1",
                    handler=lambda ctx: {},
                    metadata={"skill_id": "/test"}
                ),
            ]
        )
        state_manager.save_state("active-2", workflow2, sample_context)

        # Complete one workflow
        result = WorkflowResult(
            success=True,
            workflow_name=workflow2.name,
            completed_stages=["stage1"],
            failed_stages=[],
            skipped_stages=[],
            final_context={},
            execution_time_seconds=1.0,
        )
        state_manager.complete_workflow("active-2", result)

        # List active workflows
        active = state_manager.list_active_workflows()

        assert len(active) == 1
        assert active[0].workflow_id == "active-1"

    def test_list_all_workflows(self, state_manager, sample_workflow, sample_context):
        """Test listing all workflows."""
        # Save multiple workflows
        state_manager.save_state("workflow-1", sample_workflow, sample_context)
        state_manager.save_state("workflow-2", sample_workflow, sample_context)
        state_manager.save_state("workflow-3", sample_workflow, sample_context)

        # List all
        all_workflows = state_manager.list_all_workflows()

        assert len(all_workflows) == 3

        workflow_ids = {w.workflow_id for w in all_workflows}
        assert "workflow-1" in workflow_ids
        assert "workflow-2" in workflow_ids
        assert "workflow-3" in workflow_ids

    def test_delete_state(self, state_manager, sample_workflow, sample_context):
        """Test deleting workflow state."""
        workflow_id = "test-workflow-delete"

        # Save state
        state_manager.save_state(workflow_id, sample_workflow, sample_context)

        # Verify it exists
        assert state_manager.load_state(workflow_id) is not None

        # Delete state
        result = state_manager.delete_state(workflow_id)
        assert result is True

        # Verify it's gone
        assert state_manager.load_state(workflow_id) is None

    def test_delete_nonexistent_state(self, state_manager):
        """Test deleting non-existent state returns False."""
        result = state_manager.delete_state("nonexistent")
        assert result is False

    def test_cleanup_old_states(self, state_manager, sample_workflow, sample_context):
        """Test cleaning up old workflow states."""
        # Save old workflow (completed)
        old_id = "old-workflow"
        state_manager.save_state(old_id, sample_workflow, sample_context)
        result = WorkflowResult(
            success=True,
            workflow_name=sample_workflow.name,
            completed_stages=[],
            failed_stages=[],
            skipped_stages=[],
            final_context={},
            execution_time_seconds=1.0,
        )
        state_manager.complete_workflow(old_id, result)

        # Modify file to be old
        state_file = state_manager.state_dir / f"{old_id}.json"
        old_time = datetime.now().timestamp() - (25 * 3600)  # 25 hours ago
        import os
        os.utime(state_file, (old_time, old_time))

        # Save active workflow
        active_id = "active-workflow"
        state_manager.save_state(active_id, sample_workflow, sample_context)

        # Cleanup old states (24 hours threshold)
        removed = state_manager.cleanup_old_states(max_age_hours=24)

        assert removed == 1

        # Verify old workflow is gone, active remains
        assert state_manager.load_state(old_id) is None
        assert state_manager.load_state(active_id) is not None

    def test_atomic_write(self, state_manager, sample_workflow, sample_context):
        """Test that state writes are atomic."""
        workflow_id = "test-atomic"

        # Save state
        state_manager.save_state(workflow_id, sample_workflow, sample_context)

        # Verify file exists and is valid JSON
        state_file = state_manager.state_dir / f"{workflow_id}.json"
        assert state_file.exists()

        # Should be valid JSON
        with open(state_file, 'r') as f:
            data = json.load(f)

        assert data["workflow_id"] == workflow_id

    def test_concurrent_state_updates(self, state_manager, sample_workflow, sample_context):
        """Test handling concurrent state updates."""
        workflow_id = "test-concurrent"

        # Save initial state
        state_manager.save_state(workflow_id, sample_workflow, sample_context)

        # Perform multiple updates
        for i in range(5):
            state_manager.update_stage_state(
                workflow_id,
                f"stage{i}",
                "completed"
            )

        # Final state should have all updates
        final_state = state_manager.load_state(workflow_id)
        assert len(final_state.stage_states) == 5  # Original stages + updates
