"""W3 Task F — fixture-based acceptance smoke for replay flow.

Replaces the original kill-switch "follow rate >= 30%" criterion (which
requires real users + product telemetry) with a fixture-based smoke
that proves the algorithmic preconditions for replay hold:

1. ``should_replay`` returns True for a query that matches a gold task
   (5+ spans + InstinctLearner.success_count >= 1).
2. ``should_replay`` returns False for a task with too few spans
   (lidsleep has 2 spans → not_gold).
3. ``should_replay`` returns False for a task with no instinct
   (distract has no success record).
4. ``emit_replay_span`` produces a span with provenance metadata
   linking new trace_id ↔ old trace_id.
5. Replay prompt carries trace_id + skill_id + step_sequence.

Same fixture-based smoke pattern as W2 (replaces expensive real-LLM
follow-rate telemetry with deterministic algorithmic preconditions).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.recall import RecallResult
from vibesop.core.observability.replay import emit_replay_span, should_replay
from vibesop.core.observability.span_writer import SpanWriter
from vibesop.core.observability.tracer import ObservabilityTracer

FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "replay_gold_spans.jsonl"


def _load_fixture() -> list[dict]:
    spans: list[dict] = []
    with FIXTURE.open() as f:
        for line in f:
            line = line.strip()
            if line:
                spans.append(json.loads(line))
    return spans


def _keyword_embedding(query: str) -> np.ndarray:
    """Same multilingual keyword embedding as W2 acceptance smoke."""
    semantic_clusters = {
        "screenshot": ["screenshot", "截图", "screen capture"],
        "permission": ["permission", "权限", "authorization"],
        "popup": ["popup", "弹窗", "prompt", "反复"],
        "cmspark": ["cmspark"],
        "lid_sleep": ["lid", "合盖", "sleep", "clamshell", "closed"],
        "overheating": ["overheating", "发热", "hot", "thermal"],
        "rust": ["rust", "tokio", "async"],
    }
    v = np.zeros(16, dtype=np.float32)
    q_lower = query.lower()
    for dim, kws in enumerate(semantic_clusters.values()):
        if any(kw in q_lower for kw in kws):
            v[dim] = 1.0
    norm = np.linalg.norm(v)
    if norm > 0:
        v = v / norm
    return v


def _fake_learner_for_query(success_map: dict[str, int]) -> MagicMock:
    """Build a fake learner whose get_instinct_for_query returns instincts
    based on a {query_substring: success_count} map. Returns None for
    queries that don't match any key."""

    def lookup(query: str) -> MagicMock | None:
        q_lower = query.lower()
        for key, count in success_map.items():
            if key in q_lower:
                instinct = MagicMock()
                instinct.success_count = count
                return instinct
        return None

    learner = MagicMock()
    learner.get_instinct_for_query.side_effect = lookup
    return learner


@pytest.fixture
def fixture_spans() -> list[dict]:
    return _load_fixture()


@pytest.fixture
def cache(tmp_path: Path) -> EmbeddingCache:
    return EmbeddingCache(cache_path=tmp_path / "emb.npz", dim=64)


class TestFixtureIntegrity:
    """Sanity checks on the replay fixture."""

    def test_fixture_has_14_spans(self) -> None:
        spans = _load_fixture()
        assert len(spans) == 14

    def test_cmspark_has_5_distinct_traces_for_gold_threshold(self) -> None:
        """cmspark task must have ≥3 distinct trace_ids for is_gold=True
        (min_gold_run_count=3)."""
        spans = _load_fixture()
        cmspark = [s for s in spans if "cmspark" in s.get("task_id", "")]
        distinct = {s["trace_id"] for s in cmspark if s.get("trace_id")}
        assert len(distinct) >= 3, f"cmspark has {len(distinct)} traces, need ≥3"

    def test_lidsleep_has_only_1_distinct_trace_below_gold_threshold(self) -> None:
        """lidsleep task must have <3 distinct traces to test not_gold path."""
        spans = _load_fixture()
        lidsleep = [s for s in spans if "lidsleep" in s.get("task_id", "")]
        distinct = {s["trace_id"] for s in lidsleep if s.get("trace_id")}
        assert len(distinct) < 3

    def test_all_spans_have_trace_id(self) -> None:
        spans = _load_fixture()
        for s in spans:
            assert "trace_id" in s, f"missing trace_id: {s.get('task_id')}"
            assert s["trace_id"], "trace_id must be non-empty"

    def test_all_spans_have_skill_id(self) -> None:
        spans = _load_fixture()
        for s in spans:
            meta = s.get("metadata", {})
            assert meta.get("skill_id"), f"missing skill_id: {s.get('task_id')}"


class TestReplayDecisionOnGoldMatch:
    """W3 kill-switch preconditions: gold match triggers replay."""

    def test_cmspark_gold_match_triggers_replay(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        """Top match for cmspark query has is_gold=True → should_prompt=True."""
        learner = _fake_learner_for_query({"cmspark": 3, "lidsleep": 0})
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            d = should_replay(
                "cmspark screenshot permission popup",
                fixture_spans,
                cache=cache,
                learner=learner,
                threshold=0.30,
            )
        assert d.should_prompt is True, (
            f"cmspark gold match should trigger replay; reason={d.reason}"
        )
        assert d.reason == "gold_match"
        assert d.top_match is not None
        assert "cmspark" in d.top_match.task_id
        assert d.top_match.is_gold is True
        assert d.top_match.gold_success_count == 3

    def test_lidsleep_few_spans_not_gold(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        """lidsleep has only 1 distinct trace → not_gold even with success signal.

        Isolate from cmspark gold contamination by filtering fixture to
        lidsleep spans only.
        """
        # Filter to only lidsleep spans — cmspark would otherwise dominate
        # the top-3 with its 5 distinct traces + gold instinct.
        spans = [s for s in fixture_spans if "lidsleep" in s.get("task_id", "")]
        assert len(spans) >= 1

        # Lookup keys match representative_query content
        learner = _fake_learner_for_query({"lid": 2, "overheating": 2})
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            d = should_replay(
                "macbook lid closed overheating",
                spans,
                cache=cache,
                learner=learner,
                threshold=0.30,
            )
        # lidsleep matches but not gold (distinct_trace_count=1 < 3)
        assert d.should_prompt is False
        assert d.reason == "not_gold"
        assert d.top_match is not None
        assert d.top_match.is_gold is False
        assert d.top_match.gold_success_count == 2, "success_count surfaced even when not gold"
        assert d.top_match.distinct_trace_count == 1

    def test_distract_no_instinct_not_gold(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        """rust query → no instinct → not_gold."""
        learner = _fake_learner_for_query({"cmspark": 3, "lid": 2})  # no rust key
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            d = should_replay(
                "rust async tokio runtime question",
                fixture_spans,
                cache=cache,
                learner=learner,
                threshold=0.30,
            )
        assert d.should_prompt is False
        assert d.reason in {"not_gold", "no_recall"}


class TestReplaySpanEmission:
    """W3 replay span carries provenance metadata."""

    def test_emit_replay_span_carries_provenance(self, tmp_path: Path) -> None:
        storage = tmp_path / "spans.jsonl"
        tracer = ObservabilityTracer(storage_path=storage, enabled=True)

        top_match = RecallResult(
            task_id="t_cmspark_replay",
            similarity=0.92,
            representative_query="cmspark screenshot popup",
            span_count=7,
            step_sequence=["route:query", "llm:claude", "tool:edit"],
            last_seen="2026-07-25T09:01:00+00:00",
            trace_id="T-cmspark-3",
            skill_id="cmspark-permission-fix",
            is_gold=True,
            gold_success_count=3,
        )
        with tracer.trace("route:query", task_id="t_new_run"):
            returned_trace_id = emit_replay_span(tracer, top_match)

        assert returned_trace_id is not None

        spans = SpanWriter(storage_path=storage).query_recent(limit=10)
        replay_spans = [s for s in spans if s.get("name", "").startswith("replay:")]
        assert len(replay_spans) == 1
        rs = replay_spans[0]
        assert rs["name"] == "replay:t_cmspark_replay"
        assert rs["span_kind"] == "workflow_node"

        meta = _parse_metadata(rs.get("metadata"))
        assert meta["replay_of"] == "T-cmspark-3"
        assert meta["old_task_id"] == "t_cmspark_replay"
        assert meta["old_query"] == "cmspark screenshot popup"
        assert meta["skill_id"] == "cmspark-permission-fix"
        assert meta["similarity"] == 0.92
        assert meta["gold_success_count"] == 3


class TestReplayPromptData:
    """W3 prompt UX: top_match carries all fields the prompt needs."""

    def test_gold_match_carries_prompt_fields(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        learner = _fake_learner_for_query({"cmspark": 3})
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            d = should_replay(
                "cmspark screenshot permission",
                fixture_spans,
                cache=cache,
                learner=learner,
                threshold=0.30,
            )
        assert d.top_match is not None
        top = d.top_match
        # All fields the CLI prompt needs:
        assert top.task_id, "task_id for span name"
        assert top.trace_id, "trace_id for 'Last trace:' line"
        assert top.skill_id, "skill_id for 'Last skill:' line"
        assert top.step_sequence, "step_sequence for 'Steps:' preview"
        assert top.gold_success_count > 0, "success count for trust signal"
        assert top.is_gold is True


def _parse_metadata(raw: dict | str | None) -> dict:
    """SpanWriter persists non-empty metadata as JSON string; parse back."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}
