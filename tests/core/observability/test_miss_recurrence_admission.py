"""M12 M2 — miss_recurrence admission gate: same-day/cross-day synthetic injection.

Design v3 §阈值哲学 (gate15b final): a cluster composed entirely of
route-miss spans is admitted WITHOUT a gold-rate requirement iff BOTH

- distinct (task_id, natural-day) pairs >= MISS_RECURRENCE_MIN_PAIRS (3)
- distinct natural days                 >= MISS_RECURRENCE_MIN_DAYS (2)

hold (conjunction — neither condition implies the other). These tests
inject synthetic spans to pin down:

- same-day multi-key burst is blocked by the day condition;
- same-key same-day repeat is blocked by pair dedup;
- cross-day recurrence is admitted as ``source="miss_recurrence"``,
  stable-visible (NOT the unstable bucket), ``gold_rate`` recorded as 0.0;
- the gold path is not regressed (stable gold candidates still fire);
- not_intercepted / unknown (has_match missing) / hit spans never enter
  the miss pool;
- the thresholds are overridable via scan_candidates kwargs (the knobs
  the scan-candidates CLI flags wire onto).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.skill_promote import (
    ClusterCandidateStore,
    scan_candidates,
)

D1 = "2026-08-01T10:00:00+00:00"
D1_LATE = "2026-08-01T22:30:00+00:00"
D2 = "2026-08-02T09:15:00+00:00"


def _fake_embedding(query: str) -> np.ndarray:
    """All "miss-topic" queries collapse to one vector (cosine 1.0) so
    distinct task_ids soft-merge; "topic-A" gets a different vector.
    """
    v = np.zeros(384, dtype=np.float32)
    if "miss-topic" in query:
        v[0] = 1.0
    elif "topic-A" in query:
        v[1] = 1.0
    else:
        v[2] = 1.0
    return v


def _miss_span(
    task_id: str,
    query: str,
    started_at: str,
    *,
    mode: str | None = "single",
    has_match: bool | None = False,
    metadata_as_string: bool = False,
) -> dict:
    """One route span in the real producer shape (span_kind=task,
    name="route:<query>", query/has_match/mode in metadata).
    ``has_match=None`` models the unknown case (key absent).
    """
    metadata: dict = {"query": query, "mode": mode}
    if has_match is not None:
        metadata["has_match"] = has_match
    return {
        "span_kind": "task",
        "name": f"route:{query}",
        "task_id": task_id,
        "project_id": "test",
        "started_at": started_at,
        "metadata": json.dumps(metadata) if metadata_as_string else metadata,
    }


def _gold_span(task_id: str, query: str) -> dict:
    return {
        "span_kind": "task",
        "name": f"route:{query}",
        "task_id": task_id,
        "project_id": "test",
        "started_at": D1,
        "input_data": {"query": query},
        "metadata": {"query": query, "mode": "single", "has_match": True},
    }


@pytest.fixture
def fresh_learner(tmp_path: Path) -> InstinctLearner:
    return InstinctLearner(storage_path=tmp_path / "instincts.json")


@pytest.fixture
def cache(tmp_path: Path) -> EmbeddingCache:
    return EmbeddingCache(cache_path=tmp_path / "emb.npz")


@pytest.fixture
def store(tmp_path: Path) -> ClusterCandidateStore:
    return ClusterCandidateStore(storage_dir=tmp_path / "obs")


class TestAdmissionGate:
    def test_same_day_three_distinct_keys_not_admitted(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """3 distinct task_ids, all on ONE day: pairs=3 but days=1 →
        the cross-day condition blocks admission (this is the 'afternoon
        of iterative rephrasing' burst the day condition exists for)."""
        spans = [
            _miss_span("k1", "miss-topic one", D1),
            _miss_span("k2", "miss-topic two", D1_LATE),
            _miss_span("k3", "miss-topic three", D1_LATE),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_pool_size == 3
        assert summary.miss_admitted_count == 0
        assert store.pending_count() == 0  # nothing stable-visible
        # Existing behaviour preserved: pure-miss cluster still lands in
        # the unstable diagnosis bucket when NOT admitted.
        assert summary.unstable_count == 1

    def test_same_key_same_day_three_times_not_admitted(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """1 task_id × 3 spans on the same day: pair dedup collapses to
        a single (task_id, day) pair → blocked by the pair count."""
        spans = [
            _miss_span("k1", "miss-topic one", D1),
            _miss_span("k1", "miss-topic one", D1_LATE),
            _miss_span("k1", "miss-topic one", D1_LATE),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_pool_size == 3
        assert summary.miss_admitted_count == 0
        assert store.pending_count() == 0

    def test_cross_two_days_three_pairs_admitted(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """k1@day1, k1@day2, k2@day2 → 3 distinct (task_id, day) pairs
        across 2 days → admitted. One span uses the JSON-string metadata
        shape SpanWriter actually persists."""
        spans = [
            _miss_span("k1", "miss-topic one", D1),
            _miss_span("k1", "miss-topic one", D2, metadata_as_string=True),
            _miss_span("k2", "miss-topic two", D2),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_pool_size == 3
        assert summary.miss_admitted_count == 1
        assert summary.unstable_count == 0  # not double-filed as unstable

        rows = store.list_all()
        assert len(rows) == 1
        row = rows[0]
        assert row.source == "miss_recurrence"
        assert row.gold_rate == 0.0  # recorded as-is, no success signal
        assert row.gold_task_ids == []
        assert row.is_unstable is False
        assert row.span_count == 3
        # The whole point of the gate: visible in the default review queue.
        assert store.pending_count() == 1
        assert store.list_pending()[0].cluster_id == row.cluster_id

    def test_admission_respects_threshold_overrides(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """The knobs (CLI-flag surface): raising miss_min_pairs past the
        evidence blocks admission; so does a cosine threshold above the
        soft-merge similarity (singletons can't reach 3 pairs)."""
        spans = [
            _miss_span("k1", "miss-topic one", D1),
            _miss_span("k1", "miss-topic one", D2),
            _miss_span("k2", "miss-topic two", D2),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            blocked = scan_candidates(spans, fresh_learner, store, cache=cache, miss_min_pairs=4)
        assert blocked.miss_admitted_count == 0
        assert store.pending_count() == 0

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            unmerged = scan_candidates(
                spans, fresh_learner, store, cache=cache, miss_cosine_threshold=1.1
            )
        assert unmerged.miss_admitted_count == 0
        assert store.pending_count() == 0


class TestMissPoolExclusions:
    def test_not_intercepted_and_unknown_spans_excluded(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """mode='not_intercepted' (interceptor abstained) and spans with
        no has_match key (unknown) never enter the miss pool."""
        spans = [
            _miss_span("k1", "miss-topic one", D1, mode="not_intercepted", has_match=None),
            _miss_span("k2", "miss-topic two", D1, has_match=None),
            _miss_span("k3", "miss-topic three", D2, has_match=None),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_pool_size == 0
        assert summary.miss_admitted_count == 0
        assert store.pending_count() == 0

    def test_hit_spans_excluded(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """has_match=True spans are hits, not misses."""
        spans = [
            _miss_span("k1", "miss-topic one", D1, has_match=True),
            _miss_span("k2", "miss-topic two", D2, has_match=True),
            _miss_span("k3", "miss-topic three", D2, has_match=True),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_pool_size == 0
        assert summary.miss_admitted_count == 0

    def test_low_information_queries_excluded(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """Calibration finding (M2c): content-free queries ("继续"/"可以"/"ok")
        cosine-match EVERYTHING at 0.72–0.82 — they must be filtered BEFORE
        the miss pool, since no threshold can fix a zero-information query."""
        spans = [
            _miss_span("k1", "继续", D1),
            _miss_span("k2", "可以", D2),
            _miss_span("k3", "ok", D2),
            _miss_span("k4", "go", D1_LATE),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_pool_size == 0
        assert summary.miss_admitted_count == 0
        assert store.pending_count() == 0

    def test_short_cjk_intents_survive_filter(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """gate17 pi nit: the length rule must be Latin-only — terse CJK
        imperatives (清理吧/合并/跑测试) carry intent and stay in the pool."""
        spans = [
            _miss_span("k1", "清理吧", D1),
            _miss_span("k2", "合并", D2),
            _miss_span("k3", "跑测试", D2),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_pool_size == 3


class TestEmbeddingDegradedProbe:
    def test_probe_flags_degraded_when_embed_returns_none(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """gate17 pi BLOCK-1: embedding backend down (_compute → None)
        must surface as ``embedding_degraded=True`` on the summary —
        explicit scan-level signal, not just per-query warnings."""
        spans = [
            _miss_span("k1", "miss-topic one", D1),
            _miss_span("k2", "miss-topic two", D2),
        ]
        with patch.object(cache, "_compute", return_value=None):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.embedding_degraded is True

    def test_probe_false_when_backend_healthy(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        spans = [_miss_span("k1", "miss-topic one", D1)]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.embedding_degraded is False


class TestCapRejectionCounting:
    def test_rejected_miss_candidate_not_counted_as_admitted(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """gate17 claude nit 8: at MAX_PENDING the admit-only-if-better
        policy always refuses a gold_rate=0.0 miss candidate. The scan
        must NOT count it as admitted — it goes to miss_rejected_count."""
        from vibesop.core.observability.skill_promote import (
            MAX_PENDING,
            ClusterCandidate,
        )

        # Fill the pool to the hard cap with pending rows the miss
        # candidate can never beat (any gold_rate > 0.0).
        for i in range(MAX_PENDING):
            store.upsert(
                ClusterCandidate(
                    cluster_id=f"fill-{i}",
                    task_ids=[f"t{i}"],
                    queries=["filler query"],
                    span_count=5,
                    gold_rate=0.5,
                    gold_task_ids=[],
                )
            )
        assert store.pending_count() == MAX_PENDING

        # Cross-day fixture that WOULD be admitted into a non-full pool.
        spans = [
            _miss_span("k1", "miss-topic one", D1),
            _miss_span("k1", "miss-topic one", D2),
            _miss_span("k2", "miss-topic two", D2),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_admitted_count == 0
        assert summary.miss_rejected_count == 1
        assert summary.capped is True
        assert store.pending_count() == MAX_PENDING  # pool unchanged


class TestGoldPendingCollision:
    def test_miss_upsert_skipped_when_pending_gold_row_exists(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """gate17b claude nit 1: a pending gold row with the same cluster_id
        must NOT be overwritten by the weaker miss evidence (source flip,
        gold_rate -> 0.0, double count)."""
        import hashlib

        from vibesop.core.observability.skill_promote import ClusterCandidate

        spans = [
            _miss_span("k1", "miss-topic one", D1),
            _miss_span("k2", "miss-topic two", D2),
            _miss_span("k3", "miss-topic three", D2),
        ]
        # Pre-compute the cluster_id the miss cluster will get
        # (sha1 of "\x1f".join("test|kN") over sorted member keys, [:16]).
        keys = sorted(f"test|k{i}" for i in (1, 2, 3))
        cid = hashlib.sha1("\x1f".join(keys).encode("utf-8")).hexdigest()[:16]
        store.upsert(
            ClusterCandidate(
                cluster_id=cid,
                task_ids=["k1", "k2", "k3"],
                queries=["miss-topic one", "miss-topic two", "miss-topic three"],
                span_count=9,
                gold_rate=0.8,
                gold_task_ids=["k1"],
                source="gold",
            )
        )

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        row = store.get(cid)
        assert row is not None
        assert row.source == "gold"  # not flipped to miss_recurrence
        assert row.gold_rate == 0.8  # not zeroed
        assert summary.miss_admitted_count == 0  # no double count
        assert summary.miss_rejected_count == 0


class TestGoldPathNotRegressed:
    def test_gold_candidate_and_miss_candidate_coexist(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """A stable gold candidate (2/3 gold) and an admitted miss
        cluster in the SAME scan both land, with distinct sources."""
        spans = [
            _gold_span("g1", "topic-A one"),
            _gold_span("g2", "topic-A two"),
            _gold_span("g3", "topic-A three"),
            _miss_span("k1", "miss-topic one", D1),
            _miss_span("k1", "miss-topic one", D2),
            _miss_span("k2", "miss-topic two", D2),
        ]
        fresh_learner.learn(pattern="topic-A one", action="x")
        fresh_learner.record_outcome_for_query("topic-A one", success=True)
        fresh_learner.learn(pattern="topic-A two", action="y")
        fresh_learner.record_outcome_for_query("topic-A two", success=True)

        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.promoted_count == 1
        assert summary.miss_admitted_count == 1
        assert summary.unstable_count == 0
        rows = store.list_pending()
        assert len(rows) == 2
        by_source = {r.source: r for r in rows}
        assert by_source["gold"].gold_rate >= 0.60
        assert by_source["miss_recurrence"].gold_rate == 0.0

    def test_rescan_idempotent_for_miss_candidates(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """Re-scanning the same miss spans yields ONE row, not dupes."""
        spans = [
            _miss_span("k1", "miss-topic one", D1),
            _miss_span("k1", "miss-topic one", D2),
            _miss_span("k2", "miss-topic two", D2),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            scan_candidates(spans, fresh_learner, store, cache=cache)
            scan_candidates(spans, fresh_learner, store, cache=cache)

        assert store.pending_count() == 1
        assert len(store.list_all()) == 1


class TestMissShareByLayer:
    """M12 M4 item (done in M5) — ScanSummary.miss_share_by_layer.

    Route-span producers currently do NOT emit a ``layer`` metadata
    field, so the honest bucket for real data is "unknown".
    """

    def test_share_computed_with_layer_and_unknown_bucket(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        spans = [
            _miss_span("k1", "miss-topic one", D1),
            _miss_span("k2", "miss-topic two", D2),
            # Future-producer shape: an explicit layer field.
            {
                **_miss_span("k3", "miss-topic three", D2),
                "metadata": {
                    "query": "miss-topic three",
                    "mode": "single",
                    "has_match": False,
                    "layer": "semantic_index",
                },
            },
            # JSON-string metadata without layer → unknown.
            _miss_span("k4", "miss-topic four", D2, metadata_as_string=True),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_pool_size == 4
        assert summary.miss_share_by_layer == {
            "semantic_index": 0.25,
            "unknown": 0.75,
        }

    def test_share_empty_when_no_misses(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        spans = [_gold_span("g1", "topic-A one")]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)
        assert summary.miss_share_by_layer == {}

    def test_share_empty_when_no_spans(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        summary = scan_candidates([], fresh_learner, store, cache=cache)
        assert summary.miss_share_by_layer == {}


class TestLowInformationShapeRules:
    """Insight 1 (retention-pool-insights.md §洞察 1) — shape rules on top
    of the wordlist. The 12 retention fragments are the fixtures:
    7 filtered / 5 deliberately not filtered. Behavior-focused: verdicts
    are asserted via the public filter ``_is_low_information_query``.
    """

    @pytest.mark.parametrize(
        "query",
        [
            # Rule A — continuation prefix + phase-token-only remainder.
            "继续往后做吧",
            "继续 Phase2b 和 Phase3",
            "继续 P2 抛光",
            "开始 M1",
            "做 D1c",
            # Pre-existing rules (wordlist / latin≤4).
            "B+C",
            # Rule B — enumeration option-reply.
            "1. 接受 C′ 2. D",
            # gate19 NIT-4: 接着 prefix continuation.
            "接着做 D2",
            # gate19 NIT-4: full-width punctuation peels like ASCII.
            "继续吧！",
            # gate19 NIT-3 (documented): bare phase/particle lists carry
            # no routing intent — filtered with no continuation prefix.
            "M1 和 M2",
        ],
    )
    def test_retention_fragments_filtered(self, query: str) -> None:
        from vibesop.core.observability.skill_promote import _is_low_information_query

        assert _is_low_information_query(query) is True

    @pytest.mark.parametrize(
        "query,why",
        [
            # 2-char CJK verb+particle — 清理吧 (calibration pair) proves
            # this shape carries intent.
            ("加吧", "CJK verb+particle carries intent (cf. 清理吧)"),
            # Status update — not a routing signal, but not proven
            # content-free either; conservative pass-through.
            ("我看下恢复了", "status update"),
            # Probe string — must round-trip verbatim for diagnostics.
            ("reply with exactly: claude-ok", "probe"),
            # Substantive answer to an agent question — has content.
            (
                "我用的是 dist-package 下面的 chrome-extension",
                "substantive answer",
            ),
            # Long multi-answer enumeration — Rule B's ≤30-char cap is the
            # accepted limit (documented omission).
            (
                "1. 互斥 2. 不禁 evaluate 3. 并发最多到 5 吧 4. 根据你们的建议来选择合适的方案 5. 能",
                "long enumeration (>30 chars, accepted limit)",
            ),
            # gate19 NIT-2: space-separated "phase 3" splits into
            # ["phase", "3"] before the token fullmatch — documented
            # safe-omission (conservative direction).
            ("继续 phase 3", "space-separated phase token, documented omission"),
        ],
    )
    def test_retention_fragments_deliberately_kept(self, query: str, why: str) -> None:
        from vibesop.core.observability.skill_promote import _is_low_information_query

        assert _is_low_information_query(query) is False, f"over-filtered: {why}"

    @pytest.mark.parametrize(
        "query,why",
        [
            # Calibration counterexample — terse CJK imperative.
            ("清理吧", "calibration pair: 2-char CJK carries intent"),
            # Continuation prefix with a REAL object must survive Rule A
            # (处理 is not in the verb set; remainder has content).
            ("继续处理 backlog 里的 X 文件", "real object after 继续"),
            ("继续做用户登录模块", "real object after 继续做"),
            # Enumeration with no bare-letter option (NPE is a word) must
            # survive Rule B.
            ("1. 修复登录页面 NPE 2. 补充集成测试", "NPE is not a bare option letter"),
            # gate19 NIT-1 (both reviewers, verified over-filter): bare
            # letter FOLLOWED by content is a task shape, not an option.
            ("1. 完成 A 模块", "letter + CJK object"),
            ("1. 看 A 和 B 的差异", "letters as task subjects"),
            ("1. 对比 A 方案和 B 方案", "letters label plans, not options"),
            ("1. 方案 I 更好", "roman numeral as label"),
            ("1. 修 X 文件 2. 加日志", "letter + CJK object in enumeration"),
            # Ordinary task queries.
            ("帮我重构登录模块的鉴权逻辑", "normal CJK task query"),
            ("fix the login page NPE", "normal latin task query"),
        ],
    )
    def test_counterexamples_never_filtered(self, query: str, why: str) -> None:
        from vibesop.core.observability.skill_promote import _is_low_information_query

        assert _is_low_information_query(query) is False, f"over-filtered: {why}"

    def test_shape_rules_actually_exclude_from_miss_pool(
        self, fresh_learner: InstinctLearner, cache: EmbeddingCache, store: ClusterCandidateStore
    ) -> None:
        """End-to-end: Rule-A fragments never reach the miss pool (the
        0.72–0.82 cosine-match-everything poison the filter exists for)."""
        spans = [
            _miss_span("k1", "继续往后做吧", D1),
            _miss_span("k2", "继续 Phase2b 和 Phase3", D2),
            _miss_span("k3", "开始 M1", D2),
        ]
        with patch.object(cache, "_compute", side_effect=_fake_embedding):
            summary = scan_candidates(spans, fresh_learner, store, cache=cache)

        assert summary.miss_pool_size == 0
        assert store.pending_count() == 0
