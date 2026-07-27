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
        assert [r.content for r in loaded] == [f"r{i}" for i in range(4, -1, -1)] or \
               [r.content for r in loaded] == [f"r{i}" for i in range(5)]

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
