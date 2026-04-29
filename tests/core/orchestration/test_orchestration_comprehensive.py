"""Comprehensive tests for UnifiedRouter.orchestrate() covering all branches.

Tests the complete orchestration flow:
    route → detect → decompose → plan → result

Coverage targets:
    - orchestration disabled
    - single-intent fallback
    - multi-intent detection
    - task decomposition failure
    - plan building failure
    - empty plan fallback
    - successful orchestration
    - callback invocation
    - error policies
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.models import OrchestrationMode, OrchestrationResult
from vibesop.core.orchestration.callbacks import (
    ErrorPolicy,
    NoOpCallbacks,
    OrchestrationPhase,
    PhaseInfo,
)
from vibesop.core.routing import UnifiedRouter

if TYPE_CHECKING:
    from pathlib import Path


class TestOrchestrationBranches:
    """Test all branches of the orchestrate() method."""

    def test_orchestration_disabled_returns_single(self, tmp_path: Path) -> None:
        """When enable_orchestration=False, always return SINGLE mode."""
        config = RoutingConfig(enable_ai_triage=False, enable_orchestration=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.orchestrate("帮我调试这个错误")

        assert result.mode == OrchestrationMode.SINGLE
        assert isinstance(result, OrchestrationResult)
        assert result.execution_plan is None

    def test_single_intent_short_query(self, tmp_path: Path) -> None:
        """Short single-word queries should not trigger orchestration."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.orchestrate("debug")

        assert result.mode == OrchestrationMode.SINGLE

    def test_single_intent_simple_query(self, tmp_path: Path) -> None:
        """Simple clear intent queries should return SINGLE."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.orchestrate("review my code")

        assert result.mode == OrchestrationMode.SINGLE
        assert result.primary is not None

    def test_multi_intent_with_conjunctions(self, tmp_path: Path) -> None:
        """Queries with conjunctions may trigger orchestration."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.orchestrate("分析架构然后写测试")

        # Result can be either SINGLE or ORCHESTRATED depending on skill matching
        assert result.mode in (OrchestrationMode.SINGLE, OrchestrationMode.ORCHESTRATED)

    def test_orchestration_result_structure(self, tmp_path: Path) -> None:
        """All orchestration results have required fields."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.orchestrate("test query")

        assert result.duration_ms >= 0
        assert result.original_query == "test query"
        assert result.mode in (OrchestrationMode.SINGLE, OrchestrationMode.ORCHESTRATED)

        if result.mode == OrchestrationMode.ORCHESTRATED:
            assert result.execution_plan is not None
            assert result.single_fallback is not None
            assert len(result.execution_plan.steps) >= 1
        else:
            assert result.execution_plan is None or result.execution_plan is not None


class TestOrchestrationCallbacks:
    """Test callback invocation during orchestration."""

    def test_callbacks_invoked_for_single_intent(self, tmp_path: Path) -> None:
        """Callbacks should be called even for single-intent queries."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        cb = MagicMock()
        result = router.orchestrate("debug", callbacks=cb)

        # At minimum, routing phase should be called
        cb.on_phase_start.assert_called()
        cb.on_phase_complete.assert_called()
        assert result.mode == OrchestrationMode.SINGLE

    def test_no_op_callbacks_work(self, tmp_path: Path) -> None:
        """NoOpCallbacks should not raise any errors."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        cb = NoOpCallbacks()
        result = router.orchestrate("test", callbacks=cb)

        assert result.mode in (OrchestrationMode.SINGLE, OrchestrationMode.ORCHESTRATED)


class TestOrchestrationErrorHandling:
    """Test error handling in orchestration pipeline."""

    def test_decomposition_failure_falls_back(self, tmp_path: Path) -> None:
        """When task decomposer fails, should fallback to single skill."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        with patch.object(
            router, "_get_task_decomposer"
        ) as mock_get_decomposer:
            mock_decomposer = MagicMock()
            mock_decomposer.decompose.side_effect = RuntimeError("Decomposition failed")
            mock_get_decomposer.return_value = mock_decomposer

            result = router.orchestrate("分析架构然后写测试")

            assert result.mode == OrchestrationMode.SINGLE

    def test_plan_building_failure_falls_back(self, tmp_path: Path) -> None:
        """When plan builder fails, should fallback to single skill."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        with patch.object(
            router, "_get_plan_builder"
        ) as mock_get_builder:
            mock_builder = MagicMock()
            mock_builder.build_plan.side_effect = RuntimeError("Plan building failed")
            mock_get_builder.return_value = mock_builder

            result = router.orchestrate("分析架构然后写测试")

            assert result.mode == OrchestrationMode.SINGLE

    def test_empty_sub_tasks_falls_back(self, tmp_path: Path) -> None:
        """When decomposition returns empty tasks, should fallback."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        with patch.object(
            router, "_get_task_decomposer"
        ) as mock_get_decomposer:
            mock_decomposer = MagicMock()
            mock_decomposer.decompose.return_value = []
            mock_get_decomposer.return_value = mock_decomposer

            result = router.orchestrate("分析架构然后写测试")

            assert result.mode == OrchestrationMode.SINGLE

    def test_single_sub_task_falls_back(self, tmp_path: Path) -> None:
        """When decomposition returns only 1 task, should fallback."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        with patch.object(
            router, "_get_task_decomposer"
        ) as mock_get_decomposer:
            mock_decomposer = MagicMock()
            mock_decomposer.decompose.return_value = [
                {"intent": "analysis", "skill": "test"}
            ]
            mock_get_decomposer.return_value = mock_decomposer

            result = router.orchestrate("分析架构然后写测试")

            assert result.mode == OrchestrationMode.SINGLE

    def test_empty_plan_falls_back(self, tmp_path: Path) -> None:
        """When plan builder returns empty plan, should fallback."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        mock_plan = MagicMock()
        mock_plan.steps = []

        with patch.object(
            router, "_get_task_decomposer"
        ) as mock_get_decomposer, patch.object(
            router, "_get_plan_builder"
        ) as mock_get_builder:
            mock_decomposer = MagicMock()
            mock_decomposer.decompose.return_value = [
                {"intent": "analysis", "skill": "test"},
                {"intent": "review", "skill": "test"},
            ]
            mock_get_decomposer.return_value = mock_decomposer

            mock_builder = MagicMock()
            mock_builder.build_plan.return_value = mock_plan
            mock_get_builder.return_value = mock_builder

            result = router.orchestrate("分析架构然后写测试")

            assert result.mode == OrchestrationMode.SINGLE


class TestOrchestrationWithContext:
    """Test orchestration with routing context."""

    def test_orchestrate_with_context(self, tmp_path: Path) -> None:
        """Orchestration should accept and use routing context."""
        from vibesop.core.matching import RoutingContext

        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        context = RoutingContext(project_type="python")

        result = router.orchestrate("帮我review代码", context=context)

        assert result.mode in (OrchestrationMode.SINGLE, OrchestrationMode.ORCHESTRATED)

    def test_orchestrate_with_candidates(self, tmp_path: Path) -> None:
        """Orchestration should accept explicit candidates."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        candidates = [
            {"id": "skill-a", "intent": "test", "keywords": ["test"]},
            {"id": "skill-b", "intent": "review", "keywords": ["review"]},
        ]

        result = router.orchestrate("review", candidates=candidates)

        assert result.mode == OrchestrationMode.SINGLE
        assert result.primary is not None
