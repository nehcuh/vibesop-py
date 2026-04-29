"""Unit tests for routing layers (v3.0.0)."""

from pathlib import Path
from unittest.mock import patch

from vibesop.core.matching import MatchResult, MatcherType
from vibesop.core.models import RoutingLayer
from vibesop.core.routing import RoutingConfig, UnifiedRouter


class TestLayer1Explicit:
    """Test Layer 1: Explicit skill invocation."""

    def test_direct_skill_invocation(self) -> None:
        """Test direct skill invocation by keyword."""
        router = UnifiedRouter(project_root=Path.cwd(), config=RoutingConfig(enable_ai_triage=False))
        result = router.route("review my code")

        # Should find a match or have alternatives
        assert result is not None

    def test_slash_prefix_with_known_skill(self) -> None:
        """Test / prefix for direct skill invocation."""
        router = UnifiedRouter(project_root=Path.cwd(), config=RoutingConfig(enable_ai_triage=False))
        result = router.route("/review")

        # Should handle slash prefix
        assert result is not None


class TestLayer2Scenario:
    """Test Layer 2: Scenario-based patterns."""

    def test_test_keywords(self) -> None:
        """Test keywords trigger testing scenarios."""
        router = UnifiedRouter(project_root=Path.cwd(), config=RoutingConfig(enable_ai_triage=False))
        result = router.route("run tests")

        assert result is not None

    def test_refactor_keywords(self) -> None:
        """Test keywords trigger refactoring scenarios."""
        router = UnifiedRouter(project_root=Path.cwd(), config=RoutingConfig(enable_ai_triage=False))
        result = router.route("refactor this code")

        assert result is not None

    def test_chinese_keywords(self) -> None:
        """Test Chinese keywords work."""
        router = UnifiedRouter(project_root=Path.cwd(), config=RoutingConfig(enable_ai_triage=False))
        result = router.route("帮我调试")

        assert result is not None


class TestLayer3Semantic:
    """Test Layer 3: Semantic matching."""

    def test_semantic_similarity(self) -> None:
        """Test semantic similarity matching."""
        config = RoutingConfig(min_confidence=0.0, enable_embedding=False, enable_ai_triage=False)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)
        result = router.route("fix the bug")

        # Should attempt semantic matching
        assert result is not None

    def test_synonym_handling(self) -> None:
        """Test synonym handling in semantic layer."""
        config = RoutingConfig(min_confidence=0.0, enable_ai_triage=False)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)
        result = router.route("examine the code")

        assert result is not None


class TestLayer4Fuzzy:
    """Test Layer 4: Fuzzy matching fallback."""

    def test_typo_tolerance(self) -> None:
        """Test fuzzy matching handles typos."""
        config = RoutingConfig(min_confidence=0.0, enable_ai_triage=False)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)
        result = router.route("ddebug")  # Typo for "debug"

        # Should fall back to fuzzy matching
        assert result is not None

    def test_low_confidence_fallback(self) -> None:
        """Test fallback with very low confidence."""
        config = RoutingConfig(min_confidence=0.0, enable_ai_triage=False)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)
        result = router.route("xyz")

        # Should still return a result
        assert result is not None


class TestEarlyLayerOptimization:
    """Test that EXPLICIT/SCENARIO/AI_TRIAGE matches also go through OptimizationService.

    Before the fix, only MatcherPipeline (layers 3-6) applied optimizations
    such as session stickiness, habit boost, and quality boost. Early-layer
    matches bypassed OptimizationService entirely, causing inconsistent
    multi-turn behavior.
    """

    def test_explicit_match_calls_optimizations(self) -> None:
        """EXPLICIT layer match should trigger _apply_optimizations."""
        router = UnifiedRouter(project_root=Path.cwd(), config=RoutingConfig(enable_ai_triage=False))
        candidates = [
            {"id": "test-skill", "description": "Test skill", "enabled": True}
        ]

        with patch.object(router, "_apply_optimizations") as mock_opt:
            mock_opt.return_value = (
                MatchResult(
                    skill_id="test-skill",
                    confidence=1.0,
                    matcher_type=MatcherType.CUSTOM,
                ),
                [],
            )

            result = router.route("!test-skill hello", candidates=candidates)

            assert mock_opt.called, (
                "EXPLICIT layer match should call _apply_optimizations"
            )
            assert result.primary is not None
            assert result.primary.skill_id == "test-skill"
            assert result.primary.layer == RoutingLayer.EXPLICIT

    def test_matcher_layer_skips_duplicate_optimizations(self) -> None:
        """Matcher pipeline layers should NOT call _apply_optimizations again.

        MatcherPipeline already applies optimizations internally; calling
        them again in route() would double-count boosts.
        """
        config = RoutingConfig(min_confidence=0.0, enable_ai_triage=False)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)

        with patch.object(router, "_apply_optimizations") as mock_opt:
            # Provide a return value so _build_match_result can unpack correctly
            # when early layers (EXPLICIT/SCENARIO/AI_TRIAGE) call it.
            mock_opt.return_value = (None, [])  # type: ignore[attr-defined]

            # If matcher pipeline hits, _apply_optimizations should NOT be
            # called from route() because MatcherPipeline already did it.
            result = router.route("optimize loop performance")

            # The mock on route()'s _apply_optimizations should NOT be called
            # for matcher-pipeline layers; if it IS called, that means the
            # duplicate-optimization guard failed.
            if result.primary and result.primary.layer in {
                RoutingLayer.KEYWORD,
                RoutingLayer.TFIDF,
                RoutingLayer.EMBEDDING,
                RoutingLayer.LEVENSHTEIN,
            }:
                assert not mock_opt.called, (
                    "Matcher pipeline layers must not trigger duplicate optimizations"
                )
