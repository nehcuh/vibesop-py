"""Tests for RouterOrchestrationMixin — _to_orchestration_result, lazy init helpers."""

from __future__ import annotations

from vibesop.core.models import (
    LayerDetail,
    OrchestrationMode,
    OrchestrationResult,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)
from vibesop.core.routing.orchestration_mixin import RouterOrchestrationMixin


def _make_routing_result(has_match: bool = True) -> RoutingResult:
    primary = None
    if has_match:
        primary = SkillRoute(
            skill_id="test-skill",
            confidence=0.85,
            layer=RoutingLayer.KEYWORD,
            source="builtin",
        )
    return RoutingResult(
        primary=primary,
        alternatives=[],
        routing_path=[RoutingLayer.KEYWORD],
        layer_details=[
            LayerDetail(
                layer=RoutingLayer.KEYWORD,
                matched=has_match,
                reason="matched" if has_match else "no match",
            ),
        ],
        query="test query",
        duration_ms=10.0,
    )


class TestToOrchestrationResult:
    """Test conversion from RoutingResult to OrchestrationResult."""

    def test_single_mode_when_primary_exists(self) -> None:
        """When RoutingResult has a primary match → mode=SINGLE."""
        mixin = RouterOrchestrationMixin()
        rr = _make_routing_result(has_match=True)
        result = mixin._to_orchestration_result(rr, "test query")

        assert isinstance(result, OrchestrationResult)
        assert result.mode == OrchestrationMode.SINGLE
        assert result.primary is not None
        assert result.primary.skill_id == "test-skill"
        assert result.original_query == "test query"

    def test_fallback_mode_when_no_primary(self) -> None:
        """When RoutingResult has no primary match → mode=FALLBACK."""
        mixin = RouterOrchestrationMixin()
        rr = _make_routing_result(has_match=False)
        result = mixin._to_orchestration_result(rr, "unknown query")

        assert result.mode == OrchestrationMode.FALLBACK
        assert result.primary is None

    def test_alternatives_preserved(self) -> None:
        """Alternatives from RoutingResult are carried over."""
        mixin = RouterOrchestrationMixin()
        rr = _make_routing_result(has_match=True)
        alt = SkillRoute(
            skill_id="alt-skill",
            confidence=0.65,
            layer=RoutingLayer.TFIDF,
            source="external",
        )
        rr.alternatives = [alt]
        result = mixin._to_orchestration_result(rr, "test query")

        assert len(result.alternatives) == 1
        assert result.alternatives[0].skill_id == "alt-skill"

    def test_routing_path_and_layer_details_carried_over(self) -> None:
        """Routing path and layer details are preserved in the conversion."""
        mixin = RouterOrchestrationMixin()
        rr = _make_routing_result(has_match=True)
        assert len(rr.routing_path) > 0
        assert len(rr.layer_details) > 0

        result = mixin._to_orchestration_result(rr, "test")
        assert result.routing_path == rr.routing_path
        assert result.layer_details == rr.layer_details

    def test_duration_ms_preserved(self) -> None:
        """Duration is preserved in conversion."""
        mixin = RouterOrchestrationMixin()
        rr = _make_routing_result(has_match=True)
        rr.duration_ms = 42.5
        result = mixin._to_orchestration_result(rr, "test")
        assert result.duration_ms == 42.5

    def test_no_execution_plan_in_single_mode(self) -> None:
        """SINGLE mode result has no execution_plan."""
        mixin = RouterOrchestrationMixin()
        rr = _make_routing_result(has_match=True)
        result = mixin._to_orchestration_result(rr, "test")
        assert result.execution_plan is None
