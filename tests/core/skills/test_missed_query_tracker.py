"""Tests for the P2 missed-query tracker (live path + analytics clustering)."""

from __future__ import annotations

import json
from pathlib import Path

from vibesop.core.skills.miss_counter import MissCounter
from vibesop.core.skills.missed_query_tracker import (
    MissedQueryTracker,
    normalize_query,
)


def _write_analytics(root: Path, lines: list[str]) -> None:
    vibe_dir = root / ".vibe"
    vibe_dir.mkdir(parents=True, exist_ok=True)
    (vibe_dir / "analytics.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _miss_record(query: str, timestamp: str) -> str:
    return json.dumps(
        {
            "query": query,
            "timestamp": timestamp,
            "mode": "single",
            "primary_skill": None,
            "plan_steps": [],
            "step_count": 0,
            "duration_ms": 1.0,
        }
    )


def _hit_record(query: str, timestamp: str) -> str:
    return json.dumps(
        {
            "query": query,
            "timestamp": timestamp,
            "mode": "single",
            "primary_skill": "gstack/review",
        }
    )


class TestNormalizeQuery:
    def test_collapses_whitespace_and_lowercases(self) -> None:
        assert normalize_query("  Hello   WORLD \n") == "hello world"

    def test_matches_miss_counter_rule(self, tmp_path: Path) -> None:
        """Cosmetically different queries share one counter → one cluster."""
        counter = MissCounter(tmp_path)
        for _ in range(3):
            counter.record("  Hello   WORLD ")
        tracker = MissedQueryTracker(tmp_path)
        cluster = tracker.suggest_for_live_query("hello world", counter)
        assert cluster is not None
        assert cluster.count == 3


class TestLivePath:
    def test_below_threshold_returns_none(self, tmp_path: Path) -> None:
        counter = MissCounter(tmp_path)
        for _ in range(2):
            counter.record("how do I review a pull request")

        tracker = MissedQueryTracker(tmp_path)
        assert tracker.suggest_for_live_query("how do I review a pull request", counter) is None

    def test_at_threshold_suggests_with_current_query_text(self, tmp_path: Path) -> None:
        counter = MissCounter(tmp_path)
        for _ in range(3):
            counter.record("how do I review a pull request")

        tracker = MissedQueryTracker(tmp_path)
        cluster = tracker.suggest_for_live_query("how do I review a pull request", counter)

        assert cluster is not None
        assert cluster.source == "live"
        assert cluster.count == 3
        assert cluster.representative_query == "how do I review a pull request"
        assert cluster.cluster_key == "how do i review a pull request"
        assert cluster.first
        assert cluster.last

    def test_no_text_storage_dependency(self, tmp_path: Path) -> None:
        """Live path must work when analytics.jsonl does not exist at all."""
        counter = MissCounter(tmp_path)
        for _ in range(3):
            counter.record("zztop quantum flux capacitor")

        tracker = MissedQueryTracker(tmp_path)
        assert not (tmp_path / ".vibe" / "analytics.jsonl").exists()

        cluster = tracker.suggest_for_live_query("zztop quantum flux capacitor", counter)
        assert cluster is not None
        assert cluster.count == 3

    def test_empty_query_returns_none(self, tmp_path: Path) -> None:
        tracker = MissedQueryTracker(tmp_path)
        assert tracker.suggest_for_live_query("   \n\t ", MissCounter(tmp_path)) is None

    def test_unseen_query_returns_none(self, tmp_path: Path) -> None:
        tracker = MissedQueryTracker(tmp_path)
        assert tracker.suggest_for_live_query("never seen before", MissCounter(tmp_path)) is None


class TestAnalyticsClustering:
    def test_similar_queries_group_into_one_cluster(self, tmp_path: Path) -> None:
        _write_analytics(
            tmp_path,
            [
                _miss_record("fix the build", "2026-07-16T10:00:00+00:00"),
                _miss_record("fix the build please", "2026-07-17T10:00:00+00:00"),
                _miss_record("please fix the build", "2026-07-18T10:00:00+00:00"),
            ],
        )

        clusters = MissedQueryTracker(tmp_path).clusters_from_analytics()

        assert len(clusters) == 1
        cluster = clusters[0]
        assert cluster.count == 3
        assert cluster.source == "analytics"
        # Representative is the most recent member (file order is chronological).
        assert cluster.representative_query == "please fix the build"
        assert cluster.first == "2026-07-16T10:00:00+00:00"
        assert cluster.last == "2026-07-18T10:00:00+00:00"

    def test_dissimilar_queries_form_separate_clusters(self, tmp_path: Path) -> None:
        _write_analytics(
            tmp_path,
            [
                _miss_record("fix the build", "2026-07-16T10:00:00+00:00"),
                _miss_record("deploy the kubernetes cluster", "2026-07-16T11:00:00+00:00"),
                _miss_record("fix the build please", "2026-07-17T10:00:00+00:00"),
                _miss_record("deploy the kubernetes cluster now", "2026-07-17T11:00:00+00:00"),
                _miss_record("please fix the build", "2026-07-18T10:00:00+00:00"),
                _miss_record("please deploy the kubernetes cluster", "2026-07-18T11:00:00+00:00"),
            ],
        )

        clusters = MissedQueryTracker(tmp_path).clusters_from_analytics()

        assert len(clusters) == 2
        representatives = {c.representative_query for c in clusters}
        assert representatives == {"please fix the build", "please deploy the kubernetes cluster"}
        assert all(c.count == 3 for c in clusters)

    def test_below_min_count_excluded(self, tmp_path: Path) -> None:
        _write_analytics(
            tmp_path,
            [
                _miss_record("fix the build", "2026-07-16T10:00:00+00:00"),
                _miss_record("fix the build please", "2026-07-17T10:00:00+00:00"),
            ],
        )
        assert MissedQueryTracker(tmp_path).clusters_from_analytics() == []

    def test_custom_min_count(self, tmp_path: Path) -> None:
        _write_analytics(
            tmp_path,
            [
                _miss_record("fix the build", "2026-07-16T10:00:00+00:00"),
                _miss_record("fix the build please", "2026-07-17T10:00:00+00:00"),
            ],
        )
        clusters = MissedQueryTracker(tmp_path).clusters_from_analytics(min_count=2)
        assert len(clusters) == 1
        assert clusters[0].count == 2

    def test_hits_are_ignored(self, tmp_path: Path) -> None:
        _write_analytics(
            tmp_path,
            [
                _hit_record("fix the build", "2026-07-16T10:00:00+00:00"),
                _miss_record("fix the build please", "2026-07-17T10:00:00+00:00"),
                _miss_record("please fix the build", "2026-07-18T10:00:00+00:00"),
            ],
        )
        assert MissedQueryTracker(tmp_path).clusters_from_analytics() == []

    def test_corrupt_lines_are_tolerated(self, tmp_path: Path) -> None:
        _write_analytics(
            tmp_path,
            [
                "not json {{{",
                _miss_record("fix the build", "2026-07-16T10:00:00+00:00"),
                json.dumps({"primary_skill": None}),  # missing query
                json.dumps("just a string"),
                _miss_record("fix the build please", "2026-07-17T10:00:00+00:00"),
                _miss_record("please fix the build", "2026-07-18T10:00:00+00:00"),
            ],
        )
        clusters = MissedQueryTracker(tmp_path).clusters_from_analytics()
        assert len(clusters) == 1
        assert clusters[0].count == 3

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert MissedQueryTracker(tmp_path).clusters_from_analytics() == []

    def test_clusters_sorted_by_count_desc(self, tmp_path: Path) -> None:
        _write_analytics(
            tmp_path,
            [
                _miss_record("fix the build", "2026-07-16T10:00:00+00:00"),
                _miss_record("deploy the kubernetes cluster", "2026-07-16T11:00:00+00:00"),
                _miss_record("fix the build please", "2026-07-17T10:00:00+00:00"),
                _miss_record("deploy the kubernetes cluster", "2026-07-17T11:00:00+00:00"),
                _miss_record("please fix the build", "2026-07-18T10:00:00+00:00"),
                _miss_record("deploy the kubernetes cluster", "2026-07-18T11:00:00+00:00"),
                _miss_record("deploy the kubernetes cluster now", "2026-07-18T12:00:00+00:00"),
            ],
        )
        clusters = MissedQueryTracker(tmp_path).clusters_from_analytics()
        assert [c.count for c in clusters] == [4, 3]
        assert clusters[0].representative_query == "deploy the kubernetes cluster now"
