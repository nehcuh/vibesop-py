"""W3 Task C — should_replay() decision logic.

Contract:
1. ``should_replay(query, spans, learner=None)`` → ``should_prompt=False``, reason="no_learner"
2. ``should_replay(query, [], learner)`` → ``should_prompt=False``, reason="no_recall"
3. ``should_replay(query, spans, learner)`` where top match is_gold → ``should_prompt=True``, reason="gold_match"
4. ``should_replay(query, spans, learner)`` where top match not gold → ``should_prompt=False``, reason="not_gold"
5. ``top_match`` is the highest-similarity RecallResult when recall returns matches.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.recall import RecallResult
from vibesop.core.observability.replay import ReplayDecision, emit_replay_span, should_replay


def _unit_vec(angle: float, dim: int = 384) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[0] = np.cos(angle)
    v[1] = np.sin(angle)
    return v


def _fake_embedding(query: str) -> np.ndarray:
    """Deterministic angle-based fake embedding (same as test_recall)."""
    import hashlib

    h = int(hashlib.sha1(query.encode()).hexdigest(), 16)
    return _unit_vec((h % 360) * (np.pi / 180.0))


def _span(
    task_id: str,
    query: str,
    *,
    timestamp: datetime | None = None,
    trace_id: str | None = None,
) -> dict:
    ts = timestamp or datetime.now(UTC)
    s = {
        "task_id": task_id,
        "input_data": {"query": query},
        "name": "route:query",
        "timestamp": ts.isoformat(),
        "project_id": "test",
    }
    if trace_id:
        s["trace_id"] = trace_id
    return s


def _fake_learner(*, success_count: int) -> MagicMock:
    """Build a fake learner whose get_instinct_for_query returns an instinct
    with the given success_count."""
    learner = MagicMock()
    instinct = MagicMock()
    instinct.success_count = success_count
    learner.get_instinct_for_query.return_value = instinct
    return learner


def _parse_metadata(raw: dict | str | None) -> dict:
    """SpanWriter persists non-empty metadata as JSON string; parse back to dict."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


@pytest.fixture
def cache(tmp_path: Path) -> EmbeddingCache:
    return EmbeddingCache(cache_path=tmp_path / "emb.npz")


class TestShouldReplayDecisions:
    def test_no_learner_no_prompt(self, cache: EmbeddingCache) -> None:
        spans = [_span("t1", "hello") for _ in range(5)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            d = should_replay("hello", spans, cache=cache, learner=None)
        assert d.should_prompt is False
        assert d.reason == "no_learner"
        assert d.top_match is None

    def test_no_spans_no_prompt(self, cache: EmbeddingCache) -> None:
        learner = _fake_learner(success_count=5)
        d = should_replay("hello", [], cache=cache, learner=learner)
        assert d.should_prompt is False
        assert d.reason == "no_recall"
        assert d.top_match is None

    def test_no_recall_above_threshold(self, cache: EmbeddingCache) -> None:
        """Spans exist but no task_id extractable → no_recall (spans skipped)."""
        learner = _fake_learner(success_count=5)
        # Spans without task_id → recall skips them → empty results
        spans = [
            {
                "input_data": {"query": "no task"},
                "name": "route:query",
                "timestamp": datetime.now(UTC).isoformat(),
                "project_id": "test",
            }
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            d = should_replay("hello", spans, cache=cache, learner=learner)
        assert d.should_prompt is False
        assert d.reason == "no_recall"

    def test_gold_match_prompts(self, cache: EmbeddingCache) -> None:
        """Top match with is_gold=True → prompt."""
        learner = _fake_learner(success_count=3)
        # 5 spans same task, no trace_id → size_signal falls back to span_count
        spans = [_span("t1", "hello") for _ in range(5)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            d = should_replay("hello", spans, cache=cache, learner=learner)
        assert d.should_prompt is True
        assert d.reason == "gold_match"
        assert d.top_match is not None
        assert d.top_match.task_id == "t1"
        assert d.top_match.is_gold is True

    def test_gold_match_via_distinct_traces(self, cache: EmbeddingCache) -> None:
        """W3 Fix-1: gold gate counts distinct trace_ids, not span lines.

        3 spans with 3 distinct trace_ids → distinct_trace_count=3 → gold.
        A single chatty trace (3 spans same trace_id) must NOT meet gate.
        """
        learner = _fake_learner(success_count=2)

        # 3 distinct traces (1 span each) → gold
        spans_distinct = [_span("t1", "hello", trace_id=f"T-{i}") for i in range(3)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            d_distinct = should_replay("hello", spans_distinct, cache=cache, learner=learner)
        assert d_distinct.should_prompt is True
        assert d_distinct.reason == "gold_match"
        assert d_distinct.top_match is not None
        assert d_distinct.top_match.distinct_trace_count == 3

        # 1 trace with 5 nested spans → distinct_trace_count=1 → not gold
        spans_chatty = [_span("t1", "hello", trace_id="T-single") for _ in range(5)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            d_chatty = should_replay("hello", spans_chatty, cache=cache, learner=learner)
        assert d_chatty.should_prompt is False
        assert d_chatty.reason == "not_gold"
        assert d_chatty.top_match is not None
        assert d_chatty.top_match.distinct_trace_count == 1

    def test_gold_at_rank_2_prompts(self, cache: EmbeddingCache) -> None:
        """W3 Fix-4 (P1-1): rank-1 non-gold + rank-2 gold → should prompt.

        should_replay scans top-3 for first gold, not just rank-1.
        """
        learner = MagicMock()

        def lookup(query: str) -> MagicMock | None:
            if "alpha" in query:
                return None  # rank-1 has no instinct
            if "beta" in query:
                instinct = MagicMock()
                instinct.success_count = 2
                return instinct
            return None

        learner.get_instinct_for_query.side_effect = lookup

        # Force controlled similarities via a custom embedding that maps
        # both "alpha" and "beta" queries to nearby vectors.
        def _ranked_embedding(query: str) -> np.ndarray:
            v = np.zeros(384, dtype=np.float32)
            if "alpha" in query.lower():
                v[0] = 1.0  # exact match for the test query
                v[1] = 0.1
            elif "beta" in query.lower():
                v[0] = 0.9  # very similar to alpha
                v[1] = 0.5
            else:
                v[99] = 1.0
            n = np.linalg.norm(v)
            return v / n if n > 0 else v

        spans_a = [_span("t_a", "alpha query", trace_id=f"T-a-{i}") for i in range(3)]
        spans_b = [_span("t_b", "beta query", trace_id=f"T-b-{i}") for i in range(3)]
        spans = spans_a + spans_b

        with patch.object(cache, "_compute", side_effect=_ranked_embedding):
            d = should_replay("alpha query", spans, cache=cache, learner=learner, threshold=0.30)

        # t_a is rank-1 (higher similarity) but not gold; t_b is gold.
        # New contract: scan top-3 for first gold.
        assert d.should_prompt is True
        assert d.reason == "gold_match"
        assert d.top_match is not None
        assert d.top_match.task_id == "t_b"

    def test_top_match_not_gold_no_prompt(self, cache: EmbeddingCache) -> None:
        """Match found but not gold → no prompt, but top_match still returned."""
        # Only 2 spans → span_count < 5 → not gold even with success
        learner = _fake_learner(success_count=3)
        spans = [_span("t1", "hello") for _ in range(2)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            d = should_replay("hello", spans, cache=cache, learner=learner)
        assert d.should_prompt is False
        assert d.reason == "not_gold"
        assert d.top_match is not None, "top_match should still be surfaced"
        assert d.top_match.task_id == "t1"
        assert d.top_match.is_gold is False

    def test_no_instinct_for_query_not_gold(self, cache: EmbeddingCache) -> None:
        """Recall finds match but learner has no instinct → not_gold."""
        learner = MagicMock()
        learner.get_instinct_for_query.return_value = None
        spans = [_span("t1", "hello") for _ in range(5)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            d = should_replay("hello", spans, cache=cache, learner=learner)
        assert d.should_prompt is False
        assert d.reason == "not_gold"

    def test_zero_success_count_not_gold(self, cache: EmbeddingCache) -> None:
        """Instinct exists but success_count=0 → not_gold."""
        learner = _fake_learner(success_count=0)
        spans = [_span("t1", "hello") for _ in range(5)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            d = should_replay("hello", spans, cache=cache, learner=learner)
        assert d.should_prompt is False
        assert d.reason == "not_gold"


class TestReplayDecisionDataclass:
    def test_decision_fields(self) -> None:
        d = ReplayDecision(should_prompt=True, top_match=None, reason="gold_match")
        assert d.should_prompt is True
        assert d.top_match is None
        assert d.reason == "gold_match"

    def test_decision_with_top_match(self) -> None:
        r = RecallResult(
            task_id="t1",
            similarity=0.92,
            representative_query="hello",
            span_count=5,
        )
        d = ReplayDecision(should_prompt=True, top_match=r, reason="gold_match")
        assert d.top_match is not None
        assert d.top_match.task_id == "t1"


class TestShouldReplayCarriesTraceId:
    """W3 replay prompt needs trace_id from top_match to emit replay span."""

    def test_top_match_carries_trace_id(self, cache: EmbeddingCache) -> None:
        learner = _fake_learner(success_count=3)
        spans = [
            _span("t1", "hello", trace_id=f"T-{i}")
            for i in range(5)
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            d = should_replay("hello", spans, cache=cache, learner=learner)
        assert d.top_match is not None
        assert d.top_match.trace_id is not None
        assert d.top_match.trace_id.startswith("T-")


class TestEmitReplaySpan:
    """W3.4: emit_replay_span writes provenance marker into current trace."""

    def test_emit_replay_span_returns_trace_id(self, tmp_path: Path) -> None:
        from vibesop.core.observability.tracer import ObservabilityTracer

        storage = tmp_path / "spans.jsonl"
        tracer = ObservabilityTracer(storage_path=storage, enabled=True)
        top_match = RecallResult(
            task_id="t1",
            similarity=0.92,
            representative_query="hello world",
            span_count=5,
            trace_id="T-old-abc",
            skill_id="cmspark-fix",
            is_gold=True,
            gold_success_count=3,
        )
        with tracer.trace("route:outer", task_id="t_new"):
            returned = emit_replay_span(tracer, top_match)
        assert returned is not None, "should return the active trace_id"

    def test_emit_replay_span_metadata(self, tmp_path: Path) -> None:
        """Span metadata should carry replay_of + skill_id + similarity."""
        from vibesop.core.observability.span_writer import SpanWriter
        from vibesop.core.observability.tracer import ObservabilityTracer

        storage = tmp_path / "spans.jsonl"
        tracer = ObservabilityTracer(storage_path=storage, enabled=True)

        top_match = RecallResult(
            task_id="t_old",
            similarity=0.88,
            representative_query="prior query",
            span_count=7,
            trace_id="T-prior-123",
            skill_id="my-skill",
            is_gold=True,
            gold_success_count=4,
        )
        with tracer.trace("route:query", task_id="t_new"):
            emit_replay_span(tracer, top_match)

        # Read back spans
        spans = SpanWriter(storage_path=storage).query_recent(limit=10)
        replay_spans = [s for s in spans if s.get("name", "").startswith("replay:")]
        assert len(replay_spans) == 1, f"expected 1 replay span, got {len(replay_spans)}"
        rs = replay_spans[0]
        assert rs["name"] == "replay:t_old"
        assert rs["span_kind"] == "workflow_node"
        # SpanWriter serializes non-empty metadata as JSON string (existing convention)
        meta = _parse_metadata(rs.get("metadata"))
        assert meta.get("replay_of") == "T-prior-123"
        assert meta.get("old_task_id") == "t_old"
        assert meta.get("old_query") == "prior query"
        assert meta.get("skill_id") == "my-skill"
        assert meta.get("similarity") == 0.88
        assert meta.get("gold_success_count") == 4

    def test_emit_replay_span_extra_metadata_merged(self, tmp_path: Path) -> None:
        """Caller can pass extra_metadata to add fields."""
        from vibesop.core.observability.span_writer import SpanWriter
        from vibesop.core.observability.tracer import ObservabilityTracer

        storage = tmp_path / "spans.jsonl"
        tracer = ObservabilityTracer(storage_path=storage, enabled=True)

        top_match = RecallResult(
            task_id="t1",
            similarity=0.9,
            representative_query="hello",
            span_count=5,
            trace_id="T-old",
        )
        with tracer.trace("route:query", task_id="t_new"):
            emit_replay_span(tracer, top_match, extra_metadata={"user_confirmed_at": "2026-07-29"})

        spans = SpanWriter(storage_path=storage).query_recent(limit=10)
        rs = next(s for s in spans if s.get("name", "").startswith("replay:"))
        meta = _parse_metadata(rs.get("metadata"))
        assert meta["user_confirmed_at"] == "2026-07-29"
        assert meta["replay_of"] == "T-old"  # original still there

    def test_emit_replay_span_tracer_failure_no_crash(self) -> None:
        """If tracer raises, emit_replay_span logs + returns None (no crash)."""
        from vibesop.core.observability.recall import RecallResult

        bad_tracer = MagicMock()
        bad_tracer.span.side_effect = RuntimeError("tracer broken")
        top_match = RecallResult(
            task_id="t1",
            similarity=0.9,
            representative_query="hello",
            span_count=5,
            trace_id="T-old",
        )
        result = emit_replay_span(bad_tracer, top_match)
        assert result is None, "should return None on tracer failure, not crash"
