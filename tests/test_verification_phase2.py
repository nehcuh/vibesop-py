"""Tests for Phase 2: Adversarial Verification (v6.1.0).

Tests for:
- VerifierAgent
- VerificationLoop
- TrustLevel
- CLI --verify flag integration
"""

from __future__ import annotations

from vibesop.core.models import (
    ExecutionPlan,
    ExecutionStep,
    TrustLevel,
    WorkflowPattern,
)
from vibesop.core.orchestration.verification_loop import (
    VerificationLoop,
    VerificationLoopAction,
    VerificationLoopConfig,
    VerificationLoopState,
)
from vibesop.core.orchestration.verifier import (
    VerificationIssue,
    VerificationResult,
    VerificationStatus,
    VerificationStrictness,
    VerifierAgent,
    verify_step_with_retry,
)

# --- VerifierAgent Tests ---


def test_verification_result_model() -> None:
    """Test VerificationResult model validation."""
    result = VerificationResult(
        status=VerificationStatus.PASSED,
        confidence=0.9,
        issues=[],
        reasoning="All requirements met",
        rubric_scores={"completeness": 0.95, "correctness": 0.9},
    )

    assert result.status == VerificationStatus.PASSED
    assert result.confidence == 0.9
    assert len(result.issues) == 0
    assert result.reasoning == "All requirements met"

    result_dict = result.to_dict()
    assert result_dict["status"] == "passed"
    assert result_dict["confidence"] == 0.9


def test_verification_issue_model() -> None:
    """Test VerificationIssue model."""
    issue = VerificationIssue(
        category="completeness",
        severity="high",
        description="Missing requirement X",
        suggested_fix="Add requirement X",
    )

    assert issue.category == "completeness"
    assert issue.severity == "high"
    assert issue.description == "Missing requirement X"
    assert issue.suggested_fix == "Add requirement X"


def test_verification_status_enum() -> None:
    """Test VerificationStatus enum values."""
    assert VerificationStatus.PASSED.value == "passed"
    assert VerificationStatus.NEEDS_REVISION.value == "needs_revision"
    assert VerificationStatus.FAILED.value == "failed"


def test_verification_strictness_enum() -> None:
    """Test VerificationStrictness enum values."""
    assert VerificationStrictness.LENIENT.value == "lenient"
    assert VerificationStrictness.STANDARD.value == "standard"
    assert VerificationStrictness.STRICT.value == "strict"


def test_verifier_agent_init() -> None:
    """Test VerifierAgent initialization."""

    # Mock LLM client
    class MockLLM:
        def call(self, prompt: str, **kwargs: object) -> str:
            return '{"status": "passed", "confidence": 0.8, "reasoning": "OK", "rubric_scores": {}, "issues": []}'

    llm = MockLLM()
    verifier = VerifierAgent(llm, strictness=VerificationStrictness.STANDARD)

    assert verifier._llm is llm
    assert verifier._strictness == VerificationStrictness.STANDARD


def test_verifier_agent_empty_output() -> None:
    """Test verifier handles empty output correctly."""

    class MockLLM:
        def call(self, prompt: str, **kwargs: object) -> str:
            return "Never called"

    llm = MockLLM()
    verifier = VerifierAgent(llm)

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )

    result = verifier.verify("Test query", step, "")

    assert result.status == VerificationStatus.FAILED
    assert result.confidence == 1.0
    assert len(result.issues) == 1
    assert result.issues[0].severity == "critical"


def test_verifier_agent_parse_response() -> None:
    """Test verifier parses LLM response correctly."""

    class MockLLM:
        def call(self, prompt: str, **kwargs: object) -> str:
            return """{
                "status": "needs_revision",
                "confidence": 0.7,
                "reasoning": "Some issues found",
                "rubric_scores": {"completeness": 0.6, "correctness": 0.8},
                "issues": [
                    {"category": "completeness", "severity": "medium", "description": "Missing X", "suggested_fix": "Add X"}
                ]
            }"""

    llm = MockLLM()
    verifier = VerifierAgent(llm)

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )

    result = verifier.verify("Test query", step, "Some output")

    assert result.status == VerificationStatus.NEEDS_REVISION
    assert result.confidence == 0.7
    assert len(result.issues) == 1
    assert result.issues[0].category == "completeness"


def test_verifier_strictness_lenient() -> None:
    """Test verifier lenient strictness (only fails on critical)."""

    class MockLLM:
        def call(self, prompt: str, **kwargs: object) -> str:
            return """{
                "status": "failed",
                "confidence": 0.5,
                "reasoning": "Test",
                "rubric_scores": {},
                "issues": [
                    {"category": "correctness", "severity": "medium", "description": "Test issue"}
                ]
            }"""

    llm = MockLLM()
    verifier = VerifierAgent(llm, strictness=VerificationStrictness.LENIENT)

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )

    result = verifier.verify("Test query", step, "Output")

    # Lenient: failed becomes needs_revision if no critical issues
    assert result.status in (VerificationStatus.NEEDS_REVISION, VerificationStatus.PASSED)


def test_verifier_strictness_strict() -> None:
    """Test verifier strict strictness (medium issues trigger failure)."""

    class MockLLM:
        def call(self, prompt: str, **kwargs: object) -> str:
            return """{
                "status": "needs_revision",
                "confidence": 0.6,
                "reasoning": "Test",
                "rubric_scores": {},
                "issues": [
                    {"category": "completeness", "severity": "medium", "description": "Test issue"}
                ]
            }"""

    llm = MockLLM()
    verifier = VerifierAgent(llm, strictness=VerificationStrictness.STRICT)

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )

    result = verifier.verify("Test query", step, "Output")

    # Strict: needs_revision becomes failed if has medium+ issues
    assert result.status == VerificationStatus.FAILED


def test_verify_step_with_retry() -> None:
    """Test verify_step_with_retry function."""
    call_count = [0]

    class MockLLM:
        def call(self, prompt: str, **kwargs: object) -> str:
            call_count[0] += 1
            if call_count[0] < 3:
                return '{"status": "needs_revision", "confidence": 0.6, "reasoning": "Test", "rubric_scores": {}, "issues": []}'
            return '{"status": "passed", "confidence": 0.9, "reasoning": "Fixed", "rubric_scores": {}, "issues": []}'

    llm = MockLLM()
    verifier = VerifierAgent(llm)

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )

    result, retries = verify_step_with_retry(verifier, "Test query", step, "Output", max_retries=5)

    assert result.status == VerificationStatus.PASSED
    assert retries == 2  # 2 retries before passing


# --- VerificationLoop Tests ---


def test_verification_loop_config() -> None:
    """Test VerificationLoopConfig default values."""
    config = VerificationLoopConfig()

    assert config.max_retries == 3
    assert config.strictness == "standard"
    assert config.auto_retry is True


def test_verification_loop_state() -> None:
    """Test VerificationLoopState model."""
    state = VerificationLoopState(
        step_id="test-1",
        retry_count=2,
        consecutive_failures=1,
        last_status="needs_revision",
        last_action="retry",
    )

    assert state.step_id == "test-1"
    assert state.retry_count == 2
    assert state.consecutive_failures == 1


def test_verification_loop_init() -> None:
    """Test VerificationLoop initialization."""
    config = VerificationLoopConfig(max_retries=5)
    loop = VerificationLoop(config)

    assert loop._config.max_retries == 5
    assert len(loop._state) == 0


def test_verification_loop_get_state() -> None:
    """Test VerificationLoop state management."""
    loop = VerificationLoop()

    state1 = loop.get_state("step-1")
    state2 = loop.get_state("step-1")

    assert state1 is state2  # Same object returned
    assert state1.step_id == "step-1"


def test_verification_loop_decide_action_passed() -> None:
    """Test loop decides CONTINUE for PASSED status."""
    loop = VerificationLoop()

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )

    verification_result = {"status": "passed", "confidence": 0.9}
    action = loop.decide_action(step, verification_result)

    assert action == VerificationLoopAction.CONTINUE

    state = loop.get_state("test-1")
    assert state.consecutive_failures == 0


def test_verification_loop_decide_action_failed() -> None:
    """Test loop decides TERMINATE or ESCALATE for FAILED status."""
    loop = VerificationLoop()

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )

    verification_result = {"status": "failed", "confidence": 0.3}
    action = loop.decide_action(step, verification_result)

    assert action in (VerificationLoopAction.TERMINATE, VerificationLoopAction.ESCALATE)


def test_verification_loop_decide_action_needs_revision() -> None:
    """Test loop decides RETRY for NEEDS_REVISION status."""
    loop = VerificationLoop()

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )

    verification_result = {"status": "needs_revision", "confidence": 0.6}
    action = loop.decide_action(step, verification_result)

    assert action == VerificationLoopAction.RETRY


def test_verification_loop_max_retries_exceeded() -> None:
    """Test loop escalates when max retries exceeded."""
    loop = VerificationLoop(VerificationLoopConfig(max_retries=2))

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )

    # First retry
    loop.decide_action(step, {"status": "needs_revision", "confidence": 0.6})
    # Second retry
    loop.decide_action(step, {"status": "needs_revision", "confidence": 0.6})
    # Third attempt - should escalate
    action = loop.decide_action(step, {"status": "needs_revision", "confidence": 0.6})

    assert action == VerificationLoopAction.ESCALATE


def test_verification_loop_build_retry_query() -> None:
    """Test loop builds retry query with feedback."""
    loop = VerificationLoop()

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
        input_query="Original task",
    )

    verification_result = {
        "status": "needs_revision",
        "reasoning": "Missing requirement",
        "issues": [
            {
                "category": "completeness",
                "severity": "high",
                "description": "Missing X",
                "suggested_fix": "Add X",
            }
        ],
    }

    retry_query = loop.build_retry_query(step, verification_result)

    assert "验证反馈" in retry_query or "Verification Feedback" in retry_query
    assert "Missing X" in retry_query
    assert "Add X" in retry_query
    assert "Missing requirement" in retry_query


def test_verification_loop_should_execute_step() -> None:
    """Test loop determines which steps should execute."""
    loop = VerificationLoop()

    normal_step = ExecutionStep(
        step_id="normal-1",
        step_number=1,
        skill_id="test",
        intent="Normal step",
        is_verification_step=False,
    )

    verify_step = ExecutionStep(
        step_id="verify-1",
        step_number=2,
        skill_id="test",
        intent="Verify step",
        is_verification_step=True,
    )

    assert loop.should_execute_step(normal_step) is True
    assert loop.should_execute_step(verify_step) is False


def test_verification_loop_get_summary() -> None:
    """Test loop generates activity summary."""
    loop = VerificationLoop()

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )

    loop.decide_action(step, {"status": "passed", "confidence": 0.9})
    loop.decide_action(step, {"status": "needs_revision", "confidence": 0.6})

    summary = loop.get_summary()

    assert summary["total_steps_verified"] == 1
    assert summary["total_retries"] == 1
    assert "test-1" in summary["states"]


def test_verification_loop_action_enum() -> None:
    """Test VerificationLoopAction enum values."""
    assert VerificationLoopAction.CONTINUE.value == "continue"
    assert VerificationLoopAction.RETRY.value == "retry"
    assert VerificationLoopAction.ESCALATE.value == "escalate"
    assert VerificationLoopAction.TERMINATE.value == "terminate"


# --- TrustLevel Tests ---


def test_trust_level_enum() -> None:
    """Test TrustLevel enum values."""
    assert TrustLevel.TRUSTED.value == "trusted"
    assert TrustLevel.QUARANTINE.value == "quarantine"
    assert TrustLevel.SANDBOX.value == "sandbox"


def test_execution_step_trust_level_field() -> None:
    """Test ExecutionStep has trust_level field."""
    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
        trust_level=TrustLevel.QUARANTINE,
    )

    assert step.trust_level == TrustLevel.QUARANTINE

    step_dict = step.to_dict()
    assert step_dict["trust_level"] == "quarantine"


def test_execution_step_verification_fields() -> None:
    """Test ExecutionStep has verification-related fields."""
    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
        is_verification_step=True,
        trust_level=TrustLevel.QUARANTINE,
    )

    assert step.is_verification_step is True
    assert step.trust_level == TrustLevel.QUARANTINE


# --- Integration Tests ---


def test_adversarial_pattern_has_verification_step() -> None:
    """Test adversarial pattern adds verification step with QUARANTINE trust."""
    from vibesop.core.orchestration.plan_builder import PlanBuilder
    from vibesop.core.orchestration.task_decomposer import SubTask

    # Create a mock router with proper routing config
    class MockRouter:
        def __init__(self):
            self.routing_config = type("obj", (object,), {"enable_orchestration": True})()

        def _single_skill_route(self, query: str, context=None, candidates=None):
            from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute

            return RoutingResult(
                primary=SkillRoute(skill_id="test", confidence=0.9, layer=RoutingLayer.SCENARIO),
                alternatives=[],
                routing_path=[],
                layer_details=[],
                query=query,
                duration_ms=10,
            )

        def _get_skill_capabilities(self, skill_id: str):
            return []

        def _build_decomposition_skills(self, candidates, query):
            return []

    router = MockRouter()  # type: ignore
    builder = PlanBuilder(router)  # type: ignore

    sub_tasks = [
        SubTask(
            intent="Task 1",
            query="Do task 1",
            original_intent="Task 1",
            task_type="analysis",
        ),
        SubTask(
            intent="Task 2",
            query="Do task 2",
            original_intent="Task 2",
            task_type="review",
        ),
    ]

    plan = builder.build_plan(
        original_query="Test query",
        sub_tasks=sub_tasks,
        workflow_pattern=WorkflowPattern.ADVERSARIAL,
    )

    # Should have 3 steps: 2 execution + 1 verification
    assert len(plan.steps) == 3

    # Last step should be verification step
    verify_step = plan.steps[-1]
    assert verify_step.is_verification_step is True
    assert verify_step.trust_level == TrustLevel.QUARANTINE


def test_sequential_pattern_no_verification_step() -> None:
    """Test sequential pattern doesn't add verification step."""
    from vibesop.core.orchestration.plan_builder import PlanBuilder
    from vibesop.core.orchestration.task_decomposer import SubTask

    # Create a mock router with proper routing config
    class MockRouter:
        def __init__(self):
            self.routing_config = type("obj", (object,), {"enable_orchestration": True})()

        def _single_skill_route(self, query: str, context=None, candidates=None):
            from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute

            return RoutingResult(
                primary=SkillRoute(skill_id="test", confidence=0.9, layer=RoutingLayer.SCENARIO),
                alternatives=[],
                routing_path=[],
                layer_details=[],
                query=query,
                duration_ms=10,
            )

        def _get_skill_capabilities(self, skill_id: str):
            return []

        def _build_decomposition_skills(self, candidates, query):
            return []

    router = MockRouter()  # type: ignore
    builder = PlanBuilder(router)  # type: ignore

    sub_tasks = [
        SubTask(
            intent="Task 1",
            query="Do task 1",
            original_intent="Task 1",
            task_type="analysis",
        ),
    ]

    plan = builder.build_plan(
        original_query="Test query",
        sub_tasks=sub_tasks,
        workflow_pattern=WorkflowPattern.SEQUENTIAL,
    )

    # Should have 1 step only (no verification)
    assert len(plan.steps) == 1
    assert plan.steps[0].is_verification_step is False
    assert plan.steps[0].trust_level == TrustLevel.TRUSTED


def test_execution_order_with_dependencies() -> None:
    """Test _get_execution_order respects dependencies."""
    from vibesop.core.models import ExecutionMode, ExecutionStep
    from vibesop.core.orchestration.verification_loop import _get_execution_order

    step1 = ExecutionStep(
        step_id="s1",
        step_number=1,
        skill_id="test",
        intent="Step 1",
        dependencies=[],
    )
    step2 = ExecutionStep(
        step_id="s2",
        step_number=2,
        skill_id="test",
        intent="Step 2",
        dependencies=["s1"],
    )
    step3 = ExecutionStep(
        step_id="s3",
        step_number=3,
        skill_id="test",
        intent="Step 3",
        dependencies=["s2"],
    )

    plan = ExecutionPlan(
        plan_id="test-plan",
        original_query="Test",
        steps=[step3, step1, step2],  # Intentionally out of order
        execution_mode=ExecutionMode.SEQUENTIAL,
    )

    order = _get_execution_order(plan)

    # Should respect dependencies: 1 -> 2 -> 3
    assert order == [1, 2, 3]


# --- Phase 2.5 Fix Verification Tests ---


def test_strategy_hint_multi_key_value_parsing() -> None:
    """Test strategy_hint correctly parses multiple key:value pairs."""
    hint = "workflow_pattern:fan_out verify:strict"
    tokens = {}
    for token in hint.split():
        if ":" in token:
            k, v = token.split(":", 1)
            tokens[k.strip()] = v.strip()

    assert tokens["workflow_pattern"] == "fan_out"
    assert tokens["verify"] == "strict"


def test_strategy_hint_single_key_value() -> None:
    """Test strategy_hint correctly parses single key:value pair."""
    hint = "workflow_pattern:adversarial"
    tokens = {}
    for token in hint.split():
        if ":" in token:
            k, v = token.split(":", 1)
            tokens[k.strip()] = v.strip()

    assert tokens["workflow_pattern"] == "adversarial"
    assert "verify" not in tokens


def test_execution_plan_to_dict_includes_workflow_pattern() -> None:
    """Test ExecutionPlan.to_dict() includes workflow_pattern."""
    from vibesop.core.models import ExecutionMode

    plan = ExecutionPlan(
        plan_id="test-plan",
        original_query="Test",
        steps=[],
        execution_mode=ExecutionMode.PARALLEL,
        workflow_pattern=WorkflowPattern.FAN_OUT,
    )

    result = plan.to_dict()
    assert "workflow_pattern" in result
    assert result["workflow_pattern"] == "fan_out"


def test_execution_plan_summary_includes_workflow_pattern() -> None:
    """Test get_execution_summary() includes workflow_pattern."""
    from vibesop.core.models import ExecutionMode

    plan = ExecutionPlan(
        plan_id="test-plan",
        original_query="Test",
        steps=[],
        execution_mode=ExecutionMode.SEQUENTIAL,
        workflow_pattern=WorkflowPattern.ADVERSARIAL,
    )

    summary = plan.get_execution_summary()
    assert "workflow_pattern" in summary
    assert summary["workflow_pattern"] == "adversarial"


def test_verify_step_with_retry_accepts_executor() -> None:
    """Test verify_step_with_retry uses executor for re-execution."""
    call_count = [0]
    verify_count = [0]

    class MockLLM:
        def call(self, prompt: str, **kwargs: object) -> str:
            verify_count[0] += 1
            if verify_count[0] <= 1:
                return '{"status": "needs_revision", "confidence": 0.6, "reasoning": "Incomplete", "rubric_scores": {}, "issues": []}'
            return '{"status": "passed", "confidence": 0.9, "reasoning": "Fixed", "rubric_scores": {}, "issues": []}'

    def mock_executor(step):
        call_count[0] += 1
        return f"Re-executed output (attempt {call_count[0]})"

    llm = MockLLM()
    verifier = VerifierAgent(llm)

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
        input_query="Original query",
    )

    result, _retries = verify_step_with_retry(
        verifier,
        "Test query",
        step,
        "Initial output",
        max_retries=3,
        executor=mock_executor,
    )

    assert result.status == VerificationStatus.PASSED
    assert call_count[0] > 0  # Executor was called


def test_verify_step_with_retry_no_executor() -> None:
    """Test verify_step_with_retry works without executor (backward compat)."""
    call_count = [0]

    class MockLLM:
        def call(self, prompt: str, **kwargs: object) -> str:
            call_count[0] += 1
            if call_count[0] <= 2:
                return '{"status": "needs_revision", "confidence": 0.6, "reasoning": "Test", "rubric_scores": {}, "issues": []}'
            return '{"status": "passed", "confidence": 0.9, "reasoning": "OK", "rubric_scores": {}, "issues": []}'

    llm = MockLLM()
    verifier = VerifierAgent(llm)

    step = ExecutionStep(
        step_id="test-1",
        step_number=1,
        skill_id="test",
        intent="Test step",
    )

    result, _retries = verify_step_with_retry(
        verifier,
        "Test query",
        step,
        "Output",
        max_retries=5,
        executor=None,
    )

    assert result.status == VerificationStatus.PASSED


def test_apply_strictness_returns_new_object() -> None:
    """Test _apply_strictness returns a copy, not mutating original."""

    class MockLLM:
        def call(self, prompt: str, **kwargs: object) -> str:
            return "never called"

    llm = MockLLM()
    verifier = VerifierAgent(llm, strictness=VerificationStrictness.STRICT)

    original = VerificationResult(
        status=VerificationStatus.NEEDS_REVISION,
        confidence=0.6,
        reasoning="Test",
        issues=[
            VerificationIssue(
                category="completeness",
                severity="high",
                description="Missing X",
            )
        ],
    )

    result = verifier._apply_strictness(original)

    # Original should be unchanged
    assert original.status == VerificationStatus.NEEDS_REVISION
    # Result should be modified
    assert result.status == VerificationStatus.FAILED
    # They should be different objects
    assert original is not result


def test_verify_step_role_aware_reviewer() -> None:
    """Test verify_step runs role-aware review for reviewer/red_team roles."""
    loop = VerificationLoop()

    reviewer_step = ExecutionStep(
        step_id="rev-1",
        step_number=1,
        skill_id="review",
        intent="Review output",
        assigned_role="reviewer",
    )

    assert loop.verify_step(reviewer_step, "This is a meaningful review output.") is True
    assert loop.verify_step(reviewer_step, "") is False

    red_team_step = ExecutionStep(
        step_id="rt-1",
        step_number=1,
        skill_id="security",
        intent="Security review",
        assigned_role="red_team",
    )

    assert loop.verify_step(red_team_step, "Found XSS vulnerability") is True


def test_verify_step_quarantine_fallback() -> None:
    """Test verify_step falls back to quarantine check for non-reviewer steps."""
    loop = VerificationLoop()

    step = ExecutionStep(
        step_id="impl-1",
        step_number=1,
        skill_id="coding",
        intent="Implement feature",
        trust_level=TrustLevel.QUARANTINE,
    )

    assert loop.verify_step(step, "some output") is True
    assert loop.verify_step(step, "") is False


def test_verify_step_trusted_defaults_to_true() -> None:
    """Test verify_step returns True for trusted steps by default."""
    loop = VerificationLoop()

    step = ExecutionStep(
        step_id="impl-1",
        step_number=1,
        skill_id="coding",
        intent="Implement feature",
        trust_level=TrustLevel.TRUSTED,
    )

    assert loop.verify_step(step, "") is True
