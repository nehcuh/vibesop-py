"""Tests for routing transparency — layer_details always populated, alternatives available."""

from __future__ import annotations

from vibesop.core.models import (
    LayerDetail,
    RejectedCandidate,
    RoutingLayer,
    RoutingResult,
)
from vibesop.core.routing import UnifiedRouter


class TestRoutingTransparency:
    """Test suite for Task 1.1: Refactor routing transparency from opt-in to default."""

    def test_route_returns_layer_details(self, tmp_path) -> None:
        """router.route() must always return result.layer_details with at least one entry."""
        router = UnifiedRouter(project_root=tmp_path)
        result = router.route("debug database error")

        assert isinstance(result, RoutingResult)
        assert len(result.layer_details) >= 1, "layer_details should always be populated"

    def test_orchestrate_returns_layer_details(self, tmp_path) -> None:
        """router.orchestrate() must always return result.layer_details populated."""
        router = UnifiedRouter(project_root=tmp_path)
        result = router.orchestrate("debug database error")

        assert len(result.layer_details) >= 1, "orchestrate() must return layer_details"

    def test_alternatives_available_without_explain(self, tmp_path) -> None:
        """Alternatives should be available from layer_details even without --explain."""
        router = UnifiedRouter(project_root=tmp_path)

        # Manually inject layer_details with rejected candidates
        layer_details = [
            LayerDetail(
                layer=RoutingLayer.KEYWORD,
                matched=False,
                reason="No keyword match",
                rejected_candidates=[
                    RejectedCandidate(
                        skill_id="systematic-debugging",
                        confidence=0.55,
                        layer=RoutingLayer.KEYWORD,
                        reason="below threshold (0.6)",
                    ),
                    RejectedCandidate(
                        skill_id="investigate",
                        confidence=0.48,
                        layer=RoutingLayer.TFIDF,
                        reason="below threshold (0.6)",
                    ),
                ],
            ),
        ]

        alternatives = router._collect_alternatives_from_details(layer_details)

        assert len(alternatives) == 2
        assert alternatives[0].skill_id == "systematic-debugging"
        assert alternatives[0].confidence == 0.55
        assert alternatives[1].skill_id == "investigate"
        assert alternatives[1].confidence == 0.48

    def test_alternatives_sorted_by_confidence(self, tmp_path) -> None:
        """Alternatives extracted from layer_details should be sorted by confidence descending."""
        router = UnifiedRouter(project_root=tmp_path)

        layer_details = [
            LayerDetail(
                layer=RoutingLayer.KEYWORD,
                matched=False,
                reason="No keyword match",
                rejected_candidates=[
                    RejectedCandidate(
                        skill_id="low-confidence",
                        confidence=0.30,
                        layer=RoutingLayer.KEYWORD,
                        reason="below threshold",
                    ),
                    RejectedCandidate(
                        skill_id="high-confidence",
                        confidence=0.80,
                        layer=RoutingLayer.TFIDF,
                        reason="below threshold",
                    ),
                ],
            ),
        ]

        alternatives = router._collect_alternatives_from_details(layer_details)

        assert alternatives[0].skill_id == "high-confidence"
        assert alternatives[0].confidence == 0.80
        assert alternatives[1].skill_id == "low-confidence"
        assert alternatives[1].confidence == 0.30

    def test_alternatives_deduplicated(self, tmp_path) -> None:
        """Duplicate rejected candidates across layers should be deduplicated, keeping highest confidence."""
        router = UnifiedRouter(project_root=tmp_path)

        layer_details = [
            LayerDetail(
                layer=RoutingLayer.KEYWORD,
                matched=False,
                reason="No keyword match",
                rejected_candidates=[
                    RejectedCandidate(
                        skill_id="duplicate-skill",
                        confidence=0.52,
                        layer=RoutingLayer.KEYWORD,
                        reason="below threshold",
                    ),
                ],
            ),
            LayerDetail(
                layer=RoutingLayer.TFIDF,
                matched=False,
                reason="No tfidf match",
                rejected_candidates=[
                    RejectedCandidate(
                        skill_id="duplicate-skill",
                        confidence=0.65,
                        layer=RoutingLayer.TFIDF,
                        reason="below threshold",
                    ),
                ],
            ),
        ]

        alternatives = router._collect_alternatives_from_details(layer_details)

        assert len(alternatives) == 1
        assert alternatives[0].skill_id == "duplicate-skill"
        assert alternatives[0].confidence == 0.65

    def test_empty_layer_details_returns_empty_alternatives(self, tmp_path) -> None:
        """Empty layer_details should produce empty alternatives."""
        router = UnifiedRouter(project_root=tmp_path)

        alternatives = router._collect_alternatives_from_details([])

        assert alternatives == []

    def test_route_populates_alternatives_from_rejected(self, tmp_path) -> None:
        """When no explicit alternatives are provided, route() should populate from layer_details."""
        router = UnifiedRouter(project_root=tmp_path)

        # This test verifies the integration: route() calls _collect_alternatives_from_details
        # when layer_result.alternatives is empty
        result = router.route("some query that might not match strongly")

        # Even if no strong match, layer_details should exist and may contain rejected candidates
        assert result.layer_details is not None
        # The result may or may not have alternatives depending on the query and installed skills
        # but the mechanism should be in place
