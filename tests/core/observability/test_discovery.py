"""M12 M2 — core tests for observability.discovery (unified Discovery layer).

Synthetic fixtures only — no eval-set data, no real spans.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from vibesop.core.observability.discovery import (
    COOLING_DAYS,
    DISMISS_TIGHTEN_THRESHOLD,
    HISTORY_HIT_THRESHOLD,
    DiscoveryObservationStore,
    DiscoverySignalStore,
    behavior_evidence_label,
    build_queue,
    candidate_source,
    cluster_fingerprint,
    count_skill_route_hits,
    evidence_score,
    threshold_suggestion,
)
from vibesop.core.observability.skill_promote import ClusterCandidate

T0 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _candidate(
    cluster_id: str = "c" + "0" * 39,
    queries: list[str] | None = None,
    span_count: int = 5,
    gold_rate: float = 0.8,
    task_ids: list[str] | None = None,
    source: str = "gold",
    project_distribution: dict[str, int] | None = None,
    created_at: datetime = T0,
) -> ClusterCandidate:
    return ClusterCandidate(
        cluster_id=cluster_id,
        task_ids=task_ids if task_ids is not None else ["t1", "t2", "t3"],
        queries=queries if queries is not None else ["how do I run the tests"],
        span_count=span_count,
        gold_rate=gold_rate,
        gold_task_ids=["t1"],
        created_at=created_at,
        source=source,  # type: ignore[arg-type]
        project_distribution=project_distribution or {},
    )


class TestFingerprint:
    def test_stable_under_order_case_whitespace(self) -> None:
        a = cluster_fingerprint(["Run  the tests", "fix lint"])
        b = cluster_fingerprint(["fix lint", "run the tests"])
        assert a == b

    def test_differs_for_different_queries(self) -> None:
        assert cluster_fingerprint(["alpha"]) != cluster_fingerprint(["beta"])

    def test_empty_queries_still_fingerprints(self) -> None:
        assert isinstance(cluster_fingerprint([]), str)


class TestEvidenceScore:
    def test_larger_cluster_scores_higher(self) -> None:
        small = _candidate(span_count=3)
        big = _candidate(span_count=12)
        assert evidence_score(big) > evidence_score(small)

    def test_miss_recurrence_source_weight_beats_zero_gold(self) -> None:
        miss = _candidate(source="miss_recurrence", gold_rate=0.0)
        plain_zero_gold = _candidate(source="gold", gold_rate=0.0)
        assert evidence_score(miss) > evidence_score(plain_zero_gold)

    def test_cross_project_bonus(self) -> None:
        local = _candidate()
        xp = _candidate(project_distribution={"/p/a": 2, "/p/b": 3})
        assert evidence_score(xp) > evidence_score(local)

    def test_candidate_source_defaults_to_gold(self) -> None:
        candidate = _candidate()
        object.__delattr__(candidate, "source")  # simulate pre-M2 row
        assert candidate_source(candidate) == "gold"


class TestBehaviorLabel:
    def test_not_collected_when_field_missing(self) -> None:
        assert behavior_evidence_label(_candidate()) == "not_collected"

    def test_passthrough_known_values(self) -> None:
        candidate = _candidate()
        candidate.behavior_evidence = "consistent"  # type: ignore[attr-defined]
        assert behavior_evidence_label(candidate) == "consistent"
        candidate.behavior_evidence = "unavailable"  # type: ignore[attr-defined]
        assert behavior_evidence_label(candidate) == "unavailable"


class TestSignalStore:
    def test_dismiss_roundtrip(self, tmp_path: Path) -> None:
        store = DiscoverySignalStore(tmp_path)
        store.record_dismiss("fp1", "cid1", reason="noise")
        assert store.dismissed_fingerprints() == {"fp1"}
        assert store.dismiss_count() == 1
        assert store.dismissals()[0].reason == "noise"

    def test_mute_expires_and_auto_restores(self, tmp_path: Path) -> None:
        store = DiscoverySignalStore(tmp_path)
        store.record_mute("fp1", "cid1", days=14, now=T0)
        assert "fp1" in store.active_mutes(T0 + timedelta(days=13))
        assert "fp1" not in store.active_mutes(T0 + timedelta(days=15))

    def test_bad_lines_skipped(self, tmp_path: Path) -> None:
        store = DiscoverySignalStore(tmp_path)
        store.record_dismiss("fp1", "cid1")
        with (tmp_path / DiscoverySignalStore.FILENAME).open("a", encoding="utf-8") as f:
            f.write("not-json\n")
            f.write(json.dumps({"kind": "bogus", "fingerprint": "x", "created_at": "2026"}) + "\n")
        assert store.dismissed_fingerprints() == {"fp1"}

    def test_mute_does_not_count_as_dismiss(self, tmp_path: Path) -> None:
        store = DiscoverySignalStore(tmp_path)
        store.record_mute("fp1", "cid1", now=T0)
        assert store.dismiss_count() == 0
        assert store.dismissed_fingerprints() == set()


class TestObservationStore:
    def test_first_observe_grows_repeat_does_not(self, tmp_path: Path) -> None:
        store = DiscoveryObservationStore(tmp_path)
        assert store.observe("fp1", 5, now=T0) is True
        assert store.observe("fp1", 5, now=T0 + timedelta(days=1)) is False
        assert store.observe("fp1", 6, now=T0 + timedelta(days=1)) is True

    def test_cooling_after_14_days_without_growth(self, tmp_path: Path) -> None:
        store = DiscoveryObservationStore(tmp_path)
        store.observe("fp1", 5, now=T0)
        assert store.is_cooling("fp1", now=T0 + timedelta(days=COOLING_DAYS - 1)) is False
        assert store.is_cooling("fp1", now=T0 + timedelta(days=COOLING_DAYS)) is True

    def test_never_observed_is_not_cooling(self, tmp_path: Path) -> None:
        store = DiscoveryObservationStore(tmp_path)
        assert store.is_cooling("ghost", now=T0) is False

    def test_corrupt_file_treated_as_empty(self, tmp_path: Path) -> None:
        (tmp_path / DiscoveryObservationStore.FILENAME).write_text("{broken", encoding="utf-8")
        store = DiscoveryObservationStore(tmp_path)
        assert store.is_cooling("fp1", now=T0) is False


class TestBuildQueue:
    def test_sorts_by_evidence_score_desc(self, tmp_path: Path) -> None:
        signals = DiscoverySignalStore(tmp_path)
        observations = DiscoveryObservationStore(tmp_path)
        low = _candidate(cluster_id="l" * 40, span_count=3, gold_rate=0.6)
        high = _candidate(cluster_id="h" * 40, span_count=10, gold_rate=0.9)
        rows = build_queue([low, high], signals, observations, now=T0)
        assert [r.candidate.cluster_id for r in rows] == ["h" * 40, "l" * 40]

    def test_flags_dismissed_and_muted(self, tmp_path: Path) -> None:
        signals = DiscoverySignalStore(tmp_path)
        observations = DiscoveryObservationStore(tmp_path)
        dismissed = _candidate(cluster_id="d" * 40, queries=["alpha query"])
        muted = _candidate(cluster_id="m" * 40, queries=["beta query"])
        signals.record_dismiss(cluster_fingerprint(dismissed.queries), dismissed.cluster_id)
        signals.record_mute(cluster_fingerprint(muted.queries), muted.cluster_id, now=T0)
        rows = build_queue([dismissed, muted], signals, observations, now=T0)
        by_id = {r.candidate.cluster_id: r for r in rows}
        assert by_id["d" * 40].dismissed is True
        assert by_id["m" * 40].muted is True
        assert by_id["m" * 40].mute_expires_at is not None

    def test_extra_dismissed_scope_applies(self, tmp_path: Path) -> None:
        signals = DiscoverySignalStore(tmp_path)
        observations = DiscoveryObservationStore(tmp_path)
        candidate = _candidate(queries=["gamma query"])
        rows = build_queue(
            [candidate],
            signals,
            observations,
            now=T0,
            extra_dismissed={cluster_fingerprint(candidate.queries)},
        )
        assert rows[0].dismissed is True

    def test_observe_false_is_read_only(self, tmp_path: Path) -> None:
        signals = DiscoverySignalStore(tmp_path)
        observations = DiscoveryObservationStore(tmp_path)
        build_queue([_candidate()], signals, observations, now=T0, observe=False)
        assert not (tmp_path / DiscoveryObservationStore.FILENAME).exists()


class TestThresholdSuggestion:
    def test_none_below_threshold(self) -> None:
        assert threshold_suggestion(DISMISS_TIGHTEN_THRESHOLD - 1) is None

    def test_suggests_at_threshold(self) -> None:
        text = threshold_suggestion(DISMISS_TIGHTEN_THRESHOLD)
        assert text is not None
        assert "建议" in text


class TestCountSkillRouteHits:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert count_skill_route_hits("custom/x", tmp_path / "analytics.jsonl") is None

    def test_counts_matching_primary_skill(self, tmp_path: Path) -> None:
        path = tmp_path / "analytics.jsonl"
        lines = [
            {"query": "q", "primary_skill": "custom/x"},
            {"query": "q", "primary_skill": "custom/x"},
            {"query": "q", "primary_skill": "other/skill"},
            "not-json",
        ]
        path.write_text(
            "\n".join(json.dumps(line) if isinstance(line, dict) else line for line in lines),
            encoding="utf-8",
        )
        assert count_skill_route_hits("custom/x", path) == 2
        assert count_skill_route_hits("other/skill", path) == 1
        assert count_skill_route_hits("nobody", path) == 0

    def test_threshold_constant(self) -> None:
        assert HISTORY_HIT_THRESHOLD == 5


class TestThresholdSuggestionSourceAware:
    """gate17 claude nit 3: the hint must name knobs that actually gate
    the dismissed candidate's admission source."""

    def test_gold_source_suggests_gold_knobs(self) -> None:
        text = threshold_suggestion(DISMISS_TIGHTEN_THRESHOLD, source="gold")
        assert text is not None
        assert "--min-cluster-size" in text
        assert "--miss-min-pairs" not in text

    def test_miss_recurrence_suggests_miss_knobs(self) -> None:
        text = threshold_suggestion(DISMISS_TIGHTEN_THRESHOLD, source="miss_recurrence")
        assert text is not None
        assert "--miss-min-pairs" in text
        assert "--miss-cosine-threshold" in text
        # gold knobs are mentioned only to flag them as ineffective for miss
        assert "对 miss 准入无效" in text

    def test_unknown_source_falls_back_to_gold_knobs(self) -> None:
        text = threshold_suggestion(DISMISS_TIGHTEN_THRESHOLD)
        assert text is not None
        assert "--min-cluster-size" in text


class TestCountSkillRouteHitsSince:
    """gate17 pi nit 4: only hits at/after promotion count."""

    def _write(self, path: Path, records: list[dict]) -> None:
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    def test_since_filters_pre_promotion_hits(self, tmp_path: Path) -> None:
        path = tmp_path / "analytics.jsonl"
        self._write(
            path,
            [
                {"primary_skill": "custom/x", "timestamp": "2026-07-01T00:00:00+00:00"},
                {"primary_skill": "custom/x", "timestamp": "2026-08-02T00:00:00+00:00"},
                {"primary_skill": "custom/x", "timestamp": "2026-08-03T00:00:00+00:00"},
            ],
        )
        since = datetime(2026, 8, 1, tzinfo=UTC)
        assert count_skill_route_hits("custom/x", path, since=since) == 2
        assert count_skill_route_hits("custom/x", path) == 3  # no window → all

    def test_missing_or_bad_timestamp_still_counts(self, tmp_path: Path) -> None:
        path = tmp_path / "analytics.jsonl"
        self._write(
            path,
            [
                {"primary_skill": "custom/x"},  # no timestamp
                {"primary_skill": "custom/x", "timestamp": "not-a-date"},
            ],
        )
        since = datetime(2026, 8, 1, tzinfo=UTC)
        assert count_skill_route_hits("custom/x", path, since=since) == 2

    def test_naive_record_timestamp_treated_as_utc(self, tmp_path: Path) -> None:
        path = tmp_path / "analytics.jsonl"
        self._write(path, [{"primary_skill": "custom/x", "timestamp": "2026-07-01T00:00:00"}])
        since = datetime(2026, 8, 1, tzinfo=UTC)
        assert count_skill_route_hits("custom/x", path, since=since) == 0


class TestCrossProcessLocking:
    """gate17 claude nit 2: writes go through fcntl.flock (POSIX path of
    the repo's double-lock convention)."""

    def test_signal_append_flocks(self, tmp_path: Path, monkeypatch) -> None:
        import fcntl

        calls: list[int] = []
        real_flock = fcntl.flock

        def spy(fd: int, op: int) -> None:
            calls.append(op)
            real_flock(fd, op)

        monkeypatch.setattr(fcntl, "flock", spy)
        DiscoverySignalStore(tmp_path).record_dismiss("fp1", "cid1")
        assert fcntl.LOCK_EX in calls
        assert fcntl.LOCK_UN in calls

    def test_observe_flocks(self, tmp_path: Path, monkeypatch) -> None:
        import fcntl

        calls: list[int] = []
        real_flock = fcntl.flock

        def spy(fd: int, op: int) -> None:
            calls.append(op)
            real_flock(fd, op)

        monkeypatch.setattr(fcntl, "flock", spy)
        DiscoveryObservationStore(tmp_path).observe("fp1", 5, now=T0)
        assert fcntl.LOCK_EX in calls
        assert fcntl.LOCK_UN in calls
