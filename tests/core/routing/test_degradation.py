"""Tests for DegradationManager — 4-level confidence-gated degradation."""

from __future__ import annotations

from unittest.mock import MagicMock

from vibesop.core.models import DegradationLevel, RoutingLayer, SkillRoute
from vibesop.core.routing.degradation import DegradationManager


class TestDegradationManager:
    """Test DegradationManager confidence-gated routing."""

    def _make_config(self, **overrides) -> MagicMock:
        defaults = {
            "degradation_enabled": True,
            "degradation_auto_threshold": 0.6,
            "degradation_suggest_threshold": 0.4,
            "degradation_degrade_threshold": 0.2,
            "degradation_fallback_always_ask": True,
        }
        defaults.update(overrides)
        return MagicMock(**defaults)

    def _make_route(self, skill_id: str = "test/skill", confidence: float = 0.9) -> SkillRoute:
        return SkillRoute(skill_id=skill_id, confidence=confidence, layer=RoutingLayer.AI_TRIAGE)

    def test_auto_above_threshold(self) -> None:
        mgr = DegradationManager(self._make_config())
        route = self._make_route(confidence=0.85)
        level, result = mgr.evaluate(route)
        assert level == DegradationLevel.AUTO
        assert result is route

    def test_suggest_between_auto_and_suggest(self) -> None:
        mgr = DegradationManager(self._make_config())
        route = self._make_route(confidence=0.5)
        level, result = mgr.evaluate(route)
        assert level == DegradationLevel.SUGGEST
        assert result is route

    def test_degrade_between_suggest_and_degrade(self) -> None:
        mgr = DegradationManager(self._make_config())
        route = self._make_route(confidence=0.3)
        level, result = mgr.evaluate(route)
        assert level == DegradationLevel.DEGRADE
        assert result is not None
        assert result.metadata.get("degraded") is True

    def test_fallback_below_degrade(self) -> None:
        mgr = DegradationManager(self._make_config())
        route = self._make_route(confidence=0.1)
        level, result = mgr.evaluate(route)
        assert level == DegradationLevel.FALLBACK
        assert result is None

    def test_fallback_none_route(self) -> None:
        mgr = DegradationManager(self._make_config())
        level, result = mgr.evaluate(None)
        assert level == DegradationLevel.FALLBACK
        assert result is None

    def test_disabled_returns_auto(self) -> None:
        mgr = DegradationManager(self._make_config(degradation_enabled=False))
        route = self._make_route(confidence=0.1)
        level, result = mgr.evaluate(route)
        assert level == DegradationLevel.AUTO
        assert result is route

    def test_auto_boundary(self) -> None:
        mgr = DegradationManager(self._make_config())
        route = self._make_route(confidence=0.6)
        level, _ = mgr.evaluate(route)
        assert level == DegradationLevel.AUTO

    def test_suggest_boundary(self) -> None:
        mgr = DegradationManager(self._make_config())
        route = self._make_route(confidence=0.4)
        level, _ = mgr.evaluate(route)
        assert level == DegradationLevel.SUGGEST

    def test_degrade_boundary(self) -> None:
        mgr = DegradationManager(self._make_config())
        route = self._make_route(confidence=0.2)
        level, _ = mgr.evaluate(route)
        assert level == DegradationLevel.DEGRADE

    def test_custom_thresholds(self) -> None:
        mgr = DegradationManager(self._make_config(
            degradation_auto_threshold=0.8,
            degradation_suggest_threshold=0.5,
            degradation_degrade_threshold=0.3,
        ))
        assert mgr.evaluate(self._make_route(confidence=0.9))[0] == DegradationLevel.AUTO
        assert mgr.evaluate(self._make_route(confidence=0.7))[0] == DegradationLevel.SUGGEST
        assert mgr.evaluate(self._make_route(confidence=0.4))[0] == DegradationLevel.DEGRADE
        assert mgr.evaluate(self._make_route(confidence=0.1))[0] == DegradationLevel.FALLBACK
