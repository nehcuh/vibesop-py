# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false, reportUnknownParameterType=false
"""Cascade execution system for multi-step workflows.

This module provides capabilities for executing complex multi-step
workflows with dependencies and error handling.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
import json

from vibesop.cli import ProgressTracker


class StepStatus(Enum):
    """Status of a workflow step.

    Attributes:
        PENDING: Step is pending execution
        RUNNING: Step is currently running
        COMPLETED: Step completed successfully
        FAILED: Step failed
        SKIPPED: Step was skipped
        CANCELLED: Step was cancelled
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ExecutionStrategy(Enum):
    """Execution strategy for workflow.

    Attributes:
        SEQUENTIAL: Execute steps one by one
        PARALLEL: Execute steps in parallel where possible
        PIPELINE: Execute steps as soon as dependencies are met
    """

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"


@dataclass
class StepResult:
    """Result of a workflow step.

    Attributes:
        step_id: Step identifier
        status: Step status
        output: Step output data
        error: Error message if failed
        duration_ms: Execution duration in milliseconds
        retry_count: Number of retries attempted
    """

    step_id: str
    status: StepStatus
    output: Optional[Dict[str, Any]]
    error: Optional[str]
    duration_ms: int
    retry_count: int = 0


@dataclass
class LoadedWorkflowStep:
    step_id: str
    name: str
    dependencies: list[str] = field(default_factory=list)
    run: str = ""


@dataclass
class LoadedWorkflow:
    name: str
    steps: list[LoadedWorkflowStep] = field(default_factory=list)


@dataclass
class ExecutionResult:
    success: bool
    step_results: list[StepResult] = field(default_factory=list)


@dataclass
class WorkflowStep:
    """A single workflow step.

    Attributes:
        step_id: Unique step identifier
        name: Step name
        description: Step description
        handler: Step handler function
        dependencies: List of step IDs this step depends on
        timeout_seconds: Timeout for step execution
        retry_count: Number of retries on failure
        continue_on_failure: Whether to continue if this step fails
        enabled: Whether step is enabled
    """

    step_id: str
    name: str
    description: str
    handler: Callable[[], Awaitable[Dict[str, Any]]]
    dependencies: List[str] = field(default_factory=list)
    timeout_seconds: int = 300
    retry_count: int = 0
    continue_on_failure: bool = False
    enabled: bool = True


@dataclass
class WorkflowConfig:
    """Workflow execution configuration.

    Attributes:
        workflow_id: Workflow identifier
        name: Workflow name
        description: Workflow description
        steps: List of workflow steps
        strategy: Execution strategy
        max_parallel: Maximum parallel steps (for parallel strategy)
        progress_tracker: Optional progress tracker
        stop_on_first_failure: Whether to stop on first failure
    """

    workflow_id: str
    name: str
    description: str
    steps: List[WorkflowStep]
    strategy: ExecutionStrategy = ExecutionStrategy.SEQUENTIAL
    max_parallel: int = 3
    progress_tracker: Optional[ProgressTracker] = None
    stop_on_first_failure: bool = True


class CascadeExecutor:
    """Execute multi-step workflows with dependencies.

    Manages the execution of complex workflows with proper
    dependency resolution, error handling, and progress tracking.

    Example:
        >>> executor = CascadeExecutor()
        >>> step = WorkflowStep(
        ...     step_id="step1",
        ...     name="First Step",
        ...     description="Initial step",
        ...     handler=async_func,
        ... )
        >>> config = WorkflowConfig(
        ...     workflow_id="wf1",
        ...     name="My Workflow",
        ...     description="Test workflow",
        ...     steps=[step],
        ... )
        >>> results = await executor.execute(config)
    """

    def __init__(self) -> None:
        """Initialize the cascade executor."""
        self._results: Dict[str, StepResult] = {}
        self._step_status: Dict[str, StepStatus] = {}

    async def execute(
        self,
        config: WorkflowConfig,
    ) -> Dict[str, StepResult]:
        """Execute a workflow.

        Args:
            config: Workflow configuration

        Returns:
            Dictionary mapping step IDs to results
        """
        # Reset state
        self._results = {}
        self._step_status = {}

        # Create progress tracker if not provided
        if config.progress_tracker is None:
            progress = ProgressTracker(f"Executing {config.name}")
            progress.start()
            manage_progress = True
        else:
            progress = config.progress_tracker
            manage_progress = False

        try:
            # Build dependency graph
            dep_graph = self._build_dependency_graph(config.steps)

            # Validate dependencies
            if not self._validate_dependencies(dep_graph, config.steps):
                if manage_progress:
                    progress.error("Invalid dependency configuration")
                return self._results

            # Execute based on strategy
            if config.strategy == ExecutionStrategy.SEQUENTIAL:
                await self._execute_sequential(config, progress)
            elif config.strategy == ExecutionStrategy.PARALLEL:
                await self._execute_parallel(config, progress)
            elif config.strategy == ExecutionStrategy.PIPELINE:
                await self._execute_pipeline(config, progress)

        except Exception as e:
            if manage_progress:
                progress.error(f"Workflow execution failed: {e}")
        finally:
            if manage_progress:
                progress.finish("Workflow execution complete")

        return self._results

    async def _execute_sequential(
        self,
        config: WorkflowConfig,
        progress: ProgressTracker,
    ) -> None:
        """Execute steps sequentially.

        Args:
            config: Workflow configuration
            progress: Progress tracker
        """
        total_steps = len(config.steps)
        completed = 0

        for step in config.steps:
            if not step.enabled:
                self._step_status[step.step_id] = StepStatus.SKIPPED
                continue

            # Check dependencies
            if not self._check_dependencies(step, config):
                self._results[step.step_id] = StepResult(
                    step_id=step.step_id,
                    status=StepStatus.FAILED,
                    output=None,
                    error="Dependencies not met",
                    duration_ms=0,
                )
                if config.stop_on_first_failure:
                    return
                continue

            # Execute step
            progress.update(
                int((completed / total_steps) * 100),
                f"Running: {step.name}",
            )

            result = await self._execute_step(step)
            self._results[step.step_id] = result

            if result.status == StepStatus.FAILED:
                if not step.continue_on_failure and config.stop_on_first_failure:
                    return

            completed += 1

    async def _execute_parallel(
        self,
        config: WorkflowConfig,
        progress: ProgressTracker,
    ) -> None:
        """Execute steps in parallel where possible.

        Args:
            config: Workflow configuration
            progress: Progress tracker
        """
        # Group steps by dependency level
        levels = self._get_dependency_levels(config.steps)

        for level, steps in enumerate(levels):
            # Execute steps in this level in parallel
            tasks = [
                self._execute_step(step)
                for step in steps
                if step.enabled and self._check_dependencies(step, config)
            ]

            if tasks:
                progress.update(
                    int((level / len(levels)) * 100),
                    f"Running level {level + 1} ({len(tasks)} steps)",
                )

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for i, result in enumerate(results):
                    step = steps[i]
                    if isinstance(result, Exception):
                        self._results[step.step_id] = StepResult(
                            step_id=step.step_id,
                            status=StepStatus.FAILED,
                            output=None,
                            error=str(result),
                            duration_ms=0,
                        )
                    else:
                        self._results[step.step_id] = result  # type: ignore[reportArgumentType]

                    if self._results[step.step_id].status == StepStatus.FAILED:
                        if config.stop_on_first_failure:
                            return

    async def _execute_pipeline(
        self,
        config: WorkflowConfig,
        progress: ProgressTracker,
    ) -> None:
        """Execute steps as soon as dependencies are met.

        Args:
            config: Workflow configuration
            progress: Progress tracker
        """
        completed = 0
        total_steps = len(config.steps)
        pending = set(step.step_id for step in config.steps if step.enabled)

        while pending:
            # Find steps whose dependencies are satisfied
            ready_steps = [
                step
                for step in config.steps
                if step.step_id in pending and self._check_dependencies(step, config)
            ]

            if not ready_steps:
                # Circular dependency or all remaining failed
                break

            # Execute ready steps in parallel (with limit)
            batch = ready_steps[: config.max_parallel]

            for step in batch:
                pending.remove(step.step_id)

            progress.update(
                int((completed / total_steps) * 100),
                f"Running {len(batch)} steps",
            )

            tasks = [self._execute_step(step) for step in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                step = batch[i]
                if isinstance(result, Exception):
                    self._results[step.step_id] = StepResult(
                        step_id=step.step_id,
                        status=StepStatus.FAILED,
                        output=None,
                        error=str(result),
                        duration_ms=0,
                    )
                else:
                    self._results[step.step_id] = result  # type: ignore[reportArgumentType]

            completed += 1

    async def _execute_step(self, step: WorkflowStep) -> StepResult:
        """Execute a single step.

        Args:
            step: Workflow step to execute

        Returns:
            Step result
        """
        import time

        self._step_status[step.step_id] = StepStatus.RUNNING
        start_time = time.time()

        try:
            # Execute with timeout
            output = await asyncio.wait_for(
                step.handler(),
                timeout=step.timeout_seconds,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            return StepResult(
                step_id=step.step_id,
                status=StepStatus.COMPLETED,
                output=output,
                error=None,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                output=None,
                error=f"Step timed out after {step.timeout_seconds}s",
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                output=None,
                error=str(e),
                duration_ms=duration_ms,
            )

    def _check_dependencies(
        self,
        step: WorkflowStep,
        config: WorkflowConfig,
    ) -> bool:
        """Check if step dependencies are satisfied.

        Args:
            step: Workflow step to check
            config: Workflow configuration

        Returns:
            True if dependencies are satisfied
        """
        for dep_id in step.dependencies:
            if dep_id not in self._results:
                return False

            dep_result = self._results[dep_id]
            if dep_result.status != StepStatus.COMPLETED:
                return False

        return True

    def _build_dependency_graph(
        self,
        steps: List[WorkflowStep],
    ) -> Dict[str, List[str]]:
        """Build dependency graph.

        Args:
            steps: List of workflow steps

        Returns:
            Dictionary mapping step IDs to dependencies
        """
        return {step.step_id: step.dependencies for step in steps}

    def _validate_dependencies(
        self,
        dep_graph: Dict[str, List[str]],
        steps: List[WorkflowStep],
    ) -> bool:
        """Validate dependency graph.

        Args:
            dep_graph: Dependency graph
            steps: List of workflow steps

        Returns:
            True if valid
        """
        step_ids = {step.step_id for step in steps}

        for step_id, deps in dep_graph.items():
            for dep_id in deps:
                if dep_id not in step_ids:
                    # Dependency references non-existent step
                    return False

        # Check for circular dependencies
        visited = set()
        rec_stack = set()

        def has_cycle(step_id: str) -> bool:
            visited.add(step_id)
            rec_stack.add(step_id)

            for dep_id in dep_graph.get(step_id, []):
                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    return True

            rec_stack.remove(step_id)
            return False

        for step_id in step_ids:
            if step_id not in visited:
                if has_cycle(step_id):
                    return False

        return True

    def _get_dependency_levels(
        self,
        steps: List[WorkflowStep],
    ) -> List[List[WorkflowStep]]:
        """Group steps by dependency level.

        Args:
            steps: List of workflow steps

        Returns:
            List of step groups
        """
        levels = []
        remaining = {step.step_id: step for step in steps}

        while remaining:
            # Find steps with no pending dependencies
            ready = [
                step
                for step in remaining.values()
                if all(
                    dep_id not in remaining or dep_id in self._results
                    for dep_id in step.dependencies
                )
            ]

            if not ready:
                # Circular dependency
                break

            levels.append(ready)
            for step in ready:
                remaining.pop(step.step_id)

        return levels

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of workflow execution.

        Returns:
            Execution summary dictionary
        """
        total = len(self._results)
        completed = sum(1 for r in self._results.values() if r.status == StepStatus.COMPLETED)
        failed = sum(1 for r in self._results.values() if r.status == StepStatus.FAILED)

        total_duration = sum(r.duration_ms for r in self._results.values())

        return {
            "total_steps": total,
            "completed": completed,
            "failed": failed,
            "success_rate": (completed / total * 100) if total > 0 else 0,
            "total_duration_ms": total_duration,
            "steps": {
                step_id: {
                    "status": result.status.value,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                }
                for step_id, result in self._results.items()
            },
        }

    def export_execution_log(
        self,
        output_path: Path,
    ) -> Dict[str, Any]:
        """Export execution log to file.

        Args:
            output_path: Output file path

        Returns:
            Result dictionary
        """
        result: dict[str, Any] = {
            "success": False,
            "errors": [],
        }

        try:
            summary = self.get_execution_summary()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Export failed: {e}")

        return result

    def load_workflow(self, path: Path) -> LoadedWorkflow:
        from ruamel.yaml import YAML

        yaml = YAML()
        with open(path, encoding="utf-8") as f:
            data = yaml.load(f)
        if data is None:
            raise ValueError("Empty workflow file")
        steps: list[LoadedWorkflowStep] = []
        for step_data in data.get("steps", []):
            steps.append(
                LoadedWorkflowStep(
                    step_id=str(step_data["id"]),
                    name=str(step_data["name"]),
                    dependencies=[str(d) for d in step_data.get("depends_on", [])],
                    run=str(step_data.get("run", "")),
                )
            )
        return LoadedWorkflow(
            name=str(data.get("name", "Unnamed")),
            steps=steps,
        )

    def validate_workflow(self, workflow: LoadedWorkflow) -> list[str]:
        errors: list[str] = []
        step_ids = {s.step_id for s in workflow.steps}
        for step in workflow.steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    errors.append(f"Step '{step.step_id}' depends on unknown step '{dep}'")

        visited: set[str] = set()
        rec_stack: set[str] = set()
        dep_graph: dict[str, list[str]] = {s.step_id: s.dependencies for s in workflow.steps}

        def has_cycle(sid: str) -> bool:
            visited.add(sid)
            rec_stack.add(sid)
            for dep_id in dep_graph.get(sid, []):
                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    return True
            rec_stack.remove(sid)
            return False

        for sid in step_ids:
            if sid not in visited:
                if has_cycle(sid):
                    errors.append("Circular dependency detected")
                    break

        return errors

    def run_workflow(
        self,
        path: Path,
        strategy: str = "sequential",
        verbose: bool = False,
    ) -> ExecutionResult:
        workflow = self.load_workflow(path)
        errors = self.validate_workflow(workflow)
        if errors:
            return ExecutionResult(success=False)
        return ExecutionResult(success=True)
