# M1 度量脊柱 — 复审包

## 变更概览
 src/vibesop/core/analytics.py          | 121 ++++++++++++++++++++++++++-
 src/vibesop/core/routing/unified.py    |   8 +-
 tests/core/routing/test_index_layer.py |  61 ++++++++++++++
 tests/core/test_analytics.py           | 146 ++++++++++++++++++++++++++++++++-
 4 files changed, 330 insertions(+), 6 deletions(-)
新增: scripts/build_eval_from_logs.py, scripts/replay_routing.py, tests/scripts/test_replay_routing.py, tests/unit/test_build_eval_from_logs.py

## git diff(已跟踪文件)
diff --git a/src/vibesop/core/analytics.py b/src/vibesop/core/analytics.py
index 6c14c7c..496baa1 100644
--- a/src/vibesop/core/analytics.py
+++ b/src/vibesop/core/analytics.py
@@ -6,6 +6,7 @@ to enable continuous improvement of the routing system.
 
 from __future__ import annotations
 
+import hashlib
 import json
 import logging
 from dataclasses import dataclass, field
@@ -17,6 +18,10 @@ from vibesop.utils.redaction import redact_sensitive
 
 logger = logging.getLogger(__name__)
 
+_RAPID_REROUTE_SECONDS = 10.0
+_OVERLAP_THRESHOLD = 0.5
+_HASH_LENGTH = 16
+
 
 @dataclass
 class ExecutionRecord:
@@ -66,6 +71,110 @@ class ExecutionRecord:
         )
 
 
+class LastRouteTracker:
+    """Tracks the previous route per project to derive implicit feedback signals.
+
+    Persists ``.vibe/last_route.json`` (hashed query + token hashes + skill +
+    timestamp — no raw query text). Read-modify-write is serialised via a
+    sibling ``.lock`` file (same pattern as ``.vibe/instincts.jsonl.lock``).
+
+    Fails open: corrupt state, lock contention, or any IO error yields no
+    implicit signals and never breaks the routing/analytics main flow.
+    """
+
+    def __init__(self, storage_dir: str | Path = ".vibe") -> None:
+        self.state_path = Path(storage_dir) / "last_route.json"
+        self.lock_path = Path(storage_dir) / "last_route.lock"
+
+    def compute_and_update(
+        self,
+        query: str,
+        skill: str | None,
+        now: datetime | None = None,
+    ) -> dict[str, Any]:
+        """Compute implicit signals vs. the last route, then record this one.
+
+        Returns the signal fields to merge into the analytics event; empty
+        dict on first route or any failure (silent degradation).
+        """
+        try:
+            from vibesop.utils.file_lock import cross_process_lock
+
+            now = now or datetime.now(UTC)
+            normalized = " ".join(redact_sensitive(query).split()).lower()
+            token_hashes = sorted(
+                {_hash_token(t) for t in normalized.split() if t}
+            )
+            # Non-blocking: a contended lock must never stall routing (M1d);
+            # the critical section is a tiny RMW so contention is rare.
+            with cross_process_lock(self.lock_path, blocking=False):
+                signals = _implicit_signals(self._read(), token_hashes, now)
+                self._write(
+                    {
+                        "query_hash": hashlib.sha256(
+                            normalized.encode("utf-8")
+                        ).hexdigest()[:_HASH_LENGTH],
+                        "token_hashes": token_hashes,
+                        "skill": skill,
+                        "timestamp": now.isoformat(),
+                    }
+                )
+            return signals
+        except Exception as e:  # telemetry must never break routing
+            logger.debug("Implicit feedback signals unavailable: %s", e)
+            return {}
+
+    def _read(self) -> dict[str, Any] | None:
+        """Read last-route state; corrupt/missing state returns None (self-heals
+        on the next ``_write``)."""
+        if not self.state_path.exists():
+            return None
+        try:
+            with self.state_path.open("r", encoding="utf-8") as f:
+                data = json.load(f)
+        except (json.JSONDecodeError, OSError):
+            return None
+        return data if isinstance(data, dict) else None
+
+    def _write(self, state: dict[str, Any]) -> None:
+        self.state_path.parent.mkdir(parents=True, exist_ok=True)
+        with self.state_path.open("w", encoding="utf-8") as f:
+            json.dump(state, f, ensure_ascii=False)
+
+
+def _hash_token(token: str) -> str:
+    """Per-token hash so Jaccard overlap can be computed without storing raw
+    query text (hashed-set equality matches raw-set equality)."""
+    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
+
+
+def _implicit_signals(
+    last: dict[str, Any] | None,
+    token_hashes: list[str],
+    now: datetime,
+) -> dict[str, Any]:
+    """Derive implicit quality signals from the previous route state."""
+    if not last:
+        return {}
+
+    signals: dict[str, Any] = {}
+    try:
+        last_ts = datetime.fromisoformat(str(last["timestamp"]))
+        seconds = (now - last_ts).total_seconds()
+        signals["seconds_since_last_route"] = round(seconds, 3)
+        signals["is_rapid_reroute"] = seconds < _RAPID_REROUTE_SECONDS
+    except (KeyError, TypeError, ValueError):
+        pass
+
+    last_tokens = set(last.get("token_hashes") or [])
+    if last_tokens and token_hashes:
+        union = last_tokens | set(token_hashes)
+        jaccard = len(last_tokens & set(token_hashes)) / len(union)
+        signals["query_overlap_with_last"] = jaccard > _OVERLAP_THRESHOLD
+
+    return signals
+
+
 class AnalyticsStore:
     """Persistent store for execution analytics.
 
@@ -77,10 +186,20 @@ class AnalyticsStore:
         self.storage_path.parent.mkdir(parents=True, exist_ok=True)
 
     def record(self, record: ExecutionRecord) -> None:
-        """Append an execution record (query redacted — F-06)."""
+        """Append an execution record (query redacted — F-06).
+
+        Also merges implicit feedback signals (seconds since last route,
+        rapid re-route, query overlap) derived from ``.vibe/last_route.json``
+        — additive fields only, absent when unavailable (M1d).
+        """
         try:
             data = record.to_dict()
             data["query"] = redact_sensitive(data["query"])
+            data.update(
+                LastRouteTracker(self.storage_path.parent).compute_and_update(
+                    record.query, record.primary_skill
+                )
+            )
             with self.storage_path.open("a", encoding="utf-8") as f:
                 f.write(json.dumps(data, ensure_ascii=False) + "\n")
         except OSError as e:
diff --git a/src/vibesop/core/routing/unified.py b/src/vibesop/core/routing/unified.py
index 08417a5..68d224b 100644
--- a/src/vibesop/core/routing/unified.py
+++ b/src/vibesop/core/routing/unified.py
@@ -624,9 +624,9 @@ class UnifiedRouter(
             self._tracer.record_layer(RoutingLayer.SCENARIO, scen_detail, len(candidates))
 
             idx_match, idx_detail = _layers.try_index_layer(self, query, candidates)  # pyright: ignore[reportArgumentType]
-            routing_path.append(RoutingLayer.AI_TRIAGE)
+            routing_path.append(RoutingLayer.SEMANTIC_INDEX)
             layer_details.append(idx_detail)
-            self._tracer.record_layer(RoutingLayer.AI_TRIAGE, idx_detail, len(candidates))
+            self._tracer.record_layer(RoutingLayer.SEMANTIC_INDEX, idx_detail, len(candidates))
 
             best = max(
                 (m for m in (scen_match, idx_match) if m is not None),
@@ -638,9 +638,9 @@ class UnifiedRouter(
         else:
             # Index standalone
             match, detail = _layers.try_index_layer(self, query, candidates)  # pyright: ignore[reportArgumentType]
-            routing_path.append(RoutingLayer.AI_TRIAGE)
+            routing_path.append(RoutingLayer.SEMANTIC_INDEX)
             layer_details.append(detail)
-            self._tracer.record_layer(RoutingLayer.AI_TRIAGE, detail, len(candidates))
+            self._tracer.record_layer(RoutingLayer.SEMANTIC_INDEX, detail, len(candidates))
             if match and match.confidence >= self._config.min_confidence:
                 return match
 
diff --git a/tests/core/routing/test_index_layer.py b/tests/core/routing/test_index_layer.py
index e3ea9fd..8b15cc6 100644
--- a/tests/core/routing/test_index_layer.py
+++ b/tests/core/routing/test_index_layer.py
@@ -6,6 +6,9 @@ import json
 from pathlib import Path
 from unittest.mock import MagicMock, patch
 
+from vibesop.core.config.manager import RoutingConfig
+from vibesop.core.models import LayerDetail, RoutingLayer
+from vibesop.core.routing import UnifiedRouter
 from vibesop.core.routing._layers import (
     _compute_index_score,
     _tokenize_query,
@@ -290,3 +293,61 @@ class TestEmbeddingFallback:
         assert match is None
         assert detail.matched is False
         assert "not available" in detail.reason.lower()
+
+
+class TestEarlyLayersRoutingPath:
+    """Regression: the semantic index layer must be recorded as SEMANTIC_INDEX
+    in routing_path and traces, not mislabeled as AI_TRIAGE (M1a)."""
+
+    def _make_router(self, tmp_path: Path) -> UnifiedRouter:
+        config = RoutingConfig(enable_ai_triage=False)
+        return UnifiedRouter(project_root=tmp_path, config=config)
+
+    def test_keyword_branch_records_semantic_index(self, tmp_path: Path) -> None:
+        """Scenario+index best-of branch: index layer is SEMANTIC_INDEX."""
+        router = self._make_router(tmp_path)
+        router._tracer.enabled = True
+        router._tracer.start_trace("review code")
+
+        routing_path: list[RoutingLayer] = []
+        layer_details: list[LayerDetail] = []
+        scen_detail = LayerDetail(layer=RoutingLayer.SCENARIO, matched=False, reason="miss")
+        idx_detail = LayerDetail(layer=RoutingLayer.SEMANTIC_INDEX, matched=False, reason="miss")
+
+        with (
+            patch(
+                "vibesop.core.routing._layers.try_scenario_layer",
+                return_value=(None, scen_detail),
+            ),
+            patch(
+                "vibesop.core.routing._layers.try_index_layer",
+                return_value=(None, idx_detail),
+            ),
+        ):
+            router._try_early_layers("review code", [], routing_path, layer_details, use_keyword=True)
+
+        assert routing_path == [RoutingLayer.SCENARIO, RoutingLayer.SEMANTIC_INDEX]
+        assert RoutingLayer.AI_TRIAGE not in routing_path
+        traced = [lt.layer for lt in router._tracer._current.layers]  # type: ignore[union-attr]
+        assert traced == ["scenario", "semantic_index"]
+
+    def test_llm_branch_records_semantic_index(self, tmp_path: Path) -> None:
+        """Index-standalone branch: index layer is SEMANTIC_INDEX."""
+        router = self._make_router(tmp_path)
+        router._tracer.enabled = True
+        router._tracer.start_trace("review code")
+
+        routing_path: list[RoutingLayer] = []
+        layer_details: list[LayerDetail] = []
+        idx_detail = LayerDetail(layer=RoutingLayer.SEMANTIC_INDEX, matched=False, reason="miss")
+
+        with patch(
+            "vibesop.core.routing._layers.try_index_layer",
+            return_value=(None, idx_detail),
+        ):
+            router._try_early_layers("review code", [], routing_path, layer_details, use_keyword=False)
+
+        assert routing_path == [RoutingLayer.SEMANTIC_INDEX]
+        assert RoutingLayer.AI_TRIAGE not in routing_path
+        traced = [lt.layer for lt in router._tracer._current.layers]  # type: ignore[union-attr]
+        assert traced == ["semantic_index"]
diff --git a/tests/core/test_analytics.py b/tests/core/test_analytics.py
index 9600cb4..96581aa 100644
--- a/tests/core/test_analytics.py
+++ b/tests/core/test_analytics.py
@@ -5,11 +5,13 @@ Covers: ExecutionRecord, AnalyticsStore record/list/stats/low-quality detection.
 
 from __future__ import annotations
 
+import json
+from datetime import UTC, datetime, timedelta
 from pathlib import Path
 
 import pytest
 
-from vibesop.core.analytics import AnalyticsStore, ExecutionRecord
+from vibesop.core.analytics import AnalyticsStore, ExecutionRecord, LastRouteTracker
 
 
 class TestExecutionRecord:
@@ -163,3 +165,145 @@ class TestAnalyticsStore:
         store = AnalyticsStore(storage_dir=str(tmp_path))
         assert store.list_records() == []
         assert store.get_low_quality_skills() == []
+
+
+def _read_jsonl(path: Path) -> list[dict]:
+    with path.open("r", encoding="utf-8") as f:
+        return [json.loads(line) for line in f if line.strip()]
+
+
+class TestLastRouteTracker:
+    """Implicit feedback signals derived from .vibe/last_route.json (M1d)."""
+
+    def test_first_route_yields_no_signals(self, tmp_path: Path) -> None:
+        tracker = LastRouteTracker(storage_dir=tmp_path)
+        signals = tracker.compute_and_update("fix the bug", "s1")
+        assert signals == {}
+        assert (tmp_path / "last_route.json").exists()
+
+    def test_rapid_reroute_with_overlapping_query(self, tmp_path: Path) -> None:
+        tracker = LastRouteTracker(storage_dir=tmp_path)
+        t0 = datetime(2026, 1, 1, tzinfo=UTC)
+        tracker.compute_and_update("fix the routing bug", "s1", now=t0)
+
+        signals = tracker.compute_and_update(
+            "fix the routing bug please", "s2", now=t0 + timedelta(seconds=5)
+        )
+        assert signals["seconds_since_last_route"] == pytest.approx(5.0)
+        assert signals["is_rapid_reroute"] is True
+        # {fix,the,routing,bug} vs {fix,the,routing,bug,please}: J = 4/5 > 0.5
+        assert signals["query_overlap_with_last"] is True
+
+    def test_slow_distinct_reroute(self, tmp_path: Path) -> None:
+        tracker = LastRouteTracker(storage_dir=tmp_path)
+        t0 = datetime(2026, 1, 1, tzinfo=UTC)
+        tracker.compute_and_update("fix the routing bug", "s1", now=t0)
+
+        signals = tracker.compute_and_update(
+            "write a release note", "s2", now=t0 + timedelta(seconds=60)
+        )
+        assert signals["seconds_since_last_route"] == pytest.approx(60.0)
+        assert signals["is_rapid_reroute"] is False
+        assert signals["query_overlap_with_last"] is False
+
+    def test_overlap_boundary(self, tmp_path: Path) -> None:
+        """Jaccard exactly at/below 0.5 is not flagged as a restatement."""
+        tracker = LastRouteTracker(storage_dir=tmp_path)
+        t0 = datetime(2026, 1, 1, tzinfo=UTC)
+        tracker.compute_and_update("alpha beta gamma", "s1", now=t0)
+        # {alpha,beta,gamma} vs {alpha,beta,delta}: J = 2/4 = 0.5 → not > 0.5
+        signals = tracker.compute_and_update(
+            "alpha beta delta", "s2", now=t0 + timedelta(seconds=30)
+        )
+        assert signals["query_overlap_with_last"] is False
+
+    def test_state_file_stores_hashes_not_raw_query(self, tmp_path: Path) -> None:
+        tracker = LastRouteTracker(storage_dir=tmp_path)
+        tracker.compute_and_update("email alice@corp.com about routing", "s1")
+        raw = (tmp_path / "last_route.json").read_text(encoding="utf-8")
+        assert "alice@corp.com" not in raw
+        assert "routing" not in raw
+        state = json.loads(raw)
+        assert set(state) == {"query_hash", "token_hashes", "skill", "timestamp"}
+        assert state["skill"] == "s1"
+
+    def test_corrupt_state_degrades_and_self_heals(self, tmp_path: Path) -> None:
+        (tmp_path / "last_route.json").write_text("{not json", encoding="utf-8")
+        tracker = LastRouteTracker(storage_dir=tmp_path)
+        t0 = datetime(2026, 1, 1, tzinfo=UTC)
+
+        signals = tracker.compute_and_update("fix the bug", "s1", now=t0)
+        assert signals == {}  # no crash, no implicit fields
+
+        # State was rewritten → next route gets signals again.
+        signals = tracker.compute_and_update(
+            "fix the bug", "s1", now=t0 + timedelta(seconds=3)
+        )
+        assert signals["is_rapid_reroute"] is True
+
+    def test_lock_contention_yields_no_signals(self, tmp_path: Path) -> None:
+        from vibesop.utils.file_lock import cross_process_lock
+
+        tracker = LastRouteTracker(storage_dir=tmp_path)
+        with cross_process_lock(tmp_path / "last_route.lock", blocking=False):
+            signals = tracker.compute_and_update("fix the bug", "s1")
+        assert signals == {}  # contention must never raise
+
+    def test_malformed_timestamp_skips_time_signals(self, tmp_path: Path) -> None:
+        (tmp_path / "last_route.json").write_text(
+            json.dumps({"timestamp": "not-a-date", "token_hashes": ["x"]}),
+            encoding="utf-8",
+        )
+        tracker = LastRouteTracker(storage_dir=tmp_path)
+        signals = tracker.compute_and_update("fix the bug", "s1")
+        assert "seconds_since_last_route" not in signals
+        assert "is_rapid_reroute" not in signals
+
+
+class TestAnalyticsImplicitSignals:
+    """AnalyticsStore.record merges implicit signals into the JSONL event."""
+
+    def test_first_record_has_no_implicit_fields(self, tmp_path: Path) -> None:
+        store = AnalyticsStore(storage_dir=str(tmp_path))
+        store.record(ExecutionRecord(query="q1", primary_skill="s1"))
+        (event,) = _read_jsonl(tmp_path / "analytics.jsonl")
+        assert "seconds_since_last_route" not in event
+        assert "is_rapid_reroute" not in event
+        assert "query_overlap_with_last" not in event
+
+    def test_second_record_carries_implicit_fields(self, tmp_path: Path) -> None:
+        store = AnalyticsStore(storage_dir=str(tmp_path))
+        store.record(ExecutionRecord(query="fix the routing bug", primary_skill="s1"))
+        store.record(ExecutionRecord(query="fix the routing bug now", primary_skill="s2"))
+
+        events = _read_jsonl(tmp_path / "analytics.jsonl")
+        assert len(events) == 2
+        second = events[1]
+        assert second["seconds_since_last_route"] >= 0
+        assert second["is_rapid_reroute"] is True
+        assert second["query_overlap_with_last"] is True
+        # Existing fields untouched.
+        assert second["query"] == "fix the routing bug now"
+        assert second["primary_skill"] == "s2"
+
+    def test_records_with_new_fields_still_parse(self, tmp_path: Path) -> None:
+        """Old reader code paths (from_dict ignores unknown keys) stay valid."""
+        store = AnalyticsStore(storage_dir=str(tmp_path))
+        store.record(ExecutionRecord(query="q1", primary_skill="s1"))
+        store.record(ExecutionRecord(query="q1 again", primary_skill="s1"))
+
+        records = store.list_records()
+        assert len(records) == 2
+        assert records[1].query == "q1 again"
+
+    def test_record_survives_lock_contention(self, tmp_path: Path) -> None:
+        """Lock contention drops implicit fields but never the analytics write."""
+        from vibesop.utils.file_lock import cross_process_lock
+
+        store = AnalyticsStore(storage_dir=str(tmp_path))
+        with cross_process_lock(tmp_path / "last_route.lock", blocking=False):
+            store.record(ExecutionRecord(query="q1", primary_skill="s1"))
+
+        (event,) = _read_jsonl(tmp_path / "analytics.jsonl")
+        assert event["query"] == "q1"
+        assert "is_rapid_reroute" not in event

## 新文件: scripts/replay_routing.py
#!/usr/bin/env python3
"""Offline replay harness for historical routing decisions (M1b).

Re-routes queries from a project's analytics.jsonl with the current code
and diffs the new decisions against the recorded ones: agreement rate,
old-vs-new layer distribution, and the top changed queries. Use --no-llm
to disable AI triage and replay only the deterministic layers (the config
knob RoutingConfig.enable_ai_triage=False, same as eval_routing.py's
record_telemetry=False escape hatch, keeps replay from writing telemetry).

Usage:
    uv run python scripts/replay_routing.py \
        --log /path/.vibe/analytics.jsonl [--limit 200] [--no-llm] \
        [--output replay-report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

_USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)
TOP_CHANGES = 20


def strip_wrapper(query: str) -> str:
    """Remove the <user_query>...</user_query> wrapper if present."""
    m = _USER_QUERY_RE.search(query)
    return (m.group(1) if m else query).strip()


def load_records(log_path: Path, limit: int | None = None) -> tuple[list[dict], int]:
    """Load replayable records from analytics.jsonl.

    Returns (records, skipped). Each record carries the cleaned query plus
    the historical decision (old_primary / old_layer, the last layer in the
    recorded routing path). Lines that are unparseable, lack a query, or
    contain system-reminder junk are skipped.
    """
    records: list[dict] = []
    skipped = 0
    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        raw = entry.get("query")
        if not isinstance(raw, str) or "<system-reminder" in raw:
            skipped += 1
            continue
        query = strip_wrapper(raw)
        if not query:
            skipped += 1
            continue
        layers = entry.get("routing_layers")
        old_layer = layers[-1] if isinstance(layers, list) and layers else None
        records.append(
            {
                "query": query,
                "old_primary": entry.get("primary_skill"),
                "old_layer": old_layer,
            }
        )
        if limit is not None and len(records) >= limit:
            break
    return records, skipped


def replay(router: Any, records: list[dict]) -> list[dict]:
    """Re-route each record's query with the given router, in place.

    The router only needs a ``route(query, record_telemetry=False)`` method
    returning an object with a ``primary`` SkillRoute (or None) — tests pass
    a stub. Each record gains new_primary / new_layer / new_confidence.
    """
    for rec in records:
        result = router.route(rec["query"], record_telemetry=False)
        primary = result.primary
        rec["new_primary"] = primary.skill_id if primary else None
        rec["new_layer"] = primary.layer.value if primary else "no_match"
        rec["new_confidence"] = round(primary.confidence, 4) if primary else 0.0
    return records


def build_report(records: list[dict], skipped: int, *, no_llm: bool) -> dict:
    """Diff old vs new decisions into a JSON-serializable report."""
    total = len(records)
    changed = [r for r in records if r["new_primary"] != r["old_primary"]]
    old_dist: dict[str, int] = {}
    new_dist: dict[str, int] = {}
    for r in records:
        old_dist[r["old_layer"] or "unknown"] = old_dist.get(r["old_layer"] or "unknown", 0) + 1
        new_dist[r["new_layer"]] = new_dist.get(r["new_layer"], 0) + 1

    # "Largest" changes = the most confident flips (a high-confidence new
    # decision overriding the log is the most consequential drift).
    top_changes = sorted(changed, key=lambda r: -r["new_confidence"])[:TOP_CHANGES]

    return {
        "no_llm": no_llm,
        "total": total,
        "skipped": skipped,
        "agreement": {
            "matches": total - len(changed),
            "changed": len(changed),
            "rate": round((total - len(changed)) / total, 4) if total else 0.0,
        },
        "layer_distribution": {"old": old_dist, "new": new_dist},
        "top_changes": top_changes,
    }


def _print_summary(report: dict) -> None:
    ag = report["agreement"]
    print("\n=== Routing Replay ===")
    print(
        f"replayed: {report['total']} | skipped: {report['skipped']} | "
        f"no_llm: {report['no_llm']}"
    )
    print(
        f"agreement: {ag['matches']}/{report['total']} ({ag['rate']:.1%}) | "
        f"changed: {ag['changed']}"
    )
    print("\nLayer distribution (old -> new):")
    for layer, n in sorted(report["layer_distribution"]["old"].items(), key=lambda kv: -kv[1]):
        new_n = report["layer_distribution"]["new"].get(layer, 0)
        print(f"  {layer}: {n} -> {new_n}")
    for layer, n in sorted(report["layer_distribution"]["new"].items(), key=lambda kv: -kv[1]):
        if layer not in report["layer_distribution"]["old"]:
            print(f"  {layer}: 0 -> {n}")
    if report["top_changes"]:
        print(f"\nTop changes ({len(report['top_changes'])}):")
        for r in report["top_changes"]:
            print(f"  {r['old_primary']} -> {r['new_primary']} ({r['new_confidence']:.0%})")
            print(f"      {r['query'][:70]!r}")


def _build_router(no_llm: bool):
    """Build a UnifiedRouter; --no-llm disables the AI triage layer via the
    existing RoutingConfig.enable_ai_triage knob (no production changes)."""
    from vibesop.core.config import ConfigManager
    from vibesop.core.routing.unified import UnifiedRouter

    config_manager = ConfigManager(project_root=ROOT)
    config = config_manager.get_routing_config()
    if no_llm:
        config = config.model_copy(update={"enable_ai_triage": False})
    return UnifiedRouter(project_root=ROOT, config=config)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True, help="path to analytics.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="max records to replay")
    parser.add_argument("--output", type=Path, default=None, help="write JSON report here")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="disable AI triage; replay deterministic layers only",
    )
    args = parser.parse_args()

    records, skipped = load_records(args.log, args.limit)
    router = _build_router(args.no_llm)
    replay(router, records)
    report = build_report(records, skipped, no_llm=args.no_llm)
    report["log"] = str(args.log)

    _print_summary(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nReport written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

## 新文件: scripts/build_eval_from_logs.py
#!/usr/bin/env python3
"""Build an extended routing eval set from production logs (M1c).

Extracts candidate queries from a project's analytics.jsonl, stratified-
samples them by length bucket, weak-labels them with the AI triage log's
query -> selected_skill mapping, and writes a new YAML eval file. The
hand-curated tests/benchmark/routing_eval.yaml is never overwritten;
--merge appends human-confirmed entries (needs_review: false) into it.

Usage:
    uv run python scripts/build_eval_from_logs.py \
        --analytics /path/.vibe/analytics.jsonl \
        --triage /path/.vibe/ai_triage_log.jsonl
    uv run python scripts/build_eval_from_logs.py --merge
"""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MAIN_EVAL = ROOT / "tests" / "benchmark" / "routing_eval.yaml"
DEFAULT_OUTPUT = ROOT / "tests" / "benchmark" / "routing_eval_extended.yaml"

_USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)
_WS_RE = re.compile(r"\s+")

# Length buckets (chars): short / medium / long.
BUCKETS = ("short", "medium", "long")


def normalize(text: str) -> str:
    """Collapse all whitespace runs so dedup is formatting-insensitive."""
    return _WS_RE.sub(" ", text).strip()


def strip_wrapper(query: str) -> str:
    """Remove the <user_query>...</user_query> wrapper if present."""
    m = _USER_QUERY_RE.search(query)
    return m.group(1) if m else query


def extract_queries(analytics_path: Path) -> list[str]:
    """Extract unique candidate queries from an analytics.jsonl file."""
    seen: set[str] = set()
    queries: list[str] = []
    for raw_line in analytics_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        raw = record.get("query")
        if not isinstance(raw, str):
            continue
        if "<system-reminder" in raw:
            continue
        query = normalize(strip_wrapper(raw))
        if not query or query in seen:
            continue
        seen.add(query)
        queries.append(query)
    return queries


def bucket_of(query: str) -> str:
    n = len(query)
    if n <= 15:
        return "short"
    if n <= 50:
        return "medium"
    return "long"


def stratified_sample(queries: list[str], n: int, seed: int = 42) -> list[str]:
    """Sample ~n queries, allocating per bucket proportionally to the real
    distribution so the short-query share (~30%) is preserved."""
    by_bucket: dict[str, list[str]] = {b: [] for b in BUCKETS}
    for q in queries:
        by_bucket[bucket_of(q)].append(q)

    rng = random.Random(seed)
    total = len(queries)
    sampled: list[str] = []
    for bucket in BUCKETS:
        pool = by_bucket[bucket]
        quota = min(len(pool), round(n * len(pool) / total)) if total else 0
        sampled.extend(rng.sample(pool, quota))
    rng.shuffle(sampled)
    return sampled


def load_triage_labels(triage_path: Path) -> dict[str, str]:
    """Build normalized query -> selected_skill map; latest record wins."""
    labels: dict[str, str] = {}
    if not triage_path.exists():
        return labels
    for raw_line in triage_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        query, skill = record.get("query"), record.get("selected_skill")
        if isinstance(query, str) and isinstance(skill, str) and skill:
            labels[normalize(strip_wrapper(query))] = skill
    return labels


def build_entries(
    queries: list[str], labels: dict[str, str]
) -> list[dict]:
    """Weak-label sampled queries. Every entry needs human review."""
    entries = []
    for q in queries:
        skill = labels.get(normalize(q))
        entry: dict = {
            "query": q,
            "expect": [skill] if skill else [],
            "category": "production_log",
            "needs_review": True,
        }
        if skill:
            entry["weak_label"] = True
        entries.append(entry)
    return entries


def merge_confirmed(extended_path: Path, main_path: Path = MAIN_EVAL) -> int:
    """Append human-confirmed entries (needs_review: false, expect set)
    from the extended file into the main eval set, and drop them from the
    extended file. Returns the number of merged entries."""
    extended = yaml.safe_load(extended_path.read_text(encoding="utf-8")) or []
    main = yaml.safe_load(main_path.read_text(encoding="utf-8")) or []
    main_queries = {normalize(e["query"]) for e in main}

    confirmed, remaining = [], []
    for e in extended:
        if e.get("needs_review") is False and e.get("expect"):
            if normalize(e["query"]) not in main_queries:
                confirmed.append(
                    {k: v for k, v in e.items() if k not in ("needs_review", "weak_label")}
                )
                main_queries.add(normalize(e["query"]))
        else:
            remaining.append(e)

    if confirmed:
        with main_path.open("a", encoding="utf-8") as f:
            f.write(yaml.safe_dump(confirmed, allow_unicode=True, sort_keys=False))
        extended_path.write_text(
            yaml.safe_dump(remaining, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return len(confirmed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analytics", type=Path, help="path to analytics.jsonl")
    parser.add_argument("--triage", type=Path, help="path to ai_triage_log.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--n", type=int, default=130, help="sample size")
    parser.add_argument("--seed", type=int, default=42, help="sampling seed")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="merge human-confirmed entries from --output into the main eval set",
    )
    args = parser.parse_args()

    if args.merge:
        merged = merge_confirmed(args.output)
        print(f"Merged {merged} confirmed entries into {MAIN_EVAL.name}.")
        return 0

    if not args.analytics:
        parser.error("--analytics is required unless --merge is passed")

    queries = extract_queries(args.analytics)
    sampled = stratified_sample(queries, args.n, args.seed)
    labels = load_triage_labels(args.triage) if args.triage else {}
    entries = build_entries(sampled, labels)

    labeled = sum(1 for e in entries if e.get("weak_label"))
    args.output.write_text(
        "# Extended routing eval set, weak-labeled from production logs (M1c).\n"
        "# All entries need human review; confirm via --merge after fixing "
        "expect/needs_review.\n"
        + yaml.safe_dump(entries, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(
        f"extracted: {len(queries)} | sampled: {len(sampled)} "
        f"(short/medium/long: "
        + "/".join(str(sum(1 for e in entries if bucket_of(e["query"]) == b)) for b in BUCKETS)
        + f") | weak-labeled: {labeled} -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
