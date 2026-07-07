"""Tests for ParallelScheduler — async parallel step execution with dependencies."""

from __future__ import annotations

import pytest

from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
)
from vibesop.core.orchestration.parallel_scheduler import (
    ParallelScheduler,
    execute_plan_sync,
)


class TestParallelScheduler:
    """Core parallel scheduler tests."""

    def _make_plan(
        self,
        step_count: int = 3,
        execution_mode: ExecutionMode = ExecutionMode.PARALLEL,
    ) -> ExecutionPlan:
        steps = [
            ExecutionStep(
                step_id=f"s{i}",
                step_number=i,
                skill_id=f"skill_{i}",
                intent=f"intent_{i}",
            )
            for i in range(1, step_count + 1)
        ]
        return ExecutionPlan(
            plan_id="test-plan",
            original_query="test",
            steps=steps,
            execution_mode=execution_mode,
        )

    def _make_sequential_plan(self) -> ExecutionPlan:
        steps = [
            ExecutionStep(
                step_id="s1",
                step_number=1,
                skill_id="skill_1",
                dependencies=[],
            ),
            ExecutionStep(
                step_id="s2",
                step_number=2,
                skill_id="skill_2",
                dependencies=["s1"],
            ),
            ExecutionStep(
                step_id="s3",
                step_number=3,
                skill_id="skill_3",
                dependencies=["s2"],
            ),
        ]
        return ExecutionPlan(
            plan_id="test-plan",
            original_query="sequential test",
            steps=steps,
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

    @pytest.mark.anyio
    async def test_execute_empty_plan(self) -> None:
        scheduler = ParallelScheduler()
        plan = self._make_plan(step_count=0)

        async def fake_executor(step: ExecutionStep) -> str:
            return f"result_{step.skill_id}"

        result = await scheduler.execute_plan(plan, fake_executor)

        assert result["results"] == []
        assert result["steps_executed"] == 0
        assert result["parallel_batches"] == 0

    @pytest.mark.anyio
    async def test_execute_parallel_plan(self) -> None:
        scheduler = ParallelScheduler()
        plan = self._make_plan(step_count=3, execution_mode=ExecutionMode.PARALLEL)

        async def fake_executor(step: ExecutionStep) -> str:
            return f"result_{step.skill_id}"

        result = await scheduler.execute_plan(plan, fake_executor)

        assert result["steps_executed"] == 3
        assert len(result["results"]) == 3
        assert result["parallel_batches"] == 3  # 3 independent steps → 3 batches
        assert result["duration_ms"] >= 0

    @pytest.mark.anyio
    async def test_execute_sequential_plan(self) -> None:
        scheduler = ParallelScheduler()
        plan = self._make_sequential_plan()

        executed_order: list[str] = []

        async def fake_executor(step: ExecutionStep) -> str:
            executed_order.append(step.skill_id)
            return f"result_{step.skill_id}"

        result = await scheduler.execute_plan(plan, fake_executor)

        assert result["steps_executed"] == 3
        # Sequential plan — still executes in order
        assert executed_order == ["skill_1", "skill_2", "skill_3"]

    @pytest.mark.anyio
    async def test_max_parallel_limit(self) -> None:
        scheduler = ParallelScheduler(max_parallel=2)
        plan = self._make_plan(step_count=5, execution_mode=ExecutionMode.PARALLEL)

        async def fake_executor(step: ExecutionStep) -> str:
            return f"result_{step.skill_id}"

        result = await scheduler.execute_plan(plan, fake_executor)

        assert result["steps_executed"] == 5

    def test_sync_wrapper(self) -> None:
        plan = self._make_plan(step_count=2, execution_mode=ExecutionMode.PARALLEL)

        def fake_executor(step: ExecutionStep) -> str:
            return f"sync_result_{step.skill_id}"

        result = execute_plan_sync(plan, fake_executor)

        assert result["steps_executed"] == 2
        assert "sync_result_skill_1" in str(result["results"])
        assert "sync_result_skill_2" in str(result["results"])

    @pytest.mark.anyio
    async def test_executor_exception_handling(self) -> None:
        scheduler = ParallelScheduler()
        plan = self._make_plan(step_count=2, execution_mode=ExecutionMode.PARALLEL)

        async def failing_executor(step: ExecutionStep) -> str:
            if step.skill_id == "skill_1":
                raise ValueError("step 1 failed")
            return f"result_{step.skill_id}"

        result = await scheduler.execute_plan(plan, failing_executor)

        assert result["steps_executed"] == 2
        # Error should be captured, not raised
        assert isinstance(result["results"][0], dict)
        assert "error" in result["results"][0]

    def test_get_execution_preview(self) -> None:
        scheduler = ParallelScheduler()
        plan = self._make_plan(step_count=3, execution_mode=ExecutionMode.SEQUENTIAL)

        preview = scheduler.get_execution_preview(plan)

        assert preview["total_steps"] == 3
        assert preview["execution_mode"] == "sequential"
        assert preview["parallel_batches"] == 3
        assert "estimated_speedup" in preview
        assert len(preview["batches"]) == 3

    def test_get_execution_preview_parallel(self) -> None:
        scheduler = ParallelScheduler()
        plan = self._make_plan(step_count=4, execution_mode=ExecutionMode.PARALLEL)

        preview = scheduler.get_execution_preview(plan)

        assert preview["total_steps"] == 4
        assert preview["parallel_batches"] == 4  # All independent → 4 batches (one step each)

    def test_estimate_speedup(self) -> None:
        scheduler = ParallelScheduler()
        plan = self._make_plan(step_count=4, execution_mode=ExecutionMode.PARALLEL)

        preview = scheduler.get_execution_preview(plan)

        # 4 sequential steps vs 4 parallel batches → speedup of 1.0 (since each batch has 1 step)
        assert preview["estimated_speedup"] == 1.0

    def test_max_parallel_default(self) -> None:
        scheduler = ParallelScheduler()
        assert scheduler._max_parallel == 5

    @pytest.mark.anyio
    async def test_downstream_step_skipped_when_dependency_fails(self) -> None:
        """F-25: a step whose dependency failed must be SKIPPED, not executed.

        Previously the next batch ran unconditionally — downstream steps
        executed on missing upstream output and produced silently-wrong results.
        Cascade: s1 fails → s2 (dep s1) skipped → s3 (dep s2) skipped.
        """
        scheduler = ParallelScheduler()
        plan = ExecutionPlan(
            plan_id="test-f25",
            original_query="dep fail cascade",
            steps=[
                ExecutionStep(step_id="s1", step_number=1, skill_id="skill_1", dependencies=[]),
                ExecutionStep(step_id="s2", step_number=2, skill_id="skill_2", dependencies=["s1"]),
                ExecutionStep(step_id="s3", step_number=3, skill_id="skill_3", dependencies=["s2"]),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

        executed: list[str] = []

        async def failing_executor(step: ExecutionStep) -> str:
            executed.append(step.step_id)
            if step.step_id == "s1":
                raise ValueError("s1 failed")
            return f"result_{step.step_id}"

        result = await scheduler.execute_plan(plan, failing_executor)

        # Only s1 was dispatched (and failed); s2 and s3 skipped, not executed.
        assert executed == ["s1"]
        by_id = {s.step_id: s for s in plan.steps}
        assert by_id["s1"].status.value == "failed"
        assert by_id["s2"].status.value == "skipped"
        assert by_id["s3"].status.value == "skipped"  # transitive cascade

        # Result entries distinguish skipped from executed.
        assert isinstance(result["results"][0], dict) and "error" in result["results"][0]
        assert isinstance(result["results"][1], dict) and result["results"][1].get("skipped")
        assert isinstance(result["results"][2], dict) and result["results"][2].get("skipped")
        assert result["steps_executed"] == 1
        assert result["skipped"] == 2

    @pytest.mark.anyio
    async def test_partial_batch_skip_independent_sibling_still_runs(self) -> None:
        """F-25: in a multi-step batch, a step whose dep failed is skipped while
        an independent sibling whose dep completed still executes."""
        scheduler = ParallelScheduler()
        plan = ExecutionPlan(
            plan_id="test-f25-partial",
            original_query="partial batch skip",
            steps=[
                ExecutionStep(step_id="f", step_number=1, skill_id="fail_src", dependencies=[]),
                ExecutionStep(step_id="g", step_number=2, skill_id="ok_src", dependencies=[]),
                ExecutionStep(step_id="p", step_number=3, skill_id="dep_f", dependencies=["f"]),
                ExecutionStep(step_id="q", step_number=4, skill_id="dep_g", dependencies=["g"]),
            ],
            execution_mode=ExecutionMode.PARALLEL,
        )

        executed: list[str] = []

        async def executor(step: ExecutionStep) -> str:
            executed.append(step.step_id)
            if step.step_id == "f":
                raise ValueError("f failed")
            return f"ok-{step.step_id}"

        result = await scheduler.execute_plan(plan, executor)

        by_id = {s.step_id: s for s in plan.steps}
        assert by_id["f"].status.value == "failed"
        assert by_id["g"].status.value == "completed"
        assert by_id["p"].status.value == "skipped"  # dep f failed
        assert by_id["q"].status.value == "completed"  # dep g ok → still runs
        assert "p" not in executed
        assert set(executed) == {"f", "g", "q"}
        assert result["skipped"] == 1
        assert result["steps_executed"] == 3
