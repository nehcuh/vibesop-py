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
    # cmspark dogfood: last-resort levenshtein often reports conf=1.0
    assert (
        should_enqueue_from_route(
            has_match=True, confidence=1.0, layer="levenshtein"
        )
        == "low_confidence"
    )
    assert (
        should_enqueue_from_route(has_match=True, confidence=0.95, layer="ai_triage")
        is None
    )

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
        query="debug flaky test",
        skill_id="s1",
        confidence=0.2,
        kind="low_confidence",
        reason_zh="r",
        query_hash="h1",
    )
    assert item is not None
    store.dismiss(item.id)

    again = store.try_enqueue(
        query="debug flaky test",
        skill_id="s1",
        confidence=0.2,
        kind="low_confidence",
        reason_zh="r",
        query_hash="h1",
    )
    assert again is None


def test_dismiss_suppresses_requeue_across_skills(tmp_path: Path) -> None:
    """M7 (pi NIT-d): suppress is keyed by query_hash, same as dedup — a
    dismissed query re-routed through a different skill_id stays suppressed."""
    path = tmp_path / "routing_pending.jsonl"
    store = RoutingPendingStore(path)

    item = _enqueue(store, "route my query", "skill-a", "h-same")
    assert item is not None
    store.dismiss(item.id)

    # Same query_hash, different skill → still suppressed.
    assert _enqueue(store, "route my query", "skill-b", "h-same") is None
    assert store.is_suppressed("h-same", "skill-b")

    # Legacy rows with empty query_hash keep the (hash, skill_id) fallback:
    # a dismiss under skill-a does not suppress a different skill.
    legacy = _enqueue(store, "legacy query text", "skill-a", "")
    assert legacy is not None
    store.dismiss(legacy.id)
    assert _enqueue(store, "legacy query text", "skill-a", "") is None
    assert _enqueue(store, "legacy query text", "skill-b", "") is not None
    assert store.is_suppressed("", "skill-a")
    assert not store.is_suppressed("", "skill-b")


def test_daily_cap(tmp_path: Path) -> None:
    path = tmp_path / "routing_pending.jsonl"
    store = RoutingPendingStore(path)

    for i in range(3):
        item = store.try_enqueue(
            query=f"query topic {i}",
            skill_id=f"s{i}",
            confidence=0.1,
            kind="low_confidence",
            reason_zh="r",
            query_hash=f"h{i}",
        )
        assert item is not None

    overflow = store.try_enqueue(
        query="query topic 3",
        skill_id="s3",
        confidence=0.1,
        kind="low_confidence",
        reason_zh="r",
        query_hash="h3",
    )
    assert overflow is None
    assert store.stats()["created_today"] == 3
    assert store.stats()["daily_cap"] == 3


def _enqueue(store: RoutingPendingStore, query: str, skill_id: str, query_hash: str):
    return store.try_enqueue(
        query=query,
        skill_id=skill_id,
        confidence=0.2,
        kind="low_confidence",
        reason_zh="r",
        query_hash=query_hash,
    )


def test_low_info_gate_blocks_and_records_miss(tmp_path: Path) -> None:
    # Default layout so the store can derive the MissCounter project root.
    path = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
    store = RoutingPendingStore(path)

    for junk in ("可以", "✓", "/review"):
        assert _enqueue(store, junk, "s1", f"h-{junk}") is None

    assert store.list_pending() == []
    assert store.stats()["created_today"] == 0
    assert not path.exists()  # gate-blocked queries never touch the queue file

    from vibesop.core.skills.miss_counter import MissCounter

    counter = MissCounter(tmp_path)
    for junk in ("可以", "✓", "/review"):
        cluster = counter.count_for(junk)
        assert cluster is not None, junk
        assert cluster.count == 1


def test_low_info_gate_passes_real_queries(tmp_path: Path) -> None:
    path = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
    store = RoutingPendingStore(path)

    assert _enqueue(store, "review my code", "s1", "h-review") is not None
    assert _enqueue(store, "debug this", "s2", "h-debug") is not None
    assert len(store.list_pending()) == 2

    from vibesop.core.skills.miss_counter import MissCounter

    assert MissCounter(tmp_path).count_for("review my code") is None


def test_low_info_gate_no_match_does_not_double_record(tmp_path: Path) -> None:
    """no_match misses are already counted by UnifiedRouter._record_route_miss
    on the same event; the gate must not count them a second time."""
    path = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
    store = RoutingPendingStore(path)

    blocked = store.try_enqueue(
        query="可以",
        skill_id=None,
        confidence=0.0,
        kind="no_match",
        reason_zh="r",
        query_hash="h-nomatch",
    )
    assert blocked is None

    from vibesop.core.skills.miss_counter import MissCounter

    assert MissCounter(tmp_path).count_for("可以") is None


def test_low_info_gate_cjk_acknowledgments(tmp_path: Path) -> None:
    """pi NIT-7: CJK confirmation replies tokenize into >=2 meaningful
    overlapping bigrams and would penetrate the token rule — the exact-match
    acknowledgment stopword set blocks them."""
    path = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
    store = RoutingPendingStore(path)

    for ack in ("知道了", "没问题", "OK"):
        assert _enqueue(store, ack, "s1", f"h-{ack}") is None

    assert store.list_pending() == []

    from vibesop.core.skills.miss_counter import MissCounter

    counter = MissCounter(tmp_path)
    for ack in ("知道了", "没问题", "OK"):
        assert counter.count_for(ack) is not None, ack

    # Exact-match only: a real query merely containing "没问题" passes.
    real = _enqueue(store, "修一下没问题这个报错", "s1", "h-real")
    assert real is not None
    assert counter.count_for("修一下没问题这个报错") is None


def test_dedup_by_query_hash_across_skills(tmp_path: Path) -> None:
    """M7: the same query routed to 2 skills must not eat 2 daily slots."""
    path = tmp_path / "routing_pending.jsonl"
    store = RoutingPendingStore(path)

    a = _enqueue(store, "route my query", "skill-a", "h-same")
    assert a is not None
    # Same query_hash, different skill → deduped, no second row, no extra quota.
    b = _enqueue(store, "route my query", "skill-b", "h-same")
    assert b is None

    pending = store.list_pending()
    assert len(pending) == 1
    assert store.count_created_today() == 1
    assert store.stats()["created_today"] == 1

    # Historical rows with empty query_hash still dedup by (hash, skill_id)
    # and count individually toward the cap.
    legacy = _enqueue(store, "legacy query text", "skill-a", "")
    assert legacy is not None
    assert _enqueue(store, "legacy query text", "skill-a", "") is None
    assert _enqueue(store, "legacy query text", "skill-b", "") is not None
    assert store.count_created_today() == 3  # 1 hash + 2 legacy rows


def test_cross_instance_writes_do_not_lose_entries(tmp_path: Path) -> None:
    """Two store instances (as created per `vibe route`) must not clobber
    each other's rows even under concurrent read-modify-write."""
    import concurrent.futures
    import json

    import vibesop.core.instinct.routing_pending as rp
    from vibesop.core.instinct.routing_pending import _MAX_NEW_PER_DAY

    path = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
    store_a = RoutingPendingStore(path)
    store_b = RoutingPendingStore(path)

    n_per_store = 10
    assert 2 * n_per_store > _MAX_NEW_PER_DAY  # prove the cap is bypassed below
    original_cap = rp._MAX_NEW_PER_DAY
    rp._MAX_NEW_PER_DAY = 1000
    try:
        def write_batch(store: RoutingPendingStore, tag: str) -> None:
            for i in range(n_per_store):
                item = _enqueue(store, f"{tag} query number {i}", f"s-{tag}-{i}", f"h-{tag}-{i}")
                assert item is not None

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(write_batch, store_a, "alpha")
            f2 = pool.submit(write_batch, store_b, "bravo")
            f1.result()
            f2.result()
    finally:
        rp._MAX_NEW_PER_DAY = original_cap

    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 2 * n_per_store
    assert len({row["id"] for row in rows}) == 2 * n_per_store
    assert len({row["query_hash"] for row in rows}) == 2 * n_per_store

    # Cross-instance resolve: an instance that never saw the enqueue must
    # still resolve the item (re-read under the cross-process lock).
    fresh = RoutingPendingStore(path)
    resolved = fresh.accept(rows[0]["id"])
    assert resolved is not None
    assert resolved.status == "accepted"
    reread = RoutingPendingStore(path)
    assert reread.get(rows[0]["id"]).status == "accepted"  # type: ignore[union-attr]
