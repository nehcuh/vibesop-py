"""W4.C — scan_candidates trigger + counter-condition tests.

Verifies the orchestrator correctly classifies clusters into:

- **Stable candidate**: ``span_count >= 3 and gold_rate >= 0.60``
- **Unstable candidate**: ``span_count >= 3 and gold_rate < 0.30``
- **Skip (too small)**: ``span_count < 3``
- **Skip (neutral zone)**: ``0.30 <= gold_rate < 0.60``

Plus: dry-run, idempotent rescan, prune-before-upsert, summary shape.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar
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
        {
            "task_id": tid,
            "input_data": {"query": q},
            "name": name,
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
            summary = scan_candidates(spans, fresh_learner, store, cache=cache, dry_run=True)

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
            "miss_pool_size",
            "miss_admitted_count",
            "miss_rejected_count",
            "unstable_refused_count",
            "stable_refused_count",
            "miss_guard_skipped_count",
            "embedding_degraded",
            "miss_share_by_layer",
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


class TestEmptyTaskKeysGuard:
    """F2: empty ``cluster.task_keys`` must skip the cluster with an ERROR
    log — never an ``assert`` (stripped under ``python -O``), never a
    silently-promoted zero-step shell candidate."""

    def test_empty_task_keys_skips_candidate_and_logs_error(
        self,
        fresh_learner: InstinctLearner,
        cache: EmbeddingCache,
        store: ClusterCandidateStore,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from vibesop.core.observability.clustering import Cluster

        spans = _spans([("t1", "topic-A one")])
        fresh_learner.learn(pattern="topic-A one", action="x")
        fresh_learner.record_outcome_for_query("topic-A one", success=True)

        # Manually-constructed cluster (not from cluster_queries) that
        # would otherwise qualify as a stable candidate.
        rogue = Cluster(
            cluster_id="rogue",
            task_ids=["t1"],
            span_count=3,
            queries=["topic-A one"],
            task_keys=[],  # invariant violated
        )

        with (
            patch(
                "vibesop.core.observability.clustering.cluster_queries",
                return_value=[rogue],
            ),
            caplog.at_level(logging.ERROR, logger="vibesop.core.observability.skill_promote"),
        ):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.promoted_count == 0
        assert summary.unstable_count == 0
        assert store.list_all() == []
        assert any(
            "empty task_keys" in rec.message and rec.levelno == logging.ERROR
            for rec in caplog.records
        )


class TestFirstSeenAt:
    """M12 NIT-B — scan fills ``ClusterCandidate.first_seen_at`` from the
    cluster's earliest span timestamp; rescan keeps the earlier value."""

    @staticmethod
    def _spans_ts(entries: list[tuple[str, str, str]]) -> list[dict]:
        return [
            {
                "task_id": tid,
                "input_data": {"query": q},
                "name": "route:query",
                "project_id": "test",
                "started_at": ts,
            }
            for tid, q, ts in entries
        ]

    @staticmethod
    def _make_gold(learner: InstinctLearner, queries: list[str]) -> None:
        for q in queries:
            learner.learn(pattern=q, action="x")
            learner.record_outcome_for_query(q, success=True)

    @staticmethod
    def _miss_span(task_id: str, query: str, started_at: str) -> dict:
        """One route-miss span in the real producer shape (mirrors
        test_miss_recurrence_admission._miss_span)."""
        return {
            "span_kind": "task",
            "name": f"route:{query}",
            "task_id": task_id,
            "project_id": "test",
            "started_at": started_at,
            "metadata": {"query": query, "mode": "single", "has_match": False},
        }

    def test_first_seen_at_is_earliest_cluster_span(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        spans = self._spans_ts(
            [
                ("t1", "topic-A one", "2026-08-10T00:00:00+00:00"),
                ("t2", "topic-A two", "2026-07-20T12:00:00+00:00"),
                ("t3", "topic-A three", "2026-08-01T00:00:00+00:00"),
            ]
        )
        self._make_gold(fresh_learner, ["topic-A one", "topic-A two", "topic-A three"])

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.promoted_count == 1
        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0].first_seen_at == datetime(2026, 7, 20, 12, 0, tzinfo=UTC)

    def test_first_seen_at_none_when_spans_undated(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """Undated spans contribute nothing — None, display falls back to
        created_at (same tolerance as miss recurrence counting)."""
        spans = _spans(
            [
                ("t1", "topic-A one"),
                ("t2", "topic-A two"),
                ("t3", "topic-A three"),
            ]
        )
        self._make_gold(fresh_learner, ["topic-A one", "topic-A two", "topic-A three"])

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.promoted_count == 1
        assert store.list_pending()[0].first_seen_at is None

    def test_rescan_keeps_earlier_first_seen(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """A rescan over a shorter window (only recent spans) must not push
        the cluster's first-sight forward."""
        old_spans = self._spans_ts(
            [
                ("t1", "topic-A one", "2026-07-20T12:00:00+00:00"),
                ("t2", "topic-A two", "2026-07-21T00:00:00+00:00"),
                ("t3", "topic-A three", "2026-07-22T00:00:00+00:00"),
            ]
        )
        new_spans = self._spans_ts(
            [
                ("t1", "topic-A one", "2026-08-10T00:00:00+00:00"),
                ("t2", "topic-A two", "2026-08-11T00:00:00+00:00"),
                ("t3", "topic-A three", "2026-08-12T00:00:00+00:00"),
            ]
        )
        self._make_gold(fresh_learner, ["topic-A one", "topic-A two", "topic-A three"])

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            scan_candidates(old_spans, fresh_learner, store, cache=cache)
            scan_candidates(new_spans, fresh_learner, store, cache=cache)

        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0].first_seen_at == datetime(2026, 7, 20, 12, 0, tzinfo=UTC)

    def test_miss_recurrence_path_fills_first_seen_at(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """gate23 pi#2: the miss_recurrence construction site is covered
        too — first_seen_at comes from the admitted cluster's earliest
        span, same as the gold path. 3 distinct (task_id, day) pairs
        across 2 natural days clears the M2 admission gate."""
        spans = [
            self._miss_span("k1", "miss-topic one", "2026-08-01T10:00:00+00:00"),
            self._miss_span("k2", "miss-topic two", "2026-08-01T22:30:00+00:00"),
            self._miss_span("k3", "miss-topic three", "2026-08-02T09:15:00+00:00"),
        ]

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_admitted_count == 1
        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0].source == "miss_recurrence"
        assert pending[0].first_seen_at == datetime(2026, 8, 1, 10, 0, tzinfo=UTC)


class TestBehaviorEvidence:
    """M3 — scan fills behavior_evidence / behavior_score on candidates
    (three-state semantics; rescan overwrites with the latest value)."""

    @staticmethod
    def _spans_with_tools(
        task_queries: list[tuple[str, str]], tool_seqs: dict[str, list[str]]
    ) -> list[dict]:
        """Route spans (one trace per task) + per-trace tool_call spans.

        Tool spans deliberately carry NO project_id (pre-W5.0 producer
        shape) — the behavior join must still find them via the parent
        route span (behavior_spans is captured before the age-out filter).
        """
        spans: list[dict] = []
        for i, (tid, query) in enumerate(task_queries):
            spans.append(
                {
                    "id": f"r{i}",
                    "task_id": tid,
                    "input_data": {"query": query},
                    "name": "route:query",
                    "project_id": "test",
                    "trace_id": f"tr{i}",
                    "started_at": f"2026-08-{10 + i:02d}T00:00:00+00:00",
                }
            )
            for j, tool in enumerate(tool_seqs.get(tid, [])):
                spans.append(
                    {
                        "id": f"t{i}_{j}",
                        "name": f"tool:{tool}",
                        "span_kind": "tool_call",
                        "trace_id": f"tr{i}",
                        "parent_span_id": f"r{i}",
                        "started_at": f"2026-08-{10 + i:02d}T00:{j + 1:02d}:00+00:00",
                    }
                )
        return spans

    @staticmethod
    def _make_gold(learner: InstinctLearner, queries: list[str]) -> None:
        for q in queries:
            learner.learn(pattern=q, action="x")
            learner.record_outcome_for_query(q, success=True)

    _TASKS: ClassVar = [("t1", "topic-A one"), ("t2", "topic-A two"), ("t3", "topic-A three")]

    def test_consistent_filled_on_gold_path(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        same = ["Read", "Grep", "Read"]
        spans = self._spans_with_tools(self._TASKS, {"t1": same, "t2": same, "t3": list(same)})
        self._make_gold(fresh_learner, [q for _t, q in self._TASKS])

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.promoted_count == 1
        pending = store.list_pending()
        assert pending[0].behavior_evidence == "consistent"
        assert pending[0].behavior_score == 1.0

    def test_unavailable_filled_when_no_tool_spans(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        spans = _spans(self._TASKS)  # route spans only — no hook data
        self._make_gold(fresh_learner, [q for _t, q in self._TASKS])

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.promoted_count == 1
        pending = store.list_pending()
        assert pending[0].behavior_evidence == "unavailable"
        assert pending[0].behavior_score is None

    def test_rescan_overwrites_with_latest_behavior(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """Unlike first_seen_at (earliest-wins), behavior evidence follows
        data freshness: a rescan computes from the current spans and the
        whole-row upsert refresh installs the new verdict."""
        same = ["Read", "Grep", "Read"]
        first = self._spans_with_tools(self._TASKS, {"t1": same, "t2": same, "t3": list(same)})
        divergent = self._spans_with_tools(
            self._TASKS, {"t1": ["Read", "Grep"], "t2": ["Bash", "Write"], "t3": ["Agent", "Glob"]}
        )
        self._make_gold(fresh_learner, [q for _t, q in self._TASKS])

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            scan_candidates(first, fresh_learner, store, cache=cache)
            assert store.list_pending()[0].behavior_evidence == "consistent"
            scan_candidates(divergent, fresh_learner, store, cache=cache)

        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0].behavior_evidence == "divergent"
        assert pending[0].behavior_score == 0.0


class TestBehaviorEvidenceMissPath:
    """gate24 pi#9c — the miss_recurrence construction site fills behavior
    fields too (same helper, same spans)."""

    @staticmethod
    def _miss_span(task_id: str, query: str, started_at: str, trace: str, rid: str) -> dict:
        return {
            "id": rid,
            "span_kind": "task",
            "name": f"route:{query}",
            "task_id": task_id,
            "project_id": "test",
            "trace_id": trace,
            "started_at": started_at,
            "metadata": {"query": query, "mode": "single", "has_match": False},
        }

    @staticmethod
    def _tool(sid: str, trace: str, parent: str, name: str, ts: str) -> dict:
        return {
            "id": sid,
            "name": f"tool:{name}",
            "span_kind": "tool_call",
            "trace_id": trace,
            "parent_span_id": parent,
            "started_at": ts,
        }

    def test_miss_recurrence_candidate_gets_behavior_evidence(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        # 3 distinct (task_id, day) pairs across 2 days → admitted; two of
        # the traces carry identical tool sequences → consistent.
        spans = [
            self._miss_span("k1", "miss-topic one", "2026-08-01T10:00:00+00:00", "tr1", "r1"),
            self._miss_span("k2", "miss-topic two", "2026-08-01T22:30:00+00:00", "tr2", "r2"),
            self._miss_span("k3", "miss-topic three", "2026-08-02T09:15:00+00:00", "tr3", "r3"),
            self._tool("t1", "tr1", "r1", "Read", "2026-08-01T10:01:00+00:00"),
            self._tool("t2", "tr1", "r1", "Grep", "2026-08-01T10:02:00+00:00"),
            self._tool("t3", "tr2", "r2", "Read", "2026-08-01T22:31:00+00:00"),
            self._tool("t4", "tr2", "r2", "Grep", "2026-08-01T22:32:00+00:00"),
        ]

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_admitted_count == 1
        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0].source == "miss_recurrence"
        assert pending[0].behavior_evidence == "consistent"
        assert pending[0].behavior_score == 1.0
