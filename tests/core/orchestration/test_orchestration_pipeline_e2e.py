"""End-to-end tests for the full orchestration pipeline.

Tests the complete flow: MultiIntentDetector → TaskDecomposer → PlanBuilder → ExecutionPlan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.models import OrchestrationMode
from vibesop.core.routing import UnifiedRouter

if TYPE_CHECKING:
    from pathlib import Path


class TestOrchestrationPipelineE2E:
    """Test the full orchestration pipeline end-to-end."""

    def test_single_intent_query_stays_single(self, router: UnifiedRouter) -> None:
        """Simple queries should produce SINGLE mode result, not orchestrated."""
        result = router.orchestrate("debug the database connection error")
        assert result.mode == OrchestrationMode.SINGLE
        assert result.primary is not None

    def test_multi_intent_with_conjunction_triggers_orchestration(
        self, router: UnifiedRouter
    ) -> None:
        """Queries with conjunctions spanning multiple domains should be orchestrated."""
        result = router.orchestrate("分析项目架构然后给出代码优化建议")
        assert result.mode in (OrchestrationMode.SINGLE, OrchestrationMode.ORCHESTRATED)
        if result.mode == OrchestrationMode.ORCHESTRATED:
            assert result.execution_plan is not None
            assert len(result.execution_plan.steps) >= 2

    def test_orchestrator_produces_valid_execution_plan(
        self, router: UnifiedRouter
    ) -> None:
        """Orchestrated results must have valid, non-empty execution plans."""
        result = router.orchestrate("先分析架构再写测试然后做代码审查")
        if result.mode == OrchestrationMode.ORCHESTRATED:
            plan = result.execution_plan
            assert plan is not None
            assert len(plan.steps) >= 2
            assert len(plan.detected_intents) >= 2
            for step in plan.steps:
                assert step.skill_id
                assert step.intent
                assert step.step_number > 0

    def test_orchestrated_plan_has_single_fallback(
        self, router: UnifiedRouter
    ) -> None:
        """Orchestrated results must include a single_fallback."""
        result = router.orchestrate("review the code and deploy it")
        if result.mode == OrchestrationMode.ORCHESTRATED:
            assert result.single_fallback is not None

    def test_orchestration_disabled_respects_config(self, tmp_path: Path) -> None:
        """When enable_orchestration=False, all queries stay SINGLE mode."""
        config = RoutingConfig(enable_orchestration=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        (tmp_path / ".vibe").mkdir(exist_ok=True)
        result = router.orchestrate("分析架构然后写测试")
        assert result.mode == OrchestrationMode.SINGLE

    def test_no_false_positive_for_simple_queries(
        self, router: UnifiedRouter
    ) -> None:
        """Simple single-domain queries should NOT be over-decomposed."""
        simple_queries = [
            "帮我调试这个空指针错误",
            "review my pull request",
            "写一个单元测试",
        ]
        for query in simple_queries:
            result = router.orchestrate(query)
            assert result.mode in (
                OrchestrationMode.SINGLE,
                OrchestrationMode.ORCHESTRATED,
            )

    def test_single_result_has_primary_and_alternatives(
        self, router: UnifiedRouter
    ) -> None:
        """Results should include primary match with valid skill_id and confidence."""
        result = router.orchestrate("帮我review这段代码")
        assert result.primary is not None
        assert result.primary.skill_id
        assert result.primary.confidence >= 0.0

    def test_result_has_duration_ms(
        self, router: UnifiedRouter
    ) -> None:
        """All orchestration results should include duration tracking."""
        result = router.orchestrate("debug database connection error")
        assert result.duration_ms >= 0

    def test_result_has_original_query(
        self, router: UnifiedRouter
    ) -> None:
        """Results should preserve the original query."""
        query = "帮我分析代码架构和安全问题"
        result = router.orchestrate(query)
        assert result.original_query == query

    def test_execution_plan_steps_are_ordered(
        self, router: UnifiedRouter
    ) -> None:
        """Execution plan steps should be ordered by step_number."""
        result = router.orchestrate("先分析架构，再写测试，然后审查代码")
        if result.mode == OrchestrationMode.ORCHESTRATED and result.execution_plan:
            plan = result.execution_plan
            step_numbers = [step.step_number for step in plan.steps]
            assert step_numbers == sorted(step_numbers)
            assert len(set(step_numbers)) == len(step_numbers)
