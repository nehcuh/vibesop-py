"""Tests for CacheManager semantic similarity caching."""

from __future__ import annotations

from vibesop.core.routing.cache import CacheManager


class TestCacheSimilarity:
    def test_exact_match_returns_data(self):
        cache = CacheManager()
        cache.set("key1", {"skill": "review"}, original_query="review my code")
        result = cache.get_similar("review my code")
        assert result is not None
        assert result["skill"] == "review"

    def test_similar_query_returns_cached_data(self):
        cache = CacheManager()
        cache.set("key1", {"skill": "debug"}, original_query="debug the error")
        result = cache.get_similar("debug the error now")
        assert result is not None
        assert result["skill"] == "debug"

    def test_dissimilar_query_returns_none(self):
        cache = CacheManager()
        cache.set("key1", {"skill": "review"}, original_query="review my code")
        result = cache.get_similar("deploy to production")
        assert result is None

    def test_empty_cache_returns_none(self):
        cache = CacheManager()
        result = cache.get_similar("any query")
        assert result is None

    def test_jaccard_similarity_computation(self):
        cache = CacheManager()
        bigrams_a = cache._char_bigrams("hello")
        bigrams_b = cache._char_bigrams("hello world")
        similarity = cache._jaccard_similarity(bigrams_a, bigrams_b)
        assert 0.0 < similarity < 1.0

    def test_char_bigrams_extraction(self):
        cache = CacheManager()
        bigrams = cache._char_bigrams("abc")
        assert bigrams == {"ab", "bc"}
