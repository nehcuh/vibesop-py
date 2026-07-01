"""Tests for routing layer types and models."""

from vibesop.core.models import RoutingLayer, SkillRoute
from vibesop.core.routing.layers import LayerResult


class TestLayerResult:
    """Test LayerResult model."""

    def test_default_creation(self):
        """LayerResult should have sensible defaults."""
        result = LayerResult()
        assert result.match is None
        assert result.alternatives == []
        assert result.layer == RoutingLayer.NO_MATCH
        assert result.should_stop is True
        assert result.matched is False
        assert result.reason == ""
        assert result.diagnostics == {}

    def test_creation_with_match(self):
        """LayerResult can be created with a match."""
        route = SkillRoute(skill_id="test/skill", confidence=0.95, layer=RoutingLayer.EXPLICIT)
        result = LayerResult(
            match=route,
            layer=RoutingLayer.EXPLICIT,
            matched=True,
            should_stop=True,
            reason="Explicit match found",
            diagnostics={"pattern": "/test"},
        )
        assert result.match is not None
        assert result.match.skill_id == "test/skill"
        assert result.matched is True
        assert result.reason == "Explicit match found"
        assert result.diagnostics["pattern"] == "/test"

    def test_creation_with_alternatives(self):
        """LayerResult can include alternative matches."""
        alt1 = SkillRoute(skill_id="alt/1", confidence=0.7, layer=RoutingLayer.KEYWORD)
        alt2 = SkillRoute(skill_id="alt/2", confidence=0.6, layer=RoutingLayer.TFIDF)
        result = LayerResult(
            alternatives=[alt1, alt2],
            layer=RoutingLayer.KEYWORD,
        )
        assert len(result.alternatives) == 2
        assert result.alternatives[0].skill_id == "alt/1"

    def test_field_mutability(self):
        """LayerResult should be mutable (frozen=False)."""
        result = LayerResult()
        result.matched = True
        result.reason = "Updated"
        assert result.matched is True
        assert result.reason == "Updated"
