"""W1 Task C — gold standard detection.

Contract (per v3 design §3 W1 Task C):
1. Primary signal: ``InstinctLearner.record_outcome(success=True)`` for
   any task_id in a cluster → cluster is gold-eligible.
2. Cluster size gate: ``span_count >= 5`` required for full gold status;
   smaller clusters with success signal → ``candidate`` (provisional).
3. Clusters with no success signal remain non-gold.
4. ``gold_rate`` = fraction of member task_ids whose instinct has
   ``success_count >= 1``. Used by W4 skill promote trigger.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.observability.clustering import cluster_queries
from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.gold_detection import assess_gold_status


def _fake_embedding(query: str) -> np.ndarray:
    h = hash(query) & 0xFFFFFFFF
    rng = np.random.default_rng(h)
    return rng.standard_normal(384).astype(np.float32)


def _spans(task_id_queries: list[tuple[str, str]]) -> list[dict]:
    return [
        {
            "task_id": tid,
            "input_data": {"query": q},
            "name": "route:query",
            "project_id": "test",
        }
        for tid, q in task_id_queries
    ]


@pytest.fixture
def fresh_learner(tmp_path: Path) -> InstinctLearner:
    return InstinctLearner(storage_path=tmp_path / "instincts.json")


@pytest.fixture
def cache(tmp_path: Path) -> EmbeddingCache:
    return EmbeddingCache(cache_path=tmp_path / "emb.npz")


class TestGoldDetection:
    def test_cluster_with_success_becomes_gold(self, fresh_learner: InstinctLearner, cache: EmbeddingCache) -> None:
        """Cluster with >=5 spans AND success outcome → is_gold=True."""
        fresh_learner.learn(
            pattern="screenshot permission popup",
            action="check privacy settings",
        )
        fresh_learner.record_outcome_for_query("screenshot permission popup", success=True)

        spans = _spans(
            [("t1", "screenshot permission popup")] * 5
            + [("t1", "screenshot permission popup")]  # 6 total spans, same task_id
        )
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            clusters = cluster_queries(spans, cache=cache)
        assert len(clusters) == 1
        assert clusters[0].span_count >= 5

        [enriched] = assess_gold_status(clusters, fresh_learner)
        assert enriched.is_gold is True
        assert enriched.is_candidate is False

    def test_small_cluster_with_success_is_candidate(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache
    ) -> None:
        """Cluster with <5 spans but success signal → candidate, not gold."""
        fresh_learner.learn(pattern="hello", action="greet")
        fresh_learner.record_outcome_for_query("hello", success=True)

        spans = _spans([("t1", "hello"), ("t1", "hello")])  # only 2 spans
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            clusters = cluster_queries(spans, cache=cache)
        [enriched] = assess_gold_status(clusters, fresh_learner)
        assert enriched.is_gold is False
        assert enriched.is_candidate is True

    def test_cluster_without_success_stays_neutral(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache
    ) -> None:
        """Cluster with no instinct success signal → not gold, not candidate."""
        spans = _spans([("t1", "hello")] * 6)
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            clusters = cluster_queries(spans, cache=cache)
        [enriched] = assess_gold_status(clusters, fresh_learner)
        assert enriched.is_gold is False
        assert enriched.is_candidate is False

    def test_failed_outcome_does_not_make_gold(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache
    ) -> None:
        """record_outcome(success=False) should NOT trigger gold."""
        fresh_learner.learn(pattern="broken thing", action="try X")
        fresh_learner.record_outcome_for_query("broken thing", success=False)

        spans = _spans([("t1", "broken thing")] * 5)
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            clusters = cluster_queries(spans, cache=cache)
        [enriched] = assess_gold_status(clusters, fresh_learner)
        assert enriched.is_gold is False
        assert enriched.is_candidate is False


class TestGoldRate:
    def test_gold_rate_reflects_member_success(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache
    ) -> None:
        """Gold rate = fraction of member task_ids with success_count>=1."""
        fresh_learner.learn(pattern="q1", action="a1")
        fresh_learner.record_outcome_for_query("q1", success=True)

        # t1 has success, t2 doesn't
        spans = _spans([("t1", "q1"), ("t2", "q2")])
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            clusters = cluster_queries(spans, cache=cache)
        # May be 1 or 2 clusters depending on cosine; either way gold_rate
        # only counts members with success
        enriched = assess_gold_status(clusters, fresh_learner)
        for c in enriched:
            if "t1" in c.task_ids:
                # t1 has success; if t2 merges in, gold_rate = 0.5;
                # if t1 alone, gold_rate = 1.0
                assert c.gold_rate >= 0.5

    def test_gold_rate_zero_when_no_success(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache
    ) -> None:
        spans = _spans([("t1", "hello"), ("t2", "world")])
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            clusters = cluster_queries(spans, cache=cache)
        enriched = assess_gold_status(clusters, fresh_learner)
        assert all(c.gold_rate == 0.0 for c in enriched)


class TestMinClusterSizeConfig:
    def test_custom_min_cluster_size(self, fresh_learner: InstinctLearner, cache: EmbeddingCache) -> None:
        fresh_learner.learn(pattern="hello", action="greet")
        fresh_learner.record_outcome_for_query("hello", success=True)

        spans = _spans([("t1", "hello"), ("t1", "hello"), ("t1", "hello")])  # 3 spans
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            clusters = cluster_queries(spans, cache=cache)

        # Default min=5 → 3 spans = candidate
        [default_enriched] = assess_gold_status(clusters, fresh_learner)
        assert default_enriched.is_candidate is True

        # min=3 → 3 spans = gold
        [strict_enriched] = assess_gold_status(clusters, fresh_learner, min_cluster_size=3)
        assert strict_enriched.is_gold is True


class TestEmptyInput:
    def test_empty_clusters_returns_empty(self, fresh_learner: InstinctLearner) -> None:
        result = assess_gold_status([], fresh_learner)
        assert result == []
