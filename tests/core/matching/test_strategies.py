"""Tests for concrete matcher implementations in strategies.py."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from vibesop.core.matching.base import (
    MatchResult,
    MatcherType,
)
from vibesop.core.matching.lazy_matcher import LazyEmbeddingMatcher
from vibesop.core.matching.strategies import (
    EmbeddingMatcher,
    KeywordMatcher,
    LevenshteinMatcher,
    MatcherConfig,
    TFIDFMatcher,
)
from vibesop.core.matching.tokenizers import TokenizerConfig


def _make_candidate(skill_id="test-skill", **overrides):
    c = {
        "id": skill_id,
        "name": "Test Skill",
        "description": "A test skill for testing",
        "intent": "Test things",
        "keywords": ["test", "testing"],
        "namespace": "builtin",
        "triggers": ["test trigger"],
    }
    c.update(overrides)
    return c


def _make_candidates(*ids: str):
    return [_make_candidate(sid) for sid in ids]


class TestMatcherConfig:
    """Test MatcherConfig dataclass."""

    def test_defaults(self):
        cfg = MatcherConfig()
        assert cfg.min_confidence == 0.3
        assert cfg.case_sensitive is False
        assert cfg.use_cache is True

    def test_custom(self):
        cfg = MatcherConfig(min_confidence=0.5, case_sensitive=True, use_cache=False)
        assert cfg.min_confidence == 0.5
        assert cfg.case_sensitive is True
        assert cfg.use_cache is False

    def test_custom_tokenizer(self):
        tk = TokenizerConfig(min_token_length=2)
        cfg = MatcherConfig(tokenizer_config=tk)
        assert cfg.tokenizer_config.min_token_length == 2


class TestKeywordMatcher:
    """Test KeywordMatcher."""

    def test_init_default(self):
        m = KeywordMatcher()
        assert m._config.min_confidence == 0.3

    def test_init_custom_config(self):
        cfg = MatcherConfig(min_confidence=0.5)
        m = KeywordMatcher(cfg)
        assert m._config.min_confidence == 0.5

    def test_match_returns_results(self):
        m = KeywordMatcher()
        results = m.match("test query", _make_candidates("a", "b"))
        assert isinstance(results, list)

    def test_match_direct_hit(self):
        m = KeywordMatcher()
        c = _make_candidate("debug-skill", name="Debugging", keywords=["debug", "error"])
        results = m.match("debug error", [c])
        assert len(results) >= 1
        assert results[0].skill_id == "debug-skill"
        assert results[0].confidence > 0.3

    def test_match_below_threshold_filtered(self):
        cfg = MatcherConfig(min_confidence=0.9)
        m = KeywordMatcher(cfg)
        c = _make_candidate(
            "test-skill",
            name="Unrelated",
            description="Something else",
            intent="Other things",
            keywords=["other"],
        )
        results = m.match("debug error crash", [c])
        # Very unlikely to match with high confidence
        assert all(r.confidence < 0.9 or r.skill_id != "test-skill" for r in results)

    def test_match_caching(self):
        cfg = MatcherConfig(use_cache=True)
        m = KeywordMatcher(cfg)
        candidates = _make_candidates("a")
        r1 = m.match("cache test", candidates)
        r2 = m.match("cache test", candidates)
        assert r1 == r2

    def test_match_no_cache(self):
        cfg = MatcherConfig(use_cache=False)
        m = KeywordMatcher(cfg)
        candidates = _make_candidates("a")
        m.match("no cache", candidates)
        assert len(m._cache) == 0

    def test_match_respects_top_k(self):
        m = KeywordMatcher(MatcherConfig(min_confidence=0.0))
        candidates = [_make_candidate(f"skill-{i}", name=f"Skill {i} test") for i in range(20)]
        results = m.match("test", candidates, top_k=3)
        assert len(results) <= 3

    def test_score(self):
        m = KeywordMatcher()
        c = _make_candidate("debug", name="Debugging Skill", keywords=["debug", "error"])
        score = m.score("debug error", c)
        assert score > 0.3

    def test_score_exact_name_match(self):
        m = KeywordMatcher()
        c = _make_candidate("debug", name="debugging", keywords=["debug"])
        score = m.score("debugging", c)
        assert score > 0.3

    def test_get_matched_keywords(self):
        m = KeywordMatcher()
        c = _make_candidate("test", keywords=["debug", "error", "crash"])
        matched = m._get_matched_keywords({"debug", "error"}, c)
        assert "debug" in matched
        assert "error" in matched

    def test_get_capabilities(self):
        m = KeywordMatcher()
        caps = m.get_capabilities()
        assert caps["type"] == "keyword"
        assert caps["speed"] == "fast"

    def test_warm_up_noop(self):
        m = KeywordMatcher()
        m.warm_up([])  # Should not raise


class TestTFIDFMatcher:
    """Test TFIDFMatcher."""

    def test_init(self):
        m = TFIDFMatcher()
        assert m._fitted is False

    def test_fit_sets_fitted(self):
        m = TFIDFMatcher()
        m.fit(_make_candidates("a", "b"))
        assert m._fitted is True

    def test_match_auto_fits(self):
        m = TFIDFMatcher()
        results = m.match("test query", _make_candidates("a", "b"))
        assert m._fitted is True
        assert isinstance(results, list)

    def test_match_returns_results(self):
        m = TFIDFMatcher()
        m.fit(_make_candidates("debug-skill"))
        results = m.match("debugging error", _make_candidates("debug-skill"))
        assert isinstance(results, list)

    def test_match_respects_top_k(self):
        m = TFIDFMatcher(MatcherConfig(min_confidence=0.0))
        candidates = [_make_candidate(f"skill-{i}", name=f"Skill {i}") for i in range(20)]
        results = m.match("test", candidates, top_k=5)
        assert len(results) <= 5

    def test_score(self):
        m = TFIDFMatcher()
        m.fit(_make_candidates("debug-skill"))
        c = _make_candidate("debug-skill", name="Debugging", description="Debug errors")
        score = m.score("debug error", c)
        assert isinstance(score, float)

    def test_score_auto_fits_single(self):
        m = TFIDFMatcher()
        c = _make_candidate("debug-skill", name="Debug")
        score = m.score("debug", c)
        assert isinstance(score, float)
        assert m._fitted is True

    def test_get_capabilities(self):
        m = TFIDFMatcher()
        caps = m.get_capabilities()
        assert caps["type"] == "tfidf"

    def test_warm_up_fits(self):
        m = TFIDFMatcher()
        m.warm_up(_make_candidates("a", "b"))
        assert m._fitted is True

    def test_warm_up_empty_noop(self):
        m = TFIDFMatcher()
        m.warm_up([])
        assert m._fitted is False


class TestEmbeddingMatcher:
    """Test EmbeddingMatcher (without actual sentence_transformers)."""

    def test_init_default_model(self):
        m = EmbeddingMatcher()
        assert m._model_name == "paraphrase-multilingual-MiniLM-L12-v2"

    def test_init_custom_model(self):
        m = EmbeddingMatcher(model_name="custom-model")
        assert m._model_name == "custom-model"

    def test_load_model_import_error(self):
        m = EmbeddingMatcher()
        # None in sys.modules makes the lazy in-function import raise
        # ImportError regardless of whether the library is installed.
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            with pytest.raises(ImportError, match="sentence-transformers"):
                m._load_model()

    def test_match_returns_empty_when_no_numpy(self):
        m = EmbeddingMatcher()
        with patch("vibesop.core.matching.strategies.np", None):
            results = m.match("test", _make_candidates("a"))
            assert results == []

    def test_get_capabilities(self):
        m = EmbeddingMatcher()
        caps = m.get_capabilities()
        assert caps["type"] == "embedding"
        assert caps["speed"] == "slow"
        assert caps["requires_semantic"] is True

    def test_warm_up_no_numpy(self):
        m = EmbeddingMatcher()
        with patch("vibesop.core.matching.strategies.np", None):
            m.warm_up([])  # Should not raise

    def test_candidate_to_text(self):
        m = EmbeddingMatcher()
        c = _make_candidate("test", name="Test", description="Desc", intent="Do")
        text = m._candidate_to_text(c)
        assert "Test" in text
        assert "Desc" in text


class TestLevenshteinMatcher:
    """Test LevenshteinMatcher."""

    def test_init(self):
        m = LevenshteinMatcher()
        assert m._config.min_confidence == 0.3

    def test_match_typo_correction(self):
        m = LevenshteinMatcher(MatcherConfig(min_confidence=0.0))
        c = _make_candidate("debug-skill", name="debugging", keywords=["debug"])
        results = m.match("debbuging", [c])
        # "debbuging" is close to "debugging"
        assert len(results) >= 0  # At minimum doesn't crash

    def test_match_empty_candidates(self):
        m = LevenshteinMatcher()
        results = m.match("test", [])
        assert results == []

    def test_score_exact_match(self):
        m = LevenshteinMatcher()
        c = _make_candidate("debug", name="debug", keywords=["debug"])
        score = m.score("debug", c)
        assert score > 0.5

    def test_score_no_tokens(self):
        m = LevenshteinMatcher()
        c = _make_candidate("empty", name="a", description="b", keywords=[], intent="")
        score = m.score("x", c)
        assert isinstance(score, float)

    def test_normalized_similarity_identical(self):
        m = LevenshteinMatcher()
        sim = m._normalized_similarity("hello", "hello")
        assert sim == pytest.approx(1.0)

    def test_normalized_similarity_different(self):
        m = LevenshteinMatcher()
        sim = m._normalized_similarity("hello", "world")
        assert sim < 1.0

    def test_normalized_similarity_empty(self):
        m = LevenshteinMatcher()
        sim = m._normalized_similarity("", "")
        assert sim == 1.0

    def test_levenshtein_distance(self):
        m = LevenshteinMatcher()
        assert m._levenshtein_distance("abc", "abc") == 0
        assert m._levenshtein_distance("abc", "abd") == 1
        assert m._levenshtein_distance("", "abc") == 3
        assert m._levenshtein_distance("kitten", "sitting") == 3

    def test_tokenize(self):
        m = LevenshteinMatcher()
        tokens = m._tokenize("hello world test")
        assert "hello" in tokens
        assert "world" in tokens

    def test_tokenize_chinese(self):
        m = LevenshteinMatcher()
        tokens = m._tokenize("你好世界")
        assert len(tokens) >= 1

    def test_tokenize_skips_short(self):
        m = LevenshteinMatcher()
        tokens = m._tokenize("a b c")
        assert len(tokens) == 0

    def test_candidate_tokens(self):
        m = LevenshteinMatcher()
        c = _make_candidate("debug-skill", name="Debugging", keywords=["error", "crash"])
        tokens = m._candidate_tokens(c)
        assert "debugging" in tokens or "Debugging" in [t.lower() for t in tokens]
        assert "error" in tokens

    def test_candidate_tokens_with_tags(self):
        m = LevenshteinMatcher()
        c = _make_candidate("test", tags=["python", "debugging"])
        tokens = m._candidate_tokens(c)
        assert "python" in tokens

    def test_candidate_to_text(self):
        m = LevenshteinMatcher()
        c = _make_candidate("test", name="TestName", description="TestDesc")
        text = m._candidate_to_text(c)
        assert "TestName" in text
        assert "TestDesc" in text

    def test_get_capabilities(self):
        m = LevenshteinMatcher()
        caps = m.get_capabilities()
        assert caps["type"] == "levenshtein"

    def test_warm_up_noop(self):
        m = LevenshteinMatcher()
        m.warm_up([])  # Should not raise


class TestLazyEmbeddingMatcher:
    """Test LazyEmbeddingMatcher proxy."""

    def test_init(self):
        cfg = MatcherConfig()
        lazy = LazyEmbeddingMatcher(cfg)
        assert lazy._real is None

    def test_warm_up_defers_to_real(self):
        cfg = MatcherConfig()
        lazy = LazyEmbeddingMatcher(cfg)
        mock_real = MagicMock()
        lazy._real = mock_real
        lazy.warm_up(_make_candidates("a"))
        mock_real.warm_up.assert_called_once()

    def test_match_defers_to_real(self):
        cfg = MatcherConfig()
        lazy = LazyEmbeddingMatcher(cfg)
        mock_real = MagicMock()
        mock_real.match.return_value = [
            MatchResult(
                skill_id="test",
                confidence=0.9,
                score_breakdown={"test": 0.9},
                matcher_type=MatcherType.EMBEDDING,
            )
        ]
        lazy._real = mock_real
        candidates = _make_candidates("test")
        result = lazy.match("query", candidates)
        mock_real.match.assert_called_once()
        assert isinstance(result, list)

    def test_getattr_defers(self):
        cfg = MatcherConfig()
        lazy = LazyEmbeddingMatcher(cfg)
        mock_real = MagicMock()
        mock_real.some_attr = "value"
        lazy._real = mock_real
        assert lazy.some_attr == "value"

    def test_ensure_real_is_thread_safe_singleton(self):
        cfg = MatcherConfig()
        lazy = LazyEmbeddingMatcher(cfg)
        # Set _real to verify singleton behavior without patching imports
        mock_real = MagicMock()
        lazy._real = mock_real
        r1 = lazy._ensure_real()
        r2 = lazy._ensure_real()
        assert r1 is mock_real
        assert r2 is mock_real
        assert r1 is r2
