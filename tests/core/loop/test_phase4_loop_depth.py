"""Phase 4 loop-depth tests — failure classification, retry, cross-run memory,
state machine, reset, and corrupt-state backup.

Checker (Maker/Checker separation) is deferred to a follow-up — not covered.
"""

from __future__ import annotations

import json
import tempfile
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock

from typer.testing import CliRunner

from vibesop.cli.commands.loop_cmd import app
from vibesop.core.loop.executor import _build_query, _classify_failure, execute_loop_tick
from vibesop.core.loop.models import (
    FailureCategory,
    FailureInfo,
    LoopRunRecord,
    LoopSpec,
    LoopState,
    LoopStatus,
    RunHistory,
    validate_transition,
)
from vibesop.core.loop.store import LoopStore


def _spec(name: str = "test", **overrides) -> LoopSpec:
    base = {
        "name": name,
        "description": f"loop {name}",
        "schedule": "* * * * *",
        "skill_id": "systematic-debugging",
    }
    base.update(overrides)
    return LoopSpec(**base)


def _result(
    *, success=True, has_match=True, skill_id="systematic-debugging", errors=None
) -> MagicMock:
    r = MagicMock()
    r.success = success
    r.has_match = has_match
    r.skill_id = skill_id
    r.decision_message = "routed"
    r.errors = errors or []
    return r


def _runtime(*, success=True, has_match=True, errors=None, side_effect=None) -> MagicMock:
    runtime = MagicMock()
    if side_effect is not None:
        runtime.handle_query.side_effect = side_effect
    else:
        runtime.handle_query.return_value = _result(
            success=success, has_match=has_match, errors=errors
        )
    return runtime


# ── failure classification ────────────────────────────────────────────


class TestClassifyFailure:
    def test_transient_keywords(self) -> None:
        for kw in (
            "connection timeout",
            "rate limit exceeded",
            "HTTP 503",
            "temporarily unavailable",
        ):
            assert _classify_failure(kw).category == FailureCategory.TRANSIENT, kw

    def test_permanent_keywords(self) -> None:
        for kw in (
            "skill not found",
            "no matching skill",
            "config error",
            "auth failed",
            "api key invalid",
        ):
            assert _classify_failure(kw).category == FailureCategory.PERMANENT, kw

    def test_unknown_defaults_to_permanent(self) -> None:
        """Conservative: unknown failures don't retry (avoids wasteful ticks)."""
        assert _classify_failure("something unexpected").category == FailureCategory.PERMANENT

    def test_suggestion_present_when_classified(self) -> None:
        assert _classify_failure("connection timeout").suggestion is not None


# ── retry (inside the persistence boundary) ───────────────────────────


class TestRetry:
    def test_no_retry_by_default(self, monkeypatch) -> None:
        slept: list[float] = []
        monkeypatch.setattr(time, "sleep", slept.append)
        runtime = _runtime(success=False, errors=["connection timeout"])
        with tempfile.TemporaryDirectory() as d:
            store = LoopStore(base_dir=d)
            store.save_spec(_spec(name="no-retry"))
            record = execute_loop_tick(_spec(name="no-retry"), runtime=runtime, store=store)
        assert record.success is False
        assert record.failure_info.category == FailureCategory.TRANSIENT
        assert runtime.handle_query.call_count == 1
        assert slept == []

    def test_transient_retries_then_succeeds_persists_once(self, monkeypatch) -> None:
        monkeypatch.setattr(time, "sleep", lambda s: None)
        runtime = MagicMock()
        runtime.handle_query.side_effect = [
            _result(success=False, has_match=False, errors=["connection timeout"]),
            _result(success=True, has_match=True),
        ]
        with tempfile.TemporaryDirectory() as d:
            store = LoopStore(base_dir=d)
            spec = _spec(name="retry-ok", max_retries=2, retry_delay_base=1)
            store.save_spec(spec)
            record = execute_loop_tick(spec, runtime=runtime, store=store)
            state = store.load_state("retry-ok")
        assert record.success is True
        assert runtime.handle_query.call_count == 2
        assert state.total_runs == 1  # persist-once, not per-attempt
        assert state.consecutive_failures == 0

    def test_transient_retry_exhausted_records_single_failure(self, monkeypatch) -> None:
        """Key safety property: a transient blip that exhausts retries counts
        as ONE failure toward DEAD — not one per attempt."""
        monkeypatch.setattr(time, "sleep", lambda s: None)
        runtime = _runtime(success=False, errors=["connection timeout"])
        with tempfile.TemporaryDirectory() as d:
            store = LoopStore(base_dir=d)
            spec = _spec(name="retry-exhausted", max_retries=2, retry_delay_base=1)
            store.save_spec(spec)
            record = execute_loop_tick(spec, runtime=runtime, store=store)
            state = store.load_state("retry-exhausted")
        assert record.success is False
        assert record.failure_info.category == FailureCategory.TRANSIENT
        assert runtime.handle_query.call_count == 3  # 1 initial + 2 retries
        assert state.total_runs == 1
        assert state.consecutive_failures == 1  # NOT 3

    def test_permanent_not_retried_even_with_budget(self, monkeypatch) -> None:
        slept: list[float] = []
        monkeypatch.setattr(time, "sleep", slept.append)
        runtime = _runtime(success=False, errors=["skill not found"])
        with tempfile.TemporaryDirectory() as d:
            store = LoopStore(base_dir=d)
            spec = _spec(name="permanent", max_retries=3, retry_delay_base=1)
            store.save_spec(spec)
            record = execute_loop_tick(spec, runtime=runtime, store=store)
        assert record.failure_info.category == FailureCategory.PERMANENT
        assert runtime.handle_query.call_count == 1
        assert slept == []


# ── cross-run memory injection ────────────────────────────────────────


class TestCrossRunMemory:
    def test_history_appended_to_query(self) -> None:
        spec = _spec(skill_id="", query="check ci", inject_history=True)
        prior = [
            LoopRunRecord(
                loop_name="t", started_at=datetime.now(UTC), success=True, matched_skill="x"
            ),
            LoopRunRecord(
                loop_name="t",
                started_at=datetime.now(UTC),
                success=False,
                error="skill not found",
                failure_info=FailureInfo(
                    category=FailureCategory.PERMANENT, reason="skill not found"
                ),
            ),
        ]
        q = _build_query(
            spec, history=RunHistory(recent_runs=prior, progress_notes=["fixed api key"])
        )
        assert "check ci" in q
        assert "Cross-run context" in q
        assert "50%" in q  # 1/2 success rate
        assert "permanent" in q.lower()
        assert "fixed api key" in q

    def test_no_history_no_context(self) -> None:
        spec = _spec(skill_id="sys-debug", inject_history=True)
        assert _build_query(spec) == "/slash-route use sys-debug"
        assert _build_query(spec, history=RunHistory()) == "/slash-route use sys-debug"

    def test_inject_history_off_by_default(self) -> None:
        """Default (inject_history=False) must NOT mutate the query — preserves
        routing behaviour. Regression guard for the Lane-B H2 concern."""
        spec = _spec(skill_id="", query="check ci")  # inject_history defaults False
        prior = [
            LoopRunRecord(loop_name="t", started_at=datetime.now(UTC), success=True, matched_skill="x")
        ]
        assert _build_query(spec, history=RunHistory(recent_runs=prior)) == "check ci"


# ── state machine ─────────────────────────────────────────────────────


class TestStateMachine:
    def test_valid_edges(self) -> None:
        assert validate_transition(LoopStatus.ACTIVE, LoopStatus.PAUSED)
        assert validate_transition(LoopStatus.FAILING, LoopStatus.PAUSED)
        assert validate_transition(LoopStatus.PAUSED, LoopStatus.ACTIVE)
        assert validate_transition(LoopStatus.FAILING, LoopStatus.DEAD)

    def test_invalid_edges(self) -> None:
        assert not validate_transition(LoopStatus.PAUSED, LoopStatus.DEAD)
        assert not validate_transition(LoopStatus.DEAD, LoopStatus.ACTIVE)  # only via reset
        assert not validate_transition(LoopStatus.DEAD, LoopStatus.PAUSED)
        assert not validate_transition(LoopStatus.RETIRED, LoopStatus.ACTIVE)


# ── store robustness ──────────────────────────────────────────────────


class TestStoreRobustness:
    def test_corrupt_state_backed_up_and_fresh_returned(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = LoopStore(base_dir=d)
            store.save_spec(_spec(name="corrupt"))
            state_path = store.base_dir / "corrupt" / store.STATE_FILENAME
            state_path.write_text("{not valid json", encoding="utf-8")

            state = store.load_state("corrupt")

            assert state is not None  # fresh fallback, not silent None
            assert state.status == LoopStatus.ACTIVE
            assert (store.base_dir / "corrupt" / "state.json.corrupt").exists()

    def test_legacy_state_without_new_fields_loads(self) -> None:
        """Old state.json (pre-Phase-4, no progress_notes) loads with defaults."""
        with tempfile.TemporaryDirectory() as d:
            store = LoopStore(base_dir=d)
            spec = _spec(name="legacy")
            store.save_spec(spec)
            legacy = {
                "spec": spec.model_dump(mode="json"),
                "status": "active",
                "consecutive_failures": 0,
                "total_runs": 0,
                "last_run_at": None,
                "last_success_at": None,
                "next_run_at": None,
                "recent_runs": [],
            }
            (store.base_dir / "legacy" / "state.json").write_text(
                json.dumps(legacy), encoding="utf-8"
            )

            state = store.load_state("legacy")

            assert state is not None
            assert state.progress_notes == []  # new field, defaulted by pydantic


# ── CLI reset / resume-dead ───────────────────────────────────────────


class TestLoopCmdResetResume:
    def _seed_dead(self, tmpdir: str, name: str = "dead") -> LoopStore:
        store = LoopStore(base_dir=tmpdir)
        spec = _spec(name=name)
        store.save_spec(spec)
        state = store.load_state(name) or LoopState(spec=spec)
        state.status = LoopStatus.DEAD
        state.consecutive_failures = 3
        store.save_state(state)
        return store

    def test_reset_revives_dead(self, monkeypatch, tmp_path) -> None:
        store = self._seed_dead(str(tmp_path))
        monkeypatch.setattr("vibesop.cli.commands.loop_cmd.LoopStore", lambda *a, **kw: store)

        result = CliRunner().invoke(app, ["reset", "dead"])

        assert result.exit_code == 0
        revived = store.load_state("dead")
        assert revived.status == LoopStatus.ACTIVE
        assert revived.consecutive_failures == 0

    def test_resume_dead_refused_directed_to_reset(self, monkeypatch, tmp_path) -> None:
        store = self._seed_dead(str(tmp_path))
        monkeypatch.setattr("vibesop.cli.commands.loop_cmd.LoopStore", lambda *a, **kw: store)

        result = CliRunner().invoke(app, ["resume", "dead"])

        assert result.exit_code != 0
        assert "reset" in result.output.lower()
        assert store.load_state("dead").status == LoopStatus.DEAD  # unchanged

    def test_reset_refuses_non_dead(self, monkeypatch, tmp_path) -> None:
        store = LoopStore(base_dir=str(tmp_path))
        store.save_spec(_spec(name="active"))  # fresh → ACTIVE
        monkeypatch.setattr("vibesop.cli.commands.loop_cmd.LoopStore", lambda *a, **kw: store)

        result = CliRunner().invoke(app, ["reset", "active"])

        assert result.exit_code != 0  # reset only for DEAD
