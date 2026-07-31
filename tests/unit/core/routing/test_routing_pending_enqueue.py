"""Sprint 1 — UnifiedRouter enqueues low-conf / no-match into RoutingPendingStore."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from vibesop.core.instinct.routing_pending import RoutingPendingStore
from vibesop.core.routing.unified import UnifiedRouter


def _make_router(tmp_path: Path) -> UnifiedRouter:
    # Minimal construction: patch heavy deps via project_root only path used by enqueue
    router = object.__new__(UnifiedRouter)
    router.project_root = tmp_path
    router._instinct_learner = None  # type: ignore[attr-defined]

    # Provide _get_instinct_learner used by enqueue
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(tmp_path / ".vibe" / "instincts.jsonl")

    def _get() -> InstinctLearner:
        return learner

    router._get_instinct_learner = _get  # type: ignore[method-assign]
    return router  # type: ignore[return-value]


def test_enqueue_low_confidence(tmp_path: Path) -> None:
    router = _make_router(tmp_path)
    primary = MagicMock()
    primary.skill_id = "pack/skill-a"
    primary.confidence = 0.3
    result = MagicMock()
    result.has_match = True
    result.primary = primary

    router._maybe_enqueue_routing_pending("weird low conf query", result)  # type: ignore[attr-defined]

    store = RoutingPendingStore(tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl")
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].kind == "low_confidence"
    assert pending[0].skill_id == "pack/skill-a"


def test_enqueue_skips_high_confidence(tmp_path: Path) -> None:
    router = _make_router(tmp_path)
    primary = MagicMock()
    primary.skill_id = "pack/skill-a"
    primary.confidence = 0.95
    result = MagicMock()
    result.has_match = True
    result.primary = primary

    router._maybe_enqueue_routing_pending("clear query", result)  # type: ignore[attr-defined]

    store = RoutingPendingStore(tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl")
    assert store.list_pending() == []


def test_enqueue_no_match(tmp_path: Path) -> None:
    router = _make_router(tmp_path)
    result = MagicMock()
    result.has_match = False
    result.primary = None

    router._maybe_enqueue_routing_pending("totally unknown intent xyz", result)  # type: ignore[attr-defined]

    store = RoutingPendingStore(tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl")
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].kind == "no_match"
