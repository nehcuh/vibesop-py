"""W2 Task B — fixture-based acceptance smoke for recall + cluster.

Replaces the original kill-switch "follow rate >= 30%" criterion (which
requires real users and product-level telemetry) with a fixture-based
smoke that proves the algorithmic preconditions for follow rate hold:

1. cmspark screenshot permission queries (≥10) cluster together as one
   connected component (kill-switch precondition from design §3 W1).
2. A second real cluster (lid sleep overheating) forms separately.
3. Recall returns ≥1 cmspark task_id for a screenshot-permission query,
   and ≥1 lid-sleep task_id for an overheating query.
4. Precision: irrelevant queries (rust/postgres/react) don't get pulled
   into either gold cluster.

This is the same pattern as Dashboard v3 Phase A Task 13 — fixture-based
integration smoke replacing expensive real-LLM tests
([[project-dashboard-v3-phase-a-shipped]]).

Embeddings are mocked with deterministic per-query vectors to keep the
test fast and deterministic. Real fastembed behaviour is exercised in
the W0 benchmark script (not in unit CI).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from vibesop.core.observability.clustering import cluster_queries
from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.recall import recall_similar

FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "recall_gold_spans.jsonl"


def _load_fixture() -> list[dict]:
    spans: list[dict] = []
    with FIXTURE.open() as f:
        for line in f:
            line = line.strip()
            if line:
                spans.append(json.loads(line))
    return spans


def _keyword_embedding(query: str) -> np.ndarray:
    """Mock embedding that triggers on topical semantic clusters.

    Synonyms map to the SAME dim so semantically-equivalent queries
    (regardless of language) produce overlapping vectors. Real MiniLM
    would learn these associations from training data; we hard-code
    them so the test is deterministic and fast.
    """
    # Each cluster is a semantic concept; multilingual synonyms share one dim.
    semantic_clusters = {
        "screenshot": ["screenshot", "截图", "screen capture", "截图权限"],
        "permission": ["permission", "权限", "authorization", "authorize"],
        "popup": ["popup", "弹窗", "dialog", "keeps appearing", "反复弹"],
        "cmspark": ["cmspark"],
        "lid_sleep": ["lid", "合盖", "sleep", "休眠", "clamshell", "closed"],
        "overheating": ["overheating", "发热", "hot", "gets hot", "fan"],
        "macbook": ["macbook", "mac"],
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


@pytest.fixture
def fixture_spans() -> list[dict]:
    return _load_fixture()


@pytest.fixture
def cache(tmp_path: Path) -> EmbeddingCache:
    return EmbeddingCache(cache_path=tmp_path / "emb.npz", dim=64)


class TestClusterShape:
    """W1 kill-switch preconditions on the fixture."""

    def test_cmspark_cluster_has_at_least_10_queries(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            clusters = cluster_queries(fixture_spans, cache=cache, threshold=0.30)
        cmspark_cluster = _find_cluster_with_prefix(clusters, "t_cmspark_")
        assert cmspark_cluster is not None, "expected a cmspark cluster"
        assert len(cmspark_cluster.task_ids) >= 10, (
            f"cmspark cluster has {len(cmspark_cluster.task_ids)} task_ids, "
            "expected >= 10 per design kill-switch"
        )

    def test_lid_sleep_cluster_has_at_least_5_queries(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            clusters = cluster_queries(fixture_spans, cache=cache, threshold=0.30)
        lid_cluster = _find_cluster_with_prefix(clusters, "t_lidsleep_")
        assert lid_cluster is not None
        assert len(lid_cluster.task_ids) >= 5

    def test_at_least_two_real_clusters(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        """Kill-switch multi-cluster check: ≥2 non-trivial clusters."""
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            clusters = cluster_queries(fixture_spans, cache=cache, threshold=0.30)
        non_trivial = [c for c in clusters if c.span_count >= 3]
        assert len(non_trivial) >= 2, (
            f"expected >= 2 non-trivial clusters, got {len(non_trivial)}"
        )

    def test_distractors_dont_merge_into_gold(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        """Precision: rust/postgres/react queries stay out of gold clusters."""
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            clusters = cluster_queries(fixture_spans, cache=cache, threshold=0.30)
        for cluster in clusters:
            distract_count = sum(1 for t in cluster.task_ids if "distract" in t)
            if distract_count > 0:
                # Distractors may form their own singleton clusters, but
                # shouldn't merge with gold
                gold_count = (
                    sum(1 for t in cluster.task_ids if "cmspark" in t)
                    + sum(1 for t in cluster.task_ids if "lidsleep" in t)
                )
                assert gold_count == 0, (
                    f"distractors merged with {gold_count} gold task_ids in cluster "
                    f"{cluster.cluster_id}"
                )


class TestRecallRetrieval:
    """W2 retrieval correctness on the fixture."""

    def test_recall_finds_cmspark_for_screenshot_query(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            results = recall_similar(
                "CMSpark screenshot permission popup",
                fixture_spans,
                cache=cache,
                top_k=5,
                threshold=0.30,
            )
        assert len(results) > 0, "expected recall to find cmspark matches"
        assert any("cmspark" in r.task_id for r in results), (
            f"no cmspark task_id in top results: {[r.task_id for r in results]}"
        )

    def test_recall_finds_lid_sleep_for_overheating_query(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            results = recall_similar(
                "MacBook lid closed overheating",
                fixture_spans,
                cache=cache,
                top_k=5,
                threshold=0.30,
            )
        assert len(results) > 0
        assert any("lidsleep" in r.task_id for r in results), (
            f"no lidsleep task_id in top results: {[r.task_id for r in results]}"
        )

    def test_recall_doesnt_return_distractors_for_screenshot_query(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        """High-threshold recall shouldn't pull in unrelated queries."""
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            results = recall_similar(
                "CMSpark screenshot permission popup",
                fixture_spans,
                cache=cache,
                top_k=5,
                threshold=0.50,  # stricter
            )
        distract_results = [r for r in results if "distract" in r.task_id]
        assert distract_results == [], (
            f"distractors returned for screenshot query: "
            f"{[r.task_id for r in distract_results]}"
        )

    def test_recall_returns_step_sequence(
        self, fixture_spans: list[dict], cache: EmbeddingCache
    ) -> None:
        """Recall results carry step_sequence so W3 replay can use it."""
        with patch.object(cache, "_compute", side_effect=_keyword_embedding):
            results = recall_similar(
                "CMSpark screenshot permission",
                fixture_spans,
                cache=cache,
                top_k=3,
                threshold=0.30,
            )
        assert len(results) > 0
        for r in results:
            # Every fixture span has name=route:query; step_sequence should include it
            assert "route:query" in r.step_sequence


class TestFixtureIntegrity:
    """Sanity checks on the fixture itself."""

    def test_fixture_has_at_least_20_spans(self) -> None:
        spans = _load_fixture()
        assert len(spans) >= 20, f"fixture has {len(spans)} spans, expected >= 20"

    def test_fixture_has_expected_task_id_distribution(self) -> None:
        spans = _load_fixture()
        cmspark = sum(1 for s in spans if "cmspark" in s.get("task_id", ""))
        lid = sum(1 for s in spans if "lidsleep" in s.get("task_id", ""))
        distract = sum(1 for s in spans if "distract" in s.get("task_id", ""))
        assert cmspark >= 10
        assert lid >= 5
        assert distract >= 3


def _find_cluster_with_prefix(clusters: list, prefix: str):
    """Find the cluster containing a task_id with the given prefix."""
    for c in clusters:
        if any(t.startswith(prefix.rstrip("_") + "_") for t in c.task_ids):
            return c
    return None
