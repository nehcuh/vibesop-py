"""Frozen hybrid-recall fixtures wired into the suite (panel 2026-10-15, T1/T2).

The corpus in ``tests/fixtures/hybrid-recall/`` and the eval script were
previously consumed by nothing: a hybrid-recall regression could land with
every gate green. These tests consume the frozen corpus on the two
model-free, deterministic lanes — BM25 recall and the applicability guard —
so tokenization, ranking, and guard regressions go red in CI. The dense
lane stays in ``scripts/eval_hybrid_recall.py`` (needs a downloaded model).
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from vibesop.core.config import RoutingConfig
from vibesop.core.routing.lexical_recall import bm25_recall
from vibesop.core.routing.triage_cache import TriageCache
from vibesop.core.routing.triage_service import TriageService

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "hybrid-recall"


def _load_catalog() -> list[dict]:
    raw = yaml.safe_load((FIXTURES / "catalog.yaml").read_text(encoding="utf-8"))
    candidates = []
    for addition in raw:
        candidate = dict(addition)
        candidate.setdefault("name", candidate["id"].rsplit("/", maxsplit=1)[-1])
        for key in ("triggers", "keywords", "scenarios", "routing_requires_any"):
            candidate.setdefault(key, [])
        candidate.setdefault("management_only", False)
        candidate.setdefault("disable_model_invocation", False)
        candidates.append(candidate)
    return candidates


def _load_queries() -> list[dict]:
    return yaml.safe_load((FIXTURES / "queries.yaml").read_text(encoding="utf-8"))


def _sibling_map(ids: list[str]) -> dict[str, list[str]]:
    """Group ids by stem with the trailing version suffix stripped."""

    def stem(sid: str) -> str:
        return re.sub(r"-[0-9][0-9a-z.]*$", "", sid)

    groups: dict[str, list[str]] = {}
    for sid in ids:
        groups.setdefault(stem(sid), []).append(sid)
    return {sid: [other for other in groups[stem(sid)] if other != sid] for sid in ids}


@pytest.fixture(scope="module")
def candidates() -> list[dict]:
    return _load_catalog()


@pytest.fixture(scope="module")
def guard(tmp_path_factory):
    cost = MagicMock()
    cost.get_monthly_cost.return_value = 0.0
    return TriageService(
        config=RoutingConfig(),
        cost_tracker=cost,
        prefilter=MagicMock(),
        cache_manager=MagicMock(),
        get_skill_source=lambda sid, _ns: sid,
        triage_cache=TriageCache(tmp_path_factory.mktemp("triage-cache")),
        embedding_recall=None,
    )


def test_fixture_dataset_integrity(candidates):
    ids = [str(c["id"]) for c in candidates]
    assert len(ids) == len(set(ids)), "candidate ids must stay unique"
    known = set(ids)
    for row in _load_queries():
        for sid in row.get("expect") or []:
            assert sid in known, f"expect id {sid} missing from catalog"
        for sid in row.get("reject") or []:
            assert sid in known, f"reject id {sid} missing from catalog"


@pytest.mark.parametrize(
    "row",
    [r for r in _load_queries() if r.get("expect")],
    ids=lambda r: r["query"][:30],
)
def test_positive_query_recall_and_sibling_ranking(candidates, row):
    """T1 recall gate + T2 disambiguation: every expected id must appear in
    BM25 recall@20 AND outrank its version siblings — the panel showed the
    sibling pairs are the corpus's core risk (a ranking/tie-break regression
    routes to the wrong version with the rest of the suite green)."""
    ranked = bm25_recall(row["query"], candidates, 20)
    siblings = _sibling_map([str(c["id"]) for c in candidates])
    for expected in row["expect"]:
        assert expected in ranked, (
            f"recall miss: {expected} not in BM25 top-20 for {row['query']!r}"
        )
        for sibling in siblings[expected]:
            if sibling in ranked:
                assert ranked.index(expected) < ranked.index(sibling), (
                    f"sibling inversion: {sibling} outranks {expected} for {row['query']!r}"
                )


@pytest.mark.parametrize(
    "row",
    [r for r in _load_queries() if r.get("reject")],
    ids=lambda r: r["query"][:30],
)
def test_negative_query_guard_removes_reject_target(guard, candidates, row):
    kept = {str(c["id"]) for c in guard.applicable_candidates(row["query"], candidates)}
    leaked = [sid for sid in row["reject"] if sid in kept]
    assert not leaked, f"guard admitted negated/referenced target {leaked} for {row['query']!r}"
