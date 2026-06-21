"""Tests for matching base classes and models."""

import pytest

from vibesop.core.matching.base import (
    MatchResult,
    MatcherType,
    RoutingContext,
    SimilarityMetric,
)


class TestSimilarityMetric:
    """Test SimilarityMetric enum."""

    def test_values(self):
        assert SimilarityMetric.COSINE.value == "cosine"
        assert SimilarityMetric.DOT_PRODUCT.value == "dot_product"
        assert SimilarityMetric.EUCLIDEAN.value == "euclidean"
        assert SimilarityMetric.MANHATTAN.value == "manhattan"
        assert SimilarityMetric.JACCARD.value == "jaccard"
        assert SimilarityMetric.LEVENSHTEIN.value == "levenshtein"


class TestMatcherType:
    """Test MatcherType enum."""

    def test_values(self):
        assert MatcherType.KEYWORD.value == "keyword"
        assert MatcherType.EMBEDDING.value == "embedding"
        assert MatcherType.AI_TRIAGE.value == "ai_triage"


class TestRoutingContext:
    """Test RoutingContext dataclass."""

    def test_defaults(self):
        ctx = RoutingContext()
        assert ctx.file_type is None
        assert ctx.error_count == 0
        assert ctx.recent_files == []
        assert ctx.project_type is None
        assert ctx.user_skill_level == "intermediate"
        assert ctx.conversation_id is None
        assert ctx.recent_queries == []
        assert ctx.current_skill is None
        assert ctx.habit_boosts == {}
        assert ctx.strategy_hint is None
        assert ctx.skip_ai_triage is False

    def test_has_memory_false(self):
        ctx = RoutingContext()
        assert ctx.has_memory is False

    def test_has_memory_with_conversation_id(self):
        ctx = RoutingContext(conversation_id="conv-1")
        assert ctx.has_memory is True

    def test_has_memory_with_recent_queries(self):
        ctx = RoutingContext(recent_queries=["q1"])
        assert ctx.has_memory is True

    def test_to_dict(self):
        ctx = RoutingContext(
            file_type="py",
            error_count=2,
            recent_files=["a.py"],
            project_type="python",
            user_skill_level="expert",
            conversation_id="conv-1",
            recent_queries=["q1"],
            current_skill="test",
        )
        d = ctx.to_dict()
        assert d["file_type"] == "py"
        assert d["error_count"] == 2
        assert d["recent_files"] == ["a.py"]
        assert d["project_type"] == "python"
        assert d["user_skill_level"] == "expert"
        assert d["conversation_id"] == "conv-1"
        assert d["recent_queries"] == ["q1"]
        assert d["current_skill"] == "test"


class TestMatchResult:
    """Test MatchResult model."""

    def test_creation(self):
        result = MatchResult(
            skill_id="test/skill", confidence=0.9, matcher_type=MatcherType.KEYWORD
        )
        assert result.skill_id == "test/skill"
        assert result.confidence == pytest.approx(0.9)
        assert result.matcher_type == MatcherType.KEYWORD
        assert result.score_breakdown == {}
        assert result.matched_keywords == []
        assert result.matched_patterns == []
        assert result.semantic_score is None
        assert result.metadata == {}

    def test_meets_threshold_true(self):
        result = MatchResult(skill_id="s", confidence=0.8, matcher_type=MatcherType.KEYWORD)
        assert result.meets_threshold(0.7) is True

    def test_meets_threshold_false(self):
        result = MatchResult(skill_id="s", confidence=0.5, matcher_type=MatcherType.KEYWORD)
        assert result.meets_threshold(0.7) is False

    def test_meets_threshold_exact(self):
        result = MatchResult(skill_id="s", confidence=0.7, matcher_type=MatcherType.KEYWORD)
        assert result.meets_threshold(0.7) is True

    def test_with_boost(self):
        result = MatchResult(
            skill_id="s",
            confidence=0.7,
            matcher_type=MatcherType.KEYWORD,
            matched_keywords=["k1"],
            semantic_score=0.8,
            metadata={"layer": "keyword"},
        )
        boosted = result.with_boost(0.15, source="test")

        assert boosted.confidence == pytest.approx(0.85)
        assert boosted.skill_id == "s"
        assert boosted.matcher_type == MatcherType.KEYWORD
        assert boosted.score_breakdown["boost"] == pytest.approx(0.15)
        assert boosted.metadata["boosted"] is True
        assert boosted.metadata["boost_source"] == "test"
        assert boosted.metadata["original_confidence"] == pytest.approx(0.7)
        assert boosted.matched_keywords == ["k1"]
        assert boosted.semantic_score == pytest.approx(0.8)
        # Original should be unchanged
        assert result.confidence == pytest.approx(0.7)

    def test_with_boost_caps_at_1(self):
        result = MatchResult(skill_id="s", confidence=0.9, matcher_type=MatcherType.KEYWORD)
        boosted = result.with_boost(0.2)
        assert boosted.confidence == pytest.approx(1.0)
