"""Tests for Phase 3 (v6.2.0): Full Execution Dynamic.

Tests for:
- New WorkflowPattern values (LOOP_UNTIL_DRY, TOURNAMENT)
- DynamicNodeStatus and ReorchestrationDecision enums
- PlanBuilder _apply_loop_until_dry and _apply_tournament
- Reorchestrator decision logic
- TournamentRunner pairwise comparison
- WorkflowEngine loop-until-dry and tournament execution
- Integration with classifier and plan_builder
"""

from __future__ import annotations

from vibesop.core.models import (
    AgentSquad,
    DynamicNodeStatus,
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    ReorchestrationDecision,
    StepStatus,
    TrustLevel,
    WorkflowPattern,
)
from vibesop.core.orchestration.reorchestrator import ReorchestrationAnalysis, Reorchestrator
from vibesop.core.orchestration.tournament import (
    TournamentConfig,
    TournamentRunner,
)
from vibesop.core.orchestration.workflow_engine import (
    DynamicExecutionResult,
    WorkflowEngine,
    WorkflowEngineConfig,
)

# --- Model Tests ---


def test_workflow_pattern_loop_until_dry() -> None:
    assert WorkflowPattern.LOOP_UNTIL_DRY.value == "loop_until_dry"


def test_workflow_pattern_tournament() -> None:
    assert WorkflowPattern.TOURNAMENT.value == "tournament"


def test_dynamic_node_status_enum() -> None:
    assert DynamicNodeStatus.PENDING.value == "pending"
    assert DynamicNodeStatus.RUNNING.value == "running"
    assert DynamicNodeStatus.COMPLETED.value == "completed"
    assert DynamicNodeStatus.LOOPING.value == "looping"
    assert DynamicNodeStatus.FAILED.value == "failed"


def test_reorchestration_decision_enum() -> None:
    assert ReorchestrationDecision.CONTINUE.value == "continue"
    assert ReorchestrationDecision.APPEND_STEPS.value == "append_steps"
    assert ReorchestrationDecision.LOOP_BACK.value == "loop_back"
    assert ReorchestrationDecision.ESCALATE.value == "escalate"
    assert ReorchestrationDecision.TERMINATE_EARLY.value == "terminate_early"


def test_execution_step_phase3_fields() -> None:
    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test",
        dynamic_status=DynamicNodeStatus.RUNNING,
        loop_iteration=3,
        contestant_index=1,
    )
    assert step.dynamic_status == DynamicNodeStatus.RUNNING
    assert step.loop_iteration == 3
    assert step.contestant_index == 1

    d = step.to_dict()
    assert d["dynamic_status"] == "running"
    assert d["loop_iteration"] == 3
    assert d["contestant_index"] == 1


def test_execution_plan_phase3_fields() -> None:
    plan = ExecutionPlan(
        plan_id="test",
        original_query="Test",
        steps=[],
        execution_mode=ExecutionMode.SEQUENTIAL,
        workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        is_dynamic=True,
        dry_threshold=3,
        max_reorchestration_rounds=10,
    )
    assert plan.is_dynamic is True
    assert plan.dry_threshold == 3
    assert plan.max_reorchestration_rounds == 10

    d = plan.to_dict()
    assert d["is_dynamic"] is True
    assert d["dry_threshold"] == 3


# --- PlanBuilder Pattern Tests ---


def test_apply_loop_until_dry_marks_iterations() -> None:
    from vibesop.core.orchestration.plan_builder import PlanBuilder

    class MockRouter:
        def _single_skill_route(self, query, context=None, candidates=None):
            from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute

            return RoutingResult(
                primary=SkillRoute(skill_id="test", confidence=0.9, layer=RoutingLayer.SCENARIO),
                alternatives=[],
                routing_path=[],
                layer_details=[],
                query=query,
                duration_ms=10,
            )

    from vibesop.core.orchestration.task_decomposer import SubTask

    builder = PlanBuilder(MockRouter())  # type: ignore
    sub_tasks = [SubTask(intent="Task 1", query="Do task 1", original_intent="Task 1")]

    plan = builder.build_plan("Test", sub_tasks, workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY)

    assert plan.workflow_pattern == WorkflowPattern.LOOP_UNTIL_DRY
    for step in plan.steps:
        assert step.loop_iteration == 0


def test_apply_tournament_creates_contestants() -> None:
    from vibesop.core.orchestration.plan_builder import PlanBuilder

    class MockRouter:
        def _single_skill_route(self, query, context=None, candidates=None):
            from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute

            return RoutingResult(
                primary=SkillRoute(skill_id="test", confidence=0.9, layer=RoutingLayer.SCENARIO),
                alternatives=[],
                routing_path=[],
                layer_details=[],
                query=query,
                duration_ms=10,
            )

    from vibesop.core.orchestration.task_decomposer import SubTask

    builder = PlanBuilder(MockRouter())  # type: ignore
    sub_tasks = [SubTask(intent="Task 1", query="Do task 1", original_intent="Task 1")]

    plan = builder.build_plan("Test", sub_tasks, workflow_pattern=WorkflowPattern.TOURNAMENT)

    # Should have 3 contestants + 1 judge = 4 steps
    assert len(plan.steps) == 4
    assert plan.workflow_pattern == WorkflowPattern.TOURNAMENT

    # Last step should be judge (verification step, QUARANTINE)
    judge = plan.steps[-1]
    assert judge.is_verification_step is True
    assert judge.trust_level == TrustLevel.QUARANTINE

    # Contestants should have contestant_index set
    contestants = plan.steps[:-1]
    assert all(s.contestant_index is not None for s in contestants)


# --- Classifier Tests ---


def test_classifier_loop_until_dry_keywords() -> None:
    from vibesop.core.orchestration.classifier import ClassifierAgent

    class MockLLM:
        def call(self, prompt, **kwargs):
            return '{"pattern": "sequential", "confidence": 0.1, "reasoning": "fallback", "task_type": "", "complexity": "simple"}'

    classifier = ClassifierAgent(MockLLM())
    result = classifier._rule_classify("iteratively debug and fix all issues", None)
    assert result.pattern == WorkflowPattern.LOOP_UNTIL_DRY


def test_classifier_tournament_keywords() -> None:
    from vibesop.core.orchestration.classifier import ClassifierAgent

    class MockLLM:
        def call(self, prompt, **kwargs):
            return '{"pattern": "sequential", "confidence": 0.1, "reasoning": "fallback", "task_type": "", "complexity": "simple"}'

    classifier = ClassifierAgent(MockLLM())
    result = classifier._rule_classify("compare approaches to find the best solution", None)
    assert result.pattern == WorkflowPattern.TOURNAMENT


# --- Reorchestrator Tests ---


def test_reorchestrator_terminate_early_when_goals_met() -> None:
    class MockLLM:
        def call(self, prompt, **kwargs):
            return "never called"

    reorchestrator = Reorchestrator(MockLLM())

    plan = ExecutionPlan(
        plan_id="test",
        original_query="Test",
        steps=[
            ExecutionStep(
                step_id="s1",
                step_number=1,
                skill_id="test",
                intent="Task 1",
                status=StepStatus.COMPLETED,
                output_as="step_1_result",
            ),
        ],
        detected_intents=["Task 1"],
        execution_mode=ExecutionMode.SEQUENTIAL,
    )

    result = reorchestrator.analyze(plan, plan.steps[0], "Output", {"step_1_result": "Done"})
    assert result.decision == ReorchestrationDecision.TERMINATE_EARLY
    assert result.confidence == 1.0


def test_reorchestrator_continue_by_default() -> None:
    class MockLLM:
        def call(self, prompt, **kwargs):
            return '{"decision": "continue", "confidence": 0.8, "reasoning": "More work to do"}'

    reorchestrator = Reorchestrator(MockLLM())

    plan = ExecutionPlan(
        plan_id="test",
        original_query="Test",
        steps=[
            ExecutionStep(
                step_id="s1",
                step_number=1,
                skill_id="test",
                intent="Task 1",
                status=StepStatus.COMPLETED,
                output_as="step_1_result",
            ),
            ExecutionStep(
                step_id="s2",
                step_number=2,
                skill_id="test",
                intent="Task 2",
                status=StepStatus.PENDING,
                output_as="step_2_result",
            ),
        ],
        detected_intents=["Task 1", "Task 2"],
    )

    result = reorchestrator.analyze(plan, plan.steps[0], "Output")
    assert result.decision == ReorchestrationDecision.CONTINUE


def test_reorchestrator_analysis_model() -> None:
    analysis = ReorchestrationAnalysis(
        decision=ReorchestrationDecision.APPEND_STEPS,
        confidence=0.85,
        reasoning="New issue found",
        new_sub_tasks=[{"intent": "Fix X", "query": "Fix the X issue"}],
    )
    assert analysis.decision == ReorchestrationDecision.APPEND_STEPS
    assert len(analysis.new_sub_tasks) == 1
    d = analysis.to_dict()
    assert d["decision"] == "append_steps"


# --- Tournament Tests ---


def test_tournament_single_contestant() -> None:
    class MockLLM:
        def call(self, prompt, **kwargs):
            return "never called"

    runner = TournamentRunner(MockLLM())
    result = runner.run_tournament("Query", "Problem", ["Only output"])

    assert result.champion_index == 0
    assert result.champion_output == "Only output"


def test_tournament_two_contestants() -> None:
    class MockLLM:
        def call(self, prompt, **kwargs):
            return '{"winner_index": 1, "reasoning": "B is better", "scores": {}}'

    runner = TournamentRunner(MockLLM())
    result = runner.run_tournament("Query", "Problem", ["Output A", "Output B"])

    assert result.champion_index == 1
    assert result.champion_output == "Output B"
    assert result.scores[1] > result.scores[0]


def test_tournament_empty_outputs() -> None:
    class MockLLM:
        def call(self, prompt, **kwargs):
            return "never called"

    runner = TournamentRunner(MockLLM())
    result = runner.run_tournament("Query", "Problem", [])

    assert result.champion_index == 0
    assert result.champion_output == ""


def test_tournament_config_defaults() -> None:
    config = TournamentConfig()
    assert config.num_contestants == 3
    assert "completeness" in config.judge_rubric


# --- WorkflowEngine Tests ---


def test_workflow_engine_is_dynamic() -> None:
    WorkflowEngine()

    dynamic_plan = ExecutionPlan(
        plan_id="test",
        original_query="Test",
        steps=[],
        workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY,
    )
    assert WorkflowEngine.is_dynamic(dynamic_plan) is True

    static_plan = ExecutionPlan(
        plan_id="test",
        original_query="Test",
        steps=[],
        workflow_pattern=WorkflowPattern.SEQUENTIAL,
    )
    assert WorkflowEngine.is_dynamic(static_plan) is False


def test_workflow_engine_loop_until_dry() -> None:
    call_count = [0]

    def executor(step):
        call_count[0] += 1
        return f"Output {call_count[0]}"

    engine = WorkflowEngine()

    plan = ExecutionPlan(
        plan_id="test",
        original_query="Test",
        steps=[
            ExecutionStep(
                step_id="s1",
                step_number=1,
                skill_id="test",
                intent="Task 1",
                output_as="step_1_result",
            ),
            ExecutionStep(
                step_id="s2",
                step_number=2,
                skill_id="test",
                intent="Task 2",
                output_as="step_2_result",
            ),
        ],
        workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        detected_intents=["Task 1", "Task 2"],
    )

    result = engine.run(plan, executor)

    assert result.pattern == WorkflowPattern.LOOP_UNTIL_DRY
    assert result.total_steps_executed >= 1
    assert plan.status == PlanStatus.COMPLETED


def test_workflow_engine_tournament() -> None:
    def executor(step):
        return f"Contestant output for {step.intent}"

    class MockLLM:
        def call(self, prompt, **kwargs):
            return '{"winner_index": 1, "reasoning": "B wins", "scores": {}}'

    engine = WorkflowEngine(WorkflowEngineConfig(), llm_client=MockLLM())

    plan = ExecutionPlan(
        plan_id="test",
        original_query="Test",
        steps=[
            ExecutionStep(
                step_id="c1",
                step_number=1,
                skill_id="test",
                intent="Approach A (contestant 1)",
                output_as="c1_result",
                contestant_index=0,
            ),
            ExecutionStep(
                step_id="c2",
                step_number=2,
                skill_id="test",
                intent="Approach B (contestant 2)",
                output_as="c2_result",
                contestant_index=1,
            ),
            ExecutionStep(
                step_id="judge",
                step_number=3,
                skill_id="test",
                intent="Judge",
                output_as="judge_result",
                is_verification_step=True,
            ),
        ],
        workflow_pattern=WorkflowPattern.TOURNAMENT,
    )

    result = engine.run(plan, executor)

    assert result.pattern == WorkflowPattern.TOURNAMENT
    assert result.total_steps_executed == 2  # 2 contestants
    assert result.champion_index is not None


def test_workflow_engine_config_defaults() -> None:
    config = WorkflowEngineConfig()
    assert config.max_tournament_contestants == 3


def test_dynamic_execution_result_model() -> None:
    result = DynamicExecutionResult(
        plan_id="test",
        pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        total_steps_executed=3,
        reorchestration_rounds=2,
        final_status="completed",
    )
    assert result.plan_id == "test"
    assert result.pattern == WorkflowPattern.LOOP_UNTIL_DRY


# --- Phase 1 Regression Tests (P0/P1 fixes) ---


class _LoopBackLLM:
    """Mock LLM that always returns a LOOP_BACK decision to a target step."""

    def __init__(self, target_step_id: str) -> None:
        self._target = target_step_id

    def call(self, prompt, **kwargs):
        return (
            '{"decision": "loop_back", "confidence": 0.9, '
            f'"reasoning": "redo", "loop_target_step_id": "{self._target}"}}'
        )


def test_loop_back_actually_reexecutes() -> None:
    """P0-1: LOOP_BACK must rewind the cursor so the target step re-runs.

    Before the fix the cursor only advanced, so the target step executed once.
    """
    call_log: list[str] = []

    def executor(step):
        call_log.append(step.step_id)
        return f"output for {step.step_id}"

    engine = WorkflowEngine(llm_client=_LoopBackLLM("s1"))
    plan = ExecutionPlan(
        plan_id="regression-loop-back",
        original_query="Test LOOP_BACK cursor rewinding",
        steps=[
            ExecutionStep(
                step_id="s1",
                step_number=1,
                skill_id="test",
                intent="Step 1",
                output_as="s1_result",
            ),
        ],
        workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        # 2 intents but 1 step → _check_goals_met fast path never fires
        detected_intents=["intent-a", "intent-b"],
        dry_threshold=5,
        max_reorchestration_rounds=3,
    )

    engine._run_loop_until_dry(plan, executor)

    assert call_log.count("s1") >= 2, (
        f"LOOP_BACK should re-execute target step; s1 ran "
        f"{call_log.count('s1')} time(s): {call_log}"
    )


def test_loop_back_guard_terminates() -> None:
    """P0-1 guard: a runaway LOOP_BACK must terminate, not spin forever."""
    call_log: list[str] = []

    def executor(step):
        call_log.append(step.step_id)
        return "out"

    engine = WorkflowEngine(llm_client=_LoopBackLLM("s1"))
    plan = ExecutionPlan(
        plan_id="regression-loop-guard",
        original_query="guard",
        steps=[
            ExecutionStep(step_id="s1", step_number=1, skill_id="t", intent="x", output_as="o")
        ],
        workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        detected_intents=["a", "b"],
        dry_threshold=200,
        max_reorchestration_rounds=200,  # generous; per-step guard must kick in first
    )

    engine._run_loop_until_dry(plan, executor)

    assert len(call_log) < 20, f"Guard failed; engine spun {len(call_log)} times: {call_log}"


def test_convergence_after_revision_pass() -> None:
    """P0-2: once the latest review PASSES, the loop must converge even when
    an earlier round failed. This is the [FAIL, PASS] accumulation repro."""
    from vibesop.core.orchestration.collaboration_protocol import (
        ReviewVerdict,
        SequentialProtocol,
    )

    protocol = SequentialProtocol(AgentSquad(squad_id="conv"))
    verdicts = [
        ReviewVerdict(
            passed=False,
            reviewer_role="rev",
            target_role="impl",
            issues=["bug"],
            requires_revision=True,
            revision_feedback="fix it",
        ),
        ReviewVerdict(passed=True, reviewer_role="rev", target_role="impl", issues=[]),
    ]
    assert protocol.should_continue(round_number=2, max_rounds=5, verdicts=verdicts) is False


def test_convergence_hard_reject() -> None:
    """P0-2: FAIL with no revision requested is a hard reject → stop early."""
    from vibesop.core.orchestration.collaboration_protocol import (
        ReviewVerdict,
        SequentialProtocol,
    )

    protocol = SequentialProtocol(AgentSquad(squad_id="conv"))
    verdicts = [
        ReviewVerdict(
            passed=False,
            reviewer_role="rev",
            target_role="impl",
            issues=["fatal"],
            requires_revision=False,
        )
    ]
    assert protocol.should_continue(round_number=1, max_rounds=5, verdicts=verdicts) is False


def test_continues_when_revision_needed() -> None:
    """P0-2 guard: FAIL + revision requested must keep looping (no over-fix)."""
    from vibesop.core.orchestration.collaboration_protocol import (
        ReviewVerdict,
        SequentialProtocol,
    )

    protocol = SequentialProtocol(AgentSquad(squad_id="conv"))
    verdicts = [
        ReviewVerdict(
            passed=False,
            reviewer_role="rev",
            target_role="impl",
            issues=["bug"],
            requires_revision=True,
            revision_feedback="fix it",
        )
    ]
    assert protocol.should_continue(round_number=1, max_rounds=5, verdicts=verdicts) is True


def test_tournament_parallel_execution() -> None:
    """P1-1: contestants run in parallel (wall-clock far below serial sum)."""
    import time

    def slow_executor(step):
        time.sleep(0.06)
        return f"output from {step.step_id}"

    engine = WorkflowEngine()
    plan = ExecutionPlan(
        plan_id="regression-tournament-parallel",
        original_query="parallel",
        steps=[
            ExecutionStep(
                step_id=f"c{i}",
                step_number=i + 1,
                skill_id="t",
                intent=f"Contestant {i}",
                output_as=f"c{i}",
                contestant_index=i,
            )
            for i in range(4)
        ]
        + [
            ExecutionStep(
                step_id="judge",
                step_number=5,
                skill_id="t",
                intent="Judge",
                output_as="judge",
                is_verification_step=True,
            ),
        ],
        workflow_pattern=WorkflowPattern.TOURNAMENT,
    )

    start = time.monotonic()
    engine.run(plan, slow_executor)
    elapsed = time.monotonic() - start

    # Serial would be 4 * 0.06 = 0.24s; parallel ~0.06-0.08s.
    assert elapsed < 0.18, f"Tournament should run in parallel; took {elapsed:.3f}s"


def test_tournament_parallel_exception_isolation() -> None:
    """P1-1: a failing contestant must not abort the other contestants."""

    def executor(step):
        if step.step_id == "c1":
            raise RuntimeError("boom")
        return f"ok-{step.step_id}"

    engine = WorkflowEngine()
    plan = ExecutionPlan(
        plan_id="regression-tournament-iso",
        original_query="iso",
        steps=[
            ExecutionStep(
                step_id="c0", step_number=1, skill_id="t", intent="A", output_as="c0",
                contestant_index=0,
            ),
            ExecutionStep(
                step_id="c1", step_number=2, skill_id="t", intent="B", output_as="c1",
                contestant_index=1,
            ),
            ExecutionStep(
                step_id="c2", step_number=3, skill_id="t", intent="C", output_as="c2",
                contestant_index=2,
            ),
        ],
        workflow_pattern=WorkflowPattern.TOURNAMENT,
    )

    result = engine.run(plan, executor)

    assert "ok-c0" in str(result.results.get("c0"))
    assert "ok-c2" in str(result.results.get("c2"))
    failed = result.results.get("c1")
    assert isinstance(failed, dict) and "error" in failed


def test_tournament_no_llm_fallback_not_default_zero() -> None:
    """P1-2: without an LLM, champion is chosen by heuristic, not always 0."""

    def executor(step):
        if step.step_id == "c0":
            return "ok"  # short, unstructured
        return (
            "```python\n"
            "def solve():\n"
            "    result = compute()\n"
            "    return result\n"
            "```\n"
            "step by step conclusion: done"
        )

    engine = WorkflowEngine()  # no LLM
    plan = ExecutionPlan(
        plan_id="regression-tournament-fallback",
        original_query="fallback",
        steps=[
            ExecutionStep(
                step_id="c0", step_number=1, skill_id="t", intent="A", output_as="c0",
                contestant_index=0,
            ),
            ExecutionStep(
                step_id="c1", step_number=2, skill_id="t", intent="B", output_as="c1",
                contestant_index=1,
            ),
        ],
        workflow_pattern=WorkflowPattern.TOURNAMENT,
    )

    result = engine.run(plan, executor)
    assert result.champion_index == 1, (
        f"Heuristic should pick the richer contestant 1, got {result.champion_index}"
    )


def test_tournament_no_llm_empty_outputs_no_crash() -> None:
    """P1-2: all-empty contestant outputs must not crash and yield a valid index."""

    def executor(step):
        return ""

    engine = WorkflowEngine()
    plan = ExecutionPlan(
        plan_id="regression-tournament-empty",
        original_query="empty",
        steps=[
            ExecutionStep(
                step_id="c0", step_number=1, skill_id="t", intent="A", output_as="c0",
                contestant_index=0,
            ),
            ExecutionStep(
                step_id="c1", step_number=2, skill_id="t", intent="B", output_as="c1",
                contestant_index=1,
            ),
        ],
        workflow_pattern=WorkflowPattern.TOURNAMENT,
    )

    result = engine.run(plan, executor)
    assert result.champion_index in (0, 1)


# --- Phase 2 Regression Tests ---


def test_loop_until_dry_degraded_logs_warning(caplog) -> None:
    """P1-3: no LLM → LOOP_UNTIL_DRY logs a degradation warning (not silent)."""
    import logging

    caplog.set_level(logging.WARNING, logger="vibesop.core.orchestration.workflow_engine")
    engine = WorkflowEngine()  # no LLM

    plan = ExecutionPlan(
        plan_id="degraded-warn",
        original_query="Test",
        steps=[
            ExecutionStep(
                step_id="s1", step_number=1, skill_id="t", intent="Task 1", output_as="s1_result"
            )
        ],
        workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        detected_intents=["Task 1"],
    )

    engine.run(plan, lambda s: "ok")

    assert any("degraded" in rec.message.lower() for rec in caplog.records), (
        "no-LLM LOOP_UNTIL_DRY should log a degradation warning"
    )


def test_loop_until_dry_degraded_continues_safely() -> None:
    """P1-3: degraded LOOP_UNTIL_DRY runs steps once, flags degradation, no crash."""
    engine = WorkflowEngine()  # no LLM

    plan = ExecutionPlan(
        plan_id="degraded-safe",
        original_query="Test",
        steps=[
            ExecutionStep(
                step_id="s1", step_number=1, skill_id="t", intent="Task 1", output_as="s1_result"
            ),
            ExecutionStep(
                step_id="s2", step_number=2, skill_id="t", intent="Task 2", output_as="s2_result"
            ),
        ],
        workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        detected_intents=["Task 1", "Task 2"],
    )

    result = engine.run(plan, lambda s: f"result_{s.step_id}")

    assert plan.status == PlanStatus.COMPLETED
    assert result.total_steps_executed == 2
    assert result.reorchestration_rounds == 0
    assert any(
        entry.get("decision") == "degraded" for entry in result.reorchestration_history
    ), f"degraded path should record a 'degraded' marker: {result.reorchestration_history}"


def test_append_steps_uses_router_for_skill_id() -> None:
    """P1-5: appended steps route to a real skill via the router, not hard-coded."""

    class FixedRouter:
        def _single_skill_route(self, query, context=None, candidates=None):
            from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute

            return RoutingResult(
                primary=SkillRoute(
                    skill_id="real/debug-skill", confidence=0.85, layer=RoutingLayer.KEYWORD
                ),
                alternatives=[],
                routing_path=[],
                layer_details=[],
                query=query,
                duration_ms=10,
            )

    engine = WorkflowEngine(router=FixedRouter())
    plan = ExecutionPlan(
        plan_id="append-routing-test",
        original_query="Test",
        steps=[
            ExecutionStep(
                step_id="s1", step_number=1, skill_id="test", intent="Original", output_as="s1"
            )
        ],
        workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY,
        detected_intents=["Original"],
        dry_threshold=5,
        max_reorchestration_rounds=5,
    )

    new_steps = engine._create_steps_from_analysis(plan, [{"intent": "Fix X", "query": "fix the X"}])

    assert len(new_steps) == 1
    assert new_steps[0].skill_id == "real/debug-skill", (
        f"appended step should use the routed skill_id, got {new_steps[0].skill_id}"
    )


def test_append_steps_fallback_when_no_router() -> None:
    """P1-5: without a router, appended steps fall back to the default skill_id."""
    engine = WorkflowEngine()  # no router
    plan = ExecutionPlan(
        plan_id="append-fallback-test",
        original_query="Test",
        steps=[
            ExecutionStep(
                step_id="s1", step_number=1, skill_id="test", intent="Original", output_as="s1"
            )
        ],
        workflow_pattern=WorkflowPattern.LOOP_UNTIL_DRY,
    )

    new_steps = engine._create_steps_from_analysis(plan, [{"intent": "Task", "query": "do something"}])

    assert len(new_steps) == 1
    assert new_steps[0].skill_id == "builtin/slash-orchestrate"


class _ReviewLLM:
    """LLM whose review verdicts fail for the first N calls, then pass."""

    def __init__(self, fail_count: int) -> None:
        self._fail_count = fail_count
        self._n = 0

    def call(self, prompt, **kwargs):
        self._n += 1
        if self._n <= self._fail_count:
            return (
                '{"passed": false, "issues": ["problem"], "score": 3.0, '
                '"requires_revision": true, "revision_feedback": "fix it"}'
            )
        return (
            '{"passed": true, "issues": [], "score": 9.0, '
            '"requires_revision": false, "revision_feedback": ""}'
        )


async def test_squad_partial_rerun() -> None:
    """P1-7: after a failing review, later rounds re-run only target + reviewer."""
    from vibesop.core.models import AgentRole, AgentSquad, SquadStep

    execution_log: list[str] = []

    async def executor(step, ctx):
        execution_log.append(step.step_id)
        return {"role_id": step.role_id, "content": f"out-{step.step_id}"}

    squad = AgentSquad(
        squad_id="partial",
        roles=[
            AgentRole(role_id="implementer", name="Impl"),
            AgentRole(role_id="reviewer", name="Rev"),
            AgentRole(role_id="documenter", name="Doc"),
            AgentRole(role_id="deployer", name="Deploy"),
        ],
        steps=[
            SquadStep(step_id="s1", role_id="implementer"),
            SquadStep(step_id="s2", role_id="reviewer", input_from=["s1"]),
            SquadStep(step_id="s3", role_id="documenter"),
            SquadStep(step_id="s4", role_id="deployer"),
        ],
        execution_order=["s1", "s2", "s3", "s4"],
        collaboration_protocol="review_gate",
        max_rounds=3,
    )
    plan = ExecutionPlan(
        plan_id="partial",
        original_query="build",
        steps=[],
        workflow_pattern=WorkflowPattern.AGENT_SQUAD,
        metadata={"agent_squad": squad.to_dict()},
    )

    engine = WorkflowEngine(llm_client=_ReviewLLM(fail_count=99))  # always fails
    await engine.run_async(plan, context={}, executor=executor)

    # Round 0 runs all 4; rounds 1-2 re-run only s1 (target) + s2 (reviewer).
    assert execution_log == ["s1", "s2", "s3", "s4", "s1", "s2", "s1", "s2"], (
        f"partial rerun expected [s1,s2,s3,s4, s1,s2, s1,s2], got {execution_log}"
    )


async def test_red_team_fix_loop() -> None:
    """P1-4/P1-7: RED_TEAM loops implementer→red_team only (fixed-point), via delegation."""
    from vibesop.core.models import AgentRole, AgentSquad, SquadStep

    execution_log: list[str] = []

    async def executor(step, ctx):
        execution_log.append(step.role_id)
        return {"role_id": step.role_id, "content": f"out-{step.role_id}"}

    squad = AgentSquad(
        squad_id="redteam",
        roles=[
            AgentRole(role_id="implementer", name="Impl"),
            AgentRole(role_id="red_team", name="RT"),
        ],
        steps=[
            SquadStep(step_id="s1", role_id="implementer"),
            SquadStep(step_id="s2", role_id="red_team", input_from=["s1"]),
        ],
        execution_order=["s1", "s2"],
        collaboration_protocol="red_team",
        max_rounds=3,
    )
    plan = ExecutionPlan(
        plan_id="redteam",
        original_query="secure auth",
        steps=[],
        workflow_pattern=WorkflowPattern.RED_TEAM,
        metadata={"agent_squad": squad.to_dict()},
    )

    engine = WorkflowEngine(llm_client=_ReviewLLM(fail_count=2))  # fail, fail, pass
    result = await engine.run_async(plan, context={}, executor=executor)

    assert execution_log == [
        "implementer",
        "red_team",
        "implementer",
        "red_team",
        "implementer",
        "red_team",
    ], f"RED_TEAM should loop impl→rt per round: {execution_log}"
    assert result.verdicts[-1].passed is True


async def test_debate_pro_con_judge_flow() -> None:
    """P1-4: DEBATE executes pro→con→judge in order (delegation + DebateProtocol)."""
    from vibesop.core.models import AgentRole, AgentSquad, SquadStep

    execution_log: list[str] = []

    async def executor(step, ctx):
        execution_log.append(step.role_id)
        return {"role_id": step.role_id, "content": f"out-{step.role_id}"}

    squad = AgentSquad(
        squad_id="debate",
        roles=[
            AgentRole(role_id="pro", name="Pro"),
            AgentRole(role_id="con", name="Con"),
            AgentRole(role_id="judge", name="Judge"),
        ],
        steps=[
            SquadStep(step_id="s1", role_id="pro"),
            SquadStep(step_id="s2", role_id="con", input_from=["s1"]),
            SquadStep(step_id="s3", role_id="judge", input_from=["s1", "s2"]),
        ],
        execution_order=["s1", "s2", "s3"],
        collaboration_protocol="debate",
        max_rounds=1,
    )
    plan = ExecutionPlan(
        plan_id="debate",
        original_query="topic",
        steps=[],
        workflow_pattern=WorkflowPattern.DEBATE,
        metadata={"agent_squad": squad.to_dict()},
    )

    engine = WorkflowEngine()
    await engine.run_async(plan, context={}, executor=executor)

    assert execution_log == ["pro", "con", "judge"], (
        f"DEBATE should run pro→con→judge: {execution_log}"
    )
