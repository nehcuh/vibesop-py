"""W5.2 Task 1.2 — scan_candidates propagates project_distribution.

Verifies the field added in Task 1.1 actually gets populated when
``scan_candidates`` constructs candidates from clusters. Without this,
the field would always be empty even for heterogeneous clusters.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.skill_promote import (
    ClusterCandidateStore,
    scan_candidates,
)


def _fake_embedding(query: str) -> np.ndarray:
    """All 'shared-topic' queries collapse to the same vector → cluster."""
    v = np.zeros(384, dtype=np.float32)
    if "shared-topic" in query:
        v[0] = 1.0
    else:
        v[1] = 1.0
    return v


def _span(
    *,
    project_id: str,
    task_id: str,
    query: str,
    name: str = "route:query",
) -> dict:
    return {
        "task_id": task_id,
        "input_data": {"query": query},
        "name": name,
        "project_id": project_id,
        "started_at": datetime(2026, 7, 30, tzinfo=UTC).isoformat(),
    }


@pytest.fixture
def fresh_learner(tmp_path: Path) -> InstinctLearner:
    return InstinctLearner(storage_path=tmp_path / "instincts.json")


@pytest.fixture
def cache(tmp_path: Path) -> EmbeddingCache:
    return EmbeddingCache(cache_path=tmp_path / "emb.npz")


@pytest.fixture
def store(tmp_path: Path) -> ClusterCandidateStore:
    return ClusterCandidateStore(storage_dir=tmp_path / "obs")


class TestPropagatesProjectDistribution:
    def test_scan_candidates_propagates_project_distribution_single_project(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """Single-project cluster → candidate.project_distribution has 1 entry."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cache, "embed", _fake_embedding)
            mp.setattr(cache, "embed_batch", lambda qs: [_fake_embedding(q) for q in qs])

            spans = [
                _span(project_id="/users/me/proj-a", task_id="t1", query="shared-topic foo"),
                _span(project_id="/users/me/proj-a", task_id="t2", query="shared-topic bar"),
                _span(project_id="/users/me/proj-a", task_id="t3", query="shared-topic baz"),
            ]
            # Mark all as gold via learner so the cluster is a stable candidate.
            for s in spans:
                fresh_learner.learn(pattern=s["input_data"]["query"], action="act")
                fresh_learner.record_outcome_for_query(s["input_data"]["query"], success=True)

            scan_candidates(spans, fresh_learner, store, cache=cache)

        rows = store.list_pending()
        assert len(rows) == 1
        candidate = rows[0]
        assert candidate.project_distribution == {"/users/me/proj-a": 3}
        assert candidate.is_cross_project is False

    def test_scan_candidates_propagates_project_distribution_cross_project(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """Cross-project cluster → candidate carries both projects.

        Three task_ids across two projects sharing one topic should
        soft-merge into ONE cluster with project_distribution naming both.
        """
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cache, "embed", _fake_embedding)
            mp.setattr(cache, "embed_batch", lambda qs: [_fake_embedding(q) for q in qs])

            spans = [
                _span(project_id="/users/me/proj-a", task_id="t1", query="shared-topic foo"),
                _span(project_id="/users/me/proj-a", task_id="t2", query="shared-topic bar"),
                _span(project_id="/users/me/proj-b", task_id="t3", query="shared-topic baz"),
            ]
            for s in spans:
                fresh_learner.learn(pattern=s["input_data"]["query"], action="act")
                fresh_learner.record_outcome_for_query(s["input_data"]["query"], success=True)

            scan_candidates(spans, fresh_learner, store, cache=cache)

        rows = store.list_pending()
        assert len(rows) == 1, f"expected 1 cross-project cluster, got {len(rows)}"
        candidate = rows[0]
        # Both projects represented; span_count 2 + 1 = 3
        assert candidate.project_distribution == {
            "/users/me/proj-a": 2,
            "/users/me/proj-b": 1,
        }
        assert candidate.is_cross_project is True
