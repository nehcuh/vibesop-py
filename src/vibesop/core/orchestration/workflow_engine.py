"""WorkflowEngine — dynamic execution engine for Phase 3 patterns.

Routes to loop-until-dry or tournament based on plan's workflow pattern.
Provides runtime plan mutation — the execution graph changes based on
intermediate results.

Phase 3 (v6.2.0): Full Execution Dynamic
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from vibesop.core.models import (
    DynamicNodeStatus,
    ExecutionMode,
    ExecutionStep,
    PlanStatus,
    ReorchestrationDecision,
    StepStatus,
    TrustLevel,
    WorkflowPattern,
)

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan

logger = logging.getLogger(__name__)


@dataclass
class WorkflowEngineConfig:
    """Configuration for the dynamic workflow engine.

    Note: dry_threshold and max_reorchestration_rounds are stored on
    ExecutionPlan and read from there at runtime. This config holds
    engine-level settings only.
    """

    max_tournament_contestants: int = 3
    token_budget_multiplier: float = 3.0


class DynamicExecutionResult(BaseModel):
    """Result from dynamic execution via WorkflowEngine."""

    plan_id: str = Field(..., description="Plan ID")
    pattern: WorkflowPattern = Field(..., description="Pattern used")
    total_steps_executed: int = Field(default=0)
    reorchestration_rounds: int = Field(default=0)
    final_status: str = Field(default="completed")
    champion_index: int | None = Field(default=None, description="Tournament champion")
    results: dict[str, Any] = Field(default_factory=dict)
    reorchestration_history: list[dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "pattern": self.pattern.value,
            "total_steps_executed": self.total_steps_executed,
            "reorchestration_rounds": self.reorchestration_rounds,
            "final_status": self.final_status,
            "champion_index": self.champion_index,
            "results": self.results,
            "reorchestration_history": self.reorchestration_history,
        }


class WorkflowEngine:
    """Dynamic execution engine for LOOP_UNTIL_DRY, TOURNAMENT, and PROMPT_CHAIN patterns.

    Unlike the static ParallelScheduler which executes a pre-built plan,
    the WorkflowEngine re-evaluates after each step and can:
    - Append new steps when new work is discovered
    - Loop back to re-execute previous steps with feedback
    - Terminate early when all goals are met
    - Run tournaments with judge-selected champions
    - Generate prompt chain files for multi-agent workflows
    """

    def __init__(
        self,
        config: WorkflowEngineConfig | None = None,
        llm_client: Any = None,
        prompt_chain_output_dir: str = ".vibe/prompts",
    ):
        """Initialize the workflow engine.

        Args:
            config: Engine configuration
            llm_client: LLM client for re-orchestration analysis
            prompt_chain_output_dir: Output directory for prompt chain files
        """
        self._config = config or WorkflowEngineConfig()
        self._llm = llm_client
        self._prompt_chain_output_dir = prompt_chain_output_dir

    @staticmethod
    def is_dynamic(plan: ExecutionPlan) -> bool:
        """Check if a plan requires dynamic execution."""
        return plan.workflow_pattern in (
            WorkflowPattern.LOOP_UNTIL_DRY,
            WorkflowPattern.TOURNAMENT,
            WorkflowPattern.PROMPT_CHAIN,
        )

    def run(
        self,
        plan: ExecutionPlan,
        executor: Any,
    ) -> DynamicExecutionResult:
        """Execute a dynamic plan.

        Args:
            plan: Execution plan with dynamic pattern
            executor: Callable to execute each step

        Returns:
            DynamicExecutionResult with execution details
        """
        plan.status = PlanStatus.ACTIVE
        plan.is_dynamic = True

        if plan.workflow_pattern == WorkflowPattern.LOOP_UNTIL_DRY:
            return self._run_loop_until_dry(plan, executor)
        if plan.workflow_pattern == WorkflowPattern.TOURNAMENT:
            return self._run_tournament(plan, executor)
        if plan.workflow_pattern == WorkflowPattern.PROMPT_CHAIN:
            return self._run_prompt_chain(plan)

        # Fallback: treat as sequential
        return self._run_sequential(plan, executor)

    def _run_loop_until_dry(
        self,
        plan: ExecutionPlan,
        executor: Any,
    ) -> DynamicExecutionResult:
        """Execute LOOP_UNTIL_DRY pattern.

        Execute steps sequentially, re-orchestrating after each step.
        Continue until dry (no new discoveries) or max rounds exceeded.
        """
        from vibesop.core.orchestration.reorchestrator import Reorchestrator

        reorchestrator = Reorchestrator(self._llm) if self._llm else None
        results: dict[str, Any] = {}
        accumulated: dict[str, str] = {}
        dry_count = 0
        round_count = 0
        history: list[dict[str, Any]] = []

        step_idx = 0
        while step_idx < len(plan.steps):
            step = plan.steps[step_idx]
            if step.is_verification_step:
                step_idx += 1
                continue

            # Execute step
            step.status = StepStatus.IN_PROGRESS
            step.dynamic_status = DynamicNodeStatus.RUNNING

            try:
                output = executor(step)
                step.status = StepStatus.COMPLETED
                step.dynamic_status = DynamicNodeStatus.COMPLETED
                results[step.step_id] = output
                accumulated[step.output_as] = str(output) if output else ""
            except Exception as e:
                step.status = StepStatus.FAILED
                step.dynamic_status = DynamicNodeStatus.FAILED
                results[step.step_id] = {"error": str(e)}
                logger.warning("Dynamic step %s failed: %s", step.step_id, e)
                break

            # Re-orchestrate after each step
            if reorchestrator is not None and round_count < plan.max_reorchestration_rounds:
                round_count += 1
                analysis = reorchestrator.analyze(
                    plan, step, accumulated.get(step.output_as, ""), accumulated
                )

                history_entry = {
                    "round": round_count,
                    "step_id": step.step_id,
                    "decision": analysis.decision.value,
                    "reasoning": analysis.reasoning,
                }
                history.append(history_entry)

                if analysis.decision == ReorchestrationDecision.TERMINATE_EARLY:
                    logger.info("Loop-until-dry: terminating early after round %d", round_count)
                    break

                if analysis.decision == ReorchestrationDecision.ESCALATE:
                    logger.info("Loop-until-dry: escalating at round %d", round_count)
                    break

                if analysis.decision == ReorchestrationDecision.APPEND_STEPS:
                    dry_count = 0
                    new_steps = self._create_steps_from_analysis(plan, analysis.new_sub_tasks)
                    plan.steps.extend(new_steps)
                    logger.info("Appended %d new steps at round %d", len(new_steps), round_count)

                elif analysis.decision == ReorchestrationDecision.LOOP_BACK:
                    dry_count = 0
                    target_id = analysis.loop_target_step_id
                    target_step = next(
                        (s for s in plan.steps if s.step_id == target_id),
                        None,
                    )
                    if target_step:
                        target_step.status = StepStatus.PENDING
                        target_step.dynamic_status = DynamicNodeStatus.LOOPING
                        target_step.loop_iteration += 1
                        logger.info(
                            "Loop-until-dry: looping back to step %s (iteration %d)",
                            target_id,
                            target_step.loop_iteration,
                        )
                    else:
                        logger.warning("LOOP_BACK target step %s not found", target_id)

                else:
                    # CONTINUE or unknown — counts toward dry threshold
                    dry_count += 1

                if dry_count >= plan.dry_threshold:
                    logger.info("Loop-until-dry: dry after %d consecutive rounds", dry_count)
                    break

            step_idx += 1

        plan.status = PlanStatus.COMPLETED
        plan.reorchestration_history = history

        return DynamicExecutionResult(
            plan_id=plan.plan_id,
            pattern=WorkflowPattern.LOOP_UNTIL_DRY,
            total_steps_executed=sum(1 for s in plan.steps if s.status == StepStatus.COMPLETED),
            reorchestration_rounds=round_count,
            final_status="completed",
            results=results,
            reorchestration_history=history,
        )

    def _run_tournament(
        self,
        plan: ExecutionPlan,
        executor: Any,
    ) -> DynamicExecutionResult:
        """Execute TOURNAMENT pattern.

        Contestants run in parallel, then a judge selects the champion.
        """
        from vibesop.core.orchestration.tournament import TournamentResult, TournamentRunner

        contestant_steps = [s for s in plan.steps if not s.is_verification_step]
        results: dict[str, Any] = {}
        contestant_outputs: list[str] = []

        # Execute all contestant steps
        for step in contestant_steps:
            step.status = StepStatus.IN_PROGRESS
            step.dynamic_status = DynamicNodeStatus.RUNNING

            try:
                output = executor(step)
                step.status = StepStatus.COMPLETED
                step.dynamic_status = DynamicNodeStatus.COMPLETED
                results[step.step_id] = output
                contestant_outputs.append(str(output) if output else "")
            except Exception as e:
                step.status = StepStatus.FAILED
                step.dynamic_status = DynamicNodeStatus.FAILED
                results[step.step_id] = {"error": str(e)}
                contestant_outputs.append("")

        # Run tournament judge
        tournament_result = TournamentResult(champion_index=0)
        if self._llm and contestant_outputs:
            runner = TournamentRunner(self._llm)
            tournament_result = runner.run_tournament(
                plan.original_query,
                plan.steps[0].intent if plan.steps else "",
                contestant_outputs,
            )

        plan.status = PlanStatus.COMPLETED

        return DynamicExecutionResult(
            plan_id=plan.plan_id,
            pattern=WorkflowPattern.TOURNAMENT,
            total_steps_executed=len(contestant_steps),
            reorchestration_rounds=0,
            final_status="completed",
            champion_index=tournament_result.champion_index,
            results=results,
        )

    def _run_prompt_chain(
        self,
        plan: ExecutionPlan,
    ) -> DynamicExecutionResult:
        """Execute PROMPT_CHAIN pattern — generate prompt files, no live execution."""
        from vibesop.core.orchestration.prompt_chain_generator import PromptChainGenerator

        generator = PromptChainGenerator(
            llm_client=self._llm,
            output_dir=self._prompt_chain_output_dir,
        )
        prompt_files = generator.generate(plan)
        written = generator.write_files(prompt_files)

        plan.status = PlanStatus.COMPLETED

        results = {
            "prompt_files": [
                {"phase": pf.phase, "filename": pf.filename, "path": str(p)}
                for pf, p in zip(prompt_files, written)
            ],
        }

        return DynamicExecutionResult(
            plan_id=plan.plan_id,
            pattern=WorkflowPattern.PROMPT_CHAIN,
            total_steps_executed=0,
            reorchestration_rounds=0,
            final_status="prompts_generated",
            results=results,
        )

    def _run_sequential(
        self,
        plan: ExecutionPlan,
        executor: Any,
    ) -> DynamicExecutionResult:
        """Fallback sequential execution for dynamic plans."""
        results: dict[str, Any] = {}

        for step in plan.steps:
            step.status = StepStatus.IN_PROGRESS
            try:
                output = executor(step)
                step.status = StepStatus.COMPLETED
                results[step.step_id] = output
            except Exception as e:
                step.status = StepStatus.FAILED
                results[step.step_id] = {"error": str(e)}
                break

        plan.status = PlanStatus.COMPLETED

        return DynamicExecutionResult(
            plan_id=plan.plan_id,
            pattern=plan.workflow_pattern,
            total_steps_executed=sum(1 for s in plan.steps if s.status == StepStatus.COMPLETED),
            results=results,
        )

    def _create_steps_from_analysis(
        self,
        plan: ExecutionPlan,
        new_sub_tasks: list[dict[str, str]],
    ) -> list[ExecutionStep]:
        """Create new ExecutionSteps from reorchestration analysis."""
        steps = []
        next_number = max((s.step_number for s in plan.steps), default=0) + 1

        for task in new_sub_tasks:
            step = ExecutionStep(
                step_id=str(uuid.uuid4())[:8],
                step_number=next_number,
                skill_id="builtin/slash-orchestrate",
                intent=task.get("intent", ""),
                input_query=task.get("query", ""),
                original_query_segment=plan.original_query,
                output_as=f"appended_step_{next_number}_result",
                status=StepStatus.PENDING,
                dependencies=[],
                can_parallel=True,
                dynamic_status=DynamicNodeStatus.PENDING,
                loop_iteration=0,
            )
            steps.append(step)
            next_number += 1

        return steps
