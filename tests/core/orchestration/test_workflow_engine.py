"""Tests for WorkflowEngine squad-oriented patterns."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import Mock

import pytest

from vibesop.core.models import (
    AgentRole,
    AgentSquad,
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    SquadStep,
    WorkflowPattern,
)
from vibesop.core.orchestration.workflow_engine import (
    DynamicExecutionResult,
    SquadExecutionResult,
    WorkflowEngine,
)


def _make_squad_plan(protocol: WorkflowPattern) -> ExecutionPlan:
    """Build a minimal execution plan with an embedded agent squad."""
    squad = AgentSquad(
        squad_id="squad-test",
        roles=[
            AgentRole(role_id="implementer", name="实现者", required_skills=["coding"]),
            AgentRole(role_id="reviewer", name="审查者", required_skills=["review"]),
        ],
        steps=[
            SquadStep(step_id="impl", role_id="implementer", skill_ids=["coding"]),
            SquadStep(step_id="rev", role_id="reviewer", skill_ids=["review"], input_from=["impl"]),
        ],
        collaboration_protocol="review_gate"
        if protocol == WorkflowPattern.RED_TEAM
        else protocol.value,
        lead_role="reviewer",
        max_rounds=2,
        execution_order=["impl", "rev"],
    )

    return ExecutionPlan(
        plan_id="plan-squad-1",
        original_query="implement and review",
        workflow_pattern=protocol,
        metadata={"agent_squad": squad.to_dict()},
    )


class TestWorkflowEngineSquadPatterns:
    """Squad/debate/red-team execution through WorkflowEngine."""

    def test_is_dynamic_includes_squad_patterns(self) -> None:
        for pattern in (
            WorkflowPattern.AGENT_SQUAD,
            WorkflowPattern.DEBATE,
            WorkflowPattern.RED_TEAM,
        ):
            plan = _make_squad_plan(pattern)
            assert WorkflowEngine.is_dynamic(plan) is True

    def test_run_agent_squad_sync(self) -> None:
        plan = _make_squad_plan(WorkflowPattern.AGENT_SQUAD)
        engine = WorkflowEngine()

        calls: list[tuple[str, dict[str, Any]]] = []

        def executor(step: SquadStep, context: dict[str, Any]) -> dict[str, Any]:
            calls.append((step.role_id, context))
            return {
                "step_id": step.step_id,
                "role_id": step.role_id,
                "content": f"output-{step.role_id}",
            }

        result = engine.run(plan, executor)

        assert isinstance(result, SquadExecutionResult)
        assert result.rounds_executed == 1
        assert "impl" in result.output
        assert "rev" in result.output
        assert len(calls) == 2
        # Reviewer receives handoff context from implementer
        rev_context = next(ctx for role, ctx in calls if role == "reviewer")
        assert "handoff" in rev_context
        assert "output-implementer" in rev_context["handoff"]

    @pytest.mark.asyncio
    async def test_run_async_agent_squad(self) -> None:
        plan = _make_squad_plan(WorkflowPattern.AGENT_SQUAD)
        engine = WorkflowEngine()

        async def executor(step: SquadStep, context: dict[str, Any]) -> dict[str, Any]:
            return {"step_id": step.step_id, "role_id": step.role_id, "content": "async-output"}

        result = await engine.run_async(plan, executor=executor)

        assert isinstance(result, SquadExecutionResult)
        assert result.rounds_executed == 1
        assert result.output["impl"]["content"] == "async-output"

    @pytest.mark.asyncio
    async def test_run_debate(self) -> None:
        plan = _make_squad_plan(WorkflowPattern.DEBATE)
        engine = WorkflowEngine()

        async def executor(step: SquadStep, context: dict[str, Any]) -> dict[str, Any]:
            return {"step_id": step.step_id, "role_id": step.role_id, "content": "argument"}

        result = await engine.run_async(plan, executor=executor)

        assert isinstance(result, SquadExecutionResult)
        assert result.rounds_executed >= 1

    @pytest.mark.asyncio
    async def test_run_red_team(self) -> None:
        plan = _make_squad_plan(WorkflowPattern.RED_TEAM)
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content=json.dumps({"passed": True, "score": 8.0, "issues": []})
        )
        engine = WorkflowEngine(llm_client=mock_llm)

        async def executor(step: SquadStep, context: dict[str, Any]) -> dict[str, Any]:
            return {"step_id": step.step_id, "role_id": step.role_id, "content": "security check"}

        result = await engine.run_async(plan, executor=executor)

        assert isinstance(result, SquadExecutionResult)
        assert result.rounds_executed >= 1

    @pytest.mark.asyncio
    async def test_blocked_review_verdict_surfaces_blocked_terminal(self) -> None:
        """D08 (engine side): a genuine hard-reject review verdict must surface
        via the additive blocked/blocked_roles fields and review_status —
        while plan.status keeps the run-completed contract (F3): reaching the
        terminal event means no member crashed, so the run completed; the
        review acceptance dimension is carried by the new fields and the
        additive review_status payload key, never by repurposing
        final_status."""
        from vibesop.core.orchestration import PlanEventLog, PlanEventType

        plan = _make_squad_plan(WorkflowPattern.RED_TEAM)
        log = PlanEventLog()
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content=json.dumps(
                {
                    "passed": False,
                    "issues": ["no evidence"],
                    "score": 1.0,
                    "requires_revision": False,
                    "revision_feedback": "blocked: no evidence",
                }
            )
        )
        engine = WorkflowEngine(llm_client=mock_llm, event_log=log)

        async def executor(step: SquadStep, context: dict[str, Any]) -> dict[str, Any]:
            return {"step_id": step.step_id, "role_id": step.role_id, "content": "work"}

        result = await engine.run_async(plan, executor=executor)

        assert isinstance(result, SquadExecutionResult)
        assert result.blocked is True
        assert result.blocked_roles == ["implementer"]
        assert result.review_status == "rejected"
        assert plan.status == PlanStatus.COMPLETED, "run-completed contract (F3)"
        data = result.to_dict()
        assert data["blocked"] is True
        assert data["blocked_roles"] == ["implementer"]
        assert data["review_status"] == "rejected"
        # Terminal event: final_status keeps the run-completed vocabulary;
        # review acceptance rides the additive payload key.
        terminal = [
            e
            for e in log.replay(plan.plan_id, since_seq=0).events
            if e.type == PlanEventType.PLAN_TERMINAL
        ]
        assert terminal, "plan_terminal event must be emitted"
        assert terminal[-1].payload["final_status"] == "completed"
        assert terminal[-1].payload["review_status"] == "rejected"

    @pytest.mark.asyncio
    async def test_degraded_review_gate_keeps_completed_semantics(self) -> None:
        """A review gate that errors (no LLM) produces a degraded verdict —
        it is not a genuine review outcome and must not surface as blocked;
        acceptance is explicitly 'error' (unknown), never 'accepted'."""
        from vibesop.core.models import PlanStatus

        plan = _make_squad_plan(WorkflowPattern.RED_TEAM)
        engine = WorkflowEngine()  # no LLM → ReviewGateProtocol.review raises LLMError

        async def executor(step: SquadStep, context: dict[str, Any]) -> dict[str, Any]:
            return {"step_id": step.step_id, "role_id": step.role_id, "content": "work"}

        result = await engine.run_async(plan, executor=executor)

        assert isinstance(result, SquadExecutionResult)
        assert result.blocked is False
        assert result.blocked_roles == []
        assert result.review_status == "error"
        assert plan.status == PlanStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_squad_step_context_carries_role_prompt_and_skill_isolation(self) -> None:
        """F5 (F27 contract): the unified engine _build_step_context restores
        the role context keys the old StepRunner._execute_squad branch
        supplied — rendered role_prompt and skill_isolation.allowed_skills
        from the real SquadStep — alongside the handoff/verdicts keys."""
        from vibesop.core.orchestration.role_templates import render_role_prompt

        plan = _make_squad_plan(WorkflowPattern.AGENT_SQUAD)
        engine = WorkflowEngine()
        contexts: dict[str, dict[str, Any]] = {}

        async def executor(step: SquadStep, context: dict[str, Any]) -> dict[str, Any]:
            contexts[step.role_id] = context
            return {"step_id": step.step_id, "role_id": step.role_id, "content": "work"}

        await engine.run_async(plan, executor=executor)

        squad = AgentSquad(**plan.metadata["agent_squad"])
        expected = {s.role_id: list(s.skill_ids) for s in squad.steps}
        for role, ctx in contexts.items():
            assert ctx.get("role_prompt"), f"{role} must receive a rendered role prompt"
            assert ctx["role_prompt"] == render_role_prompt(role, expected[role])
            assert ctx.get("skill_isolation", {}).get("allowed_skills") == expected[role]
        assert contexts["reviewer"].get("handoff"), "handoff must still be delivered"

    def test_squad_execution_result_to_dict(self) -> None:
        plan = _make_squad_plan(WorkflowPattern.AGENT_SQUAD)
        engine = WorkflowEngine()

        def executor(step: SquadStep, context: dict[str, Any]) -> dict[str, Any]:
            return {"step_id": step.step_id, "role_id": step.role_id, "content": "x"}

        result = engine.run(plan, executor)
        data = result.to_dict()

        assert data["plan_id"] == plan.plan_id
        assert data["rounds_executed"] == 1
        assert "squad" in data
        assert "output" in data

    @pytest.mark.asyncio
    async def test_run_async_requires_squad_pattern(self) -> None:
        from vibesop.core.models import ExecutionMode

        plan = ExecutionPlan(
            plan_id="plan-static",
            original_query="static",
            workflow_pattern=WorkflowPattern.SEQUENTIAL,
            execution_mode=ExecutionMode.SEQUENTIAL,
        )
        engine = WorkflowEngine()

        with pytest.raises(ValueError, match="not a squad pattern"):
            await engine.run_async(plan)


class TestWorkflowEngineBackwardCompat:
    """Existing dynamic patterns still work."""

    def test_loop_until_dry_still_runs(self) -> None:
        from vibesop.core.models import ExecutionMode, StepStatus

        plan = ExecutionPlan(
            plan_id="plan-loop",
            original_query="loop test",
            workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY,
            execution_mode=ExecutionMode.SEQUENTIAL,
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="skill-a",
                    intent="step 1",
                    input_query="do 1",
                    status=StepStatus.PENDING,
                )
            ],
            dry_threshold=1,
            max_reorchestration_rounds=1,
        )
        engine = WorkflowEngine()

        def executor(step: ExecutionStep) -> str:
            return "done"

        result = engine.run(plan, executor)
        assert isinstance(result, DynamicExecutionResult)
        assert result.pattern == WorkflowPattern.LOOP_UNTIL_DRY
        assert result.total_steps_executed == 1
