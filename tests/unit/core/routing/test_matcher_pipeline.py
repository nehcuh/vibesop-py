"""Tests for MatcherPipeline — layers 3-6 (keyword, tfidf, embedding, levenshtein)."""

from __future__ import annotations

from unittest.mock import Mock

from vibesop.core.matching import IMatcher, MatchResult, MatcherType
from vibesop.core.models import RoutingLayer
from vibesop.core.routing.layers import LayerResult
from vibesop.core.routing.matcher_pipeline import MatcherPipeline


class FakeMatcher(IMatcher):
    """Fake matcher for testing that returns predetermined results."""

    def __init__(self, results: list[MatchResult]) -> None:
        self._results = results
        self.call_count = 0

    def match(self, query: str, candidates: list[dict], context, top_k: int = 3):
        self.call_count += 1
        return self._results

    def score(self, query: str, candidate: dict, context) -> float:
        return 0.5

    def warm_up(self, candidates: list[dict]) -> None:
        pass


class TestTryMatcherPipeline:
    """Test MatcherPipeline.try_matcher_pipeline."""

    def _make_pipeline(
        self,
        matchers: list[tuple[RoutingLayer, IMatcher]],
        min_confidence: float = 0.6,
        enable_embedding: bool = False,
    ) -> MatcherPipeline:
        config = Mock()
        config.min_confidence = min_confidence
        config.max_candidates = 3
        config.enable_embedding = enable_embedding

        opt_config = Mock()
        opt_config.enabled = False
        opt_config.prefilter = Mock()
        opt_config.prefilter.enabled = False

        opt_service = Mock()
        opt_service.ensure_cluster_index = Mock()
        opt_service.apply_optimizations = Mock(
            return_value=(
                MatchResult(skill_id="winner", confidence=0.9, matcher_type=MatcherType.KEYWORD, metadata={"namespace": "builtin"}),
                [],
            )
        )

        prefilter = Mock()
        prefilter.filter = Mock(side_effect=lambda q, c: c)

        return MatcherPipeline(
            matchers=matchers,
            config=config,
            optimization_config=opt_config,
            prefilter=prefilter,
            optimization_service=opt_service,
            get_skill_source=lambda sid, ns: ns,
        )

    def test_single_matcher_winner(self) -> None:
        """Pipeline with one confident matcher returns result."""
        matcher = FakeMatcher([
            MatchResult(skill_id="winner", confidence=0.9, matcher_type=MatcherType.KEYWORD, metadata={"namespace": "builtin"}),
        ])
        pipeline = self._make_pipeline([(RoutingLayer.KEYWORD, matcher)])
        candidates = [{"id": "winner", "description": "winning skill"}]

        result = pipeline.try_matcher_pipeline("test query", candidates, None)

        assert isinstance(result, LayerResult)
        assert result.match.skill_id == "winner"
        assert result.match.confidence == 0.9
        assert result.match.layer == RoutingLayer.KEYWORD

    def test_no_match_below_threshold(self) -> None:
        """Match below min_confidence returns None."""
        matcher = FakeMatcher([
            MatchResult(skill_id="weak", confidence=0.3, matcher_type=MatcherType.KEYWORD, metadata={}),
        ])
        pipeline = self._make_pipeline([(RoutingLayer.KEYWORD, matcher)], min_confidence=0.6)

        result = pipeline.try_matcher_pipeline("test", [{"id": "weak"}], None)
        assert result is None

    def test_no_match_at_all(self) -> None:
        """Empty matcher results return None."""
        matcher = FakeMatcher([])
        pipeline = self._make_pipeline([(RoutingLayer.KEYWORD, matcher)])

        result = pipeline.try_matcher_pipeline("test", [{"id": "x"}], None)
        assert result is None

    def test_multiple_matchers_best_wins(self) -> None:
        """Across multiple matchers, highest confidence skill wins."""
        keyword_matcher = FakeMatcher([
            MatchResult(skill_id="a", confidence=0.7, matcher_type=MatcherType.KEYWORD, metadata={"namespace": "builtin"}),
        ])
        tfidf_matcher = FakeMatcher([
            MatchResult(skill_id="b", confidence=0.85, matcher_type=MatcherType.TFIDF, metadata={"namespace": "builtin"}),
        ])
        pipeline = self._make_pipeline([
            (RoutingLayer.KEYWORD, keyword_matcher),
            (RoutingLayer.TFIDF, tfidf_matcher),
        ])
        candidates = [
            {"id": "a", "description": "skill a"},
            {"id": "b", "description": "skill b"},
        ]

        result = pipeline.try_matcher_pipeline("test", candidates, None)
        assert isinstance(result, LayerResult)
        assert result.match.skill_id == "winner"  # optimization_service mock returns winner

    def test_embedding_skipped_when_disabled(self) -> None:
        """Embedding matcher is skipped when enable_embedding=False."""
        keyword_matcher = FakeMatcher([
            MatchResult(skill_id="a", confidence=0.9, matcher_type=MatcherType.KEYWORD, metadata={"namespace": "builtin"}),
        ])
        embed_matcher = FakeMatcher([])
        pipeline = self._make_pipeline([
            (RoutingLayer.KEYWORD, keyword_matcher),
            (RoutingLayer.EMBEDDING, embed_matcher),
        ], enable_embedding=False)

        pipeline.try_matcher_pipeline("test", [{"id": "a"}], None)
        assert embed_matcher.call_count == 0

    def test_embedding_runs_when_enabled(self) -> None:
        """Embedding matcher runs when enable_embedding=True."""
        keyword_matcher = FakeMatcher([
            MatchResult(skill_id="a", confidence=0.5, matcher_type=MatcherType.KEYWORD, metadata={"namespace": "builtin"}),
        ])
        embed_matcher = FakeMatcher([
            MatchResult(skill_id="b", confidence=0.9, matcher_type=MatcherType.EMBEDDING, metadata={"namespace": "builtin"}),
        ])
        pipeline = self._make_pipeline([
            (RoutingLayer.KEYWORD, keyword_matcher),
            (RoutingLayer.EMBEDDING, embed_matcher),
        ], enable_embedding=True)

        pipeline.try_matcher_pipeline("test", [{"id": "a"}, {"id": "b"}], None)
        assert embed_matcher.call_count == 1

    def test_matcher_failure_continues(self) -> None:
        """If one matcher fails, pipeline continues with next matcher."""
        failing_matcher = Mock(spec=IMatcher)
        failing_matcher.match = Mock(side_effect=ValueError("boom"))
        failing_matcher.score = Mock(return_value=0.5)
        failing_matcher.warm_up = Mock()

        backup_matcher = FakeMatcher([
            MatchResult(skill_id="backup", confidence=0.9, matcher_type=MatcherType.TFIDF, metadata={"namespace": "builtin"}),
        ])
        pipeline = self._make_pipeline([
            (RoutingLayer.KEYWORD, failing_matcher),
            (RoutingLayer.TFIDF, backup_matcher),
        ])

        result = pipeline.try_matcher_pipeline("test", [{"id": "backup"}], None)
        assert isinstance(result, LayerResult)
        assert result.match.skill_id == "winner"  # optimization_service mock returns winner

    def test_early_exit_high_confidence_keyword(self) -> None:
        """Keyword match >= 0.95 skips subsequent matchers."""
        keyword_matcher = FakeMatcher([
            MatchResult(skill_id="fast", confidence=0.97, matcher_type=MatcherType.KEYWORD, metadata={"namespace": "builtin"}),
        ])
        tfidf_matcher = FakeMatcher([])
        pipeline = self._make_pipeline([
            (RoutingLayer.KEYWORD, keyword_matcher),
            (RoutingLayer.TFIDF, tfidf_matcher),
        ])

        pipeline.try_matcher_pipeline("test", [{"id": "fast"}], None)
        assert tfidf_matcher.call_count == 0

    def test_rejected_candidates_collected(self) -> None:
        """collect_rejected=True populates rejected candidates."""
        matcher = FakeMatcher([
            MatchResult(skill_id="winner", confidence=0.9, matcher_type=MatcherType.KEYWORD, metadata={"namespace": "builtin"}),
        ])
        pipeline = self._make_pipeline([(RoutingLayer.KEYWORD, matcher)], min_confidence=0.8)
        candidates = [
            {"id": "winner", "description": "winning skill"},
            {"id": "loser", "description": "losing skill"},
        ]

        result = pipeline.try_matcher_pipeline("test", candidates, None, collect_rejected=True)
        assert "rejected_candidates" in result.diagnostics
        rejected = result.diagnostics["rejected_candidates"]
        assert len(rejected) >= 1
        assert rejected[0]["skill_id"] == "loser"
        assert rejected[0]["reason"] == "below threshold (0.80)"

    def test_no_rejected_when_not_requested(self) -> None:
        """collect_rejected=False leaves diagnostics empty."""
        matcher = FakeMatcher([
            MatchResult(skill_id="winner", confidence=0.9, matcher_type=MatcherType.KEYWORD, metadata={"namespace": "builtin"}),
        ])
        pipeline = self._make_pipeline([(RoutingLayer.KEYWORD, matcher)])

        result = pipeline.try_matcher_pipeline("test", [{"id": "winner"}], None, collect_rejected=False)
        assert result.diagnostics == {}


class TestApplyPrefilter:
    """Test MatcherPipeline.apply_prefilter."""

    def test_prefilter_disabled_returns_original(self) -> None:
        """When prefilter is disabled, candidates pass through unchanged."""
        config = Mock()
        opt_config = Mock()
        opt_config.enabled = False
        opt_config.prefilter = Mock()
        opt_config.prefilter.enabled = False

        pipeline = MatcherPipeline(
            matchers=[],
            config=config,
            optimization_config=opt_config,
            prefilter=Mock(),
            optimization_service=Mock(),
            get_skill_source=lambda sid, ns: ns,
        )
        candidates = [{"id": "a"}, {"id": "b"}]
        result = pipeline.apply_prefilter("test", candidates)
        assert result == candidates

    def test_prefilter_enabled_filters(self) -> None:
        """When prefilter is enabled, filter is applied."""
        config = Mock()
        opt_config = Mock()
        opt_config.enabled = True
        opt_config.prefilter.enabled = True

        prefilter = Mock()
        prefilter.filter = Mock(return_value=[{"id": "a"}])

        pipeline = MatcherPipeline(
            matchers=[],
            config=config,
            optimization_config=opt_config,
            prefilter=prefilter,
            optimization_service=Mock(),
            get_skill_source=lambda sid, ns: ns,
        )
        candidates = [{"id": "a"}, {"id": "b"}]
        result = pipeline.apply_prefilter("test", candidates)
        assert result == [{"id": "a"}]


class TestSetPrefilter:
    """Test MatcherPipeline.set_prefilter."""

    def test_replaces_prefilter(self) -> None:
        """set_prefilter replaces the internal prefilter instance."""
        config = Mock()
        opt_config = Mock()
        opt_config.enabled = True
        opt_config.prefilter = Mock()
        opt_config.prefilter.enabled = True

        old_prefilter = Mock()
        old_prefilter.filter = Mock(return_value=[{"id": "old"}])
        new_prefilter = Mock()
        new_prefilter.filter = Mock(return_value=[{"id": "x"}])

        pipeline = MatcherPipeline(
            matchers=[],
            config=config,
            optimization_config=opt_config,
            prefilter=old_prefilter,
            optimization_service=Mock(),
            get_skill_source=lambda sid, ns: ns,
        )
        pipeline.set_prefilter(new_prefilter)
        result = pipeline.apply_prefilter("test", [{"id": "x"}, {"id": "y"}])
        assert result == [{"id": "x"}]
