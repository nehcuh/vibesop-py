"""
Workflow management system.

This module provides high-level workflow management API,
following the SkillManager pattern for consistency.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from ruamel.yaml import YAML

from vibesop.workflow.models import (
    WorkflowDefinition,
    PipelineStage,
    WorkflowResult,
    WorkflowExecutionContext,
    ExecutionStrategy,
)
from vibesop.workflow.pipeline import WorkflowPipeline
from vibesop.workflow.state import WorkflowStateManager
from vibesop.workflow.exceptions import WorkflowError
from vibesop.core.config import ConfigLoader


class WorkflowManager:
    """High-level workflow management API.

    Follows the established SkillManager pattern for consistency.
    Provides workflow discovery, loading, and execution capabilities.

    Usage:
        >>> manager = WorkflowManager(project_root=Path("."))
        >>> workflows = manager.list_workflows()
        >>> result = await manager.execute_workflow("security-review", {"input": "test"})

    Attributes:
        project_root: Path to project root directory
        workflow_dir: Directory for workflow definitions
        _pipeline: WorkflowPipeline instance
        _config: ConfigLoader instance
        _workflow_cache: Workflow cache
    """

    def __init__(
        self,
        project_root: Path = Path("."),
        workflow_dir: Path = Path(".vibe/workflows"),
    ):
        """Initialize the workflow manager.

        Args:
            project_root: Path to project root directory
            workflow_dir: Directory for workflow definitions
        """
        self.project_root = Path(project_root).resolve()
        self.workflow_dir = workflow_dir
        self._pipeline = WorkflowPipeline(self.project_root)
        self._config = ConfigLoader(self.project_root)
        self._state_manager = WorkflowStateManager()
        self._workflow_cache: Dict[str, WorkflowDefinition] = {}
        self._yaml = YAML()

    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all available workflows.

        Returns:
            List of workflow metadata dictionaries
        """
        workflows = []

        # Load from filesystem
        if self.workflow_dir.exists():
            for workflow_file in self.workflow_dir.glob("*.yaml"):
                try:
                    workflow = self._load_workflow_from_file(workflow_file)
                    workflows.append({
                        "id": workflow.name,
                        "name": workflow.name,
                        "description": workflow.description,
                        "version": workflow.version,
                        "stages": len(workflow.stages),
                        "strategy": workflow.strategy,
                        "source": str(workflow_file)
                    })
                except Exception as e:
                    # Skip invalid workflows
                    import warnings
                    warnings.warn(f"Failed to load workflow from {workflow_file}: {e}")
                    continue

        # Load from core registry
        # TODO: Integrate with ConfigLoader.get_workflows()
        # core_workflows = self._config.get_workflows()
        # workflows.extend(core_workflows)

        return workflows

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Get workflow by ID.

        Args:
            workflow_id: Workflow identifier (name)

        Returns:
            WorkflowDefinition if found, None otherwise
        """
        # Check cache first
        if workflow_id in self._workflow_cache:
            return self._workflow_cache[workflow_id]

        # Try loading from various sources
        workflow = (
            self._load_from_filesystem(workflow_id) or
            self._load_from_builtin(workflow_id)
        )

        if workflow:
            self._workflow_cache[workflow_id] = workflow

        return workflow

    async def execute_workflow(
        self,
        workflow_id: str,
        input_data: Dict[str, Any],
        strategy: Optional[ExecutionStrategy] = None
    ) -> WorkflowResult:
        """Execute workflow by ID.

        Args:
            workflow_id: Workflow identifier (name)
            input_data: Input data for workflow
            strategy: Override execution strategy

        Returns:
            WorkflowResult with execution status

        Raises:
            WorkflowError: If workflow not found or execution fails
        """
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise WorkflowError(
                f"Workflow not found: {workflow_id}",
                workflow_name=workflow_id
            )

        context = WorkflowExecutionContext(input=input_data)

        if strategy is None:
            strategy = ExecutionStrategy(workflow.strategy)

        # Generate workflow ID for tracking
        workflow_id = self._state_manager.generate_workflow_id()

        # Save initial state
        self._state_manager.save_state(workflow_id, workflow, context)

        try:
            # Execute workflow
            result = await self._pipeline.execute(workflow, context, strategy)

            # Save final state
            self._state_manager.complete_workflow(workflow_id, result)

            return result

        except Exception as e:
            # Save error state
            error_result = WorkflowResult(
                success=False,
                workflow_name=workflow.name,
                completed_stages=[],
                failed_stages=[stage.name for stage in workflow.stages],
                skipped_stages=[],
                final_context=context.model_dump(),
                execution_time_seconds=0.0,
                errors=[str(e)]
            )
            self._state_manager.complete_workflow(workflow_id, error_result)

            raise WorkflowError(
                f"Workflow execution failed: {e}",
                workflow_name=workflow.name
            ) from e

    def resume_workflow(self, workflow_id: str) -> WorkflowResult:
        """Resume a previously interrupted workflow.

        Args:
            workflow_id: Workflow execution identifier

        Returns:
            WorkflowResult with execution status

        Raises:
            WorkflowRecoveryError: If workflow state not found or cannot be resumed
        """
        # Load workflow state
        state = self._state_manager.load_state(workflow_id)
        if not state:
            raise WorkflowRecoveryError(
                f"Workflow state not found: {workflow_id}",
                workflow_id=workflow_id
            )

        if not state.is_active:
            raise WorkflowRecoveryError(
                f"Workflow is not active (status: {state.status}): {workflow_id}",
                workflow_id=workflow_id
            )

        # Reload workflow definition
        workflow = self.get_workflow(state.workflow_name)
        if not workflow:
            raise WorkflowRecoveryError(
                f"Workflow definition not found: {state.workflow_name}",
                workflow_id=workflow_id
            )

        # Restore context
        context = WorkflowExecutionContext(**state.context)

        # TODO: Implement resume logic
        raise NotImplementedError(
            "Workflow resume functionality is not yet implemented. "
            "This requires tracking which stages have completed and "
            "continuing from the current stage."
        )

    def list_active_workflows(self) -> List[Dict[str, Any]]:
        """List all active workflow executions.

        Returns:
            List of active workflow metadata
        """
        active_states = self._state_manager.list_active_workflows()

        return [
            {
                "workflow_id": state.workflow_id,
                "workflow_name": state.workflow_name,
                "status": state.status,
                "current_stage": state.current_stage,
                "started_at": state.started_at.isoformat(),
            }
            for state in active_states
        ]

    def _load_workflow_from_file(self, file_path: Path) -> Optional[WorkflowDefinition]:
        """Load workflow definition from YAML file.

        Args:
            file_path: Path to YAML file

        Returns:
            WorkflowDefinition if valid, None otherwise
        """
        if not file_path.exists():
            return None

        try:
            with file_path.open('r') as f:
                data = self._yaml.load(f)

            # Convert stages
            stages = []
            for stage_data in data.get("stages", []):
                # Create PipelineStage
                stage = PipelineStage(
                    name=stage_data["name"],
                    description=stage_data["description"],
                    dependencies=stage_data.get("dependencies", []),
                    required=stage_data.get("required", True),
                    timeout_seconds=stage_data.get("timeout_seconds"),
                    retry_count=stage_data.get("retry_count", 0),
                    metadata=stage_data.get("metadata", {}),
                )
                stages.append(stage)

            # Create WorkflowDefinition
            workflow = WorkflowDefinition(
                name=data["name"],
                description=data["description"],
                version=data.get("version", "1.0.0"),
                stages=stages,
                strategy=data.get("strategy", "sequential"),
                timeout_seconds=data.get("timeout_seconds", 300),
                max_parallel=data.get("max_parallel", 3),
                stop_on_first_failure=data.get("stop_on_first_failure", True),
                metadata=data.get("metadata", {}),
            )

            return workflow

        except Exception as e:
            import warnings
            warnings.warn(f"Failed to load workflow from {file_path}: {e}")
            return None

    def _load_from_filesystem(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Load workflow from filesystem by ID.

        Args:
            workflow_id: Workflow identifier

        Returns:
            WorkflowDefinition if found, None otherwise
        """
        # Try loading from YAML files
        workflow_file = self.workflow_dir / f"{workflow_id}.yaml"
        return self._load_workflow_from_file(workflow_file)

    def _load_from_builtin(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Load builtin workflow by ID.

        Args:
            workflow_id: Workflow identifier

        Returns:
            WorkflowDefinition if found, None otherwise
        """
        # TODO: Implement builtin workflows
        # For now, return None
        return None


__all__ = [
    "WorkflowManager",
]
