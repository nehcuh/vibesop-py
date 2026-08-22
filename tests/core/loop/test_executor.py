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

import subprocess
import tempfile
from unittest.mock import MagicMock

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
            success=True,  # no internal errors
            has_match=False,  # but no skill matched
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


class TestExecuteLoopTickRuntimeInjection:
    def test_injected_runtime_is_called_and_state_wired(self):
        """Executor calls the injected runtime and persists state. (Pre-fix the
        runtime was default-constructed inside executor via a Core->Agent import;
        now it is injected, so we pass the mock runtime directly.)"""
        runtime = _mock_runtime()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            spec = _spec(name="default-wiring")
            store.save_spec(spec)

            record = execute_loop_tick(spec, runtime=runtime, store=store)

            assert record.success is True
            assert runtime.handle_query.called

    def test_state_writes_to_real_disk(self):
        """End-to-end: real store, injected mock runtime. The state file must
        land on disk under the tmpdir."""
        runtime = _mock_runtime()
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = _spec(name="disk-write")
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(spec)

            execute_loop_tick(spec, runtime=runtime, store=store)

            state_path = store.base_dir / "disk-write" / store.STATE_FILENAME
            assert state_path.exists()
            assert state_path.read_text(encoding="utf-8").strip().startswith("{")


# ──────────────────────────────────────────────────────────────────
# command_args target — subprocess dispatch (ADR-005)
# ──────────────────────────────────────────────────────────────────


def _cmd_spec(name: str = "cmd-loop", **overrides) -> LoopSpec:
    """Build a LoopSpec with command_args set instead of skill_id/query/workflow_id."""
    base: dict[str, object] = {
        "name": name,
        "description": f"command loop {name}",
        "schedule": "*/15 * * * *",
        "skill_id": "",
        "query": "",
        "workflow_id": "",
        "command_args": ["sequence", "assemble"],
    }
    base.update(overrides)
    return LoopSpec(**base)


def _completed_process(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """Build a subprocess.CompletedProcess stand-in."""
    return subprocess.CompletedProcess(
        args=["uv", "run", "vibe", "sequence", "assemble"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestRunCommandTarget:
    """_run_command_target mutates the record in place; tests use a fresh record
    per case."""

    def _fresh_record(self, name: str = "cmd-loop"):
        from datetime import UTC, datetime

        from vibesop.core.loop.models import LoopRunRecord

        started = datetime.now(UTC)
        return LoopRunRecord(loop_name=name, started_at=started)

    def test_success_returncode_zero_marks_record_success(self, monkeypatch):
        from vibesop.core.loop.executor import _run_command_target

        spec = _cmd_spec()
        record = self._fresh_record()

        mock_run = MagicMock(return_value=_completed_process(0, stdout="done", stderr=""))
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        _run_command_target(spec, record)

        assert record.success is True
        assert record.error == ""
        assert record.failure_info is None
        assert record.output_summary == "done"

    def test_no_such_command_is_classified_permanent(self, monkeypatch):
        from vibesop.core.loop.executor import _run_command_target

        spec = _cmd_spec()
        record = self._fresh_record()

        mock_run = MagicMock(
            return_value=_completed_process(
                2, stdout="", stderr="Error: No such command 'nonexistent'"
            )
        )
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        _run_command_target(spec, record)

        assert record.success is False
        assert record.failure_info is not None
        from vibesop.core.loop.models import FailureCategory

        assert record.failure_info.category == FailureCategory.PERMANENT

    def test_unknown_stderr_defaults_to_transient(self, monkeypatch):
        """pi MUST-FIX: command-target failures default to TRANSIENT (environmental)."""
        from vibesop.core.loop.executor import _run_command_target

        spec = _cmd_spec()
        record = self._fresh_record()

        mock_run = MagicMock(
            return_value=_completed_process(1, stdout="", stderr="KeyError: 'foo'")
        )
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        _run_command_target(spec, record)

        from vibesop.core.loop.models import FailureCategory

        assert record.failure_info.category == FailureCategory.TRANSIENT

    def test_timeout_is_transient(self, monkeypatch):
        from vibesop.core.loop.executor import _run_command_target

        spec = _cmd_spec(timeout_s=1.0)
        record = self._fresh_record()

        def raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=1.0)

        mock_run = MagicMock(side_effect=raise_timeout)
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        _run_command_target(spec, record)

        from vibesop.core.loop.models import FailureCategory

        assert record.success is False
        assert "timeout" in record.error.lower()
        assert record.failure_info.category == FailureCategory.TRANSIENT

    def test_spawn_failure_is_permanent(self, monkeypatch):
        """FileNotFoundError when prefix binary itself missing — not retryable."""
        from vibesop.core.loop.executor import _run_command_target

        spec = _cmd_spec()
        record = self._fresh_record()

        def raise_oserror(*args, **kwargs):
            raise FileNotFoundError("[Errno 2] No such file or directory: 'uv'")

        mock_run = MagicMock(side_effect=raise_oserror)
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        _run_command_target(spec, record)

        from vibesop.core.loop.models import FailureCategory

        assert record.failure_info.category == FailureCategory.PERMANENT

    def test_classify_command_failure_keyword_coverage(self):
        """Characterisation tests pinning the keyword table (kimi P2 nit).
        Run before/after any keyword-table change so regressions surface fast."""
        from vibesop.core.loop.executor import _classify_command_failure
        from vibesop.core.loop.models import FailureCategory

        # PERMANENT markers
        for marker in [
            "Error: No such command 'xyz'",
            "Error: No such option '--foo'",
            "Permission denied: /etc/shadow",
            "[Errno 13] Permission denied",
            "Usage: vibe instinct [OPTIONS]",
            "Invalid value for '--min-confidence': 'abc' is not a valid float",
            "Missing argument: NAME",
        ]:
            info = _classify_command_failure(marker, return_code=2)
            assert info.category == FailureCategory.PERMANENT, (
                f"expected PERMANENT for {marker!r}, got {info.category}"
            )

        # TRANSIENT (default + intentionally omitted markers)
        for transient in [
            "KeyError: 'foo'",  # unknown
            "The process cannot access the file because it is being used by another process",
            "No such file or directory: '/tmp/instincts.jsonl'",  # kimi nit: file race
            "[Errno 11] Resource temporarily unavailable",
        ]:
            info = _classify_command_failure(transient, return_code=1)
            assert info.category == FailureCategory.TRANSIENT, (
                f"expected TRANSIENT for {transient!r}, got {info.category}"
            )


class TestExecuteLoopTickCommandPath:
    def test_command_target_success_does_not_call_runtime(self, monkeypatch):
        """When spec.command_args is set, the runtime (AgentRuntime) is never
        invoked — the subprocess path bypasses routing entirely."""
        runtime = _mock_runtime()
        spec = _cmd_spec(name="cmd-ok")

        mock_run = MagicMock(return_value=_completed_process(0, stdout="ok", stderr=""))
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(spec)
            record = execute_loop_tick(spec, runtime=runtime, store=store)

        assert record.success is True
        assert runtime.handle_query.called is False

    def test_command_target_consecutive_failures_advance_to_dead(self, monkeypatch):
        """DEAD/FAILING state machine applies to command targets (kimi/pi MUST-FIX B)."""
        spec = _cmd_spec(name="cmd-to-dead", max_failures=2, max_retries=0)

        # "No such command" → PERMANENT, no retry, advances failure counter directly.
        mock_run = MagicMock(
            return_value=_completed_process(2, stdout="", stderr="Error: No such command 'xyz'")
        )
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(spec)

            execute_loop_tick(spec, runtime=_mock_runtime(), store=store)
            s1 = store.load_state("cmd-to-dead")
            assert s1.status == LoopStatus.FAILING

            execute_loop_tick(spec, runtime=_mock_runtime(), store=store)
            s2 = store.load_state("cmd-to-dead")
            assert s2.status == LoopStatus.DEAD

    def test_command_args_with_space_in_arg_no_shell_injection(self, monkeypatch):
        """shlex.split at the CLI layer protects us, but executor itself passes
        command_args as argv (no shell=True) so a literal ';' is just an arg."""
        spec = _cmd_spec(name="injection-attempt", command_args=["foo; rm -rf /"])
        record_calls = []

        def capture_run(argv, *args, **kwargs):
            record_calls.append(argv)
            return _completed_process(0, stdout="", stderr="")

        mock_run = MagicMock(side_effect=capture_run)
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(spec)
            execute_loop_tick(spec, runtime=_mock_runtime(), store=store)

        # argv is a single list — "; rm -rf /" stays as part of one literal arg.
        called_argv = record_calls[0]
        assert "foo; rm -rf /" in called_argv
        # No separate "rm" element — no shell splitting happened.
        assert "rm" not in called_argv

    def test_command_target_retries_on_transient_then_succeeds(self, monkeypatch):
        """Transient failure on attempt 1 → retry → success on attempt 2.
        Final record must reflect attempt 2's success (no stale error fields)."""
        spec = _cmd_spec(name="retry-then-ok", max_retries=2)

        side_effects = [
            _completed_process(1, stdout="", stderr="connection reset by peer"),
            _completed_process(0, stdout="done", stderr=""),
        ]
        mock_run = MagicMock(side_effect=side_effects)
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)
        # Skip the real sleep — the exponential backoff is tested elsewhere.
        monkeypatch.setattr("vibesop.core.loop.executor.time.sleep", lambda _s: None)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(spec)
            record = execute_loop_tick(spec, runtime=_mock_runtime(), store=store)

        assert record.success is True
        assert record.error == ""
        assert record.failure_info is None
        assert record.output_summary == "done"
        assert mock_run.call_count == 2

    def test_command_target_retries_exhausted_commits_transient_with_history(self, monkeypatch):
        """All retries fail with TRANSIENT — final record.error includes earlier
        attempts for debuggability (adversarial review §2)."""
        spec = _cmd_spec(name="retry-exhausted", max_retries=2)

        mock_run = MagicMock(
            return_value=_completed_process(1, stdout="", stderr="connection reset by peer")
        )
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)
        monkeypatch.setattr("vibesop.core.loop.executor.time.sleep", lambda _s: None)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(spec)
            record = execute_loop_tick(spec, runtime=_mock_runtime(), store=store)

        assert record.success is False
        assert mock_run.call_count == 3  # 1 initial + 2 retries
        # All three attempts' errors captured for debugging.
        assert "attempt 1" in record.error
        assert "attempt 2" in record.error
        assert "final" in record.error

    def test_command_target_env_overrides_passed_to_subprocess(self, monkeypatch):
        """spec.env_overrides must reach subprocess.run's env kwarg."""
        spec = _cmd_spec(name="env-override", env_overrides={"VIBE_TEST": "1"})

        captured_kwargs: dict[str, object] = {}

        def capture_run(_argv, **kwargs):
            captured_kwargs.update(kwargs)
            return _completed_process(0, stdout="ok", stderr="")

        mock_run = MagicMock(side_effect=capture_run)
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(spec)
            execute_loop_tick(spec, runtime=_mock_runtime(), store=store)

        env = captured_kwargs.get("env")
        assert isinstance(env, dict)
        assert env.get("VIBE_TEST") == "1"

    def test_vibesop_run_prefix_with_spaces_parses_correctly(self, monkeypatch):
        """VIBESOP_RUN_PREFIX with quoted path-with-spaces must split into 3
        args (binary path kept whole), not 4 (adversarial review §15).

        Users must quote the path themselves — shlex.split respects quotes.
        Without quotes, path-with-spaces is unparseable as a single argv element.
        """
        monkeypatch.setenv("VIBESOP_RUN_PREFIX", '"/path/with space/uv" run vibe')
        spec = _cmd_spec(name="prefix-spaces", command_args=["instinct", "status"])

        captured_argv: list[str] = []

        def capture_run(argv, **_kwargs):
            captured_argv.extend(argv)
            return _completed_process(0, stdout="ok", stderr="")

        mock_run = MagicMock(side_effect=capture_run)
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(spec)
            execute_loop_tick(spec, runtime=_mock_runtime(), store=store)

        # Binary path kept whole; total argv = 3 prefix + 2 command = 5.
        assert captured_argv[0] == "/path/with space/uv"
        assert captured_argv[1] == "run"
        assert captured_argv[2] == "vibe"
        assert captured_argv[3] == "instinct"
        assert captured_argv[4] == "status"

    def test_command_target_stdout_truncated_to_200_chars(self, monkeypatch):
        """output_summary must cap at 200 chars (post-fix slice)."""
        long_stdout = "x" * 5000
        spec = _cmd_spec(name="long-stdout")

        mock_run = MagicMock(return_value=_completed_process(0, stdout=long_stdout, stderr=""))
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(spec)
            record = execute_loop_tick(spec, runtime=_mock_runtime(), store=store)

        assert record.success is True
        assert len(record.output_summary) == 200

    def test_command_target_unicode_args_pass_through_unchanged(self, monkeypatch):
        """command_args with non-ASCII (CJK, accented Latin) must reach
        subprocess.run as the original argv elements, not mojibake.

        Defended-against: any accidental encode/decode in _run_command_target
        would corrupt non-ASCII args (Phase A deferred item from pi review).
        """
        unicode_args = ["instinct", "学会", "naïve-repo", "测试/路径"]
        spec = _cmd_spec(name="unicode", command_args=unicode_args)

        captured_argv: list[str] = []

        def capture_run(argv, **_kwargs):
            captured_argv.extend(argv)
            return _completed_process(0, stdout="ok", stderr="")

        mock_run = MagicMock(side_effect=capture_run)
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LoopStore(base_dir=tmpdir)
            store.save_spec(spec)
            record = execute_loop_tick(spec, runtime=_mock_runtime(), store=store)

        # Argv tail (after the 3-element prefix) must equal the unicode args exactly.
        assert captured_argv[-len(unicode_args) :] == unicode_args
        assert record.success is True


# ──────────────────────────────────────────────────────────────────
# gate26: project_root ownership consumption
# ──────────────────────────────────────────────────────────────────

from datetime import UTC, datetime  # noqa: E402

from vibesop.core.loop.models import (  # noqa: E402
    FailureCategory,
    LoopRunRecord,
    LoopState,
)


class TestOwnershipExecution:
    """The executor consumes ``spec.project_root``: command targets run with
    the pinned root as subprocess cwd; a missing pinned root is a PERMANENT
    pre-flight failure (never silently runs in the ambient cwd)."""

    def test_command_path_passes_pinned_root_as_subprocess_cwd(self, monkeypatch, tmp_path):
        """gate26 core fix: execute_loop_tick previously never passed
        project_root to _run_command_target, so pinned loops ran in the
        ambient cwd."""
        owner = tmp_path / "owner-project"
        owner.mkdir()
        spec = _cmd_spec(name="owned-cmd", project_root=str(owner))

        captured: dict = {}
        mock_run = MagicMock(
            side_effect=lambda argv, **kwargs: (
                captured.update(kwargs),
                _completed_process(0, stdout="ok", stderr=""),
            )[1]
        )
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        store = LoopStore(base_dir=tmp_path / "loops")
        store.save_spec(spec)
        record = execute_loop_tick(spec, runtime=_mock_runtime(), store=store)

        assert record.success is True
        assert captured["cwd"] == str(owner.resolve())

    def test_unpinned_command_path_inherits_ambient_cwd(self, monkeypatch, tmp_path):
        """project_root=None (legacy/--global): cwd stays None → subprocess
        inherits the ambient cwd — pre-gate26 behaviour unchanged."""
        spec = _cmd_spec(name="global-cmd")  # project_root defaults to None

        captured: dict = {}
        mock_run = MagicMock(
            side_effect=lambda argv, **kwargs: (
                captured.update(kwargs),
                _completed_process(0, stdout="ok", stderr=""),
            )[1]
        )
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)

        store = LoopStore(base_dir=tmp_path / "loops")
        store.save_spec(spec)
        record = execute_loop_tick(spec, runtime=_mock_runtime(), store=store)

        assert record.success is True
        assert captured["cwd"] is None

    def test_missing_exec_root_is_permanent_preflight(self, monkeypatch, tmp_path):
        """Pinned root deleted → PERMANENT failure WITHOUT executing anything
        (no subprocess spawn, no runtime call), and the suggestion points at
        adopt + reset (fixed wording per gate26 review)."""
        gone = tmp_path / "deleted-project"  # never created
        spec = _cmd_spec(name="gone-root", project_root=str(gone))

        mock_run = MagicMock()
        monkeypatch.setattr("vibesop.core.loop.executor.subprocess.run", mock_run)
        runtime = _mock_runtime()

        store = LoopStore(base_dir=tmp_path / "loops")
        store.save_spec(spec)
        record = execute_loop_tick(spec, runtime=runtime, store=store)

        assert record.success is False
        assert record.failure_info is not None
        assert record.failure_info.category == FailureCategory.PERMANENT
        assert f"vibe loop adopt {spec.name}" in (record.failure_info.suggestion or "")
        assert f"vibe loop reset {spec.name}" in (record.failure_info.suggestion or "")
        # Nothing executed.
        mock_run.assert_not_called()
        runtime.handle_query.assert_not_called()
        # Failure was still persisted (DEAD budget burn is the loud signal).
        state = store.load_state(spec.name)
        assert state is not None
        assert state.consecutive_failures == 1

    def test_missing_exec_root_on_routing_path_also_preflights(self, tmp_path):
        """The pre-flight guards the routing path too — a skill-target loop
        pinned to a deleted root must not route against the ambient cwd."""
        gone = tmp_path / "deleted-project"
        spec = _spec(name="gone-routing", project_root=str(gone))
        runtime = _mock_runtime()

        store = LoopStore(base_dir=tmp_path / "loops")
        store.save_spec(spec)
        record = execute_loop_tick(spec, runtime=runtime, store=store)

        assert record.success is False
        assert record.failure_info is not None
        assert record.failure_info.category == FailureCategory.PERMANENT
        runtime.handle_query.assert_not_called()

    def test_oserror_distinguishes_missing_cwd_from_missing_uv(self, monkeypatch, tmp_path):
        """gate26 review pi#5: the OSError branch must not blame uv when the
        cwd vanished between pre-flight and spawn."""
        from vibesop.core.loop.executor import _run_command_target

        spec = _cmd_spec(name="race", project_root=str(tmp_path))
        record = LoopRunRecord(loop_name=spec.name, started_at=datetime.now(UTC))

        def raise_fnf(*args, **kwargs):
            raise FileNotFoundError("[Errno 2] No such file or directory")

        monkeypatch.setattr(
            "vibesop.core.loop.executor.subprocess.run", MagicMock(side_effect=raise_fnf)
        )

        missing_cwd = str(tmp_path / "vanished")  # does not exist
        _run_command_target(spec, record, project_root=missing_cwd)
        assert record.failure_info is not None
        assert "adopt" in (record.failure_info.suggestion or "")
        assert "uv installation" not in (record.failure_info.suggestion or "")

        # Same OSError with an EXISTING cwd → the prefix binary (uv) is at fault.
        record2 = LoopRunRecord(loop_name=spec.name, started_at=datetime.now(UTC))
        _run_command_target(spec, record2, project_root=str(tmp_path))
        assert record2.failure_info is not None
        assert "uv installation" in (record2.failure_info.suggestion or "")
        assert "adopt" not in (record2.failure_info.suggestion or "")

    def test_state_spec_rebound_to_live_spec_before_record(self, monkeypatch, tmp_path):
        """gate26 review: state.json embeds a spec copy that may be stale
        (e.g. adopt re-pinned project_root after the last run). The executor
        must re-bind state.spec = spec so the re-saved state carries the
        CURRENT spec."""
        stale = _spec(name="rebind", project_root=None)
        store = LoopStore(base_dir=tmp_path / "loops")
        store.save_spec(stale)
        store.save_state(LoopState(spec=stale))

        pinned = _spec(name="rebind", project_root=str(tmp_path))
        runtime = _mock_runtime()
        record = execute_loop_tick(pinned, runtime=runtime, store=store)
        assert record.success is True

        state = store.load_state("rebind")
        assert state is not None
        assert state.spec.project_root == str(tmp_path)
