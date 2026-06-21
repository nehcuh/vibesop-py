"""Tests for core models."""

import pytest

from vibesop.core.models import (
    LayerDetail,
    PlanStatus,
    RejectedCandidate,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
    StepStatus,
)


class TestRoutingLayer:
    """Test RoutingLayer enum."""

    def test_values(self):
        assert RoutingLayer.EXPLICIT.value == "explicit"
        assert RoutingLayer.SCENARIO.value == "scenario"
        assert RoutingLayer.AI_TRIAGE.value == "ai_triage"
        assert RoutingLayer.KEYWORD.value == "keyword"
        assert RoutingLayer.TFIDF.value == "tfidf"
        assert RoutingLayer.EMBEDDING.value == "embedding"
        assert RoutingLayer.LEVENSHTEIN.value == "levenshtein"
        assert RoutingLayer.CUSTOM.value == "custom"
        assert RoutingLayer.NO_MATCH.value == "no_match"
        assert RoutingLayer.FALLBACK_LLM.value == "fallback_llm"


class TestStepStatus:
    """Test StepStatus enum."""

    def test_values(self):
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.IN_PROGRESS.value == "in_progress"
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.SKIPPED.value == "skipped"


class TestPlanStatus:
    """Test PlanStatus enum."""

    def test_values(self):
        assert PlanStatus.PENDING.value == "pending"
        assert PlanStatus.ACTIVE.value == "active"
        assert PlanStatus.COMPLETED.value == "completed"
        assert PlanStatus.FAILED.value == "failed"


class TestSkillRoute:
    """Test SkillRoute model."""

    def test_creation(self):
        route = SkillRoute(skill_id="test/skill", confidence=0.9, layer=RoutingLayer.KEYWORD)
        assert route.skill_id == "test/skill"
        assert route.confidence == pytest.approx(0.9)
        assert route.layer == RoutingLayer.KEYWORD
        assert route.source == "builtin"

    def test_creation_with_metadata(self):
        route = SkillRoute(
            skill_id="test/skill",
            confidence=0.9,
            layer=RoutingLayer.KEYWORD,
            metadata={"key": "val"},
        )
        assert route.metadata == {"key": "val"}

    def test_to_dict(self):
        route = SkillRoute(skill_id="s", confidence=0.8, layer=RoutingLayer.EXPLICIT)
        d = route.to_dict()
        assert d["skill_id"] == "s"
        assert d["confidence"] == pytest.approx(0.8)
        assert d["layer"] == "explicit"


class TestRejectedCandidate:
    """Test RejectedCandidate model."""

    def test_creation(self):
        rc = RejectedCandidate(
            skill_id="s", confidence=0.3, layer=RoutingLayer.KEYWORD, reason="below threshold"
        )
        assert rc.skill_id == "s"
        assert rc.confidence == pytest.approx(0.3)
        assert rc.reason == "below threshold"
        assert rc.layer == RoutingLayer.KEYWORD


class TestLayerDetail:
    """Test LayerDetail model."""

    def test_creation(self):
        ld = LayerDetail(layer=RoutingLayer.KEYWORD, matched=True, reason="matched")
        assert ld.layer == RoutingLayer.KEYWORD
        assert ld.matched is True
        assert ld.reason == "matched"
        assert ld.duration_ms == pytest.approx(0.0)
        assert ld.rejected_candidates == []

    def test_creation_with_rejected(self):
        rc = RejectedCandidate(skill_id="s", confidence=0.3, layer=RoutingLayer.KEYWORD)
        ld = LayerDetail(
            layer=RoutingLayer.KEYWORD,
            matched=True,
            rejected_candidates=[rc],
        )
        assert len(ld.rejected_candidates) == 1


class TestRoutingResult:
    """Test RoutingResult model."""

    def test_creation_defaults(self):
        result = RoutingResult()
        assert result.primary is None
        assert result.alternatives == []
        assert result.has_match is False
        assert result.query == ""

    def test_creation_with_primary(self):
        route = SkillRoute(skill_id="s", confidence=0.9, layer=RoutingLayer.EXPLICIT)
        result = RoutingResult(primary=route, query="test")
        assert result.has_match is True
        assert result.primary.skill_id == "s"

    def test_has_match_with_primary(self):
        route = SkillRoute(skill_id="s", confidence=0.9, layer=RoutingLayer.EXPLICIT)
        result = RoutingResult(primary=route)
        assert result.has_match is True

    def test_has_match_fallback_not_counted(self):
        route = SkillRoute(skill_id="s", confidence=0.5, layer=RoutingLayer.FALLBACK_LLM)
        result = RoutingResult(primary=route)
        assert result.has_match is False

    def test_has_match_none(self):
        result = RoutingResult()
        assert result.has_match is False

    def test_to_dict(self):
        route = SkillRoute(skill_id="s", confidence=0.9, layer=RoutingLayer.EXPLICIT)
        result = RoutingResult(primary=route, query="test")
        d = result.to_dict()
        assert d["query"] == "test"
        assert d["has_match"] is True
        assert d["primary"]["skill_id"] == "s"
