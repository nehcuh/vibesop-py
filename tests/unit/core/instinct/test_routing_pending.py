"""Sprint 1 — RoutingPendingStore + enqueue policy tests."""

from __future__ import annotations

from pathlib import Path

from vibesop.core.instinct.routing_pending import (
    RoutingPendingStore,
    build_reason_zh,
    should_enqueue_from_route,
)


def test_should_enqueue_policy() -> None:
    assert should_enqueue_from_route(has_match=False, confidence=0.0) == "no_match"
    assert should_enqueue_from_route(has_match=True, confidence=0.3) == "low_confidence"
    assert should_enqueue_from_route(has_match=True, confidence=0.9) is None


def test_reason_zh_chinese() -> None:
    r = build_reason_zh("low_confidence", skill_id="superpowers/debug", confidence=0.4)
    assert "低置信" in r
    assert "superpowers/debug" in r


def test_enqueue_dedup_and_accept(tmp_path: Path) -> None:
    path = tmp_path / "routing_pending.jsonl"
    store = RoutingPendingStore(path)

    a = store.try_enqueue(
        query="debug asyncio hang",
        skill_id="superpowers/systematic-debugging",
        confidence=0.35,
        kind="low_confidence",
        reason_zh="test",
        query_hash="hash-a",
    )
    assert a is not None
    assert a.status == "pending"

    # Dedup open
    b = store.try_enqueue(
        query="debug asyncio hang",
        skill_id="superpowers/systematic-debugging",
        confidence=0.35,
        kind="low_confidence",
        reason_zh="test",
        query_hash="hash-a",
    )
    assert b is None

    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].id == a.id

    accepted = store.accept(a.id)
    assert accepted is not None
    assert accepted.status == "accepted"
    assert store.list_pending() == []


def test_dismiss_suppresses_requeue(tmp_path: Path) -> None:
    path = tmp_path / "routing_pending.jsonl"
    store = RoutingPendingStore(path)

    item = store.try_enqueue(
        query="q",
        skill_id="s1",
        confidence=0.2,
        kind="low_confidence",
        reason_zh="r",
        query_hash="h1",
    )
    assert item is not None
    store.dismiss(item.id)

    again = store.try_enqueue(
        query="q",
        skill_id="s1",
        confidence=0.2,
        kind="low_confidence",
        reason_zh="r",
        query_hash="h1",
    )
    assert again is None


def test_daily_cap(tmp_path: Path) -> None:
    path = tmp_path / "routing_pending.jsonl"
    store = RoutingPendingStore(path)

    for i in range(3):
        item = store.try_enqueue(
            query=f"query {i}",
            skill_id=f"s{i}",
            confidence=0.1,
            kind="low_confidence",
            reason_zh="r",
            query_hash=f"h{i}",
        )
        assert item is not None

    overflow = store.try_enqueue(
        query="query 3",
        skill_id="s3",
        confidence=0.1,
        kind="low_confidence",
        reason_zh="r",
        query_hash="h3",
    )
    assert overflow is None
    assert store.stats()["created_today"] == 3
    assert store.stats()["daily_cap"] == 3
