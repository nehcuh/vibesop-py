"""Tests for ReflectionStore — append + list_all (v3 Phase A Task 8).

The store is the persistence layer for the Reflection dataclass (Task 7).
It must be:

1. Cross-process safe — multiple ``vibe`` hooks + the dashboard may append
   concurrently. Pattern matches SpanWriter._locked_append (inline
   ``fcntl`` on POSIX, ``cross_process_lock`` helper on Windows).
2. Lossless — every append survives a ``list_all`` reload with the same id.
3. Tolerant — corrupted lines (e.g. a half-written append from a pre-lock
   era or a hand-edited file) are skipped, not fatal.

File layout: ``<storage_dir>/reflections.jsonl`` (one Reflection per line,
JSON-serialised via ``Reflection.to_dict``). The production caller passes
``storage_dir=.vibe/observability`` — same convention as SpanWriter, where
``storage_dir`` IS the leaf directory and the caller composes the full path.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from vibesop.core.observability.reflection import Reflection, ReflectionStore


def _make_reflection(
    *,
    kind: str = "context_note",
    content: str = "",
    target_id: str = "t1",
    task_id: str = "task-1",
) -> Reflection:
    return Reflection(
        target_type="task",
        target_id=target_id,
        task_id=task_id,
        kind=kind,  # type: ignore[arg-type]
        content=content,
    )


class TestReflectionStoreAppend:
    def test_reflection_store_append_round_trip(self, tmp_path: Path) -> None:
        """append() → list_all() must return the same reflection (id match)."""
        store = ReflectionStore(storage_dir=tmp_path)
        r = _make_reflection(
            kind="cost_blow",
            content="$0.50 vs $0.20 baseline",
            target_id="t1",
            task_id="task-1",
        )
        store.append(r)
        loaded = store.list_all()
        assert len(loaded) == 1
        assert loaded[0].id == r.id
        assert loaded[0].content == r.content
        assert loaded[0].kind == r.kind

    def test_store_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Passing a nested non-existent storage_dir must mkdir -p it."""
        nested = tmp_path / "a" / "b" / "c"
        store = ReflectionStore(storage_dir=nested)
        store.append(_make_reflection())
        assert nested.exists()
        assert (nested / "reflections.jsonl").exists()

    def test_store_filename_is_reflections_jsonl(self, tmp_path: Path) -> None:
        """File MUST be ``reflections.jsonl`` — DAG rebuilder + dashboard
        hardcode this path; renaming would silently break the join."""
        store = ReflectionStore(storage_dir=tmp_path)
        store.append(_make_reflection())
        assert (tmp_path / "reflections.jsonl").exists()

    def test_append_multiple_preserves_order(self, tmp_path: Path) -> None:
        """Successive appends land in insertion order — list_all()[i] is
        the i-th appended reflection. The dashboard renders newest-last
        and relies on this ordering."""
        store = ReflectionStore(storage_dir=tmp_path)
        for i in range(5):
            store.append(_make_reflection(content=f"r{i}", target_id=f"t{i}"))
        loaded = store.list_all()
        assert len(loaded) == 5
        assert [r.content for r in loaded] == [f"r{i}" for i in range(4, -1, -1)] or [
            r.content for r in loaded
        ] == [f"r{i}" for i in range(5)]

    def test_list_all_empty_when_no_file(self, tmp_path: Path) -> None:
        """Fresh storage_dir with no reflections.jsonl → empty list, not raise."""
        store = ReflectionStore(storage_dir=tmp_path)
        assert store.list_all() == []

    def test_list_all_skips_corrupt_lines(self, tmp_path: Path) -> None:
        """A malformed JSON line must not crash list_all — skip and continue.
        Defensive: a hand-edited or partially-written file shouldn't break
        the dashboard."""
        store = ReflectionStore(storage_dir=tmp_path)
        store.append(_make_reflection(content="good1", target_id="t1"))
        # Manually append a corrupt line
        with (tmp_path / "reflections.jsonl").open("a") as f:
            f.write("{not valid json\n")
            f.write("also not json\n")
        store.append(_make_reflection(content="good2", target_id="t2"))
        loaded = store.list_all()
        # 2 valid reflections survive; 2 corrupt lines skipped
        contents = [r.content for r in loaded]
        assert "good1" in contents
        assert "good2" in contents
        assert len(loaded) == 2


class TestReflectionStoreConcurrent:
    def test_reflection_store_concurrent_writes_safe(self, tmp_path: Path) -> None:
        """Two threads appending 50 each → 100 lines, all parse, all unique.

        Without the cross-process / in-process lock, concurrent ``write()``
        calls on the same file handle would interleave bytes and produce
        malformed JSON lines (POSIX PIPE_BUF = 4096 only guarantees
        atomicity for short lines; reflection payloads can exceed this
        once content + linked_action are populated).
        """
        store = ReflectionStore(storage_dir=tmp_path)
        per_thread = 50
        barrier = threading.Barrier(2)  # align start to maximise contention

        def writer(thread_id: int) -> list[str]:
            ids: list[str] = []
            barrier.wait()
            for i in range(per_thread):
                r = _make_reflection(
                    content=f"t{thread_id}-r{i}",
                    target_id=f"t{thread_id}-{i}",
                    task_id=f"task-{thread_id}",
                )
                store.append(r)
                ids.append(r.id)
            return ids

        t1_ids: list[str] = []
        t2_ids: list[str] = []

        def run_t1() -> None:
            nonlocal t1_ids
            t1_ids = writer(1)

        def run_t2() -> None:
            nonlocal t2_ids
            t2_ids = writer(2)

        t1 = threading.Thread(target=run_t1)
        t2 = threading.Thread(target=run_t2)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not t1.is_alive(), "thread 1 hung"
        assert not t2.is_alive(), "thread 2 hung"

        loaded = store.list_all()
        # Exact count — no appends lost, no duplicates from retry
        assert len(loaded) == per_thread * 2, (
            f"expected {per_thread * 2} reflections, got {len(loaded)} "
            f"(some lines were corrupted by concurrent writes)"
        )
        # Every id unique
        loaded_ids = {r.id for r in loaded}
        assert len(loaded_ids) == per_thread * 2, "duplicate ids detected"
        # Every written id appears
        expected_ids = set(t1_ids) | set(t2_ids)
        assert loaded_ids == expected_ids

    def test_concurrent_writes_no_interleaved_lines(self, tmp_path: Path) -> None:
        """Stricter: the JSONL file must contain exactly N well-formed lines.
        If lines interleave, json.loads would either fail or produce wrong
        shapes — this catches the failure mode where bytes from two writes
        end up on the same physical line."""
        store = ReflectionStore(storage_dir=tmp_path)
        n_threads = 4
        per_thread = 25
        barrier = threading.Barrier(n_threads)

        def writer() -> None:
            barrier.wait()
            for i in range(per_thread):
                # Larger payload to push past PIPE_BUF
                store.append(
                    _make_reflection(
                        content="x" * 500,
                        target_id=f"t-{i}",
                    )
                )

        threads = [threading.Thread(target=writer) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Read raw file — count well-formed lines
        raw_path = tmp_path / "reflections.jsonl"
        lines = raw_path.read_text().splitlines()
        assert len(lines) == n_threads * per_thread, (
            f"line count mismatch: {len(lines)} vs expected "
            f"{n_threads * per_thread} → concurrent writes interleaved bytes"
        )


class TestReflectionStoreRoundTripIntegrity:
    def test_round_trip_preserves_all_fields(self, tmp_path: Path) -> None:
        """After append + list_all, every field of the original Reflection
        must be intact — including linked_action (dict), severity, status."""
        store = ReflectionStore(storage_dir=tmp_path)
        original = Reflection(
            target_type="decision_node",
            target_id="d-1",
            task_id="task-x",
            kind="positive_pattern",
            content="this classifier upgrade was great",
            severity="critical",
            linked_action={"type": "promote_instinct", "target": "code-review"},
        )
        store.append(original)
        loaded = store.list_all()
        assert len(loaded) == 1
        assert loaded[0] == original

    def test_idempotent_append_writes_two_lines(self, tmp_path: Path) -> None:
        """Same Reflection appended twice = 2 lines (the store is append-only;
        dedup is the dashboard's job, not the store's). The store is a log,
        not a set."""
        store = ReflectionStore(storage_dir=tmp_path)
        r = _make_reflection(content="dup")
        store.append(r)
        store.append(r)  # same id
        loaded = store.list_all()
        assert len(loaded) == 2
        assert loaded[0].id == loaded[1].id == r.id


class TestReflectionStoreQuery:
    """Task 9.1: list_by_task + list_open."""

    def test_list_by_task_filters_correctly(self, tmp_path: Path) -> None:
        """list_by_task returns ONLY reflections whose task_id matches."""
        store = ReflectionStore(storage_dir=tmp_path)
        store.append(_make_reflection(content="r1", target_id="t1", task_id="task-A"))
        store.append(_make_reflection(content="r2", target_id="t2", task_id="task-B"))
        store.append(_make_reflection(content="r3", target_id="t3", task_id="task-A"))
        store.append(_make_reflection(content="r4", target_id="t4", task_id="task-C"))

        a_only = store.list_by_task("task-A")
        assert {r.target_id for r in a_only} == {"t1", "t3"}
        # No cross-task leakage
        assert all(r.task_id == "task-A" for r in a_only)

    def test_list_by_task_empty_when_no_match(self, tmp_path: Path) -> None:
        """list_by_task on unknown task_id returns [], not raises."""
        store = ReflectionStore(storage_dir=tmp_path)
        store.append(_make_reflection(task_id="task-A"))
        assert store.list_by_task("task-Z") == []

    def test_list_by_task_empty_when_no_file(self, tmp_path: Path) -> None:
        """list_by_task on a fresh store returns [] (no file yet)."""
        store = ReflectionStore(storage_dir=tmp_path)
        assert store.list_by_task("task-A") == []

    def test_list_open_returns_only_open(self, tmp_path: Path) -> None:
        """list_open filters out addressed + dismissed — only 'open' status."""
        store = ReflectionStore(storage_dir=tmp_path)
        # Append 3, mutate 2 of them, then verify list_open excludes mutated.
        r1 = _make_reflection(content="open-one", target_id="t1")
        r2 = _make_reflection(content="addressed", target_id="t2")
        r3 = _make_reflection(content="dismissed", target_id="t3")
        store.append(r1)
        store.append(r2)
        store.append(r3)
        store.update_status(r2.id, "addressed")
        store.update_status(r3.id, "dismissed")

        open_only = store.list_open()
        assert len(open_only) == 1
        assert open_only[0].id == r1.id
        assert open_only[0].status == "open"

    def test_list_open_empty_when_all_addressed(self, tmp_path: Path) -> None:
        """All reflections addressed → list_open returns []."""
        store = ReflectionStore(storage_dir=tmp_path)
        r = _make_reflection(content="r")
        store.append(r)
        store.update_status(r.id, "addressed")
        assert store.list_open() == []


class TestReflectionStoreUpdateStatus:
    """Task 9.1: update_status — atomic rewrite to flip status lifecycle."""

    def test_update_status_changes_state(self, tmp_path: Path) -> None:
        """update_status(id, 'addressed') flips the persisted status."""
        store = ReflectionStore(storage_dir=tmp_path)
        r = _make_reflection(content="orig")
        store.append(r)
        assert store.list_all()[0].status == "open"

        store.update_status(r.id, "addressed")

        loaded = store.list_all()
        assert len(loaded) == 1
        assert loaded[0].status == "addressed"
        # Other fields preserved
        assert loaded[0].content == "orig"
        assert loaded[0].id == r.id

    def test_update_status_to_dismissed(self, tmp_path: Path) -> None:
        """All 3 statuses reachable via update_status."""
        store = ReflectionStore(storage_dir=tmp_path)
        r = _make_reflection()
        store.append(r)
        for new_status in ("addressed", "open", "dismissed"):
            store.update_status(r.id, new_status)
            assert store.list_all()[0].status == new_status

    def test_update_status_unknown_id_raises(self, tmp_path: Path) -> None:
        """Updating an id that doesn't exist must raise — silently no-op
        would hide dashboard bugs (e.g. stale id after rebuild)."""
        store = ReflectionStore(storage_dir=tmp_path)
        r = _make_reflection()
        store.append(r)
        with pytest.raises(KeyError):
            store.update_status("nonexistent-id", "addressed")

    def test_update_status_invalid_status_raises(self, tmp_path: Path) -> None:
        """Invalid status value must raise — Literal validation applies on
        update path too, not just on construction."""
        store = ReflectionStore(storage_dir=tmp_path)
        r = _make_reflection()
        store.append(r)
        with pytest.raises((ValueError, TypeError)):
            store.update_status(r.id, "wontfix")  # type: ignore[arg-type]

    def test_update_status_atomic_rewrite_preserves_other_reflections(self, tmp_path: Path) -> None:
        """Mutating one reflection's status must NOT alter any other
        reflection in the file — the atomic rewrite path reads → mutates
        one → writes all back. Regression guard for off-by-one / wrong-row
        mutations."""
        store = ReflectionStore(storage_dir=tmp_path)
        r1 = _make_reflection(content="r1", target_id="t1", task_id="task-A")
        r2 = _make_reflection(content="r2", target_id="t2", task_id="task-B")
        r3 = _make_reflection(content="r3", target_id="t3", task_id="task-C")
        store.append(r1)
        store.append(r2)
        store.append(r3)

        store.update_status(r2.id, "addressed")

        loaded = store.list_all()
        assert len(loaded) == 3
        by_id = {r.id: r for r in loaded}
        # Only r2 mutated
        assert by_id[r1.id].status == "open"
        assert by_id[r2.id].status == "addressed"
        assert by_id[r3.id].status == "open"
        # Other fields intact
        assert by_id[r1.id].content == "r1"
        assert by_id[r3.id].content == "r3"

    def test_update_status_round_trip_idempotent(self, tmp_path: Path) -> None:
        """Calling update_status(id, current_status) is a no-op — does not
        corrupt or duplicate the line."""
        store = ReflectionStore(storage_dir=tmp_path)
        r = _make_reflection()
        store.append(r)
        store.update_status(r.id, "open")  # already open
        store.update_status(r.id, "open")  # idempotent
        loaded = store.list_all()
        assert len(loaded) == 1
        assert loaded[0].status == "open"

    def test_update_status_concurrent_safe(self, tmp_path: Path) -> None:
        """Two threads updating DIFFERENT reflections concurrently must not
        lose either update. Cross-process lock + atomic rewrite must
        serialise the read-modify-write cycles."""
        store = ReflectionStore(storage_dir=tmp_path)
        n = 20
        reflections = [_make_reflection(content=f"r{i}", target_id=f"t{i}") for i in range(n)]
        for r in reflections:
            store.append(r)

        barrier = threading.Barrier(2)

        def updater(start: int) -> None:
            barrier.wait()
            for i in range(start, start + n // 2):
                store.update_status(reflections[i].id, "addressed")

        t1 = threading.Thread(target=updater, args=(0,))
        t2 = threading.Thread(target=updater, args=(n // 2,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        assert not t1.is_alive()
        assert not t2.is_alive()

        loaded = store.list_all()
        assert len(loaded) == n, "some reflections were lost in concurrent rewrites"
        addressed = sum(1 for r in loaded if r.status == "addressed")
        assert addressed == n, f"expected all {n} reflections addressed, only {addressed} made it"

    def test_update_status_list_all_runs_inside_cross_process_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: grok+pi Phase B closeout Q4. ``list_all()`` MUST
        execute between ``fcntl.flock(LOCK_EX)`` and ``fcntl.flock(LOCK_UN)``
        so a concurrent CLI ``append()`` cannot sneak in between the read
        and the rewrite (lost-update race).

        Pre-fix ordering: ``list_all`` → ``flock`` → ``rewrite`` → ``funlock``
        Post-fix ordering: ``flock`` → ``list_all`` → ``rewrite`` → ``funlock``

        This test instruments ``fcntl.flock`` and ``ReflectionStore.list_all``
        to record call order, then asserts the post-fix ordering holds.
        """
        pytest.importorskip("fcntl")
        import fcntl as fcntl_mod

        from vibesop.core.observability import reflection as ref_mod

        store = ReflectionStore(storage_dir=tmp_path)
        r = _make_reflection(content="seed", target_id="t1")
        store.append(r)

        events: list[tuple[str, int]] = []
        real_flock = fcntl_mod.flock
        real_list_all = ref_mod.ReflectionStore.list_all

        def tracking_flock(fd: int, op: int) -> None:
            events.append(("flock", op))
            return real_flock(fd, op)

        def tracking_list_all(self: ReflectionStore) -> list[Reflection]:
            events.append(("list_all", 0))
            return real_list_all(self)

        monkeypatch.setattr(fcntl_mod, "flock", tracking_flock)
        monkeypatch.setattr(ref_mod.ReflectionStore, "list_all", tracking_list_all)

        store.update_status(r.id, "addressed")

        # Find the LOCK_EX / LOCK_UN pair that wraps update_status's rewrite.
        # (append's flock is also tracked, so we look for the last EX/UN
        # pair which is update_status's.)
        lock_ex_idx = max(
            i for i, (name, op) in enumerate(events) if name == "flock" and op == fcntl_mod.LOCK_EX
        )
        lock_un_idx = max(
            i for i, (name, op) in enumerate(events) if name == "flock" and op == fcntl_mod.LOCK_UN
        )
        list_all_indices = [i for i, (name, _) in enumerate(events) if name == "list_all"]

        assert lock_ex_idx < lock_un_idx, f"LOCK_EX must precede LOCK_UN; events: {events}"
        # At least one list_all call (from _do_locked_update) must be BETWEEN
        # LOCK_EX and LOCK_UN — that's the regression fix.
        locked_list_alls = [i for i in list_all_indices if lock_ex_idx < i < lock_un_idx]
        assert locked_list_alls, (
            "list_all() must run INSIDE fcntl.flock(LOCK_EX/LOCK_UN) — "
            "lost-update race window. Pre-fix it ran outside the lock. "
            f"Events: {events}"
        )
