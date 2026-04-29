"""Tests for DegradationManager."""

from vibesop.core.models import DegradationLevel, RoutingLayer, SkillRoute
from vibesop.core.routing.degradation import DegradationManager


class FakeConfig:
    degradation_enabled = True
    degradation_auto_threshold = 0.6
    degradation_suggest_threshold = 0.4
    degradation_degrade_threshold = 0.2
    degradation_fallback_always_ask = True
    fallback_mode = "transparent"
    min_confidence = 0.3


def make_route(skill_id: str, confidence: float) -> SkillRoute:
    return SkillRoute(
        skill_id=skill_id,
        confidence=confidence,
        layer=RoutingLayer.KEYWORD,
        source="builtin",
    )


class TestDegradationManager:
    def test_auto_level_high_confidence(self):
        mgr = DegradationManager(FakeConfig())
        route = make_route("systematic-debugging", 0.85)
        level, result_route = mgr.evaluate(route)
        assert level == DegradationLevel.AUTO
        assert result_route is route

    def test_suggest_level_moderate_confidence(self):
        mgr = DegradationManager(FakeConfig())
        route = make_route("superpowers/refactor", 0.55)
        level, result_route = mgr.evaluate(route)
        assert level == DegradationLevel.SUGGEST
        assert result_route is route

    def test_degrade_level_low_confidence(self):
        mgr = DegradationManager(FakeConfig())
        route = make_route("gstack/review", 0.35)
        level, result_route = mgr.evaluate(route)
        assert level == DegradationLevel.DEGRADE
        assert result_route is not None
        assert result_route.skill_id == route.skill_id
        assert result_route.confidence == route.confidence
        assert result_route.metadata.get("degraded") is True
        assert result_route.metadata.get("degradation_level") == "degrade"

    def test_fallback_level_below_threshold(self):
        mgr = DegradationManager(FakeConfig())
        route = make_route("some-skill", 0.15)
        level, result_route = mgr.evaluate(route)
        assert level == DegradationLevel.FALLBACK
        assert result_route is None

    def test_no_primary_returns_fallback(self):
        mgr = DegradationManager(FakeConfig())
        level, result_route = mgr.evaluate(None)
        assert level == DegradationLevel.FALLBACK
        assert result_route is None

    def test_degradation_disabled_bypasses(self):
        config = FakeConfig()
        config.degradation_enabled = False
        mgr = DegradationManager(config)
        route = make_route("some-skill", 0.35)
        level, result_route = mgr.evaluate(route)
        assert level == DegradationLevel.AUTO
        assert result_route is route

    def test_boundary_confidence_exact_threshold(self):
        mgr = DegradationManager(FakeConfig())
        route = make_route("boundary-skill", 0.6)
        level, _ = mgr.evaluate(route)
        assert level == DegradationLevel.AUTO
