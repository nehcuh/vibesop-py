"""Tests for MatcherPipeline."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from vibesop.core.exceptions import MatcherError
from vibesop.core.models import RoutingLayer
from vibesop.core.routing.matcher_pipeline import MatcherPipeline


class TestMatcherPipeline:
    """Tests for the matcher pipeline execution."""

    def _make_pipeline(
        self,
        matchers=None,
        enable_embedding=True,
        max_candidates=3,
        min_confidence=0.6,
        prefilter_enabled=True,
        optimization_enabled=True,
    ):
        config = MagicMock()
        config.enable_embedding = enable_embedding
        config.max_candidates = max_candidates
        config.min_confidence = min_confidence

        optimization_config = MagicMock()
        optimization_config.enabled = optimization_enabled
        optimization_config.prefilter.enabled = prefilter_enabled

        prefilter = MagicMock()
        prefilter.filter = MagicMock(side_effect=lambda q, c: c)

        optimization_service = MagicMock()
        optimization_service.ensure_cluster_index = MagicMock()
        optimization_service.apply_optimizations = MagicMock(
            side_effect=lambda matches, _q, _c: (matches[0], matches[1:])
        )

        return MatcherPipeline(
            matchers=matchers or [],
            config=config,
            optimization_config=optimization_config,
            prefilter=prefilter,
            optimization_service=optimization_service,
            get_skill_source=lambda _sid, ns: ns,
        )

    def _make_match(self, skill_id: str, confidence: float, namespace: str = "builtin"):
        m = MagicMock()
        m.skill_id = skill_id
        m.confidence = confidence
        m.metadata = {"namespace": namespace}
        return m

    def test_empty_matchers_returns_none(self) -> None:
        """Pipeline with no matchers returns None."""
        pipeline = self._make_pipeline()
        result = pipeline.try_matcher_pipeline("query", [{"id": "s1"}], None)
        assert result is None

    def test_first_matching_layer_wins(self) -> None:
        """First matcher that returns confident match wins."""
        matcher = MagicMock()
        matcher.match.return_value = [self._make_match("skill1", 0.9)]

        pipeline = self._make_pipeline(matchers=[(RoutingLayer.KEYWORD, matcher)])
        result = pipeline.try_matcher_pipeline("query", [{"id": "s1"}], None)

        assert result is not None
        assert result.match.skill_id == "skill1"
        assert result.layer == RoutingLayer.KEYWORD
        matcher.match.assert_called_once()

    def test_low_confidence_continues_to_next_matcher(self) -> None:
        """Matcher with low confidence causes fallback to next layer."""
        keyword_matcher = MagicMock()
        keyword_matcher.match.return_value = [self._make_match("skill1", 0.3)]

        tfidf_matcher = MagicMock()
        tfidf_matcher.match.return_value = [self._make_match("skill2", 0.85)]

        pipeline = self._make_pipeline(
            matchers=[
                (RoutingLayer.KEYWORD, keyword_matcher),
                (RoutingLayer.TFIDF, tfidf_matcher),
            ]
        )
        result = pipeline.try_matcher_pipeline("query", [{"id": "s1"}], None)

        assert result is not None
        assert result.match.skill_id == "skill2"
        assert result.layer == RoutingLayer.TFIDF

    def test_embedding_skipped_when_disabled(self) -> None:
        """Embedding matcher is skipped when config disables it."""
        embedding_matcher = MagicMock()
        tfidf_matcher = MagicMock()
        tfidf_matcher.match.return_value = [self._make_match("skill1", 0.8)]

        pipeline = self._make_pipeline(
            matchers=[
                (RoutingLayer.EMBEDDING, embedding_matcher),
                (RoutingLayer.TFIDF, tfidf_matcher),
            ],
            enable_embedding=False,
        )
        result = pipeline.try_matcher_pipeline("query", [{"id": "s1"}], None)

        assert result is not None
        assert result.layer == RoutingLayer.TFIDF
        embedding_matcher.match.assert_not_called()

    def test_matcher_exception_falls_through(self) -> None:
        """Matcher raising OSError causes fallback to next layer."""
        bad_matcher = MagicMock()
        bad_matcher.match.side_effect = OSError("disk full")

        good_matcher = MagicMock()
        good_matcher.match.return_value = [self._make_match("skill1", 0.8)]

        pipeline = self._make_pipeline(
            matchers=[
                (RoutingLayer.KEYWORD, bad_matcher),
                (RoutingLayer.TFIDF, good_matcher),
            ]
        )
        result = pipeline.try_matcher_pipeline("query", [{"id": "s1"}], None)

        assert result is not None
        assert result.layer == RoutingLayer.TFIDF

    def test_matcher_error_falls_through(self) -> None:
        """Matcher raising MatcherError causes fallback."""
        bad_matcher = MagicMock()
        bad_matcher.match.side_effect = MatcherError("keyword", "bad config")

        good_matcher = MagicMock()
        good_matcher.match.return_value = [self._make_match("skill1", 0.8)]

        pipeline = self._make_pipeline(
            matchers=[
                (RoutingLayer.KEYWORD, bad_matcher),
                (RoutingLayer.TFIDF, good_matcher),
            ]
        )
        result = pipeline.try_matcher_pipeline("query", [{"id": "s1"}], None)

        assert result is not None
        assert result.layer == RoutingLayer.TFIDF

    def test_no_matches_returns_none(self) -> None:
        """All matchers returning empty results yields None."""
        matcher = MagicMock()
        matcher.match.return_value = []

        pipeline = self._make_pipeline(matchers=[(RoutingLayer.KEYWORD, matcher)])
        result = pipeline.try_matcher_pipeline("query", [{"id": "s1"}], None)

        assert result is None

    def test_alternatives_populated(self) -> None:
        """Alternatives are returned alongside primary match."""
        matcher = MagicMock()
        matcher.match.return_value = [
            self._make_match("primary", 0.9),
            self._make_match("alt1", 0.7),
            self._make_match("alt2", 0.65),
        ]

        pipeline = self._make_pipeline(matchers=[(RoutingLayer.KEYWORD, matcher)])
        result = pipeline.try_matcher_pipeline("query", [{"id": "s1"}], None)

        assert result is not None
        assert len(result.alternatives) == 2
        assert result.alternatives[0].skill_id == "alt1"

    def test_prefilter_disabled(self) -> None:
        """When prefilter is disabled, candidates pass through unchanged."""
        prefilter = MagicMock()
        prefilter.filter = MagicMock(side_effect=lambda q, c: c[:1])

        config = MagicMock()
        config.enable_embedding = True
        config.max_candidates = 3
        config.min_confidence = 0.6

        optimization_config = MagicMock()
        optimization_config.enabled = True
        optimization_config.prefilter.enabled = False

        optimization_service = MagicMock()
        optimization_service.ensure_cluster_index = MagicMock()
        optimization_service.apply_optimizations = MagicMock(
            side_effect=lambda matches, _q, _c: (matches[0], [])
        )

        matcher = MagicMock()
        matcher.match.return_value = [self._make_match("skill1", 0.9)]

        pipeline = MatcherPipeline(
            matchers=[(RoutingLayer.KEYWORD, matcher)],
            config=config,
            optimization_config=optimization_config,
            prefilter=prefilter,
            optimization_service=optimization_service,
            get_skill_source=lambda _sid, ns: ns,
        )
        candidates = [{"id": "s1"}, {"id": "s2"}]
        result = pipeline.try_matcher_pipeline("query", candidates, None)

        assert result is not None
        prefilter.filter.assert_not_called()
        # matcher should receive full candidate list
        positional_args, _ = matcher.match.call_args
        assert len(positional_args[1]) == 2

    def test_set_prefilter(self) -> None:
        """set_prefilter replaces the internal prefilter."""
        pipeline = self._make_pipeline()
        new_prefilter = MagicMock()
        new_prefilter.filter = MagicMock(return_value=[{"id": "s1"}])

        pipeline.set_prefilter(new_prefilter)
        candidates = [{"id": "s1"}, {"id": "s2"}]
        result = pipeline.apply_prefilter("q", candidates)

        assert result == [{"id": "s1"}]
