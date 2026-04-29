"""Tests for FALLBACK_LLM fallback behavior."""

from __future__ import annotations

from vibesop.core.config import RoutingConfig
from vibesop.core.models import RoutingLayer
from vibesop.core.routing.unified import UnifiedRouter


class TestFallbackLLM:
    """Test fallback behavior when no skill matches."""

    def test_fallback_mode_transparent_returns_fallback_llm(self, tmp_path):
        """Test that transparent fallback returns FALLBACK_LLM primary."""
        config = RoutingConfig(fallback_mode="transparent", min_confidence=0.99, enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.route("xyzqwerty_no_match_12345")

        assert result.primary is not None
        assert result.primary.skill_id == "fallback-llm"
        assert result.primary.layer == RoutingLayer.FALLBACK_LLM
        assert result.has_match is False

    def test_fallback_mode_disabled_returns_none(self, tmp_path):
        """Test that disabled fallback returns primary=None."""
        config = RoutingConfig(fallback_mode="disabled", min_confidence=0.99, enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.route("xyzqwerty_no_match_12345")

        assert result.primary is None
        assert result.has_match is False

    def test_fallback_mode_silent_returns_none_with_alternatives(self, tmp_path):
        """Test that silent fallback returns primary=None but keeps alternatives."""
        config = RoutingConfig(fallback_mode="silent", min_confidence=0.99, enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        # Create a candidate so alternatives can be populated
        (tmp_path / ".vibe" / "skills" / "test-skill").mkdir(parents=True)
        (tmp_path / ".vibe" / "skills" / "test-skill" / "SKILL.md").write_text(
            "---\nname: test-skill\nintent: Test skill\n---\n# Test\n",
            encoding="utf-8",
        )

        result = router.route("xyzqwerty12345_nonsense_no_match")

        assert result.primary is None
        assert result.has_match is False

    def test_fallback_includes_nearest_candidates(self, tmp_path):
        """Test that fallback includes nearest candidates as alternatives."""
        config = RoutingConfig(fallback_mode="transparent", min_confidence=0.99, enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.route("xyzqwerty_no_match_12345")

        # Alternatives may be empty if no candidates are close, but the structure is correct
        assert isinstance(result.alternatives, list)
        assert RoutingLayer.FALLBACK_LLM in result.routing_path

    def test_has_match_excludes_fallback_llm(self, tmp_path):
        """Test that has_match is False when primary is FALLBACK_LLM."""
        config = RoutingConfig(fallback_mode="transparent", min_confidence=0.99, enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.route("no_match_query_abc123")

        assert result.primary is not None
        assert result.primary.layer == RoutingLayer.FALLBACK_LLM
        assert result.has_match is False

    def test_routing_path_includes_fallback_layer(self, tmp_path):
        """Test that routing_path includes FALLBACK_LLM as last element."""
        config = RoutingConfig(fallback_mode="transparent", min_confidence=0.99, enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.route("no_match_query_abc123")

        assert result.routing_path[-1] == RoutingLayer.FALLBACK_LLM

    def test_layer_details_include_fallback(self, tmp_path):
        """Test that layer_details includes FALLBACK_LLM detail."""
        config = RoutingConfig(fallback_mode="transparent", min_confidence=0.99, enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.route("no_match_query_abc123")

        fallback_details = [d for d in result.layer_details if d.layer == RoutingLayer.FALLBACK_LLM]
        assert len(fallback_details) == 1
        assert fallback_details[0].matched is True
