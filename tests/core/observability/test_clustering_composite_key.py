"""W5.1 composite-key + project_distribution + lazy age-out tests.

Verifies the three Phase 2 algorithm changes:

1. Hard-key changed from ``task_id`` to ``(project_id, task_id)``: same
   task_id in different projects produces distinct clusters (Task 2.1).
2. ``Cluster.project_distribution`` carries per-project span counts and
   ``is_cross_project`` flags multi-project clusters (Task 2.2).
3. ``include_legacy=False`` (default) filters pre-W5.0 spans with
   ``project_id == "default"`` out of all readers (Task 2.3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np

from vibesop.core.observability.clustering import Cluster, cluster_queries
from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.recall import recall_similar


def _unit_vec(angle: float, dim: int = 384) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[0] = np.cos(angle)
    v[1] = np.sin(angle)
    return v


def _orthogonal_embedding(query: str) -> np.ndarray:
    """Map a small set of literal queries to orthogonal axes; fallback hashes.

    Used so that the same query always maps to the same vector and known
    queries are mutually orthogonal (cosine = 0, below threshold = no merge).
    """
    axis_map = {
        "hello": 0,
        "world": 1,
        "fix bug": 2,
        "refactor api": 3,
    }
    v = np.zeros(384, dtype=np.float32)
    idx = axis_map.get(query, (hash(query) & 0xFFFF) % 384)
    v[idx] = 1.0
    return v


def _spans_two_projects(task_id: str, query: str, p1: str, p2: str) -> list[dict]:
    """Build 2 spans with the same task_id in 2 different projects."""
    return [
        {
            "task_id": task_id,
            "input_data": {"query": query},
            "name": "route:query",
            "started_at": datetime.now(UTC).isoformat(),
            "project_id": p1,
        },
        {
            "task_id": task_id,
            "input_data": {"query": query},
            "name": "route:query",
            "started_at": datetime.now(UTC).isoformat(),
            "project_id": p2,
        },
    ]


class TestCompositeHardKey:
    def test_same_task_id_different_projects_kept_separate(self, tmp_path: Path) -> None:
        """Same task_id in 2 projects with orthogonal queries → 2 clusters.

        Hard-key change: pre-W5.1 grouped by task_id alone, so the two spans
        would have been forced into ONE cluster regardless of similarity.
        Now the composite key splits them; if queries are dissimilar they
        stay as 2 separate clusters. (When queries match, soft-merge still
        recombines — see ``test_soft_merge_can_still_cross_projects``.)
        """
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},  # axis 0
                "name": "route:query",
                "project_id": "vibesop",
            },
            {
                "task_id": "t1",
                "input_data": {"query": "world"},  # axis 1 (orthogonal)
                "name": "route:query",
                "project_id": "cmspark",
            },
        ]
        with patch.object(cache, "_compute", side_effect=_orthogonal_embedding):
            clusters = cluster_queries(spans, cache=cache, threshold=0.80)

        assert len(clusters) == 2, "orthogonal queries in 2 projects → 2 clusters"
        all_task_keys = {c.task_keys[0] for c in clusters}
        assert all_task_keys == {("vibesop", "t1"), ("cmspark", "t1")}

    def test_cluster_id_changes_with_project(self, tmp_path: Path) -> None:
        """Two single-project clusters with same task_id have different IDs."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_orthogonal_embedding):
            clusters_a = cluster_queries(
                [
                    {
                        "task_id": "t1",
                        "input_data": {"query": "hello"},
                        "name": "route:query",
                        "project_id": "vibesop",
                    }
                ],
                cache=cache,
            )
            clusters_b = cluster_queries(
                [
                    {
                        "task_id": "t1",
                        "input_data": {"query": "hello"},
                        "name": "route:query",
                        "project_id": "cmspark",
                    }
                ],
                cache=cache,
            )
        assert clusters_a[0].cluster_id != clusters_b[0].cluster_id

    def test_task_keys_carries_composite_pairs(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "project_id": "vibesop",
            },
            {
                "task_id": "t2",
                "input_data": {"query": "world"},
                "name": "route:query",
                "project_id": "cmspark",
            },
        ]
        with patch.object(cache, "_compute", side_effect=_orthogonal_embedding):
            clusters = cluster_queries(spans, cache=cache, threshold=0.0)

        # threshold=0 merges everything (cosine of orthogonal vectors is 0.0
        # which is >= 0.0), so we expect 1 cluster spanning both projects.
        assert len(clusters) == 1
        cluster = clusters[0]
        assert set(cluster.task_keys) == {("vibesop", "t1"), ("cmspark", "t2")}

    def test_soft_merge_can_still_cross_projects(self, tmp_path: Path) -> None:
        """Soft-merge via cosine still crosses project boundaries for discovery.

        Two spans with similar queries in different projects should still merge
        into one cluster when their cosine ≥ threshold (this is the discovery
        path — cross-project clusters surface heterogeneity via
        ``project_distribution`` rather than being silently split).
        """
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")

        def _same_embedding(_query: str) -> np.ndarray:
            v = np.zeros(384, dtype=np.float32)
            v[0] = 1.0
            return v

        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "fix bug"},
                "name": "route:query",
                "project_id": "vibesop",
            },
            {
                "task_id": "t2",
                "input_data": {"query": "fix issue"},
                "name": "route:query",
                "project_id": "cmspark",
            },
        ]
        with patch.object(cache, "_compute", side_effect=_same_embedding):
            clusters = cluster_queries(spans, cache=cache, threshold=0.80)
        assert len(clusters) == 1, "cosine≥threshold must still merge cross-project"
        assert clusters[0].is_cross_project


class TestProjectDistribution:
    def test_project_distribution_single_project(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "project_id": "vibesop",
            },
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "project_id": "vibesop",
            },
        ]
        with patch.object(cache, "_compute", side_effect=_orthogonal_embedding):
            [cluster] = cluster_queries(spans, cache=cache, threshold=0.80)

        assert cluster.project_distribution == {"vibesop": 2}
        assert not cluster.is_cross_project

    def test_project_distribution_multi_project(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")

        def _same_embedding(_query: str) -> np.ndarray:
            v = np.zeros(384, dtype=np.float32)
            v[0] = 1.0
            return v

        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "fix"},
                "name": "route:query",
                "project_id": "vibesop",
            },
            {
                "task_id": "t1",
                "input_data": {"query": "fix"},
                "name": "route:query",
                "project_id": "vibesop",
            },
            {
                "task_id": "t2",
                "input_data": {"query": "fix-issue"},
                "name": "route:query",
                "project_id": "cmspark",
            },
        ]
        with patch.object(cache, "_compute", side_effect=_same_embedding):
            [cluster] = cluster_queries(spans, cache=cache, threshold=0.80)

        assert cluster.project_distribution == {"vibesop": 2, "cmspark": 1}
        assert cluster.is_cross_project

    def test_is_cross_project_false_when_single_project(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "project_id": "vibesop",
            },
        ]
        with patch.object(cache, "_compute", side_effect=_orthogonal_embedding):
            [cluster] = cluster_queries(spans, cache=cache)

        assert not cluster.is_cross_project


class TestLazyAgeOut:
    def test_cluster_queries_excludes_legacy_by_default(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "project_id": "default",  # pre-W5.0
            },
            {
                "task_id": "t2",
                "input_data": {"query": "world"},
                "name": "route:query",
                "project_id": "vibesop",  # W5.0+
            },
        ]
        with patch.object(cache, "_compute", side_effect=_orthogonal_embedding):
            clusters = cluster_queries(spans, cache=cache, threshold=0.80)

        tids = {c.task_ids[0] for c in clusters}
        assert tids == {"t2"}, "default project_id spans must be excluded by default"

    def test_cluster_queries_includes_legacy_when_flag_set(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "project_id": "default",
            },
            {
                "task_id": "t2",
                "input_data": {"query": "world"},
                "name": "route:query",
                "project_id": "vibesop",
            },
        ]
        with patch.object(cache, "_compute", side_effect=_orthogonal_embedding):
            clusters = cluster_queries(spans, cache=cache, threshold=0.80, include_legacy=True)

        tids = {c.task_ids[0] for c in clusters}
        assert tids == {"t1", "t2"}, "include_legacy=True must keep default-project spans"

    def test_recall_similar_excludes_legacy_by_default(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "project_id": "default",
                "started_at": datetime.now(UTC).isoformat(),
            },
            {
                "task_id": "t2",
                "input_data": {"query": "world"},
                "name": "route:query",
                "project_id": "vibesop",
                "started_at": datetime.now(UTC).isoformat(),
            },
        ]
        with patch.object(cache, "_compute", side_effect=_orthogonal_embedding):
            results = recall_similar("hello", spans, cache=cache, threshold=0.0)
        tids = {r.task_id for r in results}
        assert tids == {"t2"}, "recall must exclude default-project spans by default"

    def test_scan_candidates_excludes_legacy_by_default(self, tmp_path: Path) -> None:
        from vibesop.core.instinct.learner import InstinctLearner
        from vibesop.core.observability.skill_promote import (
            ClusterCandidateStore,
            scan_candidates,
        )

        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        learner = InstinctLearner(storage_path=tmp_path / "instincts.jsonl")
        store = ClusterCandidateStore(storage_dir=tmp_path)
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "project_id": "default",
            }
        ]
        with patch.object(cache, "_compute", side_effect=_orthogonal_embedding):
            summary = scan_candidates(spans, learner, store, cache=cache)
        assert summary.promoted_count == 0
        assert summary.unstable_count == 0


class TestClusterObjectFields:
    def test_cluster_default_task_keys_empty(self) -> None:
        c = Cluster(cluster_id="abc", task_ids=["t1"], span_count=1)
        assert c.task_keys == []
        assert c.project_distribution == {}
        assert not c.is_cross_project

    def test_cluster_is_cross_project_true_with_two_keys(self) -> None:
        c = Cluster(
            cluster_id="abc",
            task_ids=["t1", "t1"],
            span_count=2,
            task_keys=[("vibesop", "t1"), ("cmspark", "t1")],
            project_distribution={"vibesop": 1, "cmspark": 1},
        )
        assert c.is_cross_project
