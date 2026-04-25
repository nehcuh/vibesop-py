"""Verify orchestrate() is the CLI default entry point with proper fallback."""


from vibesop.core.models import OrchestrationMode
from vibesop.core.routing.unified import UnifiedRouter


class TestOrchestrateAsDefault:
    """Verify orchestrate() behavior for the CLI default path."""

    def test_single_intent_returns_single_mode(self):
        """Single-intent queries should return mode=SINGLE."""
        router = UnifiedRouter(project_root=".")
        result = router.orchestrate("帮我review这段代码")

        assert result.mode == OrchestrationMode.SINGLE
        assert result.primary is not None
        assert result.execution_plan is None

    def test_orchestrated_result_has_fallback(self):
        """Orchestrated results must include a single-skill fallback."""
        router = UnifiedRouter(project_root=".")
        # A query that might trigger orchestration
        result = router.orchestrate("分析项目架构，然后审查代码质量")

        if result.mode == OrchestrationMode.ORCHESTRATED:
            assert result.single_fallback is not None
            assert result.execution_plan is not None
            assert len(result.execution_plan.steps) >= 1

    def test_orchestration_disabled_falls_back(self):
        """When orchestration is disabled, should return single mode."""
        from vibesop.core.config import RoutingConfig

        config = RoutingConfig(enable_orchestration=False)
        router = UnifiedRouter(project_root=".", config=config)
        result = router.orchestrate("分析架构并优化性能")

        assert result.mode == OrchestrationMode.SINGLE
        assert result.primary is not None
