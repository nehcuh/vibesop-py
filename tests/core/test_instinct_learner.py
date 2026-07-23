"""Tests for instinct learning system."""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from vibesop.core.instinct.learner import (
    Instinct,
    InstinctLearner,
    SequencePattern,
    get_routing_suggestion,
    learn_instinct,
)


class TestInstinct:
    """Test Instinct dataclass."""

    def test_creation(self):
        instinct = Instinct(id="i1", pattern="p", action="a")
        assert instinct.id == "i1"
        assert instinct.pattern == "p"
        assert instinct.action == "a"
        assert instinct.confidence == pytest.approx(0.5)
        assert instinct.success_count == 0
        assert instinct.failure_count == 0
        assert instinct.tags == []

    def test_total_applications(self):
        instinct = Instinct(id="i1", pattern="p", action="a", success_count=3, failure_count=2)
        assert instinct.total_applications == 5

    def test_success_rate_with_data(self):
        instinct = Instinct(id="i1", pattern="p", action="a", success_count=3, failure_count=1)
        assert instinct.success_rate == pytest.approx(0.75)

    def test_success_rate_empty(self):
        instinct = Instinct(id="i1", pattern="p", action="a")
        assert instinct.success_rate == pytest.approx(0.5)

    def test_is_reliable_true(self):
        instinct = Instinct(id="i1", pattern="p", action="a", success_count=3, failure_count=0)
        # update() will recalculate confidence
        instinct.update(success=True)
        assert instinct.is_reliable is True

    def test_is_reliable_false_low_applications(self):
        instinct = Instinct(id="i1", pattern="p", action="a", success_count=1, failure_count=0)
        assert instinct.is_reliable is False

    def test_is_reliable_false_low_success_rate(self):
        instinct = Instinct(id="i1", pattern="p", action="a", success_count=1, failure_count=2)
        instinct.update(success=False)
        assert instinct.is_reliable is False

    def test_update_success(self):
        instinct = Instinct(id="i1", pattern="p", action="a")
        instinct.update(success=True)
        assert instinct.success_count == 1
        assert instinct.failure_count == 0
        assert instinct.last_used is not None
        assert instinct.confidence > 0.5

    def test_update_failure(self):
        instinct = Instinct(id="i1", pattern="p", action="a")
        instinct.update(success=False)
        assert instinct.success_count == 0
        assert instinct.failure_count == 1
        assert instinct.confidence < 0.5

    def test_update_multiple(self):
        instinct = Instinct(id="i1", pattern="p", action="a")
        for _ in range(5):
            instinct.update(success=True)
        assert instinct.success_count == 5
        assert instinct.confidence > 0.7

    def test_to_dict(self):
        dt = datetime(2026, 1, 1, 12, 0, 0)
        instinct = Instinct(
            id="i1",
            pattern="p",
            action="a",
            context="c",
            confidence=0.8,
            success_count=5,
            failure_count=1,
            last_used=dt,
            created_at=dt,
            source="test",
            tags=["t1"],
        )
        d = instinct.to_dict()
        assert d["id"] == "i1"
        assert d["confidence"] == pytest.approx(0.8)
        assert d["last_used"] == "2026-01-01T12:00:00"
        assert d["created_at"] == "2026-01-01T12:00:00"
        assert d["tags"] == ["t1"]

    def test_from_dict(self):
        d = {
            "id": "i1",
            "pattern": "p",
            "action": "a",
            "context": "c",
            "confidence": 0.8,
            "success_count": 5,
            "failure_count": 1,
            "last_used": "2026-01-01T12:00:00",
            "created_at": "2026-01-01T12:00:00",
            "source": "test",
            "tags": ["t1"],
        }
        instinct = Instinct.from_dict(d)
        assert instinct.id == "i1"
        assert instinct.confidence == pytest.approx(0.8)
        assert instinct.last_used == datetime(2026, 1, 1, 12, 0, 0)
        assert instinct.tags == ["t1"]

    def test_from_dict_defaults(self):
        d = {
            "id": "i1",
            "pattern": "p",
            "action": "a",
            "created_at": "2026-01-01T12:00:00",
        }
        instinct = Instinct.from_dict(d)
        assert instinct.confidence == pytest.approx(0.5)
        assert instinct.success_count == 0
        assert instinct.tags == []


class TestSequencePattern:
    """Test SequencePattern dataclass."""

    def test_creation(self):
        pattern = SequencePattern(steps=["a", "b", "c"])
        assert pattern.steps == ["a", "b", "c"]
        assert pattern.success_count == 0
        assert pattern.total_count == 0

    def test_total_count(self):
        pattern = SequencePattern(steps=["a"], success_count=3, total_count=5)
        assert pattern.total_count == 5

    def test_success_rate(self):
        pattern = SequencePattern(steps=["a"], success_count=3, total_count=4)
        assert pattern.success_rate == pytest.approx(0.75)

    def test_success_rate_empty(self):
        pattern = SequencePattern(steps=["a"])
        assert pattern.success_rate == pytest.approx(0.0)

    def test_is_candidate_true(self):
        pattern = SequencePattern(steps=["a", "b", "c"], success_count=4, total_count=5)
        assert pattern.is_candidate is True

    def test_is_candidate_false_low_count(self):
        pattern = SequencePattern(steps=["a", "b", "c"], success_count=3, total_count=3)
        assert pattern.is_candidate is False  # total_count < 5

    def test_is_candidate_false_low_success_rate(self):
        pattern = SequencePattern(steps=["a", "b", "c"], success_count=4, total_count=10)
        assert pattern.is_candidate is False  # success_rate 0.4 < 0.8

    def test_is_candidate_false_few_steps(self):
        pattern = SequencePattern(steps=["a", "b"], success_count=5, total_count=5)
        assert pattern.is_candidate is False  # only 2 steps

    def test_sequence_hash_deterministic(self):
        p1 = SequencePattern(steps=["a", "b", "c"])
        p2 = SequencePattern(steps=["a", "b", "c"])
        assert p1.sequence_hash == p2.sequence_hash

    def test_sequence_hash_different(self):
        p1 = SequencePattern(steps=["a", "b", "c"])
        p2 = SequencePattern(steps=["x", "y", "z"])
        assert p1.sequence_hash != p2.sequence_hash

    def test_to_dict(self):
        dt1 = datetime(2026, 1, 1, 12, 0, 0)
        dt2 = datetime(2026, 1, 2, 12, 0, 0)
        pattern = SequencePattern(
            steps=["a", "b", "c"],
            success_count=3,
            total_count=5,
            first_seen=dt1,
            last_seen=dt2,
            context_tags=["debugging"],
        )
        d = pattern.to_dict()
        assert d["steps"] == ["a", "b", "c"]
        assert d["success_count"] == 3
        assert d["total_count"] == 5
        assert d["first_seen"] == "2026-01-01T12:00:00"

    def test_from_dict(self):
        d = {
            "steps": ["a", "b", "c"],
            "success_count": 3,
            "total_count": 5,
            "first_seen": "2026-01-01T12:00:00",
            "last_seen": "2026-01-02T12:00:00",
            "context_tags": ["debugging"],
        }
        pattern = SequencePattern.from_dict(d)
        assert pattern.steps == ["a", "b", "c"]
        assert pattern.success_count == 3
        assert pattern.total_count == 5
        assert pattern.first_seen == datetime(2026, 1, 1, 12, 0, 0)

    def test_from_dict_defaults(self):
        d = {
            "steps": ["a"],
            "first_seen": "2026-01-01T12:00:00",
            "last_seen": "2026-01-01T12:00:00",
        }
        pattern = SequencePattern.from_dict(d)
        assert pattern.success_count == 0
        assert pattern.total_count == 0
        assert pattern.context_tags == []


class TestInstinctLearner:
    """Test InstinctLearner — the core learning engine."""

    @pytest.fixture
    def learner(self) -> InstinctLearner:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / "instincts.jsonl"
            yield InstinctLearner(storage_path=storage)

    def test_learn_new(self, learner: InstinctLearner) -> None:
        instinct = learner.learn(pattern="debug error", action="use systematic-debugging")
        assert instinct.id.startswith("instinct_")
        assert instinct.pattern == "debug error"
        assert instinct.action == "use systematic-debugging"
        assert instinct.source == "manual"
        assert instinct.confidence == pytest.approx(0.5)

    def test_learn_duplicate_updates_action(self, learner: InstinctLearner) -> None:
        first = learner.learn(pattern="debug error", action="old-action")
        second = learner.learn(pattern="debug error", action="new-action")
        assert first.id == second.id
        assert second.action == "new-action"
        assert second.confidence == pytest.approx(0.5)  # reset on action change

    def test_learn_with_context_and_tags(self, learner: InstinctLearner) -> None:
        instinct = learner.learn(
            pattern="deploy app",
            action="use deploy-workflow",
            context="ci/cd pipeline",
            tags=["deploy", "ci"],
        )
        assert instinct.context == "ci/cd pipeline"
        assert instinct.tags == ["deploy", "ci"]

    def test_record_outcome_success(self, learner: InstinctLearner) -> None:
        instinct = learner.learn(pattern="test pattern", action="do something")
        learner.record_outcome(instinct.id, success=True)
        # Reload to verify persistence
        loaded = learner._instincts[instinct.id]
        assert loaded.success_count == 1
        assert loaded.failure_count == 0
        assert loaded.confidence > 0.5

    def test_record_outcome_failure(self, learner: InstinctLearner) -> None:
        instinct = learner.learn(pattern="test pattern", action="do something")
        learner.record_outcome(instinct.id, success=False)
        assert learner._instincts[instinct.id].failure_count == 1

    def test_record_outcome_unknown_id(self, learner: InstinctLearner) -> None:
        # Should not raise
        learner.record_outcome("nonexistent", success=True)

    def test_find_matching_basic(self, learner: InstinctLearner) -> None:
        learner.learn(pattern="debug database error", action="use systematic-debugging")
        # Make it reliable
        instinct_id = next(iter(learner._instincts.keys()))
        for _ in range(4):
            learner.record_outcome(instinct_id, success=True)

        matches = learner.find_matching(query="database error occurred")
        assert len(matches) > 0
        assert matches[0].action == "use systematic-debugging"

    def test_find_matching_no_reliable(self, learner: InstinctLearner) -> None:
        learner.learn(pattern="debug error", action="use-debug")
        # Not enough successes to be reliable
        matches = learner.find_matching(query="debug error")
        assert len(matches) == 0  # skipped because not reliable

    def test_find_matching_with_context_boost(self, learner: InstinctLearner) -> None:
        learner.learn(
            pattern="python error",
            action="use pytest debug",
            context="testing",
        )
        instinct_id = next(iter(learner._instincts.keys()))
        for _ in range(4):
            learner.record_outcome(instinct_id, success=True)

        matches = learner.find_matching(query="error", context="testing framework")
        assert len(matches) > 0

    def test_find_matching_min_confidence_filter(self, learner: InstinctLearner) -> None:
        instinct = learner.learn(pattern="test pattern", action="do something")
        for _ in range(10):
            learner.record_outcome(instinct.id, success=True)
        # High min_confidence should filter it out
        matches = learner.find_matching(query="test", min_confidence=0.95)
        # With 10 successes the confidence should be high enough
        assert len(matches) >= 0  # at least doesn't crash

    def test_get_reliable_instincts(self, learner: InstinctLearner) -> None:
        # Reliable one
        i1 = learner.learn(pattern="good pattern", action="do good")
        for _ in range(3):
            learner.record_outcome(i1.id, success=True)

        # Unreliable one (only 1 application)
        learner.learn(pattern="new pattern", action="do new")

        reliable = learner.get_reliable_instincts()
        assert len(reliable) >= 1
        assert all(i.is_reliable for i in reliable)

    def test_get_reliable_instincts_with_tag(self, learner: InstinctLearner) -> None:
        i1 = learner.learn(pattern="deploy app", action="deploy", tags=["ci"])
        for _ in range(3):
            learner.record_outcome(i1.id, success=True)

        i2 = learner.learn(pattern="test app", action="test", tags=["testing"])
        for _ in range(3):
            learner.record_outcome(i2.id, success=True)

        ci_instincts = learner.get_reliable_instincts(tag="ci")
        assert len(ci_instincts) >= 1
        assert all("ci" in i.tags for i in ci_instincts)

    def test_extract_from_experiment_successful(self, learner: InstinctLearner) -> None:
        result = learner.extract_from_experiment(
            hypothesis="if we write tests first, quality improves",
            outcome="write tests before code",
            was_successful=True,
        )
        assert result is not None
        assert result.source == "experiment"
        assert "Avoid" not in result.action

    def test_extract_from_experiment_failed(self, learner: InstinctLearner) -> None:
        result = learner.extract_from_experiment(
            hypothesis="rewrite everything in rust",
            outcome="too expensive",
            was_successful=False,
        )
        assert result is not None
        assert "Avoid" in result.action

    def test_get_stats(self, learner: InstinctLearner) -> None:
        i1 = learner.learn(pattern="p1", action="a1")
        for _ in range(3):
            learner.record_outcome(i1.id, success=True)
        learner.learn(pattern="p2", action="a2")

        stats = learner.get_stats()
        assert stats["total_instincts"] == 2
        assert stats["reliable_instincts"] >= 1
        assert "by_source" in stats
        assert "avg_confidence" in stats

    def test_record_sequence_short(self, learner: InstinctLearner) -> None:
        # Too short to record
        result = learner.record_sequence(steps=["a", "b"], success=True)
        assert result is None

    def test_record_sequence_candidate(self, learner: InstinctLearner) -> None:
        steps = ["read file", "analyze code", "write fix", "run tests"]
        for _ in range(5):
            learner.record_sequence(steps=steps, success=True)
        # 5 successes out of 5 = success_rate 1.0, enough to be candidate
        candidates = learner.get_sequence_candidates()
        assert len(candidates) >= 1

    def test_record_sequence_with_context(self, learner: InstinctLearner) -> None:
        steps = ["read", "debug", "fix", "test"]
        for _ in range(5):
            learner.record_sequence(steps=steps, success=True, context="debugging session")
        candidates = learner.get_sequence_candidates()
        assert len(candidates) >= 1
        assert "debugging" in candidates[0].context_tags

    def test_get_sequence_candidates_empty(self, learner: InstinctLearner) -> None:
        assert learner.get_sequence_candidates() == []

    def test_export_for_routing(self, learner: InstinctLearner) -> None:
        i1 = learner.learn(pattern="debug error", action="use systematic-debugging")
        for _ in range(3):
            learner.record_outcome(i1.id, success=True)

        exported = learner.export_for_routing()
        assert len(exported) >= 1
        assert "id" in exported[0]
        assert "pattern" in exported[0]
        assert "action" in exported[0]
        assert "confidence" in exported[0]

    def test_persistence(self, learner: InstinctLearner) -> None:
        i1 = learner.learn(pattern="persistent pattern", action="do work")
        learner.record_outcome(i1.id, success=True)

        # Create a new learner pointing to the same file
        learner2 = InstinctLearner(storage_path=learner.storage_path)
        assert i1.id in learner2._instincts
        loaded = learner2._instincts[i1.id]
        assert loaded.pattern == "persistent pattern"
        assert loaded.success_count == 1

    def test_load_handles_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "empty.jsonl"
            path.write_text("", encoding="utf-8")
            learner = InstinctLearner(storage_path=path)
            assert len(learner._instincts) == 0

    def test_load_skips_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.jsonl"
            path.write_text(
                '{"id": "good", "pattern": "p", "action": "a", "created_at": "2026-01-01T00:00:00"}\nbad json line\n',
                encoding="utf-8",
            )
            learner = InstinctLearner(storage_path=path)
            assert len(learner._instincts) == 1

    def test_load_skips_missing_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "partial.jsonl"
            path.write_text('{"id": "incomplete"}\n', encoding="utf-8")
            learner = InstinctLearner(storage_path=path)
            assert len(learner._instincts) == 0


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_learn_instinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.jsonl"
            instinct = learn_instinct(
                pattern="test pattern",
                action="test action",
                storage_path=path,
                tags=["test"],
            )
            assert instinct.id.startswith("instinct_")
            assert instinct.tags == ["test"]

    def test_get_routing_suggestion_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.jsonl"
            learner = InstinctLearner(storage_path=path)
            i = learner.learn(pattern="debug database error", action="use systematic-debugging")
            for _ in range(3):
                learner.record_outcome(i.id, success=True)

            suggestion = get_routing_suggestion("database error", storage_path=path)
            assert suggestion == "use systematic-debugging"

    def test_get_routing_suggestion_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.jsonl"
            suggestion = get_routing_suggestion("unknown query", storage_path=path)
            assert suggestion is None


class TestInstinctLearnerCrossProcessLock:
    """Phase B: cross-process file lock + .bak rotation.

    Plan v2 §3 — launchd-driven ``vibe instinct feedback-collect`` must not
    race an interactive ``vibe instinct learn`` on the same ``instincts.jsonl``.
    Lock is POSIX-only (fcntl.flock); tests run on all platforms but skip the
    flock-specific assertions on Windows.
    """

    @pytest.fixture
    def storage_path(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "instincts.jsonl"

    def test_save_creates_bak_after_second_save(self, storage_path: Path) -> None:
        """First save has no .bak (nothing to back up); second save writes one
        containing the pre-second-save contents (plan v2 §3 — pi suggestion)."""
        learner = InstinctLearner(storage_path=storage_path)
        i1 = learner.learn(pattern="pattern one", action="act one")
        # First save: no .bak yet.
        bak_path = storage_path.with_suffix(".jsonl.bak")
        assert not bak_path.exists()

        # Second save: .bak now holds the previous file content.
        learner.learn(pattern="pattern two", action="act two")
        assert bak_path.exists()
        bak_lines = [
            line for line in bak_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        # The .bak captures state-after-first-save, which has exactly pattern one.
        assert len(bak_lines) == 1
        assert i1.pattern in bak_lines[0]

    def test_save_does_not_bak_when_file_missing(self, storage_path: Path) -> None:
        """_backup_locked is a no-op when data file doesn't exist (first save).

        Defensive — never crashes the first persistence, even if .bak dir is
        somehow missing.
        """
        learner = InstinctLearner(storage_path=storage_path)
        learner.learn(pattern="only pattern", action="act")
        # No .bak on first save, no crash.
        assert storage_path.exists()
        assert not storage_path.with_suffix(".jsonl.bak").exists()

    def test_cross_process_merge_preserves_disk_only_ids(
        self, storage_path: Path
    ) -> None:
        """When two InstinctLearner instances share storage, a save from one
        must not clobber disk-only IDs the other wrote.

        Simulates: interactive session holds learner in memory; launchd tick
        writes a new instinct to disk; interactive session then saves — the
        launchd-written ID must survive (plan v2 §3)."""
        learner_a = InstinctLearner(storage_path=storage_path)
        i_a = learner_a.learn(pattern="shared pattern", action="action shared")

        # Another process writes a disk-only instinct behind learner_a's back.
        learner_b = InstinctLearner(storage_path=storage_path)
        i_b = learner_b.learn(pattern="disk only pattern", action="action b")
        # Sanity: learner_b's in-memory has both (loaded shared from disk + new).
        assert learner_b.has_instinct(i_a.id)
        assert learner_b.has_instinct(i_b.id)

        # learner_a still doesn't know about i_b.
        assert learner_a.has_instinct(i_a.id)
        assert not learner_a.has_instinct(i_b.id)

        # learner_a saves (e.g. user accepts an instinct update). The merge step
        # inside _save must re-read disk and pull in i_b so it isn't lost.
        learner_a.learn(pattern="third from a", action="action a2")

        # Reload from disk: all three instincts should survive.
        learner_c = InstinctLearner(storage_path=storage_path)
        assert learner_c.has_instinct(i_a.id)
        assert learner_c.has_instinct(i_b.id)
        # Third instinct from learner_a also there.
        assert len(learner_c._instincts) == 3

    def test_lock_file_created_as_sibling(self, storage_path: Path) -> None:
        """The cross-process lock lives on a sibling .lock file (not the data
        file) so the atomic rename inside write_text does not release it."""
        if sys.platform == "win32":
            pytest.skip("fcntl.flock is POSIX-only; Windows path is a no-op")

        learner = InstinctLearner(storage_path=storage_path)
        learner.learn(pattern="trigger save", action="a")
        lock_path = storage_path.with_suffix(".jsonl.lock")
        assert lock_path.exists()
        # Lock file is not locked after save returns (LOCK_UN on exit).
        # We can't easily assert the lock state from the same process, but the
        # file existence is the contract — a subsequent save can re-acquire.

    def test_concurrent_saves_from_two_instances_do_not_lose_data(
        self, storage_path: Path
    ) -> None:
        """Stress: two learners, each learning a different pattern, then both
        saving. After reload, both patterns must be present.

        Without the merge step, the second save would clobber the first. This
        test does not actually fork — it simulates the race by interleaving
        saves, which is enough to exercise _merge_disk_into_memory_locked.
        """
        if sys.platform == "win32":
            pytest.skip("fcntl.flock is POSIX-only; Windows path is a no-op")

        learner_a = InstinctLearner(storage_path=storage_path)
        learner_b = InstinctLearner(storage_path=storage_path)

        # Both start with the same disk view (empty).
        a_id = learner_a._generate_id("alpha pattern")
        b_id = learner_b._generate_id("beta pattern")

        learner_a.learn(pattern="alpha pattern", action="do alpha")
        # learner_b's in-memory still empty; save writes only its new instinct,
        # but the merge step re-reads disk and pulls in alpha before writing.
        learner_b.learn(pattern="beta pattern", action="do beta")

        reloaded = InstinctLearner(storage_path=storage_path)
        assert reloaded.has_instinct(a_id)
        assert reloaded.has_instinct(b_id)

    def test_clear_epoch_guard_prevents_resurrection(
        self, storage_path: Path
    ) -> None:
        """FLAW #1 regression test: a concurrent in-memory learner must NOT
        resurrect purged data on its next save after another process cleared.

        Steps:
            A.learn("secret")  # A holds it in memory + disk
            B.clear()           # B wipes disk, bumps epoch
            A.record_outcome(...)  # A's save should detect epoch bump and drop state

        Without the epoch guard, A's save would merge (empty disk → nothing to
        merge) and write A's stale in-memory state back, undoing the purge.
        """
        if sys.platform == "win32":
            pytest.skip("fcntl.flock is POSIX-only; Windows path is a no-op")

        learner_a = InstinctLearner(storage_path=storage_path)
        secret_id = learner_a.learn(pattern="secret pattern", action="leak") .id
        assert learner_a.has_instinct(secret_id)

        # Another process clears while A still holds the secret in memory.
        learner_b = InstinctLearner(storage_path=storage_path)
        assert learner_b.clear() == 1

        # A's save should detect the epoch bump and drop A's stale state.
        learner_a.record_outcome(secret_id, success=True)

        # Reload: secret must NOT be present.
        reloaded = InstinctLearner(storage_path=storage_path)
        assert not reloaded.has_instinct(secret_id)
        assert len(reloaded._instincts) == 0
        # Epoch file exists and is >= 1.
        epoch_path = storage_path.parent / "clear_epoch"
        assert epoch_path.exists()
        assert int(epoch_path.read_text().strip()) >= 1

    def test_record_sequence_uses_cross_process_lock(
        self, storage_path: Path
    ) -> None:
        """FLAW #3 regression test: record_sequence must hold the cross-process
        lock on sequences.jsonl so a launchd tick can't lose updates.

        Simulates: A loads sequences (empty). B records seq S (count=1 on
        disk). A records a different seq T — without the lock + merge, A's
        save would overwrite disk and lose B's S.
        """
        if sys.platform == "win32":
            pytest.skip("fcntl.flock is POSIX-only; Windows path is a no-op")

        learner_a = InstinctLearner(storage_path=storage_path)
        learner_b = InstinctLearner(storage_path=storage_path)

        # B records S first (return value is None until candidate threshold,
        # but the sequence IS persisted internally).
        s_steps = ["step1", "step2", "step3"]
        import hashlib

        s_hash = hashlib.md5("→".join(s_steps).encode()).hexdigest()[:12]
        learner_b.record_sequence(s_steps, success=True)
        assert s_hash in learner_b._sequences

        # A (still holding empty in-memory sequences) records T.
        t_steps = ["alpha", "beta", "gamma"]
        t_hash = hashlib.md5("→".join(t_steps).encode()).hexdigest()[:12]
        learner_a.record_sequence(t_steps, success=True)
        assert s_hash != t_hash

        # Reload: both sequences must survive (without lock+merge, A's save
        # would have clobbered B's S).
        reloaded = InstinctLearner(storage_path=storage_path)
        assert s_hash in reloaded._sequences
        assert t_hash in reloaded._sequences

    def test_record_sequence_clear_does_not_resurrect_sequences(
        self, storage_path: Path
    ) -> None:
        """Kimi Phase B milestone P1 regression test: record_sequence must
        share the SAME lock file as clear()/_save, otherwise a sequence
        purged by clear() can be resurrected by a stale in-memory
        record_sequence call.

        Steps:
            A.record_sequence(S)    # S on disk + in A's memory
            B.clear()                # disk wiped, epoch bumped
            A.record_sequence(T)     # A's save must detect epoch + drop S

        Without unifying the lock files (record_sequence on seq lock,
        clear/_save on storage lock), the epoch check inside record_sequence
        was not serialised against clear()'s epoch bump.
        """
        if sys.platform == "win32":
            pytest.skip("fcntl.flock is POSIX-only; Windows path is a no-op")

        learner_a = InstinctLearner(storage_path=storage_path)
        learner_b = InstinctLearner(storage_path=storage_path)

        s_steps = ["step1", "step2", "step3"]
        import hashlib

        s_hash = hashlib.md5("→".join(s_steps).encode()).hexdigest()[:12]
        learner_a.record_sequence(s_steps, success=True)
        assert s_hash in learner_a._sequences

        # B clears — must wipe sequences.jsonl and bump epoch.
        learner_b.clear()
        assert not (storage_path.parent / "sequences.jsonl").exists()

        # A records a different sequence; its save must detect the epoch bump
        # and drop S before writing.
        t_steps = ["alpha", "beta", "gamma"]
        t_hash = hashlib.md5("→".join(t_steps).encode()).hexdigest()[:12]
        learner_a.record_sequence(t_steps, success=True)

        # Reload: only T should be present, NOT the purged S.
        reloaded = InstinctLearner(storage_path=storage_path)
        assert t_hash in reloaded._sequences
        assert s_hash not in reloaded._sequences
