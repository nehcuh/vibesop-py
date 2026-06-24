"""WorkflowEngine — dynamic execution engine for Phase 3 patterns.

Routes to loop-until-dry or tournament based on plan's workflow pattern.
Provides runtime plan mutation — the execution graph changes based on
intermediate results.

Phase 3 (v6.2.0): Full Execution Dynamic
Phase 4 (v7.1.0): Agent squad/debate/red-team execution
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from vibesop.core.models import (
    AgentSquad,
    DynamicNodeStatus,
    ExecutionStep,
    PlanStatus,
    ReorchestrationDecision,
    StepStatus,
    WorkflowPattern,
)

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan

logger = logging.getLogger(__name__)

# Safety cap on how many times a single step may be re-executed via LOOP_BACK.
# The primary bound is ``plan.max_reorchestration_rounds`` (caps total analyses);
# this guards a single step against a runaway loop-back decision.
MAX_LOOP_ITERATIONS = 5


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


class SquadExecutionResult(BaseModel):
    """Result from executing an agent squad workflow."""

    model_config = {"arbitrary_types_allowed": True}

    squad: AgentSquad = Field(..., description="Executed agent squad")
    plan: Any = Field(..., description="Source execution plan")
    output: dict[str, Any] = Field(default_factory=dict, description="Outputs keyed by step_id")
    agent_outputs: dict[str, Any] = Field(
        default_factory=dict, description="Alias for output (agent-centric view)"
    )
    duration_ms: float = Field(default=0.0, description="Execution duration in milliseconds")
    rounds_executed: int = Field(default=0, description="Number of rounds executed")
    verdicts: list[Any] = Field(default_factory=list, description="Review verdicts collected")

    def to_dict(self) -> dict[str, Any]:
        return {
            "squad": self.squad.to_dict(),
            "plan_id": self.plan.plan_id,
            "output": self.output,
            "agent_outputs": self.agent_outputs,
            "duration_ms": self.duration_ms,
            "rounds_executed": self.rounds_executed,
            "verdicts": [v.to_dict() if hasattr(v, "to_dict") else v for v in self.verdicts],
        }


class WorkflowEngine:
    """Dynamic execution engine for LOOP_UNTIL_DRY, TOURNAMENT, PROMPT_CHAIN,
    and squad-oriented patterns (AGENT_SQUAD, DEBATE, RED_TEAM).

    Unlike the static ParallelScheduler which executes a pre-built plan,
    the WorkflowEngine re-evaluates after each step and can:
    - Append new steps when new work is discovered
    - Loop back to re-execute previous steps with feedback
    - Terminate early when all goals are met
    - Run tournaments with judge-selected champions
    - Generate prompt chain files for multi-agent workflows
    - Execute multi-role agent squads with handoff and review gates
    """

    def __init__(
        self,
        config: WorkflowEngineConfig | None = None,
        llm_client: Any = None,
        prompt_chain_output_dir: str = ".vibe/prompts",
        router: Any = None,
    ):
        """Initialize the workflow engine.

        Args:
            config: Engine configuration
            llm_client: LLM client for re-orchestration analysis and squad reviews
            prompt_chain_output_dir: Output directory for prompt chain files
            router: Optional router for routing appended steps to real skills
        """
        self._config = config or WorkflowEngineConfig()
        self._llm = llm_client
        self._prompt_chain_output_dir = prompt_chain_output_dir
        self._router = router
        self._start_time: float = 0.0

    @staticmethod
    def is_dynamic(plan: ExecutionPlan) -> bool:
        """Check if a plan requires dynamic execution."""
        return plan.workflow_pattern in (
            WorkflowPattern.LOOP_UNTIL_DRY,
            WorkflowPattern.TOURNAMENT,
            WorkflowPattern.PROMPT_CHAIN,
            WorkflowPattern.AGENT_SQUAD,
            WorkflowPattern.DEBATE,
            WorkflowPattern.RED_TEAM,
        )

    def run(
        self,
        plan: ExecutionPlan,
        executor: Any,
        context: dict[str, Any] | None = None,
    ) -> DynamicExecutionResult | SquadExecutionResult:
        """Execute a dynamic plan.

        Args:
            plan: Execution plan with dynamic pattern
            executor: Callable to execute each step
            context: Optional execution context for squad patterns

        Returns:
            DynamicExecutionResult or SquadExecutionResult with execution details
        """
        plan.status = PlanStatus.ACTIVE
        plan.is_dynamic = True

        if plan.workflow_pattern in (
            WorkflowPattern.AGENT_SQUAD,
            WorkflowPattern.DEBATE,
            WorkflowPattern.RED_TEAM,
        ):
            try:
                return asyncio.run(self.run_async(plan, context=context, executor=executor))
            except RuntimeError as e:
                if "cannot be called from a running event loop" in str(e):
                    raise RuntimeError(
                        "Squad patterns must be run with await engine.run_async() "
                        "when called from an async context"
                    ) from e
                raise

        if plan.workflow_pattern == WorkflowPattern.LOOP_UNTIL_DRY:
            return self._run_loop_until_dry(plan, executor)
        if plan.workflow_pattern == WorkflowPattern.TOURNAMENT:
            return self._run_tournament(plan, executor)
        if plan.workflow_pattern == WorkflowPattern.PROMPT_CHAIN:
            return self._run_prompt_chain(plan)

        # Fallback: treat as sequential
        return self._run_sequential(plan, executor)

    async def run_async(
        self,
        plan: ExecutionPlan,
        context: dict[str, Any] | None = None,
        executor: Any | None = None,
    ) -> SquadExecutionResult:
        """Async entry point for squad-oriented patterns.

        Args:
            plan: Execution plan with squad pattern
            context: Optional execution context passed to each step
            executor: Optional callable(step, context) -> Any to execute steps

        Returns:
            SquadExecutionResult with squad execution details
        """
        plan.status = PlanStatus.ACTIVE
        plan.is_dynamic = True
        context = context or {}

        pattern = plan.workflow_pattern
        if pattern == WorkflowPattern.AGENT_SQUAD:
            return await self._run_agent_squad(plan, context, executor)
        if pattern == WorkflowPattern.DEBATE:
            return await self._run_debate(plan, context, executor)
        if pattern == WorkflowPattern.RED_TEAM:
            return await self._run_red_team(plan, context, executor)

        raise ValueError(f"Pattern {pattern.value} is not a squad pattern")

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
        # Degraded path: with no LLM the full reorchestration analysis is
        # unavailable. We still expose the goals-met fast path so the loop can
        # terminate early, and record a marker so callers know degradation
        # occurred (APPEND_STEPS / LOOP_BACK require LLM analysis).
        degraded = self._llm is None
        rule_checker = Reorchestrator(None) if degraded else None
        if degraded:
            logger.warning(
                "LOOP_UNTIL_DRY: no LLM configured — reorchestration degraded to "
                "goals-met check only; APPEND_STEPS and LOOP_BACK will not trigger."
            )
        results: dict[str, Any] = {}
        accumulated: dict[str, str] = {}
        dry_count = 0
        round_count = 0
        history: list[dict[str, Any]] = []
        if degraded:
            history.append(
                {
                    "round": -1,
                    "step_id": "",
                    "decision": "degraded",
                    "reasoning": "No LLM configured — APPEND_STEPS/LOOP_BACK unavailable",
                }
            )

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
                    target_idx = next(
                        (i for i, s in enumerate(plan.steps) if s.step_id == target_id),
                        None,
                    )
                    # Rewind to the current or an earlier step. The tail
                    # ``step_idx += 1`` then advances onto target_idx, so we
                    # set the cursor to ``target_idx - 1`` (valid even for
                    # target_idx == 0, since the increment runs this iteration).
                    if (
                        target_idx is not None
                        and target_idx <= step_idx
                        and plan.steps[target_idx].loop_iteration < MAX_LOOP_ITERATIONS
                    ):
                        target_step = plan.steps[target_idx]
                        target_step.status = StepStatus.PENDING
                        target_step.dynamic_status = DynamicNodeStatus.LOOPING
                        target_step.loop_iteration += 1
                        step_idx = target_idx - 1
                        logger.info(
                            "Loop-until-dry: looping back to step %s (iteration %d)",
                            target_id,
                            target_step.loop_iteration,
                        )
                    else:
                        logger.warning(
                            "LOOP_BACK to step %s skipped (not found, ahead of cursor, "
                            "or iteration cap %d reached)",
                            target_id,
                            MAX_LOOP_ITERATIONS,
                        )

                else:
                    # CONTINUE or unknown — counts toward dry threshold
                    dry_count += 1

                if dry_count >= plan.dry_threshold:
                    logger.info("Loop-until-dry: dry after %d consecutive rounds", dry_count)
                    break

            elif rule_checker is not None:
                # Degraded (no LLM): only the goals-met fast path is available.
                # APPEND_STEPS / LOOP_BACK require LLM analysis and are skipped.
                if rule_checker.goals_met(plan, accumulated):
                    logger.info("Loop-until-dry (degraded): all goals met, terminating early")
                    history.append(
                        {
                            "round": -1,
                            "step_id": step.step_id,
                            "decision": "terminate_early",
                            "reasoning": "degraded goals-met (no LLM)",
                        }
                    )
                    break
                dry_count += 1
                if dry_count >= plan.dry_threshold:
                    logger.info("Loop-until-dry (degraded): dry after %d rounds", dry_count)
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

        Contestants run in parallel via a thread pool, then a judge selects
        the champion. Without an LLM, a rubric-style heuristic picks the
        champion instead of defaulting to the first contestant.
        """
        from vibesop.core.orchestration.tournament import TournamentResult, TournamentRunner

        contestant_steps = [s for s in plan.steps if not s.is_verification_step]
        results: dict[str, Any] = {}
        # Pre-size so each contestant writes its own slot by index, preserving
        # the contestant-order ↔ output-index correspondence the judge relies on.
        contestant_outputs: list[str] = [""] * len(contestant_steps)

        def run_contestant(step: ExecutionStep) -> Any:
            """Execute one contestant; mutate its status, propagate errors."""
            step.status = StepStatus.IN_PROGRESS
            step.dynamic_status = DynamicNodeStatus.RUNNING
            try:
                output = executor(step)
                step.status = StepStatus.COMPLETED
                step.dynamic_status = DynamicNodeStatus.COMPLETED
                return output
            except Exception:
                step.status = StepStatus.FAILED
                step.dynamic_status = DynamicNodeStatus.FAILED
                raise

        # Execute all contestants in parallel; each worker mutates its own step.
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, len(contestant_steps))
        ) as pool:
            future_to_idx = {
                pool.submit(run_contestant, step): idx
                for idx, step in enumerate(contestant_steps)
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                step = contestant_steps[idx]
                try:
                    output = future.result()
                    results[step.step_id] = output
                    contestant_outputs[idx] = str(output) if output else ""
                except Exception as e:
                    results[step.step_id] = {"error": str(e)}
                    contestant_outputs[idx] = ""

        # Select champion: LLM judge when available, heuristic fallback otherwise.
        if self._llm and contestant_outputs:
            runner = TournamentRunner(self._llm)
            tournament_result = runner.run_tournament(
                plan.original_query,
                plan.steps[0].intent if plan.steps else "",
                contestant_outputs,
            )
        elif contestant_outputs:
            tournament_result = self._heuristic_tournament(contestant_outputs)
        else:
            tournament_result = TournamentResult(champion_index=0)

        plan.status = PlanStatus.COMPLETED

        return DynamicExecutionResult(
            plan_id=plan.plan_id,
            pattern=WorkflowPattern.TOURNAMENT,
            total_steps_executed=sum(
                1 for s in contestant_steps if s.status == StepStatus.COMPLETED
            ),
            reorchestration_rounds=0,
            final_status="completed",
            champion_index=tournament_result.champion_index,
            results=results,
        )

    @staticmethod
    def _heuristic_tournament(contestant_outputs: list[str]) -> Any:
        """Pick a champion without an LLM using a lightweight rubric.

        Scores each output on substance (length), vocabulary diversity, code
        presence, and structural keywords. Ties resolve to the earliest index.
        """
        from vibesop.core.orchestration.tournament import TournamentResult

        scores: list[float] = []
        for raw in contestant_outputs:
            text = raw or ""
            lowered = text.lower()
            score = 0.0
            if len(text) > 50:
                score += 0.3
            if len(set(lowered.split())) > 20:
                score += 0.3
            if "```" in text:
                score += 0.2
            if any(kw in lowered for kw in ("step", "result", "conclusion")):
                score += 0.2
            scores.append(score)

        champion_index = max(range(len(scores)), key=lambda i: scores[i]) if scores else 0
        return TournamentResult(
            champion_index=champion_index,
            champion_output=contestant_outputs[champion_index] if contestant_outputs else "",
            scores={i: scores[i] for i in range(len(scores))},
            comparison_reasoning="Heuristic fallback (no LLM configured)",
            all_outputs=contestant_outputs,
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
                for pf, p in zip(prompt_files, written, strict=False)
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
            intent = task.get("intent", "")
            query = task.get("query", "")
            step = ExecutionStep(
                step_id=str(uuid.uuid4())[:8],
                step_number=next_number,
                skill_id=self._route_appended_skill(query, intent),
                intent=intent,
                input_query=query,
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

    def _route_appended_skill(self, query: str, intent: str) -> str:
        """Route an appended sub-task to a real skill via the configured router.

        Falls back to ``builtin/slash-orchestrate`` when no router is configured
        or routing fails, matching the prior hard-coded behaviour.
        """
        default = "builtin/slash-orchestrate"
        route_method = getattr(self._router, "_single_skill_route", None) if self._router else None
        if route_method is None:
            return default
        try:
            route = route_method(query)
            primary = getattr(route, "primary", None)
            skill_id = getattr(primary, "skill_id", None) if primary else None
            if skill_id:
                logger.info("APPEND step routed to %s for intent=%s", skill_id, intent)
                return skill_id
        except Exception as e:
            logger.warning("APPEND step routing failed for intent=%s: %s", intent, e)
        return default

    # ── Phase 4: Agent squad executors ───────────────────────────────────────

    async def _run_agent_squad(
        self,
        plan: ExecutionPlan,
        context: dict[str, Any],
        executor: Any | None = None,
    ) -> SquadExecutionResult:
        """Agent Squad execution engine.

        Flow:
        1. Restore AgentSquad from plan.metadata
        2. Execute steps in execution_order
        3. Hand off outputs via CollaborationProtocol.handoff()
        4. Run review gate when protocol is review_gate / red_team
        5. Loop while protocol.should_continue() returns True
        6. Return SquadExecutionResult
        """
        squad_data = plan.metadata.get("agent_squad", {})
        squad = AgentSquad(**squad_data)
        protocol = self._get_protocol(squad)

        outputs: dict[str, Any] = {}
        round_num = 0
        all_verdicts: list[Any] = []
        self._start_time = time.monotonic()

        while protocol.should_continue(round_num, squad.max_rounds, all_verdicts):
            for step_id in squad.execution_order:
                step = self._find_step(squad.steps, step_id)
                step_context = self._build_step_context(
                    step, squad, outputs, protocol, all_verdicts, context
                )

                result = await self._execute_squad_step(step, step_context, executor)
                outputs[step_id] = result

                if step.role_id in ("reviewer", "red_team"):
                    target_role = self._infer_target_role(step, squad)
                    verdict = protocol.review(target_role, [self._normalize_output(result)])
                    all_verdicts.append(verdict)

            round_num += 1

        plan.status = PlanStatus.COMPLETED

        return SquadExecutionResult(
            squad=squad,
            plan=plan,
            output=outputs,
            agent_outputs=outputs,
            duration_ms=self._elapsed(),
            rounds_executed=round_num,
            verdicts=all_verdicts,
        )

    async def _run_debate(
        self,
        plan: ExecutionPlan,
        context: dict[str, Any],
        executor: Any | None = None,
    ) -> SquadExecutionResult:
        """Debate execution engine.

        1. Pro-agent outputs proposal A
        2. Con-agent outputs proposal B (and rebuts A)
        3. Judge agent compares A/B, selects or synthesises
        """
        return await self._run_agent_squad(plan, context, executor)

    async def _run_red_team(
        self,
        plan: ExecutionPlan,
        context: dict[str, Any],
        executor: Any | None = None,
    ) -> SquadExecutionResult:
        """Red-team execution engine.

        1. Implementer outputs code/solution
        2. Red-team outputs security analysis
        3. If review fails, loop back and fix
        """
        return await self._run_agent_squad(plan, context, executor)

    def _get_protocol(self, squad: AgentSquad) -> Any:
        """Return the collaboration protocol for a squad."""
        from vibesop.core.orchestration.collaboration_protocol import create_protocol

        return create_protocol(squad, self._llm)

    def _find_step(self, steps: list[Any], step_id: str) -> Any:
        """Find a squad step by ID."""
        for step in steps:
            if step.step_id == step_id:
                return step
        raise ValueError(f"Squad step {step_id!r} not found")

    def _build_step_context(
        self,
        step: Any,
        squad: AgentSquad,
        outputs: dict[str, Any],
        protocol: Any,
        verdicts: list[Any],
        base_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build execution context for a squad step, including handoff payload."""
        from vibesop.core.orchestration.collaboration_protocol import HandoffPayload

        upstream_outputs: dict[str, Any] = {}
        for input_step_id in getattr(step, "input_from", []):
            if input_step_id in outputs:
                upstream_outputs[input_step_id] = outputs[input_step_id]

        handoff_context = ""
        if upstream_outputs:
            latest_id = list(upstream_outputs.keys())[-1]
            latest_output = upstream_outputs[latest_id]
            source_step = self._find_step(squad.steps, latest_id)
            payload = HandoffPayload(
                from_role=source_step.role_id,
                to_role=step.role_id,
                step_id=latest_id,
                output=str(latest_output),
            )
            payload = protocol.handoff(payload)
            handoff_context = payload.output

        return {
            **base_context,
            "step_id": step.step_id,
            "role": step.role_id,
            "upstream_outputs": upstream_outputs,
            "handoff": handoff_context,
            "verdicts": [v.model_dump() if hasattr(v, "model_dump") else v for v in verdicts],
        }

    async def _execute_squad_step(
        self,
        step: Any,
        step_context: dict[str, Any],
        executor: Any | None,
    ) -> Any:
        """Execute a single squad step.

        If an executor is provided it is called as executor(step, context).
        Otherwise a placeholder result is returned.
        """
        if executor is None:
            return {
                "step_id": step.step_id,
                "role_id": step.role_id,
                "content": "",
            }

        result = executor(step, step_context)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    def _normalize_output(self, output: Any) -> dict[str, Any]:
        """Normalize a step output for protocol.review()."""
        if isinstance(output, dict):
            return {
                "role": output.get("role_id", output.get("role", "unknown")),
                "content": output.get("content", output.get("output", str(output))),
            }
        return {"role": "unknown", "content": str(output)}

    def _infer_target_role(self, step: Any, squad: AgentSquad) -> str:
        """Infer which role's output is being reviewed by a reviewer/red_team step."""
        if step.step_id not in squad.execution_order:
            return "unknown"
        step_idx = squad.execution_order.index(step.step_id)
        if step_idx > 0:
            prev_step_id = squad.execution_order[step_idx - 1]
            prev_step = self._find_step(squad.steps, prev_step_id)
            return prev_step.role_id
        return "unknown"

    def _elapsed(self) -> float:
        """Return elapsed time since execution started in milliseconds."""
        if not self._start_time:
            return 0.0
        return (time.monotonic() - self._start_time) * 1000
