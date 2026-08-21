"""Sanity tests for scripts/calibrate_behavior_threshold.py (M3).

Synthetic data only — never reads the real cmspark files. Covers the
script's self-test, the honest "sample too thin" fail-closed exit code
(gate24 pi#8a), the dual folded/unfolded report, and the same-trace
anti-leak guards (gate24 MAJOR-A).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = ROOT / "scripts" / "calibrate_behavior_threshold.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("calibrate_behavior_threshold", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("calibrate_behavior_threshold", module)
    spec.loader.exec_module(module)
    return module


calib = _load_module()


def _cluster(items: dict[str, list[tuple[str, list[str]]]]) -> dict:
    return items


class TestSelfTest:
    def test_builtin_self_test_passes(self) -> None:
        assert calib._self_test() == 0


class TestThinSampleReport:
    def test_zero_positive_pairs_reports_sample_too_thin(self, capsys) -> None:
        """One sequence per cluster → no positive pairs → refuse a decision
        band AND exit 2 (fail-closed for future gated callers, pi#8a)."""
        by_cluster = _cluster(
            {
                "a" * 16: [("tr1", ["Read", "Grep", "Read"])],
                "b" * 16: [("tr2", ["Bash", "Write"])],
            }
        )
        assert calib.report(by_cluster, by_cluster) == 2
        out = capsys.readouterr().out
        assert "positive (same cluster) = 0" in out
        assert "negative (cross cluster) = 1" in out
        assert "SAMPLE TOO THIN" in out
        assert "decision band (min errors" not in out

    def test_sufficient_pairs_emit_decision_band(self, capsys) -> None:
        by_cluster = _cluster(
            {
                "a" * 16: [("tr1", ["Read", "Grep", "Read"]), ("tr2", ["Read", "Grep", "Bash"])],
                "b" * 16: [("tr3", ["Bash", "Write", "Bash"]), ("tr4", ["Bash", "Write", "Glob"])],
            }
        )
        assert calib.report(by_cluster, by_cluster) == 0
        out = capsys.readouterr().out
        assert "positive (same cluster) = 2" in out
        assert "decision band (min errors" in out


class TestSameTraceAntiLeak:
    """gate24 MAJOR-A — overlapping candidate pools must not let one trace
    pair with itself (as a fake cross-cluster negative at Jaccard 1.0)."""

    @staticmethod
    def _spans_with_shared_task() -> tuple[list[dict], list[dict]]:
        """Two candidates share task_id "shared-t" (cross-scan-window pool
        overlap); its single trace tr1 must not self-pair."""
        spans = [
            {
                "id": "r1",
                "name": "route:q",
                "task_id": "shared-t",
                "trace_id": "tr1",
                "project_id": "test",
                "span_kind": "task",
                "started_at": "2026-08-01T00:00:00+00:00",
            },
            {
                "id": "t1",
                "name": "tool:Read",
                "span_kind": "tool_call",
                "trace_id": "tr1",
                "parent_span_id": "r1",
                "started_at": "2026-08-01T00:01:00+00:00",
            },
            {
                "id": "t2",
                "name": "tool:Grep",
                "span_kind": "tool_call",
                "trace_id": "tr1",
                "parent_span_id": "r1",
                "started_at": "2026-08-01T00:02:00+00:00",
            },
        ]
        candidates = [
            {"cluster_id": "a" * 16, "task_ids": ["shared-t"], "status": "pending"},
            {"cluster_id": "b" * 16, "task_ids": ["shared-t"], "status": "pending"},
        ]
        return spans, candidates

    def test_shared_trace_never_becomes_a_pair(self) -> None:
        spans, candidates = self._spans_with_shared_task()
        by_cluster = calib.collect_cluster_sequences(spans, candidates)
        # The trace is attributed to BOTH clusters (honest reflection of
        # the overlapping pool)…
        assert set(by_cluster) == {"a" * 16, "b" * 16}
        positives, negatives = calib.score_pairs(by_cluster)
        # …but the same-trace pair is skipped entirely — no Jaccard-1.0
        # self-pair poisoning the negative pool.
        assert positives == []
        assert negatives == []

    def test_duplicate_cluster_rows_cannot_self_pair(self) -> None:
        """Same cluster_id in two pool rows (rescan artifact) → dedup by
        (cluster_id, trace) — the trace can't pair with itself as a
        positive either."""
        spans, _candidates = self._spans_with_shared_task()
        dup = [
            {"cluster_id": "a" * 16, "task_ids": ["shared-t"], "status": "pending"},
            {"cluster_id": "a" * 16, "task_ids": ["shared-t"], "status": "promoted"},
        ]
        by_cluster = calib.collect_cluster_sequences(spans, dup)
        assert len(by_cluster["a" * 16]) == 1
        positives, negatives = calib.score_pairs(by_cluster)
        assert positives == []
        assert negatives == []
