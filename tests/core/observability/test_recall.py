"""W2 Task A — recall retrieval logic.

Contract:
1. ``recall_similar(query, spans, cache)`` returns top-k similar task_ids
   by cosine on representative query embedding.
2. Absolute threshold filters out weak matches (default 0.70).
3. Spans older than ``days`` window are excluded.
4. Returns ``RecallResult`` per match: task_id, similarity, representative
   query, span_count, step sequence, last_seen timestamp.
5. Empty spans → empty list (no crash).
6. Library missing (embeddings=None) → empty list with a flag.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.recall import (
    recall_similar,
)


def _unit_vec(angle: float, dim: int = 384) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[0] = np.cos(angle)
    v[1] = np.sin(angle)
    return v


def _fake_embedding(query: str) -> np.ndarray:
    h = hash(query) & 0xFFFF
    return _unit_vec((h % 360) * (np.pi / 180.0))


def _span(
    task_id: str,
    query: str,
    *,
    name: str = "route:query",
    timestamp: datetime | None = None,
) -> dict:
    ts = timestamp or datetime.now(UTC)
    return {
        "task_id": task_id,
        "input_data": {"query": query},
        "name": name,
        "timestamp": ts.isoformat(),
    }


class TestRecallBasic:
    def test_returns_top_k_similar(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            _span("t1", "alpha"),
            _span("t2", "beta"),
            _span("t3", "gamma"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("alpha", spans, cache=cache, top_k=2)
        assert len(results) <= 2
        assert results[0].task_id == "t1", "exact match should be top"
        assert results[0].similarity == pytest.approx(1.0, abs=1e-5)

    def test_threshold_filters_weak_matches(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")

        # Map "query" to angle 0, "different" to angle pi (cosine=-1)
        def _controlled(query: str) -> np.ndarray:
            return _unit_vec(0.0 if query == "query" else np.pi)

        with patch.object(cache, "_compute", side_effect=_controlled):
            spans = [_span("t1", "different")]
            results = recall_similar("query", spans, cache=cache, threshold=0.70)
        assert results == [], "cosine=-1 should not pass threshold 0.70"

    def test_results_sorted_by_similarity_desc(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            _span("t_far", "zeta"),
            _span("t_near", "alpha"),
            _span("t_mid", "beta"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("alpha", spans, cache=cache, top_k=3)
        sims = [r.similarity for r in results]
        assert sims == sorted(sims, reverse=True), "results must be sorted desc"
        assert results[0].task_id == "t_near"


class TestRecallResult:
    def test_result_has_task_id_and_similarity(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span("t1", "hello")]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.task_id == "t1"
        assert r.similarity == pytest.approx(1.0, abs=1e-5)
        assert r.representative_query == "hello"

    def test_result_has_span_count(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            _span("t1", "hello"),
            _span("t1", "hello"),
            _span("t1", "hello"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.span_count == 3

    def test_result_has_step_sequence(self, tmp_path: Path) -> None:
        """Step sequence extracts span names in temporal order."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            _span("t1", "hello", name="route:query"),
            _span("t1", "hello", name="llm:claude"),
            _span("t1", "hello", name="tool:read"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.step_sequence == ["route:query", "llm:claude", "tool:read"]

    def test_result_has_last_seen_timestamp(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        old_ts = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
        new_ts = datetime(2026, 7, 28, 18, 30, tzinfo=UTC)
        spans = [
            _span("t1", "hello", timestamp=old_ts),
            _span("t1", "hello", timestamp=new_ts),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.last_seen is not None
        # last_seen should be the most recent
        assert "2026-07-28" in r.last_seen


class TestDaysWindow:
    def test_old_spans_excluded(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        old_ts = datetime.now(UTC) - timedelta(days=60)
        spans = [_span("t1", "hello", timestamp=old_ts)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert results == [], "spans older than window should be excluded"

    def test_recent_spans_included(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        recent_ts = datetime.now(UTC) - timedelta(days=5)
        spans = [_span("t1", "hello", timestamp=recent_ts)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert len(results) == 1


class TestFilterRecentEdgeCases:
    """P1-4: _filter_recent keeps spans with missing/malformed/future timestamps.

    Rationale: don't drop data on a formatting quirk. Spans without a parseable
    timestamp are kept; spans with future timestamps are kept (clock skew tolerant).
    """

    def test_missing_timestamp_kept(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                # no "timestamp" key
            }
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert len(results) == 1, "missing timestamp should be kept (not dropped)"

    def test_malformed_timestamp_kept(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "timestamp": "not-a-date",
            }
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert len(results) == 1, "malformed timestamp should be kept"

    def test_future_timestamp_kept(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        future_ts = datetime.now(UTC) + timedelta(days=10)
        spans = [_span("t1", "hello", timestamp=future_ts)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert len(results) == 1, "future timestamp should be kept"

    def test_empty_timestamp_string_kept(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "timestamp": "",
            }
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert len(results) == 1, "empty timestamp string should be kept"


class TestEmptyQuerySkipped:
    """P1-2: task_ids with no extractable query are skipped (not embedded as noise)."""

    def test_task_id_with_empty_query_skipped(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t_empty",
                "input_data": {},  # no "query" key
                "name": "route:query",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            _span("t_real", "hello"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache)
        task_ids = [r.task_id for r in results]
        assert "t_empty" not in task_ids, "empty-query task_id should be skipped"
        assert "t_real" in task_ids


class TestEdgeCases:
    def test_empty_spans_returns_empty(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", [], cache=cache)
        assert results == []

    def test_spans_without_task_id_skipped(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {"name": "route:query", "input_data": {"query": "no task"}, "timestamp": datetime.now(UTC).isoformat()},
            _span("t1", "hello"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache)
        assert len(results) == 1
        assert results[0].task_id == "t1"

    def test_library_missing_returns_empty(self, tmp_path: Path) -> None:
        """If embeddings return None (library missing), results are empty."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span("t1", "hello")]
        with patch.object(cache, "_compute", return_value=None):
            results = recall_similar("hello", spans, cache=cache)
        assert results == []


class TestTopKBound:
    def test_top_k_caps_results(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span(f"t{i}", f"q{i}") for i in range(10)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("q0", spans, cache=cache, top_k=3)
        assert len(results) <= 3
