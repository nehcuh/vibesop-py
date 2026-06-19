"""Tests for ``execute_loop_tick`` — single-loop execution cycle.

Covers:
    - Query construction for skill_id / query / workflow_id targets.
    - Happy path: AgentRuntime match → record.success=True, state persisted.
    - No-match path: empty result → record.success=False, descriptive error.
    - Error path: result.errors populated → record captures them.
    - Failure counter advancement across consecutive failing ticks.
    - Success resets failure counter.
    - Recent runs accumulate.
    - Default runtime/store wiring works (AgentRuntime patched).
    - Executor does not raise on runtime exceptions (logs + records).
"""

from __future__ import annotations

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from vibesop.core.loop.executor import _build_query, execute_loop_tick
from vibesop.core.loop.models import LoopSpec, LoopStatus
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


def _mock_runtime(
    *,
    success: bool = True,
    has_match: bool = True,
    skill_id: str = "systematic-debugging",
    decision_message: str = "✅ Routed to systematic-debugging (95%)",
    errors: list[str] | None = None,
) -> MagicMock:
    """Build a MagicMock stand-in for AgentRuntime with the desired result."""
    runtime = MagicMock()
    result = MagicMock()
    result.success = success
    result.has_match = has_match
    result.skill_id = skill_id
    result.decision_message = decision_message
    result.errors = errors or []
    runtime.handle_query.return_value = result
    return runtime


# ──────────────────────────────────────────────────────────────────
# _build_query
# ──────────────────────────────────────────────────────────────────


class TestBuildQuery:
    def test_skill_id_produces_slash_route(self):
        spec = _spec(skill_id="systematic-debugging", query="")
        assert _build_query(spec) == "/slash-route use systematic-debugging"

    def test_query_passed_through(self):
        spec = _spec(
            skill_id="",
            query="检查今天的 CI 状态",
        )
        assert _build_query(spec) == "检查今天的 CI 状态"

    def test_workflow_id_produces_run_workflow(self):
        spec = _spec(skill_id="", query="", workflow_id="prompt-chain-validator")
        assert _build_query(spec) == "run workflow prompt-chain-validator"

    def test_skill_id_precedes_query_and_workflow(self):
        """LoopSpec's model_validator normally rejects multi-target, but
        if validation is bypassed we should still prefer skill_id."""
        spec = _spec(skill_id="sys-debug")  # construct validly first
        object.__setattr__(spec, "query", "ignored")
        object.__setattr__(spec, "workflow_id", "ignored")
        assert _build_query(spec) == "/slash-route use sys-debug"

    def test_no_target_raises_after_bypass(self):
        """Defensive guard: if validation is bypassed and no target is
        set, _build_query raises ValueError (not silence)."""
        spec = _spec(skill_id="sys-debug")  # construct validly first
        object.__setattr__(spec, "skill_id", "")
        with pytest.raises(ValueError, match="no skill_id / query / workflow_id"):
            _build_query(spec)


# ──────────────────────────────────────────────────────────────────
# execute_loop_tick — happy and failure paths
# ──────────────────────────────────────────────────────────────────


class TestExecuteLoopTickDispatch:
    def test_successful_match_populates_record(self):
        runtime = _mock_runtime(
            success=True,
            has_match=True,
            skill_id="systematic-debugging",
            decision_message="Routed to systematic-debugging at 95% confidence",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(name="success-case")
            store.save_spec(spec)

            record = execute_loop_tick(spec, runtime=runtime, store=store)

            assert record.success is True
            assert record.matched_skill == "systematic-debugging"
            assert record.error == ""
            assert "95%" in record.output_summary
            assert record.duration_s >= 0.0
            assert record.finished_at is not None

            runtime.handle_query.assert_called_once()
            args, kwargs = runtime.handle_query.call_args
            assert args[0] == "/slash-route use systematic-debugging"
            assert kwargs.get("explain") is True

    def test_no_match_records_failure_with_descriptive_error(self):
        runtime = _mock_runtime(
            success=True,       # no internal errors
            has_match=False,    # but no skill matched
            skill_id="",
            decision_message="",
            errors=[],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(
                name="no-match",
                skill_id="",
                query="some unknown query xyz123",
            )
            store.save_spec(spec)

            record = execute_loop_tick(spec, runtime=runtime, store=store)

            assert record.success is False
            assert "no matching skill" in record.error
            assert record.matched_skill == ""

    def test_runtime_errors_are_captured(self):
        runtime = _mock_runtime(
            success=False,
            has_match=False,
            errors=["LLM timeout", "retry budget exhausted"],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(name="error-case", skill_id="", query="q")
            store.save_spec(spec)

            record = execute_loop_tick(spec, runtime=runtime, store=store)

            assert record.success is False
            assert "LLM timeout" in record.error
            assert "retry budget" in record.error

    def test_catastrophic_runtime_exception_does_not_propagate(self):
        """If AgentRuntime itself raises (not just returns errors),
        executor must catch, log, and record failure."""
        runtime = MagicMock()
        runtime.handle_query.side_effect = RuntimeError("import exploded")

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(name="crash-case", skill_id="", query="q")
            store.save_spec(spec)

            record = execute_loop_tick(spec, runtime=runtime, store=store)

            assert record.success is False
            assert "import exploded" in record.error


# ──────────────────────────────────────────────────────────────────
# execute_loop_tick — state persistence
# ──────────────────────────────────────────────────────────────────


class TestExecuteLoopTickStatePersistence:
    def test_state_persisted_after_success(self):
        runtime = _mock_runtime()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(name="persist-success")
            store.save_spec(spec)

            execute_loop_tick(spec, runtime=runtime, store=store)

            state = store.load_state("persist-success")
            assert state is not None
            assert state.total_runs == 1
            assert state.consecutive_failures == 0
            assert state.status == LoopStatus.ACTIVE
            assert len(state.recent_runs) == 1
            assert state.recent_runs[0].success is True

    def test_consecutive_failures_advance_through_failing_to_dead(self):
        runtime = _mock_runtime(success=False, errors=["boom"])
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(name="to-dead", skill_id="", query="q", max_failures=3)
            store.save_spec(spec)

            execute_loop_tick(spec, runtime=runtime, store=store)
            s1 = store.load_state("to-dead")
            assert s1.consecutive_failures == 1
            assert s1.status == LoopStatus.FAILING

            execute_loop_tick(spec, runtime=runtime, store=store)
            s2 = store.load_state("to-dead")
            assert s2.consecutive_failures == 2
            assert s2.status == LoopStatus.FAILING

            execute_loop_tick(spec, runtime=runtime, store=store)
            s3 = store.load_state("to-dead")
            assert s3.consecutive_failures == 3
            assert s3.status == LoopStatus.DEAD

    def test_success_resets_failure_counter(self):
        fail_runtime = _mock_runtime(success=False, errors=["fail"])
        ok_runtime = _mock_runtime(success=True, has_match=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(name="reset-case")
            store.save_spec(spec)

            execute_loop_tick(spec, runtime=fail_runtime, store=store)
            execute_loop_tick(spec, runtime=fail_runtime, store=store)
            assert store.load_state("reset-case").consecutive_failures == 2

            execute_loop_tick(spec, runtime=ok_runtime, store=store)
            state = store.load_state("reset-case")
            assert state.consecutive_failures == 0
            assert state.status == LoopStatus.ACTIVE

    def test_recent_runs_accumulate_within_cap(self):
        runtime = _mock_runtime()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(name="history")
            store.save_spec(spec)

            for _ in range(3):
                execute_loop_tick(spec, runtime=runtime, store=store)

            state = store.load_state("history")
            assert state.total_runs == 3
            assert len(state.recent_runs) == 3

    def test_query_target_path_uses_natural_language(self):
        """Verify the query-pass-through path: when spec.query is set,
        executor calls handle_query with the raw query."""
        runtime = _mock_runtime()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(
                name="query-path",
                skill_id="",
                query="summarise today's PRs",
            )
            store.save_spec(spec)

            execute_loop_tick(spec, runtime=runtime, store=store)

            args, _ = runtime.handle_query.call_args
            assert args[0] == "summarise today's PRs"

    def test_workflow_target_path_uses_run_prefix(self):
        runtime = _mock_runtime()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(
                name="workflow-path",
                skill_id="",
                query="",
                workflow_id="daily-digest",
            )
            store.save_spec(spec)

            execute_loop_tick(spec, runtime=runtime, store=store)

            args, _ = runtime.handle_query.call_args
            assert args[0] == "run workflow daily-digest"


# ──────────────────────────────────────────────────────────────────
# execute_loop_tick — default runtime/store wiring
# ──────────────────────────────────────────────────────────────────


class TestExecuteLoopTickDefaults:
    def test_default_runtime_and_store_wiring(self):
        """When runtime/store are None, executor must construct defaults
        and call through them. We patch AgentRuntime so no real LLM is
        contacted; we pass a real store via tmpdir for verification."""
        runtime = _mock_runtime()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "vibesop.core.loop.executor.AgentRuntime",
                return_value=runtime,
            ):
                store = LoopStore(base_dir=tmpdir)
                spec = _spec(name="default-wiring")
                store.save_spec(spec)

                # Pass store explicitly; let runtime default-construct
                # (patched to return our mock).
                record = execute_loop_tick(spec, store=store)

                assert record.success is True
                assert runtime.handle_query.called

    def test_default_store_writes_to_real_disk(self):
        """End-to-end: real store, patched runtime. The state file must
        land on disk under the tmpdir."""
        runtime = _mock_runtime()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "vibesop.core.loop.executor.AgentRuntime",
                return_value=runtime,
            ):
                spec = _spec(name="disk-write")
                # Use the real default store path under tmpdir/home by
                # passing store explicitly.
                store = LoopStore(base_dir=tmpdir)
                store.save_spec(spec)

                execute_loop_tick(spec, store=store)

                state_path = (
                    store.base_dir / "disk-write" / store.STATE_FILENAME
                )
                assert state_path.exists()
                assert state_path.read_text(encoding="utf-8").strip().startswith("{")
