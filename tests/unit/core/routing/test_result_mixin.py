"""Tests for RouterResultMixin — _build_result, _build_fallback_result, _collect_alternatives_from_details."""

from __future__ import annotations

import contextlib
import time
from unittest.mock import MagicMock

from vibesop.core.models import (
    LayerDetail,
    RejectedCandidate,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)
from vibesop.core.routing.result_mixin import RouterResultMixin


class TestCollectAlternativesFromDetails:
    """Test extraction of alternatives from layer_details."""

    def test_collects_rejected_candidates(self) -> None:
        """Rejected candidates from layer_details become alternatives."""
        mixin = RouterResultMixin()
        details = [
            LayerDetail(
                layer=RoutingLayer.KEYWORD,
                matched=False,
                reason="below threshold",
                rejected_candidates=[
                    RejectedCandidate(
                        skill_id="skill-a",
                        confidence=0.55,
                        layer=RoutingLayer.KEYWORD,
                        reason="below threshold (0.6)",
                    ),
                    RejectedCandidate(
                        skill_id="skill-b",
                        confidence=0.48,
                        layer=RoutingLayer.KEYWORD,
                        reason="below threshold (0.6)",
                    ),
                ],
            ),
        ]
        alternatives = mixin._collect_alternatives_from_details(details)
        assert len(alternatives) == 2

    def test_sorted_by_confidence_descending(self) -> None:
        """Alternatives are sorted highest confidence first."""
        mixin = RouterResultMixin()
        details = [
            LayerDetail(
                layer=RoutingLayer.KEYWORD,
                matched=False,
                reason="test",
                rejected_candidates=[
                    RejectedCandidate(
                        skill_id="low", confidence=0.30, layer=RoutingLayer.KEYWORD, reason="x"
                    ),
                    RejectedCandidate(
                        skill_id="high", confidence=0.80, layer=RoutingLayer.TFIDF, reason="x"
                    ),
                    RejectedCandidate(
                        skill_id="mid", confidence=0.55, layer=RoutingLayer.KEYWORD, reason="x"
                    ),
                ],
            ),
        ]
        alternatives = mixin._collect_alternatives_from_details(details)
        assert alternatives[0].skill_id == "high"
        assert alternatives[1].skill_id == "mid"
        assert alternatives[2].skill_id == "low"

    def test_same_skill_highest_confidence_kept(self) -> None:
        """If a skill appears in multiple layers, only the highest confidence is kept."""
        mixin = RouterResultMixin()
        details = [
            LayerDetail(
                layer=RoutingLayer.KEYWORD,
                matched=False,
                reason="test",
                rejected_candidates=[
                    RejectedCandidate(
                        skill_id="dup", confidence=0.40, layer=RoutingLayer.KEYWORD, reason="a"
                    ),
                ],
            ),
            LayerDetail(
                layer=RoutingLayer.TFIDF,
                matched=False,
                reason="test",
                rejected_candidates=[
                    RejectedCandidate(
                        skill_id="dup", confidence=0.70, layer=RoutingLayer.TFIDF, reason="b"
                    ),
                ],
            ),
        ]
        alternatives = mixin._collect_alternatives_from_details(details)
        assert len(alternatives) == 1
        assert alternatives[0].confidence == 0.70
        assert alternatives[0].layer == RoutingLayer.TFIDF

    def test_empty_details_returns_empty_list(self) -> None:
        """No layer_details → empty alternatives."""
        mixin = RouterResultMixin()
        alternatives = mixin._collect_alternatives_from_details([])
        assert alternatives == []

    def test_details_without_rejected_candidates(self) -> None:
        """Layer details without rejected_candidates → empty list."""
        mixin = RouterResultMixin()
        details = [
            LayerDetail(layer=RoutingLayer.KEYWORD, matched=True, reason="matched"),
        ]
        alternatives = mixin._collect_alternatives_from_details(details)
        assert alternatives == []


class TestBuildResult:
    """Test _build_result method."""

    def test_builds_valid_routing_result(self) -> None:
        """_build_result produces a correctly structured RoutingResult."""
        mixin = RouterResultMixin()
        primary = SkillRoute(
            skill_id="test-skill",
            confidence=0.85,
            layer=RoutingLayer.KEYWORD,
            source="builtin",
        )
        start = time.perf_counter()
        result = mixin._build_result(
            query="test query",
            primary=primary,
            alternatives=[],
            routing_path=[RoutingLayer.KEYWORD],
            layer_details=[LayerDetail(layer=RoutingLayer.KEYWORD, matched=True, reason="matched")],
            start_time=start,
        )
        assert isinstance(result, RoutingResult)
        assert result.primary.skill_id == "test-skill"
        assert result.primary.confidence == 0.85
        assert result.query == "test query"
        assert result.duration_ms >= 0

    def test_deprecated_warnings_in_metadata(self) -> None:
        """Deprecated warnings are stored in primary.metadata."""
        mixin = RouterResultMixin()
        primary = SkillRoute(
            skill_id="dep-skill",
            confidence=0.75,
            layer=RoutingLayer.KEYWORD,
            source="builtin",
        )
        result = mixin._build_result(
            query="test",
            primary=primary,
            alternatives=[],
            routing_path=[RoutingLayer.KEYWORD],
            layer_details=[],
            start_time=time.perf_counter(),
            deprecated_warnings=["dep-skill is deprecated"],
        )
        assert result.primary is not None
        assert result.primary.metadata["deprecated_warnings"] == ["dep-skill is deprecated"]

    def test_record_routing_decision_uses_original_query_not_enriched(self, monkeypatch) -> None:
        """Regression (kimi CRITICAL): the instinct/preference record must be
        keyed on ``original_query`` (what feedback.py feeds back), NOT the
        conversation-enriched ``query``. Otherwise multi-turn routing sends the
        reward signal to the wrong instinct / no-ops."""
        from vibesop.core.routing.degradation import DegradationLevel

        mixin = RouterResultMixin()
        mixin._config = MagicMock()
        mixin._degradation_manager = MagicMock()
        primary = SkillRoute(
            skill_id="x", confidence=0.9, layer=RoutingLayer.KEYWORD, source="builtin"
        )
        mixin._degradation_manager.evaluate.return_value = (DegradationLevel.AUTO, primary)

        recorded: list[str] = []
        # Direct-assign: in production `self` is the UnifiedRouter host (which
        # defines _record_routing_decision); a bare mixin instance doesn't have it.
        mixin._record_routing_decision = lambda q, p, c: recorded.append(q)

        # _build_match_result also runs alternatives-enrichment that needs the
        # full UnifiedRouter host (skill_recommender, candidate_manager, ...).
        # The CRITICAL fix is the _record_routing_decision call, which executes
        # BEFORE that enrichment — capture it even though the bare mixin can't
        # complete the downstream work.
        with contextlib.suppress(AttributeError):
            mixin._build_match_result(
                query="ENRICHED query with prior-turn context",
                primary=primary,
                alternatives=[],
                routing_path=[RoutingLayer.KEYWORD],
                layer_details=[LayerDetail(layer=RoutingLayer.KEYWORD, matched=True, reason="m")],
                start_time=time.perf_counter(),
                deprecated_warnings=None,
                conversation=None,
                original_query="raw user query",
                context=None,
            )
        assert recorded == ["raw user query"]


class TestBuildFallbackResult:
    """Test _build_fallback_result method."""

    def test_returns_fallback_llm_route(self, monkeypatch) -> None:
        """Fallback result uses FALLBACK_LLM layer."""

        def mock_run_matcher(*args, **kwargs):
            return (None, [], MagicMock())

        monkeypatch.setattr(
            "vibesop.core.routing._pipeline.run_matcher_pipeline",
            mock_run_matcher,
        )
        mixin = RouterResultMixin()
        mixin._config = MagicMock()
        mixin._config.fallback_mode = "silent"
        result = mixin._build_fallback_result(
            query="unknown query",
            candidates=[],
            routing_path=[RoutingLayer.KEYWORD, RoutingLayer.AI_TRIAGE],
            layer_details=[],
            duration_ms=50.0,
        )
        assert result.primary is not None
        assert result.primary.skill_id == "fallback-llm"
        assert result.primary.layer == RoutingLayer.FALLBACK_LLM
        assert result.primary.confidence == 1.0
        assert RoutingLayer.FALLBACK_LLM in result.routing_path

    def test_fallback_includes_nearest_candidates(self, monkeypatch) -> None:
        """Fallback result includes nearest candidates from matcher pipeline."""
        mock_primary = SkillRoute(
            skill_id="nearest", confidence=0.25, layer=RoutingLayer.KEYWORD, source="external"
        )
        mock_alt = SkillRoute(
            skill_id="near-alt", confidence=0.20, layer=RoutingLayer.TFIDF, source="external"
        )

        def mock_run_matcher(*args, **kwargs):
            return (mock_primary, [mock_alt], MagicMock())

        monkeypatch.setattr(
            "vibesop.core.routing._pipeline.run_matcher_pipeline",
            mock_run_matcher,
        )
        mixin = RouterResultMixin()
        mixin._config = MagicMock()
        mixin._config.fallback_mode = "silent"
        result = mixin._build_fallback_result(
            query="test",
            candidates=[{"id": "nearest"}, {"id": "near-alt"}],
            routing_path=[],
            layer_details=[],
            duration_ms=50.0,
        )
        assert len(result.alternatives) >= 1
        assert result.alternatives[0].skill_id == "nearest"

    def test_fallback_excludes_guarded_skill_without_signal(self, monkeypatch) -> None:
        """Guarded skills rejected by the matcher gate must not resurface as
        'nearest' suggestions in the fallback result."""
        guarded = SkillRoute(
            skill_id="builtin/riper-workflow",
            confidence=0.8,
            layer=RoutingLayer.KEYWORD,
            source="builtin",
        )
        legit = SkillRoute(
            skill_id="other/skill", confidence=0.3, layer=RoutingLayer.TFIDF, source="external"
        )

        def mock_run_matcher(*args, **kwargs):
            return (guarded, [legit], MagicMock())

        monkeypatch.setattr(
            "vibesop.core.routing._pipeline.run_matcher_pipeline",
            mock_run_matcher,
        )
        mixin = RouterResultMixin()
        mixin._config = MagicMock()
        mixin._config.fallback_mode = "silent"
        mixin._triage_service = MagicMock()
        mixin._triage_service.has_explicit_guard_signal = lambda query, candidates, skill_id: (
            skill_id != "builtin/riper-workflow"
        )
        result = mixin._build_fallback_result(
            query="使用合适的 workflow 开发",
            candidates=[{"id": "builtin/riper-workflow"}, {"id": "other/skill"}],
            routing_path=[],
            layer_details=[],
            duration_ms=50.0,
        )
        assert all(a.skill_id != "builtin/riper-workflow" for a in result.alternatives)
        assert any(a.skill_id == "other/skill" for a in result.alternatives)
