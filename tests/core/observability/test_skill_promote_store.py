"""W4.A — ClusterCandidate + ClusterCandidateStore tests.

Verifies the persistence layer for the skill-promote pipeline:

1. Round-trip: ``from_dict(to_dict()) == original``.
2. Upsert idempotency on ``cluster_id``:
   - New row → append.
   - Existing pending → refresh counts, preserve created_at + ttl.
   - Existing promoted/dismissed → no-op (terminal sticky).
3. Hard cap eviction: at ``MAX_PENDING`` + 1, drop lowest gold_rate.
4. TTL prune: delete expired pending; keep terminal + unexpired.
5. State transitions: promote / dismiss flip status + set fields.
6. list_unstable filters by ``is_unstable`` flag.

Pattern mirrors ``test_reflection_store.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from vibesop.core.observability.skill_promote import (
    MAX_PENDING,
    ClusterCandidate,
    ClusterCandidateStore,
)


def _make_candidate(
    *,
    cluster_id: str = "c1",
    task_ids: list[str] | None = None,
    queries: list[str] | None = None,
    span_count: int = 5,
    gold_rate: float = 0.8,
    gold_task_ids: list[str] | None = None,
    is_unstable: bool = False,
    created_at: datetime | None = None,
    ttl_expires_at: datetime | None = None,
    status: str = "pending",
) -> ClusterCandidate:
    return ClusterCandidate(
        cluster_id=cluster_id,
        task_ids=task_ids or ["t1", "t2"],
        queries=queries or ["hello world", "hi world"],
        span_count=span_count,
        gold_rate=gold_rate,
        gold_task_ids=gold_task_ids or ["t1"],
        created_at=created_at or datetime(2026, 7, 1, tzinfo=UTC),
        ttl_expires_at=ttl_expires_at,
        is_unstable=is_unstable,
        status=status,  # type: ignore[arg-type]
    )


class TestRoundTrip:
    def test_round_trip_to_dict_from_dict(self) -> None:
        """ClusterCandidate survives to_dict → from_dict with every field."""
        c = _make_candidate(
            cluster_id="abc123",
            task_ids=["t1", "t2"],
            queries=["q1", "q2"],
            span_count=7,
            gold_rate=0.85,
            gold_task_ids=["t1"],
            is_unstable=False,
        )
        c.step_freq = {"route:query": 7, "tool:edit": 5}
        c.step_labels = {"route:query": "core", "tool:edit": "common"}
        c.core_steps = ["route:query"]
        c.dismiss_reason = None
        c.source_skill_id = None
        c.reviewed_at = None

        round_tripped = ClusterCandidate.from_dict(c.to_dict())
        assert round_tripped == c


class TestUpsert:
    def test_upsert_new_inserts(self, tmp_path: Path) -> None:
        """A new cluster_id appends a row; pending_count increments."""
        store = ClusterCandidateStore(storage_dir=tmp_path)
        assert store.pending_count() == 0

        store.upsert(_make_candidate(cluster_id="c1"))
        assert store.pending_count() == 1

        store.upsert(_make_candidate(cluster_id="c2"))
        assert store.pending_count() == 2

    def test_upsert_existing_pending_refreshes_counts_preserves_created_at(
        self, tmp_path: Path
    ) -> None:
        """Re-upserting a pending cluster_id updates mutable signal
        (span_count, gold_rate, step_freq) but does NOT reset
        ``created_at`` or ``ttl_expires_at`` (TTL must not slide)."""
        store = ClusterCandidateStore(storage_dir=tmp_path)
        original_created = datetime(2026, 7, 1, tzinfo=UTC)
        original_ttl = datetime(2026, 7, 31, tzinfo=UTC)
        first = _make_candidate(
            cluster_id="c1",
            span_count=3,
            gold_rate=0.5,
            created_at=original_created,
            ttl_expires_at=original_ttl,
        )
        store.upsert(first)

        # Rescan sees more data — span_count + gold_rate climb.
        refreshed = _make_candidate(
            cluster_id="c1",
            span_count=10,
            gold_rate=0.9,
            created_at=datetime(2026, 8, 1, tzinfo=UTC),  # later
            ttl_expires_at=datetime(2026, 9, 1, tzinfo=UTC),  # later
        )
        store.upsert(refreshed)

        stored = store.get("c1")
        assert stored is not None
        assert stored.span_count == 10
        assert stored.gold_rate == 0.9
        # Preserved from first insert, NOT overwritten by refreshed.
        assert stored.created_at == original_created
        assert stored.ttl_expires_at == original_ttl

    def test_upsert_terminal_state_is_noop(self, tmp_path: Path) -> None:
        """A promoted/dismissed row is sticky — re-scan does NOT
        overwrite the human decision with fresh signal."""
        store = ClusterCandidateStore(storage_dir=tmp_path)
        store.upsert(_make_candidate(cluster_id="c1", span_count=5))
        store.promote("c1", "skill-abc")
        promoted = store.get("c1")
        assert promoted is not None
        assert promoted.status == "promoted"
        assert promoted.source_skill_id == "skill-abc"

        # Rescan sees the same cluster_id with different counts — MUST
        # NOT overwrite the promoted row.
        store.upsert(
            _make_candidate(cluster_id="c1", span_count=99, gold_rate=0.99)
        )
        still_promoted = store.get("c1")
        assert still_promoted is not None
        assert still_promoted.status == "promoted"
        assert still_promoted.source_skill_id == "skill-abc"
        assert still_promoted.span_count == 5  # unchanged

    def test_upsert_idempotent_no_duplicate_rows(self, tmp_path: Path) -> None:
        """Re-upserting the same cluster_id does not create a duplicate
        line in the JSONL file."""
        store = ClusterCandidateStore(storage_dir=tmp_path)
        cand = _make_candidate(cluster_id="c1")
        store.upsert(cand)
        store.upsert(cand)
        store.upsert(cand)
        all_rows = store.list_all()
        assert len(all_rows) == 1


class TestHardCap:
    def test_hard_cap_evicts_lowest_gold_rate(self, tmp_path: Path) -> None:
        """At MAX_PENDING+1 new insert, the lowest-gold_rate pending row
        is evicted (FIFO tiebreak).

        Verifies the documented eviction policy: silent drop of the
        weakest signal. Reviewer Q4 may challenge this — the alternative
        is to block the scan with a "review your backlog" warning.
        """
        store = ClusterCandidateStore(storage_dir=tmp_path)
        # Fill to MAX_PENDING with strictly increasing gold_rate.
        # Span_count also strictly increasing so min-by-(gold_rate,
        # created_at) selects cluster c0 unambiguously.
        for i in range(MAX_PENDING):
            store.upsert(
                _make_candidate(
                    cluster_id=f"c{i}",
                    gold_rate=0.10 + i * 0.01,
                    span_count=10 + i,
                    created_at=datetime(2026, 1, 1, tzinfo=UTC)
                    + timedelta(hours=i),
                )
            )
        assert store.pending_count() == MAX_PENDING

        # Insert one more — c0 (lowest gold_rate=0.10) should be evicted.
        store.upsert(
            _make_candidate(
                cluster_id="c_new",
                gold_rate=0.95,
                span_count=100,
            )
        )
        assert store.pending_count() == MAX_PENDING  # still capped
        assert store.get("c0") is None, "lowest gold_rate row should be evicted"
        assert store.get("c_new") is not None

    def test_hard_cap_rejects_new_row_below_min(
        self, tmp_path: Path, caplog
    ) -> None:
        """Admit-only-if-better: a new row whose gold_rate doesn't beat
        the current minimum is REJECTED, not inserted.

        Grok P1 + pi P0 on W4 review: prior version always evicted
        lowest then appended — an unstable new arrival (rate≈0.15)
        could displace a stable pending row (rate≈0.65). The new policy
        refuses to displace better rows with worse ones.
        """
        import logging

        store = ClusterCandidateStore(storage_dir=tmp_path)
        # Fill to MAX_PENDING with rates 0.50 → 0.99.
        for i in range(MAX_PENDING):
            store.upsert(
                _make_candidate(
                    cluster_id=f"c{i}",
                    gold_rate=0.50 + i * 0.01,
                    span_count=10 + i,
                    created_at=datetime(2026, 1, 1, tzinfo=UTC)
                    + timedelta(hours=i),
                )
            )
        assert store.pending_count() == MAX_PENDING

        # Try to insert a new row with gold_rate BELOW current min (0.50).
        with caplog.at_level(logging.WARNING):
            store.upsert(
                _make_candidate(
                    cluster_id="c_worse",
                    gold_rate=0.10,  # well below min
                    span_count=5,
                )
            )

        assert store.pending_count() == MAX_PENDING
        assert store.get("c_worse") is None, (
            "admit-only-if-better: worse new row must NOT be inserted"
        )
        # Eviction was logged at WARNING (pi P0: cron visibility).
        assert any(
            "rejecting new cluster c_worse" in rec.message for rec in caplog.records
        ), f"expected rejection log; got: {[r.message for r in caplog.records]}"

    def test_hard_cap_admits_better_unstable_displacing_unstable(
        self, tmp_path: Path
    ) -> None:
        """At cap, a new unstable row can displace an existing unstable
        row if its gold_rate is higher. But it cannot displace a stable
        row (admit-only-if-better compares against the minimum)."""
        store = ClusterCandidateStore(storage_dir=tmp_path)
        # Fill to MAX_PENDING with a mix: 49 stable + 1 unstable (min).
        for i in range(MAX_PENDING - 1):
            store.upsert(
                _make_candidate(
                    cluster_id=f"stable{i}",
                    gold_rate=0.60 + i * 0.005,
                    is_unstable=False,
                )
            )
        store.upsert(
            _make_candidate(
                cluster_id="worst_unstable",
                gold_rate=0.20,
                is_unstable=True,
            )
        )
        assert store.pending_count(include_unstable=True) == MAX_PENDING

        # New unstable with higher rate than the worst — should displace.
        store.upsert(
            _make_candidate(
                cluster_id="new_unstable",
                gold_rate=0.25,
                is_unstable=True,
            )
        )
        assert store.get("worst_unstable") is None, (
            "new unstable (0.25) should displace worst unstable (0.20)"
        )
        assert store.get("new_unstable") is not None
        # Stable rows untouched.
        assert store.get("stable0") is not None


class TestTzNaiveDatetime:
    """P1-7: tz-naive datetimes in stored JSON must not crash prune_expired."""

    def test_from_dict_attaches_utc_to_naive_datetimes(self) -> None:
        """Hand-edited ISO strings without offset get UTC attached."""
        naive_payload = {
            "cluster_id": "c1",
            "task_ids": ["t1"],
            "queries": ["q"],
            "span_count": 5,
            "gold_rate": 0.8,
            "gold_task_ids": ["t1"],
            "created_at": "2026-06-01T00:00:00",  # naive
            "ttl_expires_at": "2026-06-30T00:00:00",  # naive
            "reviewed_at": None,
            "step_freq": {},
            "step_labels": {},
            "core_steps": [],
            "status": "pending",
            "is_unstable": False,
            "source_skill_id": None,
            "dismiss_reason": None,
        }
        c = ClusterCandidate.from_dict(naive_payload)
        assert c.created_at.tzinfo is not None, "naive dt must get UTC attached"
        assert c.ttl_expires_at is not None
        assert c.ttl_expires_at.tzinfo is not None

    def test_prune_expired_does_not_crash_on_naive_ttl(self, tmp_path: Path) -> None:
        """A single row with naive ttl_expires_at must not crash the
        whole prune pass (grok P1: TypeError on aware-vs-naive compare).
        """
        store = ClusterCandidateStore(storage_dir=tmp_path)
        # Hand-write a JSONL line with naive ttl_expires_at.
        store._path.parent.mkdir(parents=True, exist_ok=True)
        store._path.write_text(
            '{"cluster_id":"c1","task_ids":["t1"],"queries":["q"],'
            '"span_count":5,"gold_rate":0.8,"gold_task_ids":["t1"],'
            '"created_at":"2026-06-01T00:00:00",'
            '"ttl_expires_at":"2026-06-30T00:00:00",'
            '"reviewed_at":null,"step_freq":{},'
            '"step_labels":{},"core_steps":[],'
            '"status":"pending","is_unstable":false,'
            '"source_skill_id":null,"dismiss_reason":null}\n',
            encoding="utf-8",
        )

        # Pruning at a date past the TTL should remove the row without
        # raising TypeError.
        pruned = store.prune_expired(now=datetime(2026, 7, 31, tzinfo=UTC))
        assert pruned == 1
        assert store.get("c1") is None


class TestPruneExpired:
    def test_prune_expired_removes_only_pending_past_ttl(
        self, tmp_path: Path
    ) -> None:
        """TTL-expired pending rows are pruned. Promoted / dismissed
        rows survive even if their TTL has passed — terminal states are
        audit records, not backlog."""
        store = ClusterCandidateStore(storage_dir=tmp_path)
        now = datetime(2026, 7, 31, tzinfo=UTC)

        # 1) Pending + TTL expired → pruned.
        store.upsert(
            _make_candidate(
                cluster_id="expired_pending",
                created_at=datetime(2026, 6, 1, tzinfo=UTC),
                ttl_expires_at=datetime(2026, 6, 30, tzinfo=UTC),
            )
        )
        # 2) Pending + TTL not expired → kept.
        store.upsert(
            _make_candidate(
                cluster_id="fresh_pending",
                created_at=now - timedelta(days=1),
                ttl_expires_at=now + timedelta(days=29),
            )
        )
        # 3) Promoted + TTL expired → kept (audit).
        store.upsert(
            _make_candidate(
                cluster_id="expired_promoted",
                created_at=datetime(2026, 6, 1, tzinfo=UTC),
                ttl_expires_at=datetime(2026, 6, 30, tzinfo=UTC),
            )
        )
        store.promote("expired_promoted", "skill-x")
        # 4) Dismissed + TTL expired → kept (audit).
        store.upsert(
            _make_candidate(
                cluster_id="expired_dismissed",
                created_at=datetime(2026, 6, 1, tzinfo=UTC),
                ttl_expires_at=datetime(2026, 6, 30, tzinfo=UTC),
            )
        )
        store.dismiss("expired_dismissed", reason="noise")

        pruned = store.prune_expired(now=now)
        assert pruned == 1, "only expired_pending should be pruned"
        assert store.get("expired_pending") is None
        assert store.get("fresh_pending") is not None
        assert store.get("expired_promoted") is not None
        assert store.get("expired_dismissed") is not None


class TestTransitions:
    def test_promote_flips_status_sets_skill_id(self, tmp_path: Path) -> None:
        """promote() sets status=promoted, source_skill_id, reviewed_at."""
        store = ClusterCandidateStore(storage_dir=tmp_path)
        store.upsert(_make_candidate(cluster_id="c1"))

        before = datetime.now(UTC)
        result = store.promote("c1", "my-skill-id")
        after = datetime.now(UTC)

        assert result is not None
        assert result.status == "promoted"
        assert result.source_skill_id == "my-skill-id"
        assert result.reviewed_at is not None
        assert before <= result.reviewed_at <= after

        stored = store.get("c1")
        assert stored is not None
        assert stored.status == "promoted"

    def test_dismiss_records_reason(self, tmp_path: Path) -> None:
        """dismiss() sets status=dismissed + dismiss_reason."""
        store = ClusterCandidateStore(storage_dir=tmp_path)
        store.upsert(_make_candidate(cluster_id="c1"))

        result = store.dismiss("c1", reason="multi-task noise cluster")
        assert result is not None
        assert result.status == "dismissed"
        assert result.dismiss_reason == "multi-task noise cluster"
        assert result.reviewed_at is not None

    def test_promote_unknown_id_returns_none(self, tmp_path: Path) -> None:
        """promote on missing cluster_id returns None (no error)."""
        store = ClusterCandidateStore(storage_dir=tmp_path)
        assert store.promote("does-not-exist", "x") is None


class TestListUnstable:
    def test_list_unstable_filters_gold_rate_below_threshold(
        self, tmp_path: Path
    ) -> None:
        """``list_unstable`` returns only pending candidates with
        ``is_unstable=True``. Sorted by gold_rate asc (worst first)."""
        store = ClusterCandidateStore(storage_dir=tmp_path)
        store.upsert(
            _make_candidate(
                cluster_id="stable1", gold_rate=0.8, is_unstable=False
            )
        )
        store.upsert(
            _make_candidate(
                cluster_id="unstable1",
                gold_rate=0.25,
                is_unstable=True,
            )
        )
        store.upsert(
            _make_candidate(
                cluster_id="unstable2",
                gold_rate=0.15,
                is_unstable=True,
            )
        )

        unstable = store.list_unstable()
        assert len(unstable) == 2
        assert {u.cluster_id for u in unstable} == {"unstable1", "unstable2"}
        # Sorted by gold_rate asc — worst first.
        assert unstable[0].cluster_id == "unstable2"
        assert unstable[1].cluster_id == "unstable1"

        # list_pending defaults to stable-only (grok+pi P1: default
        # review queue should not be polluted by diagnosis rows).
        # Pass include_unstable=True for the combined view.
        stable_only = store.list_pending()
        assert len(stable_only) == 1
        assert stable_only[0].cluster_id == "stable1"

        all_pending = store.list_pending(include_unstable=True)
        assert len(all_pending) == 3
