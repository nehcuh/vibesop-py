"""Tests for analytics store.

Covers: ExecutionRecord, AnalyticsStore record/list/stats/low-quality detection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.core.analytics import AnalyticsStore, ExecutionRecord


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
        store.record(ExecutionRecord(query="q1", primary_skill="s1", user_satisfied=True, duration_ms=100.0))
        store.record(ExecutionRecord(query="q2", primary_skill="s1", user_satisfied=True, duration_ms=200.0))
        store.record(ExecutionRecord(query="q3", primary_skill="s1", user_satisfied=False, duration_ms=300.0))

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
            store.record(ExecutionRecord(
                query=f"q{i}",
                primary_skill="s1",
                user_satisfied=(i == 0),
            ))
        # s2: 3/3 satisfied → not low quality
        for i in range(3):
            store.record(ExecutionRecord(
                query=f"q{i}",
                primary_skill="s2",
                user_satisfied=True,
            ))

        low_quality = store.get_low_quality_skills(threshold=0.5)
        assert len(low_quality) == 1
        assert low_quality[0][0] == "s1"
        assert low_quality[0][1] == pytest.approx(1 / 3)

    def test_low_quality_not_enough_samples(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        # Only 2 samples for s1 — not enough to flag
        for i in range(2):
            store.record(ExecutionRecord(
                query=f"q{i}",
                primary_skill="s1",
                user_satisfied=False,
            ))

        low_quality = store.get_low_quality_skills(threshold=0.5)
        assert len(low_quality) == 0

    def test_empty_store(self, tmp_path: Path) -> None:
        store = AnalyticsStore(storage_dir=str(tmp_path))
        assert store.list_records() == []
        assert store.get_low_quality_skills() == []
