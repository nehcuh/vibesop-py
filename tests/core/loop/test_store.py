"""Tests for ``LoopStore`` — JSON persistence with atomic writes.

Covers:
    - Spec CRUD: save / load / delete / list / overwrite
    - State persistence with default-on-missing behaviour
    - Atomic write semantics: ``.tmp`` is replaced, target is updated atomically
    - Path traversal defence: unsafe names rejected at store layer
    - Schema drift detection: corrupted JSON / wrong shape returns None
    - Cross-loop isolation
"""

from __future__ import annotations

import tempfile
from datetime import UTC
from pathlib import Path

import pytest

from vibesop.core.loop.models import LoopSpec, LoopState, LoopStatus
from vibesop.core.loop.store import LoopStore


def _spec(name: str, **overrides) -> LoopSpec:
    base = {
        "name": name,
        "description": f"loop {name}",
        "schedule": "0 0 * * *",
        "query": f"check {name}",
    }
    base.update(overrides)
    return LoopSpec(**base)


# ──────────────────────────────────────────────────────────────────
# Spec CRUD
# ──────────────────────────────────────────────────────────────────


class TestSpecCRUD:
    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(
                "ci-watcher",
                schedule="*/30 * * * *",
                skill_id="systematic-debugging",
                query="",  # skill_id takes precedence
            )
            store.save_spec(spec)
            loaded = store.load_spec("ci-watcher")
            assert loaded is not None
            assert loaded.name == "ci-watcher"
            assert loaded.schedule == "*/30 * * * *"
            assert loaded.skill_id == "systematic-debugging"

    def test_load_nonexistent_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            assert store.load_spec("nonexistent") is None

    def test_delete_returns_true_when_existed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(_spec("to-delete"))
            assert store.delete_spec("to-delete") is True
            assert store.load_spec("to-delete") is None

    def test_delete_returns_false_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            assert store.delete_spec("never-existed") is False

    def test_delete_removes_state_too(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec("full")
            store.save_spec(spec)
            store.save_state(LoopState(spec=spec, total_runs=7))
            loop_dir = Path(tmpdir) / "full"
            assert (loop_dir / "state.json").exists()
            store.delete_spec("full")
            assert not loop_dir.exists()

    def test_list_specs_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            assert store.list_specs() == []

    def test_list_specs_sorted_by_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            # Insert in non-sorted order
            for n in ("c-third", "a-first", "b-second"):
                store.save_spec(_spec(n))
            result = store.list_specs()
            assert [s.name for s in result] == ["a-first", "b-second", "c-third"]

    def test_list_specs_skips_hidden_and_files(self):
        """macOS .DS_Store and stray files must not break listing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(_spec("real-loop"))
            # Stray non-dir file
            (Path(tmpdir) / "stray.txt").write_text("noise", encoding="utf-8")
            # Hidden dir (would be invalid name anyway)
            (Path(tmpdir) / ".hidden-dir").mkdir()
            result = store.list_specs()
            assert [s.name for s in result] == ["real-loop"]

    def test_overwrite_spec_replaces_in_place(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(_spec("x", description="v1", schedule="0 0 * * *"))
            store.save_spec(_spec("x", description="v2", schedule="*/5 * * * *"))
            loaded = store.load_spec("x")
            assert loaded is not None
            assert loaded.description == "v2"
            assert loaded.schedule == "*/5 * * * *"

    def test_corrupted_json_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(_spec("corrupt-me"))
            path = store._spec_path("corrupt-me")
            path.write_text("{bad json", encoding="utf-8")
            assert store.load_spec("corrupt-me") is None

    def test_schema_drift_returns_none(self):
        """JSON parses but doesn't match LoopSpec (e.g. missing required field)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(_spec("drift-me"))
            path = store._spec_path("drift-me")
            # Replace with valid JSON that violates LoopSpec schema
            path.write_text('{"description": "no name field"}', encoding="utf-8")
            assert store.load_spec("drift-me") is None


# ──────────────────────────────────────────────────────────────────
# State persistence
# ──────────────────────────────────────────────────────────────────


class TestStatePersistence:
    def test_save_and_load_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec("test-ci")
            store.save_spec(spec)
            state = LoopState(
                spec=spec,
                total_runs=5,
                consecutive_failures=2,
                status=LoopStatus.FAILING,
            )
            store.save_state(state)
            loaded = store.load_state("test-ci")
            assert loaded is not None
            assert loaded.total_runs == 5
            assert loaded.consecutive_failures == 2
            assert loaded.status == LoopStatus.FAILING

    def test_load_state_returns_default_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(_spec("fresh"))
            state = store.load_state("fresh")
            assert state is not None
            assert state.total_runs == 0
            assert state.consecutive_failures == 0
            assert state.status == LoopStatus.ACTIVE
            assert state.recent_runs == []

    def test_load_state_returns_none_when_spec_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            assert store.load_state("no-spec") is None

    def test_state_round_trip_preserves_recent_runs(self):
        """Critical: Phase 1-1 had a half-finished _dict_to_state that
        dropped recent_runs. BaseModel round-trip must preserve them."""
        from datetime import datetime

        from vibesop.core.loop.models import LoopRunRecord

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec("with-history")
            store.save_spec(spec)
            state = LoopState(spec=spec)
            now = datetime.now(UTC)
            state.record_run(
                LoopRunRecord(
                    loop_name="with-history",
                    started_at=now,
                    finished_at=now,
                    success=True,
                    output_summary="ok",
                    duration_s=0.1,
                )
            )
            state.record_run(
                LoopRunRecord(
                    loop_name="with-history",
                    started_at=now,
                    success=False,
                    error="boom",
                    duration_s=0.2,
                )
            )
            store.save_state(state)

            loaded = store.load_state("with-history")
            assert loaded is not None
            assert loaded.total_runs == 2
            assert len(loaded.recent_runs) == 2
            assert loaded.recent_runs[0].success is True
            assert loaded.recent_runs[1].success is False
            assert loaded.recent_runs[1].error == "boom"


# ──────────────────────────────────────────────────────────────────
# Atomic write
# ──────────────────────────────────────────────────────────────────


class TestAtomicWrite:
    def test_save_leaves_no_tmp_residue(self):
        """After a successful save, no .tmp file should remain."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(_spec("clean"))
            loop_dir = Path(tmpdir) / "clean"
            files = {f.name for f in loop_dir.iterdir()}
            assert "spec.json" in files
            assert "spec.tmp" not in files

    def test_missing_target_returns_none_and_recoverable(self):
        """A interrupted write (target absent) reads as None; subsequent
        save recovers. This is the *real* guarantee atomic writes give us:
        the target is either the previous version or the new version,
        never a half-written file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(_spec("atomic"))
            path = store._spec_path("atomic")
            path.unlink()  # simulate interrupted write: target gone

            assert store.load_spec("atomic") is None

            store.save_spec(_spec("atomic"))  # recovery
            loaded = store.load_spec("atomic")
            assert loaded is not None
            assert loaded.name == "atomic"


# ──────────────────────────────────────────────────────────────────
# Path traversal defence (P0 fix)
# ──────────────────────────────────────────────────────────────────


class TestPathTraversalDefence:
    @pytest.mark.parametrize(
        "unsafe_name",
        [
            "..",
            "../etc",
            "foo/bar",
            "foo\\bar",
            "",
            ".",
            "..hidden",
            "-leading",
            "UPPER",
            "with space",
        ],
    )
    def test_load_rejects_unsafe_name(self, unsafe_name: str):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            # load_spec must not even attempt to read; returns None silently.
            assert store.load_spec(unsafe_name) is None

    @pytest.mark.parametrize(
        "unsafe_name",
        ["..", "../etc", "foo/bar", "foo\\bar"],
    )
    def test_delete_raises_on_unsafe_name(self, unsafe_name: str):
        """delete_spec must refuse unsafe names loudly (ValueError),
        not silently traverse."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            with pytest.raises(ValueError, match="unsafe loop name"):
                store.delete_spec(unsafe_name)

    def test_save_rejects_unsafe_name(self):
        """Even though LoopSpec itself enforces the pattern, save_spec
        re-validates defensively."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            # Bypass LoopSpec validation by crafting a spec and renaming
            spec = _spec("safe-name")
            object.__setattr__(spec, "name", "../evil")  # type: ignore[attr-defined]
            with pytest.raises(ValueError, match="unsafe loop name"):
                store.save_spec(spec)


# ──────────────────────────────────────────────────────────────────
# Cross-loop isolation
# ──────────────────────────────────────────────────────────────────


class TestCrossLoopIsolation:
    def test_two_loops_do_not_interfere(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(_spec("loop-a", description="A"))
            store.save_spec(_spec("loop-b", description="B"))
            assert store.load_spec("loop-a").description == "A"
            assert store.load_spec("loop-b").description == "B"
            store.delete_spec("loop-a")
            assert store.load_spec("loop-a") is None
            assert store.load_spec("loop-b") is not None

    def test_full_field_round_trip(self):
        """All LoopSpec fields survive a save→load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = LoopSpec(
                name="full-spec",
                description="Full field test",
                schedule="30 22 * * 1-5",
                query="check PR status and summarize",
                max_failures=5,
                tags=["ci", "nightly"],
                env_overrides={"LOG_LEVEL": "DEBUG"},
            )
            store.save_spec(spec)
            loaded = store.load_spec("full-spec")
            assert loaded is not None
            assert loaded.name == spec.name
            assert loaded.description == spec.description
            assert loaded.schedule == spec.schedule
            assert loaded.query == spec.query
            assert loaded.max_failures == spec.max_failures
            assert loaded.tags == spec.tags
            assert loaded.env_overrides == spec.env_overrides
            assert abs((loaded.created_at - spec.created_at).total_seconds()) < 1
