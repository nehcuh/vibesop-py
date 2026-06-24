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


# --- P2 Regression Tests: defensive squad metadata parsing ---


async def test_agent_squad_missing_metadata_raises_clear_error() -> None:
    """Missing/empty squad metadata raises a clear ValueError, not a cryptic ValidationError."""
    import pytest

    engine = WorkflowEngine()
    plan = ExecutionPlan(
        plan_id="no-squad",
        original_query="test",
        steps=[],
        workflow_pattern=WorkflowPattern.AGENT_SQUAD,
        metadata={},
    )
    with pytest.raises(ValueError, match="empty or missing"):
        await engine.run_async(plan)


async def test_agent_squad_malformed_metadata_raises_clear_error() -> None:
    """Non-dict squad metadata (e.g. a list) is rejected cleanly by the type guard."""
    import pytest

    engine = WorkflowEngine()
    plan = ExecutionPlan(
        plan_id="malformed-squad",
        original_query="test",
        steps=[],
        workflow_pattern=WorkflowPattern.AGENT_SQUAD,
        metadata={"agent_squad": ["not", "a", "dict"]},
    )
    with pytest.raises(ValueError, match="empty or missing"):
        await engine.run_async(plan)


async def test_agent_squad_invalid_metadata_raises_clear_error() -> None:
    """Structurally invalid squad metadata raises a clear ValueError wrapping the details."""
    import pytest

    engine = WorkflowEngine()
    plan = ExecutionPlan(
        plan_id="bad-squad",
        original_query="test",
        steps=[],
        workflow_pattern=WorkflowPattern.AGENT_SQUAD,
        metadata={"agent_squad": {"roles": []}},  # missing required squad_id
    )
    with pytest.raises(ValueError, match="Invalid agent squad metadata"):
        await engine.run_async(plan)
