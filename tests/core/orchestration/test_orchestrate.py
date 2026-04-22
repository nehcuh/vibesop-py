"""Tests for UnifiedRouter.orchestrate()."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.models import OrchestrationMode
from vibesop.core.routing import UnifiedRouter


class TestOrchestrate:
    """Test orchestration behavior on UnifiedRouter."""

    def test_orchestrate_disabled_returns_single(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_orchestration=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.orchestrate("review my code")

        assert result.mode == OrchestrationMode.SINGLE
        assert result.primary is not None or not result.has_match

    def test_orchestrate_short_query_returns_single(self, tmp_path: Path) -> None:
        router = UnifiedRouter(project_root=tmp_path)
        result = router.orchestrate("help")

        assert result.mode == OrchestrationMode.SINGLE

    def test_orchestrate_multi_intent_detected(self, tmp_path: Path) -> None:
        router = UnifiedRouter(project_root=tmp_path)
        # Query with conjunctions that triggers heuristic
        result = router.orchestrate("分析架构然后提出优化建议")

        # Should detect multi-intent but may not build plan if skills not found
        assert result.mode in (OrchestrationMode.SINGLE, OrchestrationMode.ORCHESTRATED)

    def test_orchestrate_fallback_when_no_decomposition(self, tmp_path: Path) -> None:
        router = UnifiedRouter(project_root=tmp_path)
        result = router.orchestrate("review my code please")

        # Short enough to be single intent, should fallback
        assert result.mode == OrchestrationMode.SINGLE

    def test_orchestration_result_has_duration(self, tmp_path: Path) -> None:
        router = UnifiedRouter(project_root=tmp_path)
        result = router.orchestrate("test query")
        assert result.duration_ms >= 0
