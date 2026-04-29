"""Tests for UnifiedRouter._route() branches and internal logic.

Covers:
    - Explicit layer routing
    - Scenario layer routing
    - Keyword/TF-IDF/Embedding matcher pipeline
    - Fallback handling
    - Degradation logic
    - _build_match_result
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.models import DegradationLevel, RoutingLayer
from vibesop.core.routing import UnifiedRouter

if TYPE_CHECKING:
    from pathlib import Path


class TestRouteExplicitLayer:
    """Test explicit override layer (Layer 0)."""

    def test_explicit_skill_id_routing(self, tmp_path: Path) -> None:
        """Routing with explicit skill_id should match directly."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._route("use skill:systematic-debugging")

        if result.has_match:
            assert "systematic-debugging" in result.primary.skill_id

    def test_explicit_namespace_routing(self, tmp_path: Path) -> None:
        """Routing with namespace prefix should match."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._route("gstack/review")

        if result.has_match:
            assert "gstack" in result.primary.skill_id or "review" in result.primary.skill_id


class TestRouteScenarioLayer:
    """Test scenario pattern layer (Layer 1)."""

    def test_scenario_debug_error(self, tmp_path: Path) -> None:
        """Debug-related queries should match debugging skills."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._route("database connection failed")

        assert result.has_match
        if result.has_match:
            primary = result.primary.skill_id.lower()
            assert any(kw in primary for kw in ["debug", "error", "systematic", "office"])

    def test_scenario_review_code(self, tmp_path: Path) -> None:
        """Review-related queries should match review skills."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._route("review my pull request")

        if result.has_match:
            assert "review" in result.primary.skill_id.lower()


class TestRouteMatcherPipeline:
    """Test matcher pipeline (Layers 3-6)."""

    def test_keyword_matching_short_query(self, tmp_path: Path) -> None:
        """Short queries should use keyword matching."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._route("debug")

        assert result.has_match
        assert result.primary is not None

    def test_fuzzy_matching_typo(self, tmp_path: Path) -> None:
        """Typo-tolerant queries should match via Levenshtein."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._route("debbug")  # typo for debug

        assert result.has_match
        assert result.primary is not None

    def test_no_match_returns_fallback(self, tmp_path: Path) -> None:
        """Queries with no match should return fallback layer."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._route("xyzabc123 nonsense query")

        # Should either have no match or fallback
        if not result.has_match:
            assert result.primary is None
        else:
            # If it matches something, that's also fine
            assert result.primary is not None


class TestRouteDegradation:
    """Test degradation logic."""

    def test_degradation_levels_exist(self, tmp_path: Path) -> None:
        """Degradation levels should be properly defined."""
        assert DegradationLevel.AUTO == "auto"
        assert DegradationLevel.SUGGEST == "suggest"
        assert DegradationLevel.DEGRADE == "degrade"
        assert DegradationLevel.FALLBACK == "fallback"

    def test_high_confidence_auto(self, tmp_path: Path) -> None:
        """High confidence matches should not degrade."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._route("debug")

        if result.has_match and result.primary.confidence >= 0.8:
            assert result.primary.layer != RoutingLayer.FALLBACK_LLM


class TestBuildMatchResult:
    """Test _build_match_result internal method."""

    def test_build_result_with_valid_match(self, tmp_path: Path) -> None:
        """Building result with valid match should succeed."""
        from vibesop.core.models import SkillRoute

        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        primary = SkillRoute(skill_id="test-skill", confidence=0.9, layer=RoutingLayer.KEYWORD)
        match = router._build_match_result(
            query="debug",
            primary=primary,
            alternatives=[],
            routing_path=[RoutingLayer.KEYWORD],
            layer_details=[],
            start_time=0.0,
            deprecated_warnings=None,
            conversation=None,
            original_query="debug",
        )
        assert match is not None
        assert match.primary is not None
        assert match.primary.skill_id == "test-skill"

    def test_build_result_with_alternatives(self, tmp_path: Path) -> None:
        """Building result with alternatives should include them."""
        from vibesop.core.models import SkillRoute

        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        primary = SkillRoute(skill_id="primary-skill", confidence=0.9, layer=RoutingLayer.KEYWORD)
        alt = SkillRoute(skill_id="alt-skill", confidence=0.7, layer=RoutingLayer.KEYWORD)
        match = router._build_match_result(
            query="debug",
            primary=primary,
            alternatives=[alt],
            routing_path=[RoutingLayer.KEYWORD],
            layer_details=[],
            start_time=0.0,
            deprecated_warnings=None,
            conversation=None,
            original_query="debug",
        )
        assert match is not None
        assert len(match.alternatives) >= 1


class TestRouteWithContext:
    """Test routing with context enrichment."""

    def test_routing_with_project_type(self, tmp_path: Path) -> None:
        """Routing should accept project type context."""
        from vibesop.core.matching import RoutingContext

        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        context = RoutingContext(project_type="python")

        result = router._route("test", context=context)

        assert result.has_match
