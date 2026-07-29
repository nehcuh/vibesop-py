"""W4.F — kill-switch smoke test.

Spec: ``docs/decisions/2026-07-29-task-memory-product-design.md``
§5 row "W4 末": gold cluster 数 ≥5 / 候选池积压 <10 — else freeze.

Loads ``tests/fixtures/w4_gold_clusters_spans.jsonl`` (5 distinct
clusters × 3 task_ids × 1 span = 15 spans), scans with a fake embedding
that cleanly partitions by topic prefix, and verifies the kill-switch
criteria hold on the resulting pool.

Uses fakes instead of real ``sentence-transformers`` to keep the test
deterministic and fast (no model load).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.skill_promote import (
    ClusterCandidateStore,
    scan_candidates,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "w4_gold_clusters_spans.jsonl"


def _topic_embedding(query: str) -> np.ndarray:
    """Deterministic embedding keyed on cluster prefix.

    Each topic (auth/file/image/git/test) maps to a different one-hot
    dimension so cosine sim within a topic = 1.0 (cluster together) and
    across topics = 0.0 (no cross-cluster merging).
    """
    v = np.zeros(384, dtype=np.float32)
    topics = ["auth", "file", "image", "git", "test"]
    for i, topic in enumerate(topics):
        if topic in query.lower():
            v[i] = 1.0
            return v
    v[10] = 0.5  # fallback for unmatched queries
    return v


@pytest.fixture
def fixture_spans() -> list[dict]:
    """Load spans from the W4 fixture file."""
    spans: list[dict] = []
    with FIXTURE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            spans.append(json.loads(line))
    return spans


@pytest.fixture
def fresh_learner(tmp_path: Path) -> InstinctLearner:
    """Real InstinctLearner with success recorded for every fixture task."""
    learner = InstinctLearner(storage_path=tmp_path / "instincts.json")
    queries = [
        "auth login user", "auth signup new user", "auth logout session",
        "file read contents", "file write bytes", "file delete path",
        "image resize pixels", "image crop bounds", "image rotate degrees",
        "git commit message", "git push remote", "git pull branch",
        "test run unit", "test coverage report", "test fixture setup",
    ]
    for q in queries:
        learner.learn(pattern=q, action="gold-action")
        learner.record_outcome_for_query(q, success=True)
    return learner


@pytest.fixture
def cache(tmp_path: Path) -> EmbeddingCache:
    return EmbeddingCache(cache_path=tmp_path / "emb.npz")


@pytest.fixture
def store(tmp_path: Path) -> ClusterCandidateStore:
    return ClusterCandidateStore(storage_dir=tmp_path / "obs")


class TestKillSwitchSmoke:
    """Spec §5 kill-switch criteria: ≥5 gold clusters AND <10 backlog."""

    def test_kill_switch_gold_cluster_count_meets_5(
        self,
        fixture_spans: list[dict],
        fresh_learner: InstinctLearner,
        cache: EmbeddingCache,
        store: ClusterCandidateStore,
    ) -> None:
        """Scanning the fixture yields ≥5 stable candidates.

        With 5 distinct topics × 3 task_ids each + gold success recorded
        for all, every cluster should classify as a stable candidate.
        """
        with patch.object(cache, "_compute", side_effect=_topic_embedding):
            summary = scan_candidates(
                fixture_spans, fresh_learner, store, cache=cache
            )

        assert summary.clusters_seen == 5, (
            f"expected 5 distinct clusters from fixture, got {summary.clusters_seen}"
        )
        assert summary.promoted_count >= 5, (
            f"kill-switch requires ≥5 stable candidates; got {summary.promoted_count}"
        )
        pending = store.list_pending()
        stable = [p for p in pending if not p.is_unstable]
        assert len(stable) >= 5

    def test_kill_switch_backlog_under_10(
        self,
        fixture_spans: list[dict],
        fresh_learner: InstinctLearner,
        cache: EmbeddingCache,
        store: ClusterCandidateStore,
    ) -> None:
        """After scan, total pending (stable + unstable) < 10.

        The fixture is deliberately sized so a single scan stays well
        under the hard cap of 50 (reviewer Q4). In production, repeated
        scans of high-volume projects could approach the cap; the
        kill-switch then warns "review your backlog" before freeze.
        """
        with patch.object(cache, "_compute", side_effect=_topic_embedding):
            scan_candidates(fixture_spans, fresh_learner, store, cache=cache)

        backlog = store.pending_count()
        assert backlog < 10, (
            f"kill-switch requires <10 pending rows; got {backlog}. "
            "Either fixture grew or the hard cap isn't bounding the pool."
        )

    def test_kill_switch_idempotent_rescan(
        self,
        fixture_spans: list[dict],
        fresh_learner: InstinctLearner,
        cache: EmbeddingCache,
        store: ClusterCandidateStore,
    ) -> None:
        """Re-scanning the same spans does NOT inflate the backlog.

        Idempotency is critical for the kill-switch: a cron-scheduled
        scan that runs hourly must not push the pool toward the cap
        just by running multiple times.
        """
        with patch.object(cache, "_compute", side_effect=_topic_embedding):
            scan_candidates(fixture_spans, fresh_learner, store, cache=cache)
            scan_candidates(fixture_spans, fresh_learner, store, cache=cache)
            scan_candidates(fixture_spans, fresh_learner, store, cache=cache)

        backlog = store.pending_count()
        assert backlog < 10, (
            f"idempotent rescan should keep backlog <10; got {backlog}"
        )
