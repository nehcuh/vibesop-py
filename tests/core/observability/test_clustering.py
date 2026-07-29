"""W1 Task B — cluster algorithm.

Contract:
1. Same task_id always in same cluster (hard group, never split).
2. Cosine ≥ threshold across task_ids merges them into one cluster.
3. Singletons (no near-neighbour) form their own cluster.
4. cluster_id is deterministic given the same input set.
5. Empty input → empty output.
6. Gold flag is set externally (Task C wires this) — Task B always emits is_gold=False.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np

from vibesop.core.observability.clustering import (
    Cluster,
    cluster_queries,
)
from vibesop.core.observability.embedding import EmbeddingCache


def _unit_vec(angle: float, dim: int = 384) -> np.ndarray:
    """Build a deterministic unit vector parameterised by angle.

    Uses first 2 dims as (cos(angle), sin(angle)); rest zero. Two vectors
    with the same angle → cosine = 1.0; angle delta δ → cosine = cos(δ).
    """
    v = np.zeros(dim, dtype=np.float32)
    v[0] = np.cos(angle)
    v[1] = np.sin(angle)
    return v


def _angle_embedding(query: str) -> np.ndarray:
    """Map query → unit vector via deterministic hash → [0, 2π).

    Used so that the same query always maps to the same vector, but
    different queries land at different angles.
    """
    h = hash(query) & 0xFFFF
    angle = (h % 360) * (np.pi / 180.0)
    return _unit_vec(angle)


def _spans(task_id_queries: list[tuple[str, str]]) -> list[dict]:
    """Build minimal span dicts for clustering input."""
    return [
        {"task_id": tid, "input_data": {"query": q}, "name": "route:query"}
        for tid, q in task_id_queries
    ]


class TestHardGrouping:
    def test_same_task_id_always_in_same_cluster(self, tmp_path: Path) -> None:
        """Multiple spans with same task_id → one cluster with that task_id."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_angle_embedding):
            spans = _spans([("t1", "hello"), ("t1", "hello world"), ("t1", "hi")])
            clusters = cluster_queries(spans, cache=cache, threshold=0.80)
        assert len(clusters) == 1
        assert clusters[0].task_ids == ["t1"]
        assert clusters[0].span_count == 3

    def test_repeated_task_id_not_duplicated(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_angle_embedding):
            spans = _spans([("t1", "hello"), ("t1", "hello"), ("t1", "hello")])
            clusters = cluster_queries(spans, cache=cache)
        assert len(clusters) == 1
        assert clusters[0].task_ids == ["t1"]


class TestSoftMerge:
    def test_high_cosine_merges_different_task_ids(self, tmp_path: Path) -> None:
        """task_ids whose representative queries have cosine ≥ threshold merge."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")

        # Two queries with same angle → cosine = 1.0
        def _fixed_compute(query: str) -> np.ndarray:
            return _unit_vec(0.0)  # angle=0 for all queries

        with patch.object(cache, "_compute", side_effect=_fixed_compute):
            spans = _spans([("t1", "q1"), ("t2", "q2"), ("t3", "q3")])
            clusters = cluster_queries(spans, cache=cache, threshold=0.80)
        assert len(clusters) == 1, f"expected 1 merged cluster, got {len(clusters)}"
        assert set(clusters[0].task_ids) == {"t1", "t2", "t3"}

    def test_low_cosine_keeps_separate(self, tmp_path: Path) -> None:
        """task_ids with cosine < threshold remain separate clusters."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")

        # angle delta 180° → cosine = -1 (maximally dissimilar)
        angles = {"q1": 0.0, "q2": np.pi}

        def _alt_compute(query: str) -> np.ndarray:
            # Map queries to alternating angles
            key = "q1" if query == "q1" else "q2"
            return _unit_vec(angles[key])

        with patch.object(cache, "_compute", side_effect=_alt_compute):
            spans = _spans([("t1", "q1"), ("t2", "q2")])
            clusters = cluster_queries(spans, cache=cache, threshold=0.80)
        assert len(clusters) == 2

    def test_threshold_at_boundary_includes(self, tmp_path: Path) -> None:
        """Cosine exactly at threshold should merge (>= comparison)."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        # angle delta = arccos(0.80) ≈ 36.87° → cosine exactly 0.80
        delta = np.arccos(0.80)

        def _boundary_compute(query: str) -> np.ndarray:
            return _unit_vec(0.0 if query == "q1" else delta)

        with patch.object(cache, "_compute", side_effect=_boundary_compute):
            spans = _spans([("t1", "q1"), ("t2", "q2")])
            clusters = cluster_queries(spans, cache=cache, threshold=0.80)
        assert len(clusters) == 1, (
            f"cosine==threshold should merge; got {len(clusters)} clusters"
        )

    def test_threshold_just_below_boundary_excludes(self, tmp_path: Path) -> None:
        """Cosine just below threshold should NOT merge."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        # angle delta = arccos(0.79) → cosine 0.79 < 0.80
        delta = np.arccos(0.79)

        def _below_compute(query: str) -> np.ndarray:
            return _unit_vec(0.0 if query == "q1" else delta)

        with patch.object(cache, "_compute", side_effect=_below_compute):
            spans = _spans([("t1", "q1"), ("t2", "q2")])
            clusters = cluster_queries(spans, cache=cache, threshold=0.80)
        assert len(clusters) == 2


class TestTransitiveMerge:
    def test_chain_merges_into_one_cluster(self, tmp_path: Path) -> None:
        """t1~t2, t2~t3 (transitively) → one cluster of {t1, t2, t3}."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        # t1 at angle 0, t2 at angle 30° (cosine≈0.866 ≥ 0.80 → merge),
        # t3 at angle 60° (cosine to t2 ≈ 0.866 ≥ 0.80 → merge,
        # but cosine to t1 = 0.5 < 0.80; transitivity must still merge).
        angles = {"q1": 0.0, "q2": np.deg2rad(30), "q3": np.deg2rad(60)}

        def _chain_compute(query: str) -> np.ndarray:
            return _unit_vec(angles[query])

        with patch.object(cache, "_compute", side_effect=_chain_compute):
            spans = _spans([("t1", "q1"), ("t2", "q2"), ("t3", "q3")])
            clusters = cluster_queries(spans, cache=cache, threshold=0.80)
        assert len(clusters) == 1
        assert set(clusters[0].task_ids) == {"t1", "t2", "t3"}


class TestEdgeCases:
    def test_empty_input_returns_empty(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        clusters = cluster_queries([], cache=cache)
        assert clusters == []

    def test_single_query_single_cluster(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_angle_embedding):
            spans = _spans([("t1", "hello")])
            clusters = cluster_queries(spans, cache=cache)
        assert len(clusters) == 1
        assert clusters[0].task_ids == ["t1"]
        assert clusters[0].span_count == 1

    def test_spans_without_task_id_are_skipped(self, tmp_path: Path) -> None:
        """A span missing task_id should be ignored, not crash."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {"task_id": "t1", "input_data": {"query": "hello"}, "name": "route:query"},
            {"task_id": None, "input_data": {"query": "noise"}, "name": "route:query"},
            {"input_data": {"query": "no-task-id"}, "name": "route:query"},
        ]
        with patch.object(cache, "_compute", side_effect=_angle_embedding):
            clusters = cluster_queries(spans, cache=cache)
        assert len(clusters) == 1
        assert clusters[0].task_ids == ["t1"]


class TestClusterIdDeterminism:
    def test_same_input_same_cluster_id(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = _spans([("t1", "hello"), ("t2", "world")])
        with patch.object(cache, "_compute", side_effect=_angle_embedding):
            c1 = cluster_queries(spans, cache=cache)
            c2 = cluster_queries(spans, cache=cache)
        assert c1[0].cluster_id == c2[0].cluster_id, (
            "cluster_id must be deterministic for same input"
        )

    def test_different_input_different_cluster_id(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_angle_embedding):
            c1 = cluster_queries(_spans([("t1", "hello")]), cache=cache)
            c2 = cluster_queries(_spans([("t2", "world")]), cache=cache)
        # Different task_id sets → different cluster_id
        assert c1[0].cluster_id != c2[0].cluster_id


class TestGoldFlagDefault:
    def test_clusters_default_to_not_gold(self, tmp_path: Path) -> None:
        """Task C sets is_gold based on InstinctLearner signals; Task B always False."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_angle_embedding):
            spans = _spans([("t1", "hello")])
            clusters = cluster_queries(spans, cache=cache)
        assert all(c.is_gold is False for c in clusters)


class TestClusterObject:
    def test_cluster_repr_includes_task_ids(self) -> None:
        c = Cluster(cluster_id="abc123", task_ids=["t1", "t2"], span_count=5)
        s = repr(c)
        assert "abc123" in s
        assert "t1" in s
