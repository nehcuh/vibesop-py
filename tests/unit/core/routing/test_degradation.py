"""Tests for DegradationManager — 4-level confidence gating (AUTO/SUGGEST/DEGRADE/FALLBACK)."""

from __future__ import annotations

from vibesop.core.config import RoutingConfig
from vibesop.core.models import DegradationLevel, RoutingLayer, SkillRoute
from vibesop.core.routing.degradation import DegradationManager


def _make_route(skill_id: str = "test-skill", confidence: float = 0.85) -> SkillRoute:
    return SkillRoute(
        skill_id=skill_id,
        confidence=confidence,
        layer=RoutingLayer.KEYWORD,
        source="builtin",
    )


class TestDegradationManager:
    """Test the 4-level degradation gating logic."""

    def test_auto_when_confidence_above_auto_threshold(self) -> None:
        """Confidence >= auto_threshold (default 0.6) → AUTO, primary returned as-is."""
        config = RoutingConfig()
        mgr = DegradationManager(config)
        primary = _make_route(confidence=0.85)
        level, result = mgr.evaluate(primary)
        assert level == DegradationLevel.AUTO
        assert result is not None
        assert result.skill_id == "test-skill"
        assert result.confidence == 0.85

    def test_suggest_when_confidence_between_suggest_and_auto(self) -> None:
        """Confidence in [0.4, 0.6) → SUGGEST."""
        config = RoutingConfig()
        mgr = DegradationManager(config)
        primary = _make_route(confidence=0.50)
        level, result = mgr.evaluate(primary)
        assert level == DegradationLevel.SUGGEST
        assert result is not None
        assert result.skill_id == "test-skill"

    def test_degrade_when_confidence_between_degrade_and_suggest(self) -> None:
        """Confidence in [0.2, 0.4) → DEGRADE with degraded metadata."""
        config = RoutingConfig()
        mgr = DegradationManager(config)
        primary = _make_route(confidence=0.30)
        level, result = mgr.evaluate(primary)
        assert level == DegradationLevel.DEGRADE
        assert result is not None
        assert result.metadata.get("degraded") is True
        assert result.metadata.get("degradation_level") == "degrade"

    def test_fallback_when_confidence_below_degrade_threshold(self) -> None:
        """Confidence < 0.2 → FALLBACK (None)."""
        config = RoutingConfig()
        mgr = DegradationManager(config)
        primary = _make_route(confidence=0.05)
        level, result = mgr.evaluate(primary)
        assert level == DegradationLevel.FALLBACK
        assert result is None

    def test_fallback_when_primary_is_none(self) -> None:
        """None primary → FALLBACK immediately."""
        config = RoutingConfig()
        mgr = DegradationManager(config)
        level, result = mgr.evaluate(None)
        assert level == DegradationLevel.FALLBACK
        assert result is None

    def test_auto_when_degradation_disabled(self) -> None:
        """When enabled=False, every match is AUTO regardless of confidence."""
        config = RoutingConfig(degradation_enabled=False)
        mgr = DegradationManager(config)
        primary = _make_route(confidence=0.05)
        level, result = mgr.evaluate(primary)
        assert level == DegradationLevel.AUTO
        assert result is primary

    def test_boundary_auto_threshold_exact(self) -> None:
        """Confidence exactly at auto_threshold → AUTO."""
        config = RoutingConfig(degradation_auto_threshold=0.60)
        mgr = DegradationManager(config)
        primary = _make_route(confidence=0.60)
        level, result = mgr.evaluate(primary)
        assert level == DegradationLevel.AUTO

    def test_boundary_suggest_threshold_exact(self) -> None:
        """Confidence exactly at suggest_threshold → SUGGEST."""
        config = RoutingConfig(degradation_suggest_threshold=0.40)
        mgr = DegradationManager(config)
        primary = _make_route(confidence=0.40)
        level, result = mgr.evaluate(primary)
        assert level == DegradationLevel.SUGGEST

    def test_boundary_degrade_threshold_exact(self) -> None:
        """Confidence exactly at degrade_threshold → DEGRADE."""
        config = RoutingConfig(degradation_degrade_threshold=0.20)
        mgr = DegradationManager(config)
        primary = _make_route(confidence=0.20)
        level, result = mgr.evaluate(primary)
        assert level == DegradationLevel.DEGRADE

    def test_custom_thresholds_respected(self) -> None:
        """Custom threshold values are properly honored."""
        config = RoutingConfig(
            degradation_auto_threshold=0.80,
            degradation_suggest_threshold=0.60,
            degradation_degrade_threshold=0.30,
        )
        mgr = DegradationManager(config)

        assert mgr.evaluate(_make_route(confidence=0.85))[0] == DegradationLevel.AUTO
        assert mgr.evaluate(_make_route(confidence=0.70))[0] == DegradationLevel.SUGGEST
        assert mgr.evaluate(_make_route(confidence=0.50))[0] == DegradationLevel.DEGRADE
        assert mgr.evaluate(_make_route(confidence=0.10))[0] == DegradationLevel.FALLBACK

    def test_always_ask_on_fallback_default(self) -> None:
        """Default config should have always_ask_on_fallback as True."""
        config = RoutingConfig()
        mgr = DegradationManager(config)
        assert mgr.always_ask_on_fallback is True
