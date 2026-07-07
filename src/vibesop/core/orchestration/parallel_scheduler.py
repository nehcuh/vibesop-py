"""Parallel scheduler for executing ExecutionPlan steps with dependencies.

This module provides the execution engine for parallel step execution,
handling topological sorting, dependency resolution, and result aggregation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from vibesop.core.models import StepStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from vibesop.core.models import ExecutionPlan, ExecutionStep

logger = logging.getLogger(__name__)


class ParallelScheduler:
    """Schedule and execute steps with parallel support.

    The scheduler analyzes the execution plan's dependency graph and
    executes independent steps in parallel while respecting dependencies.

    Example:
        >>> scheduler = ParallelScheduler()
        >>> async def execute_step(step):
        ...     # Your step execution logic
        ...     return f"Result of {step.skill_id}"
        >>> results = await scheduler.execute_plan(plan, execute_step)
    """

    def __init__(self, max_parallel: int = 5):
        """Initialize the parallel scheduler.

        Args:
            max_parallel: Maximum number of steps to run concurrently
        """
        self._max_parallel = max_parallel

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        executor: Callable[[ExecutionStep], Any],
    ) -> dict[str, Any]:
        """Execute plan with parallel steps.

        Args:
            plan: Execution plan with dependencies
            executor: Async function to execute a single step

        Returns:
            Dictionary with:
                - results: results in step_number order (includes {"error": ...}
                  for failed steps and {"skipped": ...} for steps whose
                  dependencies failed/skipped)
                - duration_ms: total execution time
                - steps_executed: steps actually dispatched (excludes skipped;
                  includes failed)
                - skipped: steps skipped due to a failed/skipped upstream
                  dependency (F-25)
                - parallel_batches: number of parallel batches
        """
        if not plan.steps:
            return {
                "results": [],
                "duration_ms": 0.0,
                "steps_executed": 0,
                "parallel_batches": 0,
            }

        start_time = time.time()

        # Get parallel groups from plan
        groups = plan.get_parallel_groups()

        results_map: dict[int, Any] = {}  # step_number -> result

        # F-25: index steps by id so we can detect failed/skipped dependencies
        # before dispatching each batch (avoids running downstream steps on
        # missing upstream output — the "silently-wrong success" bug).
        steps_by_id = {s.step_id: s for s in plan.steps}
        executed_count = 0
        skipped_count = 0

        for batch_num, group in enumerate(groups, 1):
            # F-25: skip steps whose dependencies FAILED or were SKIPPED in an
            # earlier batch. Otherwise they'd execute on empty upstream output
            # and produce results presented as success.
            ready_group: list[ExecutionStep] = []
            for step in group:
                if self._has_failed_dependency(step, steps_by_id):
                    step.status = StepStatus.SKIPPED
                    results_map[step.step_number] = {
                        "skipped": True,
                        "reason": "upstream dependency failed or was skipped",
                    }
                    skipped_count += 1
                    logger.info(
                        "Skipping step %s in batch %d: upstream dependency failed/skipped",
                        step.step_id,
                        batch_num,
                    )
                else:
                    ready_group.append(step)

            if not ready_group:
                logger.info("Batch %d fully skipped (all dependencies failed)", batch_num)
                continue

            executed_count += len(ready_group)
            logger.info("Executing batch %d with %d steps", batch_num, len(ready_group))

            # Wait for all tasks in this batch (with semaphore for max_parallel)
            if len(ready_group) > self._max_parallel:
                _semaphore = asyncio.Semaphore(self._max_parallel)

                async def limited_execute(
                    step: ExecutionStep, exec_fn: Any, _sem: asyncio.Semaphore = _semaphore
                ) -> Any:
                    async with _sem:
                        return await self._execute_with_tracking(step, exec_fn)

                batch_results = await asyncio.gather(
                    *(limited_execute(step, executor) for step in ready_group),
                    return_exceptions=True,
                )
            else:
                batch_tasks = [self._execute_with_tracking(step, executor) for step in ready_group]
                batch_results = await asyncio.gather(
                    *batch_tasks,
                    return_exceptions=True,
                )

            # Store results
            for step, result in zip(ready_group, batch_results, strict=True):
                if isinstance(result, Exception):
                    logger.error("Step %s failed: %s", step.step_id, result)
                    results_map[step.step_number] = {"error": str(result)}
                else:
                    results_map[step.step_number] = result

        duration_ms = (time.time() - start_time) * 1000

        # Convert results to step_number order
        ordered_results = [
            results_map.get(step.step_number)
            for step in plan.steps
            if step.step_number in results_map
        ]

        return {
            "results": ordered_results,
            "duration_ms": duration_ms,
            "steps_executed": executed_count,
            "skipped": skipped_count,
            "parallel_batches": len(groups),
        }

    async def _execute_with_tracking(
        self,
        step: ExecutionStep,
        executor: Callable[[ExecutionStep], Any],
    ) -> Any:
        """Execute a single step with status tracking.

        Args:
            step: Execution step to execute
            executor: Async executor function

        Returns:
            Step execution result
        """
        logger.debug("Executing step %s: %s", step.step_id, step.skill_id)
        step.status = StepStatus.IN_PROGRESS

        try:
            result = await executor(step)
            step.status = StepStatus.COMPLETED
            return result
        except Exception as e:
            step.status = StepStatus.FAILED
            logger.warning("Step %s failed: %s", step.step_id, e)
            raise

    @staticmethod
    def _has_failed_dependency(
        step: ExecutionStep,
        steps_by_id: dict[str, ExecutionStep],
    ) -> bool:
        """F-25: True if any of step's dependencies FAILED or was SKIPPED.

        A skipped dependency cascades transitively — if A fails, B (depends on
        A) is skipped, and C (depends on B) is skipped too.
        """
        for dep_id in step.dependencies:
            dep = steps_by_id.get(dep_id)
            if dep is not None and dep.status in (StepStatus.FAILED, StepStatus.SKIPPED):
                return True
        return False

    def get_execution_preview(self, plan: ExecutionPlan) -> dict[str, Any]:
        """Get preview of how execution will be parallelized.

        Args:
            plan: Execution plan to analyze

        Returns:
            Dictionary with execution preview including parallel groups
        """
        groups = plan.get_parallel_groups()

        return {
            "plan_id": plan.plan_id,
            "total_steps": len(plan.steps),
            "execution_mode": plan.execution_mode,
            "parallel_batches": len(groups),
            "max_parallel_steps": max(len(g) for g in groups) if groups else 0,
            "estimated_speedup": self._estimate_speedup(groups),
            "batches": [
                {
                    "batch_number": i + 1,
                    "step_count": len(group),
                    "steps": [
                        {
                            "step_number": s.step_number,
                            "skill_id": s.skill_id,
                            "intent": s.intent,
                        }
                        for s in group
                    ],
                }
                for i, group in enumerate(groups)
            ],
        }

    def _estimate_speedup(self, groups: list[list[ExecutionStep]]) -> float:
        """Estimate theoretical speedup from parallelization.

        Args:
            groups: Parallel groups from plan

        Returns:
            Estimated speedup factor (1.0 = no speedup)
        """
        if not groups:
            return 1.0

        # Assume each step takes unit time
        total_sequential_time = sum(len(g) for g in groups)
        total_parallel_time = len(groups)

        if total_parallel_time == 0:
            return 1.0

        speedup = total_sequential_time / total_parallel_time
        return min(speedup, total_sequential_time)  # Cap at theoretical max


def execute_plan_sync(
    plan: ExecutionPlan,
    executor: Callable[[ExecutionStep], Any],
    max_parallel: int = 5,
) -> dict[str, Any]:
    """Synchronous wrapper for parallel plan execution.

    This is a convenience function for code that doesn't use async/await.

    Args:
        plan: Execution plan with dependencies
        executor: Function to execute a single step (can be sync or async)
        max_parallel: Maximum concurrent steps

    Returns:
        Execution results dictionary

    Example:
        >>> def my_executor(step):
        ...     return f"Result: {step.skill_id}"
        >>> results = execute_plan_sync(plan, my_executor)
    """

    async def async_executor(step: ExecutionStep) -> Any:
        result = executor(step)
        if asyncio.iscoroutine(result):
            return await result
        return result

    scheduler = ParallelScheduler(max_parallel=max_parallel)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(scheduler.execute_plan(plan, async_executor))
