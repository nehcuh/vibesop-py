"""
WorkflowPipeline - Core workflow orchestration engine.

This module provides the main workflow orchestration system,
integrating Pydantic v2 validation with the proven CascadeExecutor.
"""

from pathlib import Path
from typing import Any, Dict
import uuid
import asyncio

from vibesop.workflow.models import (
    WorkflowDefinition,
    WorkflowResult,
    WorkflowExecutionContext,
    ExecutionStrategy,
    PipelineStage,
)
from vibesop.workflow.exceptions import WorkflowError, StageError
from vibesop.workflow.cascade import CascadeExecutor, WorkflowConfig, WorkflowStep, StepStatus


class WorkflowPipeline:
    """Main workflow orchestration engine.

    Provides type-safe workflow execution using Pydantic v2 validation
    while leveraging proven CascadeExecutor for execution logic.

    Usage:
        >>> from pathlib import Path
        >>> pipeline = WorkflowPipeline(project_root=Path("."))
        >>> definition = WorkflowDefinition(
        ...     name="test-workflow",
        ...     description="Test workflow",
        ...     stages=[
        ...         PipelineStage(
        ...             name="stage1",
        ...             description="First stage",
        ...             handler=lambda ctx: {"result": "done"}
        ...         )
        ...     ]
        ... )
        >>> context = WorkflowExecutionContext(input={"data": "test"})
        >>> result = await pipeline.execute(definition, context)
        >>> assert result.success
    """

    def __init__(
        self,
        project_root: Path,
        skill_manager: Any | None = None,
        router: Any | None = None,
        state_dir: Path = Path(".vibe/state/workflows"),
    ):
        """Initialize the workflow pipeline.

        Args:
            project_root: Path to project root directory
            skill_manager: Optional SkillManager instance
            router: Optional SkillRouter instance
            state_dir: Directory for workflow state storage
        """
        self.project_root = Path(project_root).resolve()
        self._executor = CascadeExecutor()  # Reuse proven logic
        self._skill_manager = skill_manager
        self._router = router
        # TODO: Initialize WorkflowStateManager in next task

    async def execute(
        self,
        workflow: WorkflowDefinition,
        context: WorkflowExecutionContext,
        strategy: ExecutionStrategy | None = None
    ) -> WorkflowResult:
        """Execute a workflow with validation.

        Args:
            workflow: Workflow definition (Pydantic model)
            context: Execution context
            strategy: Override execution strategy

        Returns:
            WorkflowResult with execution status and outputs

        Raises:
            WorkflowError: If workflow execution fails
        """
        import time
        start_time = time.time()

        # 1. Validate workflow definition
        self._validate_workflow(workflow)

        # 2. Determine execution strategy
        if strategy is None:
            strategy = ExecutionStrategy(workflow.strategy)

        # 3. Convert to CascadeExecutor format
        cascade_config = self._to_cascade_config(workflow, context, strategy)

        # 4. Execute using CascadeExecutor
        try:
            step_results = await self._executor.execute(cascade_config)
            workflow_result = self._to_workflow_result(
                workflow, step_results, context, start_time
            )

            return workflow_result

        except Exception as e:
            # Handle failure
            execution_time = time.time() - start_time
            error_result = WorkflowResult(
                success=False,
                workflow_name=workflow.name,
                completed_stages=[],
                failed_stages=[stage.name for stage in workflow.stages],
                skipped_stages=[],
                final_context={},
                execution_time_seconds=execution_time,
                errors=[str(e)],
                metadata={"exception_type": type(e).__name__}
            )
            raise WorkflowError(f"Workflow execution failed: {e}") from e

    def _validate_workflow(self, workflow: WorkflowDefinition) -> None:
        """Validate workflow definition.

        Args:
            workflow: Workflow to validate

        Raises:
            WorkflowError: If workflow is invalid
        """
        if not workflow.stages:
            raise WorkflowError(f"Workflow '{workflow.name}' has no stages")

        # Check for duplicate stage names
        stage_names = [stage.name for stage in workflow.stages]
        if len(stage_names) != len(set(stage_names)):
            duplicates = [name for name in stage_names if stage_names.count(name) > 1]
            raise WorkflowError(
                f"Workflow '{workflow.name}' has duplicate stage names: {duplicates}"
            )

        # Validate all dependencies exist
        all_stage_names = set(stage_names)
        for stage in workflow.stages:
            for dep in stage.dependencies:
                if dep not in all_stage_names:
                    raise WorkflowError(
                        f"Stage '{stage.name}' depends on non-existent stage '{dep}'"
                    )

    def _to_cascade_config(
        self,
        workflow: WorkflowDefinition,
        context: WorkflowExecutionContext,
        strategy: ExecutionStrategy
    ) -> WorkflowConfig:
        """Convert WorkflowDefinition to WorkflowConfig.

        Args:
            workflow: Pydantic workflow definition
            context: Execution context
            strategy: Execution strategy

        Returns:
            WorkflowConfig for CascadeExecutor
        """
        # Convert PipelineStage to WorkflowStep
        workflow_steps = []
        for stage in workflow.stages:
            # Create async handler wrapper
            async def handler_wrapper(ctx: Dict[str, Any]) -> Dict[str, Any]:
                # Call the original handler
                if stage.handler:
                    result = stage.handler(ctx)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
                elif 'skill_id' in stage.metadata:
                    # TODO: Execute skill using SkillManager
                    return {"status": "executed", "skill": stage.metadata['skill_id']}
                else:
                    raise StageError(
                        f"Stage '{stage.name}' has no handler or skill_id",
                        stage_name=stage.name
                    )

            workflow_step = WorkflowStep(
                step_id=stage.name,
                name=stage.name,
                description=stage.description,
                handler=handler_wrapper,
                dependencies=stage.dependencies,
                timeout_seconds=stage.timeout_seconds or workflow.timeout_seconds,
                retry_count=stage.retry_count,
                continue_on_failure=not stage.required,
                enabled=True,
            )
            workflow_steps.append(workflow_step)

        # Create WorkflowConfig
        return WorkflowConfig(
            workflow_id=str(uuid.uuid4()),
            name=workflow.name,
            description=workflow.description,
            steps=workflow_steps,
            strategy=strategy.value,
            max_parallel=workflow.max_parallel,
            progress_tracker=None,  # TODO: Add progress tracking
            stop_on_first_failure=workflow.stop_on_first_failure,
        )

    def _to_workflow_result(
        self,
        workflow: WorkflowDefinition,
        step_results: Dict[str, Any],
        context: WorkflowExecutionContext,
        start_time: float
    ) -> WorkflowResult:
        """Convert CascadeExecutor results to WorkflowResult.

        Args:
            workflow: Original workflow definition
            step_results: Results from CascadeExecutor
            context: Execution context
            start_time: Execution start time

        Returns:
            WorkflowResult with execution status
        """
        import time

        execution_time = time.time() - start_time

        completed_stages = []
        failed_stages = []
        skipped_stages = []
        errors = []

        for stage_name, step_result in step_results.items():
            if step_result.status == StepStatus.COMPLETED:
                completed_stages.append(stage_name)
                # Store stage result in context
                context.update_stage_result(stage_name, step_result.output or {})
            elif step_result.status == StepStatus.FAILED:
                failed_stages.append(stage_name)
                if step_result.error:
                    errors.append(f"{stage_name}: {step_result.error}")
            elif step_result.status == StepStatus.SKIPPED:
                skipped_stages.append(stage_name)

        return WorkflowResult(
            success=len(failed_stages) == 0,
            workflow_name=workflow.name,
            completed_stages=completed_stages,
            failed_stages=failed_stages,
            skipped_stages=skipped_stages,
            final_context=context.model_dump(),
            execution_time_seconds=execution_time,
            errors=errors,
            metadata={
                "workflow_version": workflow.version,
                "total_stages": len(workflow.stages),
                "strategy": workflow.strategy,
            }
        )

    def _generate_workflow_id(self) -> str:
        """Generate unique workflow ID.

        Returns:
            Unique workflow identifier
        """
        return f"workflow-{uuid.uuid4()}"


__all__ = [
    "WorkflowPipeline",
]
