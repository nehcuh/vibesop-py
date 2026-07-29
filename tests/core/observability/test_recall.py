"""W2 Task A — recall retrieval logic.

Contract:
1. ``recall_similar(query, spans, cache)`` returns top-k similar task_ids
   by cosine on representative query embedding.
2. Absolute threshold filters out weak matches (default 0.70).
3. Spans older than ``days`` window are excluded.
4. Returns ``RecallResult`` per match: task_id, similarity, representative
   query, span_count, step sequence, last_seen timestamp.
5. Empty spans → empty list (no crash).
6. Library missing (embeddings=None) → empty list with a flag.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.recall import recall_similar


def _unit_vec(angle: float, dim: int = 384) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[0] = np.cos(angle)
    v[1] = np.sin(angle)
    return v


def _fake_embedding(query: str) -> np.ndarray:
    h = hash(query) & 0xFFFF
    return _unit_vec((h % 360) * (np.pi / 180.0))


def _span(
    task_id: str,
    query: str,
    *,
    name: str = "route:query",
    timestamp: datetime | None = None,
) -> dict:
    ts = timestamp or datetime.now(UTC)
    return {
        "task_id": task_id,
        "input_data": {"query": query},
        "name": name,
        "timestamp": ts.isoformat(),
    }


class TestRecallBasic:
    def test_returns_top_k_similar(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            _span("t1", "alpha"),
            _span("t2", "beta"),
            _span("t3", "gamma"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("alpha", spans, cache=cache, top_k=2)
        assert len(results) <= 2
        assert results[0].task_id == "t1", "exact match should be top"
        assert results[0].similarity == pytest.approx(1.0, abs=1e-5)

    def test_threshold_filters_weak_matches(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")

        # Map "query" to angle 0, "different" to angle pi (cosine=-1)
        def _controlled(query: str) -> np.ndarray:
            return _unit_vec(0.0 if query == "query" else np.pi)

        with patch.object(cache, "_compute", side_effect=_controlled):
            spans = [_span("t1", "different")]
            results = recall_similar("query", spans, cache=cache, threshold=0.70)
        assert results == [], "cosine=-1 should not pass threshold 0.70"

    def test_results_sorted_by_similarity_desc(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            _span("t_far", "zeta"),
            _span("t_near", "alpha"),
            _span("t_mid", "beta"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("alpha", spans, cache=cache, top_k=3)
        sims = [r.similarity for r in results]
        assert sims == sorted(sims, reverse=True), "results must be sorted desc"
        assert results[0].task_id == "t_near"


class TestRecallResult:
    def test_result_has_task_id_and_similarity(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span("t1", "hello")]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.task_id == "t1"
        assert r.similarity == pytest.approx(1.0, abs=1e-5)
        assert r.representative_query == "hello"

    def test_result_has_span_count(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            _span("t1", "hello"),
            _span("t1", "hello"),
            _span("t1", "hello"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.span_count == 3

    def test_result_has_step_sequence(self, tmp_path: Path) -> None:
        """Step sequence extracts span names in temporal order."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            _span("t1", "hello", name="route:query"),
            _span("t1", "hello", name="llm:claude"),
            _span("t1", "hello", name="tool:read"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.step_sequence == ["route:query", "llm:claude", "tool:read"]

    def test_result_has_last_seen_timestamp(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        old_ts = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
        new_ts = datetime(2026, 7, 28, 18, 30, tzinfo=UTC)
        spans = [
            _span("t1", "hello", timestamp=old_ts),
            _span("t1", "hello", timestamp=new_ts),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.last_seen is not None
        # last_seen should be the most recent
        assert "2026-07-28" in r.last_seen


class TestDaysWindow:
    def test_old_spans_excluded(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        old_ts = datetime.now(UTC) - timedelta(days=60)
        spans = [_span("t1", "hello", timestamp=old_ts)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert results == [], "spans older than window should be excluded"

    def test_recent_spans_included(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        recent_ts = datetime.now(UTC) - timedelta(days=5)
        spans = [_span("t1", "hello", timestamp=recent_ts)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert len(results) == 1


class TestFilterRecentEdgeCases:
    """P1-4: _filter_recent keeps spans with missing/malformed/future timestamps.

    Rationale: don't drop data on a formatting quirk. Spans without a parseable
    timestamp are kept; spans with future timestamps are kept (clock skew tolerant).
    """

    def test_missing_timestamp_kept(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                # no "timestamp" key
            }
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert len(results) == 1, "missing timestamp should be kept (not dropped)"

    def test_malformed_timestamp_kept(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "timestamp": "not-a-date",
            }
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert len(results) == 1, "malformed timestamp should be kept"

    def test_future_timestamp_kept(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        future_ts = datetime.now(UTC) + timedelta(days=10)
        spans = [_span("t1", "hello", timestamp=future_ts)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert len(results) == 1, "future timestamp should be kept"

    def test_empty_timestamp_string_kept(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "timestamp": "",
            }
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache, days=30)
        assert len(results) == 1, "empty timestamp string should be kept"


class TestEmptyQuerySkipped:
    """P1-2: task_ids with no extractable query are skipped (not embedded as noise)."""

    def test_task_id_with_empty_query_skipped(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t_empty",
                "input_data": {},  # no "query" key
                "name": "route:query",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            _span("t_real", "hello"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache)
        task_ids = [r.task_id for r in results]
        assert "t_empty" not in task_ids, "empty-query task_id should be skipped"
        assert "t_real" in task_ids


class TestEdgeCases:
    def test_empty_spans_returns_empty(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", [], cache=cache)
        assert results == []

    def test_spans_without_task_id_skipped(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {"name": "route:query", "input_data": {"query": "no task"}, "timestamp": datetime.now(UTC).isoformat()},
            _span("t1", "hello"),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("hello", spans, cache=cache)
        assert len(results) == 1
        assert results[0].task_id == "t1"

    def test_library_missing_returns_empty(self, tmp_path: Path) -> None:
        """If embeddings return None (library missing), results are empty."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span("t1", "hello")]
        with patch.object(cache, "_compute", return_value=None):
            results = recall_similar("hello", spans, cache=cache)
        assert results == []


class TestTopKBound:
    def test_top_k_caps_results(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span(f"t{i}", f"q{i}") for i in range(10)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar("q0", spans, cache=cache, top_k=3)
        assert len(results) <= 3


class TestW3TraceIdAndSkillId:
    """W3.1: RecallResult carries trace_id + skill_id from spans."""

    def test_trace_id_from_most_recent_span(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        old_ts = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
        new_ts = datetime(2026, 7, 28, 18, 30, tzinfo=UTC)
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "timestamp": old_ts.isoformat(),
                "trace_id": "T-old",
            },
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "timestamp": new_ts.isoformat(),
                "trace_id": "T-new",
            },
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.trace_id == "T-new", "trace_id should be from most recent span"

    def test_trace_id_none_when_no_trace_in_spans(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span("t1", "hello")]  # _span helper doesn't add trace_id
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.trace_id is None

    def test_skill_id_mode_across_spans(self, tmp_path: Path) -> None:
        """skill_id = most common (mode) across spans for the task_id."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "timestamp": datetime(2026, 7, 1, tzinfo=UTC).isoformat(),
                "metadata": {"skill_id": "skill_a"},
            },
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "timestamp": datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
                "metadata": {"skill_id": "skill_a"},
            },
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "timestamp": datetime(2026, 7, 3, tzinfo=UTC).isoformat(),
                "metadata": {"skill_id": "skill_b"},
            },
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.skill_id == "skill_a", "mode should win (2 vs 1)"

    def test_skill_id_from_top_level_field(self, tmp_path: Path) -> None:
        """Newer span schema stores skill_id at top level."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [
            {
                "task_id": "t1",
                "input_data": {"query": "hello"},
                "name": "route:query",
                "timestamp": datetime.now(UTC).isoformat(),
                "skill_id": "top_level_skill",
            }
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.skill_id == "top_level_skill"

    def test_skill_id_none_when_missing(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span("t1", "hello")]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache)
        assert r.skill_id is None


class TestW3LearnerGoldFusion:
    """W3.2: recall_similar accepts optional learner to populate is_gold."""

    def test_no_learner_keeps_is_gold_false(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span("t1", "hello")]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache, learner=None)
        assert r.is_gold is False
        assert r.gold_success_count == 0

    def test_learner_with_success_marks_gold_when_span_count_sufficient(
        self, tmp_path: Path
    ) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        # 5 spans for the same task_id to meet min_gold_span_count=5
        spans = [_span("t1", "hello") for _ in range(5)]

        fake_learner = MagicMock()
        fake_instinct = MagicMock()
        fake_instinct.success_count = 3
        fake_learner.get_instinct_for_query.return_value = fake_instinct

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache, learner=fake_learner)
        assert r.is_gold is True
        assert r.gold_success_count == 3

    def test_learner_with_success_but_few_spans_not_gold(self, tmp_path: Path) -> None:
        """Success but span_count < 5 → is_gold=False (mirrors W1 candidate logic)."""
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span("t1", "hello") for _ in range(2)]  # only 2 spans

        fake_learner = MagicMock()
        fake_instinct = MagicMock()
        fake_instinct.success_count = 5
        fake_learner.get_instinct_for_query.return_value = fake_instinct

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache, learner=fake_learner)
        assert r.is_gold is False, "span_count < 5 should not be gold"
        assert r.gold_success_count == 5, "but success_count still surfaced"

    def test_learner_no_instinct_for_query(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span("t1", "hello") for _ in range(5)]

        fake_learner = MagicMock()
        fake_learner.get_instinct_for_query.return_value = None  # no instinct

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache, learner=fake_learner)
        assert r.is_gold is False
        assert r.gold_success_count == 0

    def test_learner_zero_success_not_gold(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz")
        spans = [_span("t1", "hello") for _ in range(5)]

        fake_learner = MagicMock()
        fake_instinct = MagicMock()
        fake_instinct.success_count = 0  # never succeeded
        fake_learner.get_instinct_for_query.return_value = fake_instinct

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            [r] = recall_similar("hello", spans, cache=cache, learner=fake_learner)
        assert r.is_gold is False
        assert r.gold_success_count == 0


class TestW3RealInstinctLearnerIntegration:
    """W3 Fix-6 (P1-3): real InstinctLearner integration for gold fusion.

    All other tests use MagicMock for learner. This class uses a real
    InstinctLearner on tmp storage to verify:
    - representative_query → instinct_id normalization matches
    - record_outcome → success_count actually increments
    - get_instinct_for_query → returns the learned instinct
    - recall_similar picks up real gold signal end-to-end
    """

    def test_real_learner_gold_path(
        self, tmp_path: Path
    ) -> None:
        """Real learner + real record_outcome → recall returns is_gold=True."""
        from vibesop.core.instinct.learner import InstinctLearner
        from vibesop.core.observability.embedding import EmbeddingCache
        from vibesop.core.observability.recall import recall_similar

        # Real learner on tmp storage
        learner = InstinctLearner(storage_path=tmp_path / "instincts.jsonl")
        query_text = "fix cmspark screenshot permission popup"
        learner.learn(pattern=query_text, action="cmspark-permission-fix")
        # Bump success_count via the public API
        for _ in range(2):
            learner.record_outcome_for_query(query_text, success=True)

        # Verify learner state via its own API
        instinct = learner.get_instinct_for_query(query_text)
        assert instinct is not None, "real learner should return learned instinct"
        assert instinct.success_count >= 1, f"expected success_count>=1, got {instinct.success_count}"

        # Cache with deterministic fake embedding
        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz", dim=384)

        # Spans: 3 distinct traces for same task_id → distinct_trace_count=3
        spans = [
            {
                "task_id": "t_cmspark_real",
                "input_data": {"query": query_text},
                "name": "route:query",
                "timestamp": f"2026-07-2{i}T12:00:00+00:00",
                "trace_id": f"T-real-{i}",
                "metadata": {"skill_id": "cmspark-fix"},
            }
            for i in range(1, 4)
        ]

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar(
                query_text, spans, cache=cache, learner=learner, threshold=0.30
            )

        assert len(results) >= 1
        top = results[0]
        assert top.task_id == "t_cmspark_real"
        assert top.is_gold is True, (
            f"real learner + 3 distinct traces should be gold; "
            f"gold_success_count={top.gold_success_count}, "
            f"distinct_trace_count={top.distinct_trace_count}"
        )
        assert top.distinct_trace_count == 3
        assert top.gold_success_count >= 1

    def test_real_learner_normalization_drift_safe(
        self, tmp_path: Path
    ) -> None:
        """Verify recall's representative_query feeds correctly into generate_id.

        recall uses task_info["query"] (first raw query) as lookup key for
        learner.get_instinct_for_query. This test verifies the normalization
        chain doesn't drift between learn() and get_instinct_for_query().
        """
        from vibesop.core.instinct.learner import InstinctLearner
        from vibesop.core.observability.embedding import EmbeddingCache
        from vibesop.core.observability.recall import recall_similar

        learner = InstinctLearner(storage_path=tmp_path / "instincts.jsonl")
        # Learn with EXACT same string as the span's representative_query
        # (this is what production path does)
        canonical_query = "macbook lid closed overheating"
        learner.learn(pattern=canonical_query, action="mac-thermal-fix")
        learner.record_outcome_for_query(canonical_query, success=True)

        cache = EmbeddingCache(cache_path=tmp_path / "emb.npz", dim=384)
        # Span query matches canonical_query exactly (first span = rep_query)
        spans = [
            {
                "task_id": "t_lid_real",
                "input_data": {"query": canonical_query},
                "name": "route:query",
                "timestamp": f"2026-07-2{i}T18:00:00+00:00",
                "trace_id": f"T-lid-{i}",
            }
            for i in range(1, 4)
        ]

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            results = recall_similar(
                canonical_query, spans, cache=cache, learner=learner, threshold=0.30
            )

        assert len(results) == 1
        assert results[0].is_gold is True
        assert results[0].gold_success_count >= 1
