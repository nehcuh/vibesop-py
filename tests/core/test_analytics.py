"""Tests for analytics store.

Covers: ExecutionRecord, AnalyticsStore record/list/stats/low-quality detection.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from vibesop.core.analytics import AnalyticsStore, ExecutionRecord, LastRouteTracker


class TestExecutionRecord:
    """Test ExecutionRecord dataclass."""

    def test_to_dict(self) -> None:
        record = ExecutionRecord(
            query="test",
            mode="single",
            primary_skill="builtin/test",
            step_count=1,
            duration_ms=100.0,
            user_satisfied=True,
        )
        d = record.to_dict()
        assert d["query"] == "test"
        assert d["mode"] == "single"
        assert d["primary_skill"] == "builtin/test"
        assert d["user_satisfied"] is True

    def test_from_dict(self) -> None:
        data = {
            "query": "test",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "mode": "orchestrated",
            "primary_skill": "builtin/test",
            "plan_steps": ["step1", "step2"],
            "step_count": 2,
            "duration_ms": 250.0,
            "user_modified": True,
            "user_satisfied": False,
            "routing_layers": ["keyword"],
            "metadata": {"key": "value"},
        }
        record = ExecutionRecord.from_dict(data)
        assert record.query == "test"
        assert record.mode == "orchestrated"
        assert record.user_modified is True
        assert record.user_satisfied is False
        assert record.plan_steps == ["step1", "step2"]


class TestAnalyticsStore:
    """Test AnalyticsStore persistence and queries."""

    def test_record_and_list(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        record = ExecutionRecord(query="q1", primary_skill="s1", user_satisfied=True)
        store.record(record)

        records = store.list_records()
        assert len(records) == 1
        assert records[0].query == "q1"

    def test_record_redacts_pii_from_query(self, tmp_path: Path) -> None:
        """F-06: PII/secrets in the query are redacted before persistence."""
        store = AnalyticsStore(storage_dir=str(tmp_path))
        leak = "email alice@corp.com key sk-" + "a" * 24
        store.record(ExecutionRecord(query=leak, primary_skill="s1"))

        records = store.list_records()
        assert len(records) == 1
        stored = records[0].query
        assert "alice@corp.com" not in stored
        assert "sk-" + "a" * 24 not in stored
        assert "[REDACTED_EMAIL]" in stored

    def test_list_with_skill_filter(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        store.record(ExecutionRecord(query="q1", primary_skill="s1"))
        store.record(ExecutionRecord(query="q2", primary_skill="s2"))

        records = store.list_records(skill_id="s1")
        assert len(records) == 1
        assert records[0].primary_skill == "s1"

    def test_list_limit(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        for i in range(5):
            store.record(ExecutionRecord(query=f"q{i}", primary_skill="s1"))

        records = store.list_records(limit=3)
        assert len(records) == 3

    def test_skill_stats(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        store.record(
            ExecutionRecord(query="q1", primary_skill="s1", user_satisfied=True, duration_ms=100.0)
        )
        store.record(
            ExecutionRecord(query="q2", primary_skill="s1", user_satisfied=True, duration_ms=200.0)
        )
        store.record(
            ExecutionRecord(query="q3", primary_skill="s1", user_satisfied=False, duration_ms=300.0)
        )

        stats = store.get_skill_stats("s1")
        assert stats["total_uses"] == 3
        assert stats["satisfaction_rate"] == pytest.approx(2 / 3)
        assert stats["dissatisfaction_rate"] == pytest.approx(1 / 3)
        assert stats["avg_duration_ms"] == pytest.approx(200.0)

    def test_skill_stats_empty(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        stats = store.get_skill_stats("nonexistent")
        assert stats["total_uses"] == 0
        assert stats["satisfaction_rate"] is None

    def test_low_quality_skills(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        # s1: 1/3 satisfied → low quality
        for i in range(3):
            store.record(
                ExecutionRecord(
                    query=f"q{i}",
                    primary_skill="s1",
                    user_satisfied=(i == 0),
                )
            )
        # s2: 3/3 satisfied → not low quality
        for i in range(3):
            store.record(
                ExecutionRecord(
                    query=f"q{i}",
                    primary_skill="s2",
                    user_satisfied=True,
                )
            )

        low_quality = store.get_low_quality_skills(threshold=0.5)
        assert len(low_quality) == 1
        assert low_quality[0][0] == "s1"
        assert low_quality[0][1] == pytest.approx(1 / 3)

    def test_low_quality_not_enough_samples(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        # Only 2 samples for s1 — not enough to flag
        for i in range(2):
            store.record(
                ExecutionRecord(
                    query=f"q{i}",
                    primary_skill="s1",
                    user_satisfied=False,
                )
            )

        low_quality = store.get_low_quality_skills(threshold=0.5)
        assert len(low_quality) == 0

    def test_empty_store(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        assert store.list_records() == []
        assert store.get_low_quality_skills() == []


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestLastRouteTracker:
    """Implicit feedback signals derived from .vibe/last_route.json (M1d)."""

    def test_first_route_yields_no_signals(self, tmp_path: Path) -> None:
        tracker = LastRouteTracker(storage_dir=tmp_path)
        signals = tracker.compute_and_update("fix the bug", "s1")
        assert signals == {}
        assert (tmp_path / "last_route.json").exists()

    def test_new_instance_reads_state_written_by_another(self, tmp_path: Path) -> None:
        """Cross-process visibility: a fresh tracker instance (cold in-memory
        cache, e.g. a new CLI process) must read the state file written by
        another instance and derive its first signals from it."""
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        writer = LastRouteTracker(storage_dir=tmp_path)
        writer.compute_and_update("fix the routing bug", "s1", now=t0)

        reader = LastRouteTracker(storage_dir=tmp_path)
        signals = reader.compute_and_update(
            "fix the routing bug please", "s2", now=t0 + timedelta(seconds=5)
        )

        assert signals["seconds_since_last_route"] == pytest.approx(5.0)
        assert signals["is_rapid_reroute"] is True
        assert signals["query_overlap_with_last"] is True

    def test_rapid_reroute_with_overlapping_query(self, tmp_path: Path) -> None:
        tracker = LastRouteTracker(storage_dir=tmp_path)
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        tracker.compute_and_update("fix the routing bug", "s1", now=t0)

        signals = tracker.compute_and_update(
            "fix the routing bug please", "s2", now=t0 + timedelta(seconds=5)
        )
        assert signals["seconds_since_last_route"] == pytest.approx(5.0)
        assert signals["is_rapid_reroute"] is True
        # {fix,the,routing,bug} vs {fix,the,routing,bug,please}: J = 4/5 > 0.5
        assert signals["query_overlap_with_last"] is True

    def test_slow_distinct_reroute(self, tmp_path: Path) -> None:
        tracker = LastRouteTracker(storage_dir=tmp_path)
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        tracker.compute_and_update("fix the routing bug", "s1", now=t0)

        signals = tracker.compute_and_update(
            "write a release note", "s2", now=t0 + timedelta(seconds=60)
        )
        assert signals["seconds_since_last_route"] == pytest.approx(60.0)
        assert signals["is_rapid_reroute"] is False
        assert signals["query_overlap_with_last"] is False

    def test_overlap_boundary(self, tmp_path: Path) -> None:
        """Jaccard exactly at/below 0.5 is not flagged as a restatement."""
        tracker = LastRouteTracker(storage_dir=tmp_path)
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        tracker.compute_and_update("alpha beta gamma", "s1", now=t0)
        # {alpha,beta,gamma} vs {alpha,beta,delta}: J = 2/4 = 0.5 → not > 0.5
        signals = tracker.compute_and_update(
            "alpha beta delta", "s2", now=t0 + timedelta(seconds=30)
        )
        assert signals["query_overlap_with_last"] is False

    def test_state_file_stores_hashes_not_raw_query(self, tmp_path: Path) -> None:
        tracker = LastRouteTracker(storage_dir=tmp_path)
        tracker.compute_and_update("email alice@corp.com about routing", "s1")
        raw = (tmp_path / "last_route.json").read_text(encoding="utf-8")
        assert "alice@corp.com" not in raw
        assert "routing" not in raw
        state = json.loads(raw)
        assert set(state) == {"token_hashes", "skill", "timestamp"}
        assert state["skill"] == "s1"

    def test_corrupt_state_degrades_and_self_heals(self, tmp_path: Path) -> None:
        (tmp_path / "last_route.json").write_text("{not json", encoding="utf-8")
        tracker = LastRouteTracker(storage_dir=tmp_path)
        t0 = datetime(2026, 1, 1, tzinfo=UTC)

        signals = tracker.compute_and_update("fix the bug", "s1", now=t0)
        assert signals == {}  # no crash, no implicit fields

        # State was rewritten → next route gets signals again.
        signals = tracker.compute_and_update("fix the bug", "s1", now=t0 + timedelta(seconds=3))
        assert signals["is_rapid_reroute"] is True

    def test_lock_contention_yields_no_signals(self, tmp_path: Path) -> None:
        from vibesop.utils.file_lock import cross_process_lock

        tracker = LastRouteTracker(storage_dir=tmp_path)
        with cross_process_lock(tmp_path / "last_route.lock", blocking=False):
            signals = tracker.compute_and_update("fix the bug", "s1")
        assert signals == {}  # contention must never raise

    def test_malformed_timestamp_skips_time_signals(self, tmp_path: Path) -> None:
        (tmp_path / "last_route.json").write_text(
            json.dumps({"timestamp": "not-a-date", "token_hashes": ["x"]}),
            encoding="utf-8",
        )
        tracker = LastRouteTracker(storage_dir=tmp_path)
        signals = tracker.compute_and_update("fix the bug", "s1")
        assert "seconds_since_last_route" not in signals
        assert "is_rapid_reroute" not in signals

    def test_clock_skew_clamps_negative_seconds(self, tmp_path: Path) -> None:
        """A last-route timestamp in the future (clock rollback) clamps to 0."""
        tracker = LastRouteTracker(storage_dir=tmp_path)
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        tracker.compute_and_update("fix the bug", "s1", now=t0)

        signals = tracker.compute_and_update("fix the bug", "s1", now=t0 - timedelta(seconds=30))
        assert signals["seconds_since_last_route"] == 0.0
        assert signals["is_rapid_reroute"] is True

    def test_steady_state_skips_file_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hot path: after the first write, the in-memory cache serves the
        state and ``_read`` is never called again."""
        tracker = LastRouteTracker(storage_dir=tmp_path)
        reads = 0
        original_read = tracker._read

        def counting_read() -> dict | None:
            nonlocal reads
            reads += 1
            return original_read()

        monkeypatch.setattr(tracker, "_read", counting_read)
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        tracker.compute_and_update("fix the bug", "s1", now=t0)
        assert reads == 1  # cold start: no cache yet

        signals = tracker.compute_and_update(
            "fix the bug again", "s2", now=t0 + timedelta(seconds=5)
        )
        assert reads == 1  # steady state: cache served, no file read
        assert signals["is_rapid_reroute"] is True

    def test_failed_write_does_not_poison_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If ``_write`` raises, the cache must stay empty so the next call
        re-reads from disk instead of trusting unwritten state."""
        tracker = LastRouteTracker(storage_dir=tmp_path)

        def boom(state: dict) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(tracker, "_write", boom)
        assert tracker.compute_and_update("fix the bug", "s1") == {}
        assert tracker._cached_state is None

        # Recovered write path: signals flow again on the *next* route.
        monkeypatch.undo()
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        tracker.compute_and_update("fix the bug", "s1", now=t0)
        signals = tracker.compute_and_update("fix the bug", "s1", now=t0 + timedelta(seconds=3))
        assert signals["is_rapid_reroute"] is True

    def test_cache_degrades_to_per_process_signals(self, tmp_path: Path) -> None:
        """Pin the accepted trade-off: when another process writes between our
        routes, our cached state wins (last-writer-wins) and signals compare
        against our own last route, not the interleaved one."""
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        ours = LastRouteTracker(storage_dir=tmp_path)
        ours.compute_and_update("alpha beta", "s1", now=t0)

        other = LastRouteTracker(storage_dir=tmp_path)
        other.compute_and_update("completely different words", "s9", now=t0 + timedelta(seconds=1))

        signals = ours.compute_and_update("alpha beta", "s1", now=t0 + timedelta(seconds=2))
        # Compared vs. our own "alpha beta" (cache), not the interleaved write.
        assert signals["query_overlap_with_last"] is True
        state = json.loads((tmp_path / "last_route.json").read_text(encoding="utf-8"))
        assert state["skill"] == "s1"


class TestAnalyticsImplicitSignals:
    """AnalyticsStore.record merges implicit signals into the JSONL event."""

    def test_first_record_has_no_implicit_fields(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        store.record(ExecutionRecord(query="q1", primary_skill="s1"))
        (event,) = _read_jsonl(tmp_path / "analytics.jsonl")
        assert "seconds_since_last_route" not in event
        assert "is_rapid_reroute" not in event
        assert "query_overlap_with_last" not in event

    def test_second_record_carries_implicit_fields(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        store.record(ExecutionRecord(query="fix the routing bug", primary_skill="s1"))
        store.record(ExecutionRecord(query="fix the routing bug now", primary_skill="s2"))

        events = _read_jsonl(tmp_path / "analytics.jsonl")
        assert len(events) == 2
        second = events[1]
        assert second["seconds_since_last_route"] >= 0
        assert second["is_rapid_reroute"] is True
        assert second["query_overlap_with_last"] is True
        # Existing fields untouched.
        assert second["query"] == "fix the routing bug now"
        assert second["primary_skill"] == "s2"

    def test_records_with_new_fields_still_parse(self, tmp_path: Path) -> None:
        """Old reader code paths (from_dict ignores unknown keys) stay valid."""
        store = AnalyticsStore(storage_dir=str(tmp_path))
        store.record(ExecutionRecord(query="q1", primary_skill="s1"))
        store.record(ExecutionRecord(query="q1 again", primary_skill="s1"))

        records = store.list_records()
        assert len(records) == 2
        assert records[1].query == "q1 again"

    def test_record_survives_lock_contention(self, tmp_path: Path) -> None:
        """Lock contention drops implicit fields but never the analytics write."""
        from vibesop.utils.file_lock import cross_process_lock

        store = AnalyticsStore(storage_dir=str(tmp_path))
        with cross_process_lock(tmp_path / "last_route.lock", blocking=False):
            store.record(ExecutionRecord(query="q1", primary_skill="s1"))

        (event,) = _read_jsonl(tmp_path / "analytics.jsonl")
        assert event["query"] == "q1"
        assert "is_rapid_reroute" not in event

    def test_store_reuses_single_tracker_with_cache(self, tmp_path: Path) -> None:
        """record() must not rebuild LastRouteTracker per call — that would
        defeat its in-memory state cache on every hot-path write."""
        store = AnalyticsStore(storage_dir=str(tmp_path))
        tracker = store._last_route
        store.record(ExecutionRecord(query="q1", primary_skill="s1"))
        assert store._last_route is tracker
        assert tracker._cached_state is not None
