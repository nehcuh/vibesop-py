"""Tests for rejected candidates (near-miss) transparency."""

from __future__ import annotations

import pytest

from vibesop.core.models import (
    LayerDetail,
    RejectedCandidate,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)


class TestRejectedCandidate:
    def test_rejected_candidate_creation(self):
        rc = RejectedCandidate(
            skill_id="test-skill",
            confidence=0.45,
            layer=RoutingLayer.KEYWORD,
            reason="below threshold (0.60)",
        )
        assert rc.skill_id == "test-skill"
        assert rc.confidence == 0.45
        assert rc.layer == RoutingLayer.KEYWORD
        assert rc.reason == "below threshold (0.60)"

    def test_rejected_candidate_to_dict(self):
        rc = RejectedCandidate(
            skill_id="test-skill",
            confidence=0.45,
            layer=RoutingLayer.KEYWORD,
            reason="below threshold (0.60)",
        )
        d = rc.to_dict()
        assert d["skill_id"] == "test-skill"
        assert d["confidence"] == 0.45
        assert d["layer"] == "keyword"
        assert d["reason"] == "below threshold (0.60)"


class TestLayerDetailWithRejectedCandidates:
    def test_layer_detail_default_rejected_candidates(self):
        ld = LayerDetail(
            layer=RoutingLayer.KEYWORD,
            matched=False,
            reason="No confident match",
        )
        assert ld.rejected_candidates == []

    def test_layer_detail_with_rejected_candidates(self):
        rc = RejectedCandidate(
            skill_id="near-miss",
            confidence=0.55,
            layer=RoutingLayer.KEYWORD,
            reason="below threshold",
        )
        ld = LayerDetail(
            layer=RoutingLayer.KEYWORD,
            matched=False,
            reason="No confident match",
            rejected_candidates=[rc],
        )
        assert len(ld.rejected_candidates) == 1
        assert ld.rejected_candidates[0].skill_id == "near-miss"

    def test_layer_detail_to_dict_includes_rejected(self):
        rc = RejectedCandidate(
            skill_id="near-miss",
            confidence=0.55,
            layer=RoutingLayer.KEYWORD,
            reason="below threshold",
        )
        ld = LayerDetail(
            layer=RoutingLayer.KEYWORD,
            matched=False,
            reason="No confident match",
            rejected_candidates=[rc],
        )
        d = ld.to_dict()
        assert "rejected_candidates" in d
        assert d["rejected_candidates"][0]["skill_id"] == "near-miss"


class TestRoutingResultWithRejectedCandidates:
    def test_routing_result_layer_details_with_rejected(self):
        rc = RejectedCandidate(
            skill_id="gstack/guard",
            confidence=0.52,
            layer=RoutingLayer.KEYWORD,
            reason="below threshold (0.60)",
        )
        ld = LayerDetail(
            layer=RoutingLayer.KEYWORD,
            matched=False,
            reason="No confident match",
            rejected_candidates=[rc],
        )
        result = RoutingResult(
            primary=None,
            layer_details=[ld],
            query="security scan",
        )
        assert len(result.layer_details) == 1
        assert len(result.layer_details[0].rejected_candidates) == 1
