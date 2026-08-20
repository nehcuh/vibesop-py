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

import hashlib
from pathlib import Path
from unittest.mock import patch

import numpy as np

from vibesop.core.observability.clustering import (
    Cluster,
    _extract_query,
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

    Uses hashlib (NOT built-in hash(), which is PYTHONHASHSEED-randomized
    per process and made the metadata e2e test flaky ~15% of runs — gate16).
    Same query always maps to the same vector; different queries land at
    different angles.
    """
    h = int.from_bytes(hashlib.sha1(query.encode("utf-8")).digest()[:2], "big")
    angle = (h % 360) * (np.pi / 180.0)
    return _unit_vec(angle)


def _spans(task_id_queries: list[tuple[str, str]]) -> list[dict]:
    """Build minimal span dicts for clustering input.

    Includes ``project_id="test"`` so the lazy age-out filter (W5.1 Task 2.3)
    does not exclude them. Pre-W5.0 spans (project_id="default") are filtered
    out by default in cluster_queries; tests that want to exercise legacy
    filtering pass project_id="default" explicitly.
    """
    return [
        {
            "task_id": tid,
            "input_data": {"query": q},
            "name": "route:query",
            "project_id": "test",
        }
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
        assert len(clusters) == 1, f"cosine==threshold should merge; got {len(clusters)} clusters"

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
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "project_id": "test",
            },
            {
                "task_id": None,
                "input_data": {"query": "noise"},
                "name": "route:query",
                "project_id": "test",
            },
            {
                "input_data": {"query": "no-task-id"},
                "name": "route:query",
                "project_id": "test",
            },
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


class TestMaxSpansPerTaskSampling:
    """W5.0.C: ``max_spans_per_task`` caps the spans counted per task_id.

    When a task has more spans than the cap, only the most-recent-N (by
    ``started_at`` descending) contribute to ``Cluster.span_count``.
    Default ``None`` preserves all spans (pre-W5.0 behavior).
    """

    @staticmethod
    def _span_with_ts(task_id: str, query: str, started_at: str) -> dict:
        return {
            "task_id": task_id,
            "input_data": {"query": query},
            "name": "route:query",
            "started_at": started_at,
            "project_id": "test",
        }

    def test_default_none_preserves_all_spans(self, tmp_path: Path) -> None:
        """max_spans_per_task=None (default) → all spans counted."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = _spans([("t1", "hello")] * 10)  # 10 spans same task
        with patch.object(cache, "_compute", side_effect=_angle_embedding):
            clusters = cluster_queries(spans, cache=cache)
        assert len(clusters) == 1
        assert clusters[0].span_count == 10

    def test_cap_limits_span_count_to_most_recent_n(self, tmp_path: Path) -> None:
        """max_spans_per_task=3 → span_count capped at 3 even when task has 10."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        # 10 spans for task t1, each 1 day apart, oldest first.
        spans = [
            self._span_with_ts("t1", "hello", (now - timedelta(days=9 - i)).isoformat())
            for i in range(10)
        ]
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_angle_embedding):
            clusters = cluster_queries(spans, cache=cache, max_spans_per_task=3)
        assert len(clusters) == 1
        assert clusters[0].span_count == 3

    def test_cap_does_not_affect_tasks_below_limit(self, tmp_path: Path) -> None:
        """Tasks with ≤ max_spans_per_task spans are unchanged."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = _spans([("t1", "hello"), ("t1", "hello"), ("t2", "world")])

        def _orthogonal(query: str) -> np.ndarray:
            # hello → dim 0; anything else → dim 1. Cosine = 0 (below 0.80 threshold).
            v = np.zeros(384, dtype=np.float32)
            v[0 if query == "hello" else 1] = 1.0
            return v

        with patch.object(cache, "_compute", side_effect=_orthogonal):
            clusters = cluster_queries(spans, cache=cache, max_spans_per_task=10)
        # Both tasks below cap — span_count unchanged. Two clusters (orthogonal).
        assert len(clusters) == 2
        by_task = {c.task_ids[0]: c.span_count for c in clusters}
        assert by_task["t1"] == 2
        assert by_task["t2"] == 1

    def test_cap_does_not_change_cluster_count(self, tmp_path: Path) -> None:
        """Sampling is per-task; doesn't merge/split clusters."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        # Two tasks, each with 5 spans. Cap at 3.
        spans = []
        for tid in ("t1", "t2"):
            for i in range(5):
                spans.append(
                    self._span_with_ts(
                        tid, f"query-{tid}", (now - timedelta(days=4 - i)).isoformat()
                    )
                )

        def _orthogonal(query: str) -> np.ndarray:
            # query-t1 → dim 0; query-t2 → dim 1. Orthogonal → no soft merge.
            v = np.zeros(384, dtype=np.float32)
            v[0 if "t1" in query else 1] = 1.0
            return v

        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_orthogonal):
            clusters = cluster_queries(spans, cache=cache, max_spans_per_task=3)
        # Still 2 clusters (orthogonal), each capped at 3.
        assert len(clusters) == 2
        assert all(c.span_count == 3 for c in clusters)


class TestExtractQueryMetadataFallback:
    """M12 M0: ``_extract_query`` falls back to ``metadata`` when
    ``input_data`` carries no query.

    Route span producers (agent_runtime.py / cli/main.py) put the query
    only into ``metadata["query"]`` (a JSON string) and the span name.
    Pre-M0, ``_extract_query`` read only ``input_data``, so route spans
    yielded zero extractable queries and clustering silently spun empty.
    """

    def test_metadata_json_string_fallback(self) -> None:
        """input_data absent + metadata as JSON string with query → extracted."""
        span = {
            "task_id": "t1",
            "name": "route:how do I fix lint errors",
            "input_data": None,
            "metadata": '{"query": "how do I fix lint errors", "platform": "vibe-cli"}',
        }
        assert _extract_query(span) == "how do I fix lint errors"

    def test_metadata_dict_fallback(self) -> None:
        """metadata already a dict (e.g. in-memory span objects) → extracted."""
        span = {
            "task_id": "t1",
            "metadata": {"query": "run the tests", "platform": "claude-code"},
        }
        assert _extract_query(span) == "run the tests"

    def test_input_data_preferred_over_metadata(self) -> None:
        """input_data wins when both sources carry a query (compat strategy)."""
        span = {
            "input_data": {"query": "from input_data"},
            "metadata": '{"query": "from metadata"}',
        }
        assert _extract_query(span) == "from input_data"

    def test_input_data_dict_without_query_falls_back(self) -> None:
        """input_data dict lacking 'query' → metadata fallback kicks in."""
        span = {
            "input_data": {"prompt_preview": "not a query"},
            "metadata": '{"query": "fallback query"}',
        }
        assert _extract_query(span) == "fallback query"

    def test_both_missing_returns_none(self) -> None:
        """No input_data, no metadata → None."""
        assert _extract_query({"task_id": "t1"}) is None
        assert _extract_query({"input_data": None, "metadata": None}) is None

    def test_metadata_missing_query_key_returns_none(self) -> None:
        """metadata parses fine but has no 'query' key → None (not the raw string)."""
        span = {"metadata": '{"platform": "vibe-cli", "mode": "matched"}'}
        assert _extract_query(span) is None

    def test_malformed_metadata_json_does_not_crash(self) -> None:
        """Broken JSON metadata → silent None, never raises."""
        span = {"metadata": '{"query": "unterminated'}
        assert _extract_query(span) is None
        span2 = {"metadata": "not json at all"}
        assert _extract_query(span2) is None

    def test_non_dict_metadata_json_returns_none(self) -> None:
        """metadata parsing to a non-dict (list/number) → None."""
        assert _extract_query({"metadata": '["a", "b"]'}) is None
        assert _extract_query({"metadata": "42"}) is None

    def test_input_data_shapes_unchanged(self) -> None:
        """Regression: the three pre-M0 input_data shapes still work."""
        assert _extract_query({"input_data": {"query": "dict shape"}}) == "dict shape"
        assert _extract_query({"input_data": '{"query": "json shape"}'}) == "json shape"
        assert _extract_query({"input_data": "raw query string"}) == "raw query string"
        # input_data dict without query and no metadata → None (unchanged)
        assert _extract_query({"input_data": {"other": 1}}) is None

    def test_cluster_queries_extracts_from_metadata(self, tmp_path: Path) -> None:
        """End-to-end: route-shaped spans (metadata-only query) now cluster."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "name": "route:fix the flaky test",
                "input_data": None,
                "metadata": '{"query": "fix the flaky test"}',
                "project_id": "test",
            },
            {
                "task_id": "t2",
                "name": "route:unrelated topic",
                "input_data": None,
                "metadata": {"query": "unrelated topic"},
                "project_id": "test",
            },
        ]
        with patch.object(cache, "_compute", side_effect=_angle_embedding):
            clusters = cluster_queries(spans, cache=cache)
        assert len(clusters) == 2
        queries = {q for c in clusters for q in c.queries}
        assert queries == {"fix the flaky test", "unrelated topic"}
