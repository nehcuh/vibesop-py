"""W4.C — scan_candidates trigger + counter-condition tests.

Verifies the orchestrator correctly classifies clusters into:

- **Stable candidate**: ``span_count >= 3 and gold_rate >= 0.60``
- **Unstable candidate**: ``span_count >= 3 and gold_rate < 0.30``
- **Skip (too small)**: ``span_count < 3``
- **Skip (neutral zone)**: ``0.30 <= gold_rate < 0.60``

Plus: dry-run, idempotent rescan, prune-before-upsert, summary shape.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.skill_promote import (
    ClusterCandidateStore,
    scan_candidates,
)


def _fake_embedding(query: str) -> np.ndarray:
    """All "test-topic" queries collapse to the same vector so they
    cluster. Other queries get a deterministic different vector.
    """
    v = np.zeros(384, dtype=np.float32)
    if "topic-A" in query:
        v[0] = 1.0
    elif "topic-B" in query:
        v[1] = 1.0
    else:
        v[0] = 0.5
    return v


def _spans(task_id_queries: list[tuple[str, str]], *, name: str = "route:query") -> list[dict]:
    return [
        {"task_id": tid, "input_data": {"query": q}, "name": name}
        for tid, q in task_id_queries
    ]


@pytest.fixture
def fresh_learner(tmp_path: Path) -> InstinctLearner:
    return InstinctLearner(storage_path=tmp_path / "instincts.json")


@pytest.fixture
def cache(tmp_path: Path) -> EmbeddingCache:
    return EmbeddingCache(cache_path=tmp_path / "emb.npz")


@pytest.fixture
def store(tmp_path: Path) -> ClusterCandidateStore:
    return ClusterCandidateStore(storage_dir=tmp_path / "obs")


class TestTriggerStable:
    def test_trigger_fires_when_size_3_and_gold_rate_60(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """3 task_ids, 2 of them gold (gold_rate=2/3≈0.67 >= 0.60) →
        one stable candidate upserted."""
        # 3 distinct task_ids, all "topic-A" so they soft-merge.
        # Spans: 1 per task_id → span_count = 3.
        spans = _spans(
            [
                ("t1", "topic-A query one"),
                ("t2", "topic-A query two"),
                ("t3", "topic-A query three"),
            ]
        )
        # 2 of 3 task_ids have instinct success → gold_rate = 2/3.
        fresh_learner.learn(pattern="topic-A query one", action="act-1")
        fresh_learner.record_outcome_for_query("topic-A query one", success=True)
        fresh_learner.learn(pattern="topic-A query two", action="act-2")
        fresh_learner.record_outcome_for_query("topic-A query two", success=True)

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.promoted_count == 1
        assert summary.unstable_count == 0
        assert summary.pruned_count == 0
        assert summary.capped is False
        assert summary.clusters_seen == 1
        assert store.pending_count() == 1

        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0].is_unstable is False
        assert pending[0].gold_rate >= 0.60
        assert pending[0].span_count >= 3


class TestTriggerSizeGate:
    def test_no_trigger_below_size_3(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """2 spans, both gold (gold_rate=1.0) but size < 3 → skip."""
        spans = _spans(
            [
                ("t1", "topic-A one"),
                ("t2", "topic-A two"),
            ]
        )
        fresh_learner.learn(pattern="topic-A one", action="x")
        fresh_learner.record_outcome_for_query("topic-A one", success=True)
        fresh_learner.learn(pattern="topic-A two", action="y")
        fresh_learner.record_outcome_for_query("topic-A two", success=True)

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.promoted_count == 0
        assert summary.unstable_count == 0
        assert summary.clusters_seen == 1
        assert store.pending_count() == 0


class TestNeutralZone:
    def test_no_trigger_in_neutral_zone_50pct(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """gold_rate between 0.30 and 0.60 → neutral zone, skip.

        4 task_ids, 2 gold (50%) — not stable (need >= 60%) and not
        unstable (need < 30%). Silent skip.
        """
        spans = _spans(
            [
                ("t1", "topic-A one"),
                ("t2", "topic-A two"),
                ("t3", "topic-A three"),
                ("t4", "topic-A four"),
            ]
        )
        fresh_learner.learn(pattern="topic-A one", action="x")
        fresh_learner.record_outcome_for_query("topic-A one", success=True)
        fresh_learner.learn(pattern="topic-A two", action="y")
        fresh_learner.record_outcome_for_query("topic-A two", success=True)

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.promoted_count == 0
        assert summary.unstable_count == 0
        assert summary.clusters_seen == 1
        assert store.pending_count() == 0


class TestUnstableBucket:
    def test_unstable_bucket_when_gold_rate_below_30(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """4 task_ids, 1 gold (25%) → unstable candidate."""
        spans = _spans(
            [
                ("t1", "topic-A one"),
                ("t2", "topic-A two"),
                ("t3", "topic-A three"),
                ("t4", "topic-A four"),
            ]
        )
        fresh_learner.learn(pattern="topic-A one", action="x")
        fresh_learner.record_outcome_for_query("topic-A one", success=True)

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.promoted_count == 0
        assert summary.unstable_count == 1
        # pending_count defaults to stable-only (grok+pi P1) — the
        # unstable row doesn't count toward the kill-switch backlog.
        # Use include_unstable=True to count it.
        assert store.pending_count() == 0
        assert store.pending_count(include_unstable=True) == 1

        unstable = store.list_unstable()
        assert len(unstable) == 1
        assert unstable[0].is_unstable is True
        assert unstable[0].gold_rate < 0.30


class TestDryRun:
    def test_dry_run_does_not_write(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """``dry_run=True`` classifies but does not modify the store."""
        spans = _spans(
            [
                ("t1", "topic-A one"),
                ("t2", "topic-A two"),
                ("t3", "topic-A three"),
            ]
        )
        fresh_learner.learn(pattern="topic-A one", action="x")
        fresh_learner.record_outcome_for_query("topic-A one", success=True)
        fresh_learner.learn(pattern="topic-A two", action="y")
        fresh_learner.record_outcome_for_query("topic-A two", success=True)

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(
                spans, fresh_learner, store, cache=cache, dry_run=True
            )

        # Classification happened.
        assert summary.promoted_count == 1
        # But store is untouched.
        assert store.pending_count() == 0
        assert summary.pruned_count == 0  # dry_run also skips prune


class TestIdempotentRescan:
    def test_rescan_idempotent_no_duplicate_rows(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """Scanning the same spans twice produces ONE row, not two."""
        spans = _spans(
            [
                ("t1", "topic-A one"),
                ("t2", "topic-A two"),
                ("t3", "topic-A three"),
            ]
        )
        fresh_learner.learn(pattern="topic-A one", action="x")
        fresh_learner.record_outcome_for_query("topic-A one", success=True)
        fresh_learner.learn(pattern="topic-A two", action="y")
        fresh_learner.record_outcome_for_query("topic-A two", success=True)

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            scan_candidates(spans, fresh_learner, store, cache=cache)
            scan_candidates(spans, fresh_learner, store, cache=cache)
            scan_candidates(spans, fresh_learner, store, cache=cache)

        assert store.pending_count() == 1
        rows = store.list_all()
        assert len(rows) == 1


class TestPruneBeforeUpsert:
    def test_prune_runs_before_upsert(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """``scan_candidates`` prunes TTL-expired rows BEFORE upserting
        new candidates. Verifies the documented pipeline order."""
        # Pre-populate one expired row manually.
        from vibesop.core.observability.skill_promote import ClusterCandidate

        expired = ClusterCandidate(
            cluster_id="expired_static",
            task_ids=["old1"],
            queries=["old query"],
            span_count=10,
            gold_rate=0.8,
            gold_task_ids=["old1"],
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            ttl_expires_at=datetime(2026, 1, 31, tzinfo=UTC),
        )
        store.upsert(expired)

        # New spans that would form a fresh candidate.
        spans = _spans(
            [
                ("t1", "topic-A one"),
                ("t2", "topic-A two"),
                ("t3", "topic-A three"),
            ]
        )
        fresh_learner.learn(pattern="topic-A one", action="x")
        fresh_learner.record_outcome_for_query("topic-A one", success=True)
        fresh_learner.learn(pattern="topic-A two", action="y")
        fresh_learner.record_outcome_for_query("topic-A two", success=True)

        # Patch _now_utc to a date AFTER the expired TTL.
        from vibesop.core.observability import skill_promote as sp_module

        future_now = datetime(2026, 7, 29, tzinfo=UTC)
        with (
            patch.object(cache, "_compute", side_effect=_fake_embedding),
            patch.object(sp_module, "_now_utc", return_value=future_now),
        ):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.pruned_count == 1, "expired row should be pruned"
        assert summary.promoted_count == 1
        assert store.get("expired_static") is None
        assert store.pending_count() == 1  # only the new candidate


class TestSummaryShape:
    def test_scan_returns_summary_dict(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """``ScanSummary`` has the documented fields with correct types.

        Uses a 2/3 gold_rate setup (stable candidate) so the summary
        carries non-zero values to verify type as well as presence.
        """
        spans = _spans(
            [
                ("t1", "topic-A one"),
                ("t2", "topic-A two"),
                ("t3", "topic-A three"),
            ]
        )
        fresh_learner.learn(pattern="topic-A one", action="x")
        fresh_learner.record_outcome_for_query("topic-A one", success=True)
        fresh_learner.learn(pattern="topic-A two", action="y")
        fresh_learner.record_outcome_for_query("topic-A two", success=True)

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        d = asdict(summary)
        assert set(d.keys()) == {
            "promoted_count",
            "unstable_count",
            "pruned_count",
            "capped",
            "clusters_seen",
        }
        assert d["promoted_count"] == 1
        assert d["unstable_count"] == 0
        assert d["pruned_count"] == 0
        assert d["capped"] is False
        assert d["clusters_seen"] == 1
        assert isinstance(d["promoted_count"], int)
        assert isinstance(d["unstable_count"], int)
        assert isinstance(d["pruned_count"], int)
        assert isinstance(d["capped"], bool)
        assert isinstance(d["clusters_seen"], int)
