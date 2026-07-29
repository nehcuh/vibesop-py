"""W1 Task A — embedding cache + lazy singleton.

Verifies that:
1. ``EmbeddingCache.embed(query)`` returns deterministic 384-dim vector
2. Cache hits avoid re-computing (mock the underlying model to prove this)
3. Cache file persists across instances
4. Model_id bump invalidates old cache (old keys → miss → re-compute)
5. Library missing returns None gracefully (fastembed is optional)
6. Concurrent writes are serialised (no JSONL interleaving-style corruption)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vibesop.core.observability.embedding import (
    EmbeddingCache,
    get_embedding_cache,
)


def _fake_embedding(text: str) -> np.ndarray:
    """Deterministic fake embedding for testing — hashed to 384-dim."""
    h = hash(text) & 0xFFFFFFFF
    rng = np.random.default_rng(h)
    return rng.standard_normal(384).astype(np.float32)


class TestEmbeddingCacheBasic:
    def test_returns_vector_for_query(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            v = cache.embed("hello world")
        assert v is not None
        assert v.shape == (384,)
        assert v.dtype == np.float32

    def test_same_query_same_vector(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            v1 = cache.embed("hello world")
            v2 = cache.embed("hello world")
        assert v1 is not None and v2 is not None
        np.testing.assert_array_equal(v1, v2)

    def test_different_queries_different_vectors(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            v1 = cache.embed("hello")
            v2 = cache.embed("world")
        assert v1 is not None and v2 is not None
        assert not np.array_equal(v1, v2)


class TestCachePersistence:
    def test_cache_hit_avoids_recompute(self, tmp_path: Path) -> None:
        """Second embed() with same query must not re-invoke _compute."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        mock_compute = MagicMock(side_effect=_fake_embedding)
        with patch.object(cache, "_compute", mock_compute):
            cache.embed("hello world")
            assert mock_compute.call_count == 1
            cache.embed("hello world")  # should hit cache
            assert mock_compute.call_count == 1, "cache miss on second call"

    def test_cache_persists_across_instances(self, tmp_path: Path) -> None:
        """New EmbeddingCache pointing at same file must read existing cache."""
        cache_path = tmp_path / "emb.npz"
        cache1 = EmbeddingCache(cache_path=cache_path)
        with patch.object(cache1, "_compute", side_effect=_fake_embedding):
            v1 = cache1.embed("hello world")

        # New instance, same path — should NOT re-compute
        cache2 = EmbeddingCache(cache_path=cache_path)
        mock_compute = MagicMock(side_effect=_fake_embedding)
        with patch.object(cache2, "_compute", mock_compute):
            v2 = cache2.embed("hello world")
            assert mock_compute.call_count == 0, "expected cache hit, got miss"

        assert v1 is not None and v2 is not None
        np.testing.assert_array_equal(v1, v2)

    def test_cache_survives_normalize_equivalent_queries(self, tmp_path: Path) -> None:
        """Queries that normalize to the same string must share cache entries."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        mock_compute = MagicMock(side_effect=_fake_embedding)
        with patch.object(cache, "_compute", mock_compute):
            cache.embed("Hello, World!")
            cache.embed("hello world")  # normalizes the same
            assert mock_compute.call_count == 1, (
                "normalize-equivalent queries should share cache entry"
            )


class TestModelIdInvalidation:
    def test_model_id_change_invalidates_cache(self, tmp_path: Path) -> None:
        """Bumping model_id must treat all old entries as misses."""
        cache_path = tmp_path / "emb.npz"
        cache1 = EmbeddingCache(cache_path=cache_path, model_id="minilm-l12-v2")
        with patch.object(cache1, "_compute", side_effect=_fake_embedding):
            cache1.embed("hello")

        # New cache with different model_id — must re-compute everything
        cache2 = EmbeddingCache(cache_path=cache_path, model_id="bge-m3-v1")
        mock_compute = MagicMock(side_effect=_fake_embedding)
        with patch.object(cache2, "_compute", mock_compute):
            cache2.embed("hello")
            assert mock_compute.call_count == 1, (
                "model_id bump should invalidate cache"
            )

    def test_cache_file_records_model_id(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "emb.npz"
        cache = EmbeddingCache(cache_path=cache_path, model_id="minilm-l12-v2")
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            cache.embed("hello")
        # Reload + inspect metadata
        npz = np.load(cache_path, allow_pickle=False)
        assert "metadata" in npz
        meta = json.loads(str(npz["metadata"]))
        assert meta["model_id"] == "minilm-l12-v2"


class TestLibraryMissing:
    def test_returns_none_when_library_missing(self, tmp_path: Path) -> None:
        """If _compute signals library missing (returns None), embed() returns None."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", return_value=None):
            v = cache.embed("hello world")
        assert v is None

    def test_batch_handles_missing_gracefully(self, tmp_path: Path) -> None:
        """Batch returns None for queries when library unavailable."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", return_value=None):
            results = cache.embed_batch(["a", "b"])
        assert results == [None, None]


class TestBatchEmbedding:
    def test_batch_returns_one_vector_per_query(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = cache.embed_batch(["a", "b", "c"])
        assert len(results) == 3
        assert all(r is not None for r in results)
        assert all(r.shape == (384,) for r in results if r is not None)

    def test_batch_uses_cache(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            cache.embed("a")  # warm cache for "a"
            mock_compute = MagicMock(side_effect=_fake_embedding)
            with patch.object(cache, "_compute", mock_compute):
                cache.embed_batch(["a", "b"])
                # Only "b" should trigger compute; "a" hits cache
                assert mock_compute.call_count == 1


class TestSingleton:
    def test_get_embedding_cache_returns_same_instance(self) -> None:
        import vibesop.core.observability.embedding as emb_mod

        emb_mod._embedding_cache = None
        try:
            c1 = get_embedding_cache()
            c2 = get_embedding_cache()
            assert c1 is c2
        finally:
            emb_mod._embedding_cache = None


class TestGapCoverage:
    """Tests added post-grok-review for coverage gaps."""

    def test_embed_batch_mixed_hit_and_miss(self, tmp_path: Path) -> None:
        """Batch with one cached + one uncached query — only miss triggers compute."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            cache.embed("cached")  # warm the cache

        mock_compute = MagicMock(side_effect=_fake_embedding)
        with patch.object(cache, "_compute", mock_compute):
            results = cache.embed_batch(["cached", "fresh"])
        assert mock_compute.call_count == 1, (
            "only the miss should trigger compute"
        )
        assert results[0] is not None
        assert results[1] is not None
        # Same key behaviour as single embed
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            same_again = cache.embed("fresh")
        np.testing.assert_array_equal(results[1], same_again)

    def test_corrupted_cache_file_starts_cold(self, tmp_path: Path) -> None:
        """Garbage in cache file → log warning, start with empty cache."""
        cache_path = tmp_path / "emb.npz"
        cache_path.write_bytes(b"NOT A VALID NPZ FILE")
        cache = EmbeddingCache(cache_path=cache_path)
        assert cache._cache == {}, "corrupted file should yield empty cache"
        # And embed() should still work (computes fresh)
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            v = cache.embed("hello")
        assert v is not None
        assert v.shape == (384,)

    def test_merge_external_picks_up_keys_added_by_another_process(
        self, tmp_path: Path
    ) -> None:
        """Simulate process B adding keys to the cache file while process A holds lock.

        Writes the cache file with one entry from "another process", then
        calls _merge_external_locked() on a fresh EmbeddingCache that has
        its own in-memory state, and asserts the external key is merged.
        """
        # Arrange: "process B" writes a cache with one entry
        other = EmbeddingCache(cache_path=tmp_path / "emb.npz", model_id="minilm-l12-v2")
        with patch.object(other, "_compute", side_effect=_fake_embedding):
            other.embed("from-other-process")
        other_path = other._cache_path

        # "process A" loads same file, adds its own entry
        main = EmbeddingCache(cache_path=other_path, model_id="minilm-l12-v2")
        # _load should pick up other's entry
        assert len(main._cache) == 1, "load should pick up other process's entry"

        # Simulate new external write while we're not looking
        # (write another key directly to the file via a third EmbeddingCache)
        third = EmbeddingCache(cache_path=other_path, model_id="minilm-l12-v2")
        with patch.object(third, "_compute", side_effect=_fake_embedding):
            third.embed("from-third-process")

        # main now has stale in-memory state (1 entry); calling _merge_external_locked
        # should pick up the third's entry without losing main's in-memory state
        main._merge_external_locked()
        assert len(main._cache) == 2, (
            "merge should pick up entries added externally since last load"
        )

    def test_empty_query_returns_none(self, tmp_path: Path) -> None:
        """Empty/whitespace-only query → normalize returns '' → key is None → None."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        mock_compute = MagicMock(side_effect=_fake_embedding)
        with patch.object(cache, "_compute", mock_compute):
            assert cache.embed("") is None
            assert cache.embed("   ") is None
            assert cache.embed("\n\n") is None
        assert mock_compute.call_count == 0, "empty query should not invoke compute"

    def test_readonly_filesystem_skips_flush_gracefully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If lock acquisition raises OSError, flush is skipped (not crashed)."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")

        # Make cross_process_lock raise OSError

        def _raising_lock(_path):
            raise OSError("simulated read-only filesystem")

        monkeypatch.setattr(
            "vibesop.utils.file_lock.cross_process_lock", _raising_lock
        )
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            v = cache.embed("hello")  # should not raise
        assert v is not None, "embed should still return a vector"
        # The in-memory cache should have the entry even though flush failed
        assert any(cache._cache)
