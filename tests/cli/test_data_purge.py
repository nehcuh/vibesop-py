"""Tests for `vibe data purge` (F-08) and the new clear() methods.

Project-local targets (analytics/traces/instincts) are tested end-to-end via the
CLI; --all/--feedback touch the GLOBAL ~/.vibe and are excluded from unit tests
(verified manually instead).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from vibesop.cli.commands import data_cmd
from vibesop.core.analytics import AnalyticsStore, ExecutionRecord
from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.routing.tracer import RoutingTracer
from vibesop.core.skills.pack_lock import PackLock, PackLockStore

if TYPE_CHECKING:
    import pytest

runner = CliRunner()


def test_analytics_store_clear(tmp_path: Path) -> None:
    store = AnalyticsStore(storage_dir=tmp_path)
    store.record(ExecutionRecord(query="q1", primary_skill="s1"))
    store.record(ExecutionRecord(query="q2", primary_skill="s2"))
    assert tmp_path.joinpath("analytics.jsonl").exists()
    assert store.clear() == 2
    assert not tmp_path.joinpath("analytics.jsonl").exists()
    assert store.clear() == 0  # already absent


def test_tracer_clear(tmp_path: Path) -> None:
    t = RoutingTracer(enabled=True, traces_dir=tmp_path / "traces")
    t.start_trace("q")
    trace = t.finish_trace(final_skill="s", final_confidence=0.5, final_layer="keyword")
    t.save(trace)
    assert len(list((tmp_path / "traces").glob("*.json"))) == 1
    assert t.clear() == 1
    assert len(list((tmp_path / "traces").glob("*.json"))) == 0
    assert t.clear() == 0  # already absent


def test_instinct_learner_clear(tmp_path: Path) -> None:
    learner = InstinctLearner(storage_path=tmp_path / "instincts.jsonl")
    learner.learn(pattern="how do I test", action="suggest x", source="auto_routing")
    assert len(learner.instincts) == 1
    assert learner.clear() == 1
    assert len(learner.instincts) == 0


def test_data_purge_analytics(tmp_path: Path) -> None:
    AnalyticsStore(storage_dir=tmp_path / ".vibe").record(
        ExecutionRecord(query="q", primary_skill="s")
    )
    assert (tmp_path / ".vibe" / "analytics.jsonl").exists()

    result = runner.invoke(
        data_cmd.app,
        ["purge", "--analytics", "--yes", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert not (tmp_path / ".vibe" / "analytics.jsonl").exists()
    assert "analytics" in result.output


def test_data_purge_no_target_errors(tmp_path: Path) -> None:
    result = runner.invoke(data_cmd.app, ["purge", "--yes", "--project-root", str(tmp_path)])
    assert result.exit_code == 2
    assert "No purge target" in result.output


def test_data_purge_traces(tmp_path: Path) -> None:
    t = RoutingTracer(enabled=True, traces_dir=tmp_path / ".vibe" / "traces")
    t.start_trace("q")
    t.save(t.finish_trace(final_skill="s", final_confidence=0.5, final_layer="k"))
    assert (tmp_path / ".vibe" / "traces").glob("*.json")

    result = runner.invoke(
        data_cmd.app,
        ["purge", "--traces", "--yes", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert not list((tmp_path / ".vibe" / "traces").glob("*.json"))


def test_data_purge_sessions(tmp_path: Path) -> None:
    """F-08 (Kimi #1): --sessions purges .vibe/session/*.json."""
    session_dir = tmp_path / ".vibe" / "session"
    session_dir.mkdir(parents=True)
    (session_dir / "s1.json").write_text("{}")
    (session_dir / "s2.json").write_text("{}")

    result = runner.invoke(
        data_cmd.app,
        ["purge", "--sessions", "--yes", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert not list(session_dir.glob("*.json"))
    assert "sessions" in result.output


def test_feedback_clear_records_unlinks_file(tmp_path: Path) -> None:
    """F-08 (Kimi #2): clear_records() must delete the file — the old
    _save_records() no-op'd on an empty list, leaving records on disk."""
    from vibesop.core.feedback import FeedbackCollector

    path = tmp_path / "feedback.jsonl"
    path.write_text('{"query": "q", "routed_skill": "s", "was_correct": true}\n')
    collector = FeedbackCollector(storage_path=path)
    assert path.exists()

    collector.clear_records()

    assert not path.exists()


def test_preference_clear_resets_query_associations(tmp_path: Path) -> None:
    """F-08 (Kimi #3): preference.clear() resets word/ngram associations too
    (clear_old_data(days=0) left these query-derived fields behind)."""
    from vibesop.core.preference import PreferenceLearner

    learner = PreferenceLearner(storage_path=tmp_path / "preferences.json")
    learner.record_feedback("skill-a", "how do I test my code", helpful=True)
    assert learner._storage.word_associations  # query-derived data present

    learner.clear()

    assert learner._storage.selections == []
    assert learner._storage.word_associations == {}
    assert learner._storage.ngram_associations == {}


def test_instinct_clear_also_clears_sequences(tmp_path: Path) -> None:
    """F-08 (Kimi #4): instinct.clear() must clear _sequences too, else
    sequences survive the purge."""
    learner = InstinctLearner(storage_path=tmp_path / "instincts.jsonl")
    learner.learn(pattern="how do I test", action="suggest x", source="auto_routing")
    learner.clear()

    assert len(learner.instincts) == 0
    assert len(learner._sequences) == 0


def test_pack_lock_store_clear_all(tmp_path: Path) -> None:
    """F-02 completion: PackLockStore.clear_all() removes every lock file."""
    store = PackLockStore(locks_dir=tmp_path)
    store.write(PackLock("a", "u", "c1", "h1", "t"))
    store.write(PackLock("b", "u", "c2", "h2", "t"))
    assert store.clear_all() == 2
    assert store.get("a") is None
    assert store.get("b") is None
    assert store.clear_all() == 0  # already absent


def test_data_purge_pack_locks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """F-02 completion: `vibe data purge --pack-locks` clears install locks."""
    locks_dir = tmp_path / "pack-locks"
    monkeypatch.setattr(PackLockStore, "LOCKS_DIR", locks_dir)

    store = PackLockStore()
    store.write(PackLock("demo", "https://example.com", "abc", "def", "2026-01-01"))
    assert (locks_dir / "demo.json").exists()

    result = runner.invoke(data_cmd.app, ["purge", "--pack-locks", "--yes"])
    assert result.exit_code == 0, result.output
    assert not (locks_dir / "demo.json").exists()
    assert "pack-locks" in result.output


def test_data_purge_all_includes_pack_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-02 completion: `vibe data purge --all` lists pack-locks in the prompt."""
    locks_dir = tmp_path / "pack-locks"
    monkeypatch.setattr(PackLockStore, "LOCKS_DIR", locks_dir)

    store = PackLockStore()
    store.write(PackLock("demo", "https://example.com", "abc", "def", "2026-01-01"))

    result = runner.invoke(data_cmd.app, ["purge", "--all", "--yes"])
    assert result.exit_code == 0, result.output
    assert not (locks_dir / "demo.json").exists()
    assert "pack-locks" in result.output


def test_data_purge_miss_counter(tmp_path: Path) -> None:
    """P1: `vibe data purge --miss-counter` clears miss telemetry (keeps the salt)."""
    from vibesop.core.skills.miss_counter import MissCounter

    counter = MissCounter(tmp_path)
    counter.record("some unmatched query")
    assert (tmp_path / ".vibe" / "miss_counter.json").exists()
    salt_before = (tmp_path / ".vibe" / "miss_salt").read_bytes()

    result = runner.invoke(
        data_cmd.app,
        ["purge", "--miss-counter", "--yes", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert not (tmp_path / ".vibe" / "miss_counter.json").exists()
    assert "miss-counter" in result.output
    # The salt is not user data — purge keeps it, byte-for-byte.
    assert (tmp_path / ".vibe" / "miss_salt").read_bytes() == salt_before
