"""Tests for routing layer types and models."""

import pytest
from pydantic import ValidationError

from vibesop.core.models import RoutingLayer, SkillRoute
from vibesop.core.routing.layers import IRouteLayer, LayerResult


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


class TestIRouteLayer:
    """Test IRouteLayer protocol."""

    def test_protocol_exists(self):
        """IRouteLayer should be importable and usable as a protocol."""
        assert hasattr(IRouteLayer, "layer")
        assert hasattr(IRouteLayer, "try_route")

    def test_conforming_class(self):
        """A class implementing the protocol should work."""

        class DummyLayer:
            @property
            def layer(self) -> RoutingLayer:
                return RoutingLayer.EXPLICIT

            def try_route(self, query, candidates, context=None):
                return LayerResult(match=None, layer=self.layer)

        dummy = DummyLayer()
        # IRouteLayer is not @runtime_checkable, so we verify by duck typing
        assert hasattr(dummy, "layer")
        assert hasattr(dummy, "try_route")
        result = dummy.try_route("test", [])
        assert result.layer == RoutingLayer.EXPLICIT
