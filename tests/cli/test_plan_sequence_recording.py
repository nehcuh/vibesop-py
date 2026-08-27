"""Tests for the P3 orchestration plan-sequence recording.

Covers:
- the CLI confirmation flow (``_orchestration_confirmation_flow``): explicit
  Confirm/Execute/edit-proceed → success=True; Skip/single/edit-cancel →
  success=False; abort (None) records nothing; <3-step plans are a no-op;
  learner failures never break the flow;
- the unattended flag set by ``vibe route`` on the routing context;
- ``Orchestrator._record_plan_sequence`` (application-only, success=False);
- the lazy tool-sequence assembly trigger beside the P2 hook in ``vibe route``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.agent.runtime import InterceptionMode
from vibesop.cli.main import (
    _maybe_assemble_tool_sequences,
    _orchestration_confirmation_flow,
    app,
)
from vibesop.core.routing.orchestrator import Orchestrator

if TYPE_CHECKING:
    import pytest

_QUERY = "refactor the auth module and add tests"


def _plan(*skill_ids: str) -> Any:
    return SimpleNamespace(steps=[SimpleNamespace(skill_id=s) for s in skill_ids])


def _result(plan: Any) -> Any:
    return SimpleNamespace(
        execution_plan=plan,
        original_query=_QUERY,
        single_fallback=None,
    )


def _router() -> Any:
    return SimpleNamespace(
        _config=SimpleNamespace(confirmation_mode="always", auto_select_threshold=0.9)
    )


def _stored_sequences(tmp_path: Path) -> list[dict[str, Any]]:
    seq_file = tmp_path / ".vibe" / "sequences.jsonl"
    if not seq_file.exists():
        return []
    return [json.loads(line) for line in seq_file.read_text(encoding="utf-8").splitlines()]


def _run_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    choice: str | None,
    plan: Any,
    *,
    execute: bool = False,
) -> bool:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(
        "vibesop.cli.main._safe_questionary_select",
        lambda message, choices, default="confirm": choice,
    )
    monkeypatch.setattr(
        "vibesop.cli.main._safe_questionary_confirm",
        lambda message, default=True: default,
    )
    monkeypatch.setattr("vibesop.cli.main.render_orchestration_result", MagicMock())
    monkeypatch.setattr("vibesop.cli.main._execute_plan_interactive", MagicMock())
    return _orchestration_confirmation_flow(
        _result(plan),
        yes=False,
        execute=execute,
        json_output=False,
        console=MagicMock(),
        router=_router(),
        already_rendered=True,
    )


class TestConfirmationFlowRecording:
    def test_confirm_records_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        confirmed = _run_flow(tmp_path, monkeypatch, "confirm", _plan("a", "b", "c"))
        assert confirmed is True
        stored = _stored_sequences(tmp_path)
        assert len(stored) == 1
        assert stored[0]["steps"] == ["a", "b", "c"]
        assert stored[0]["success_count"] == 1
        assert stored[0]["total_count"] == 1

    def test_skip_records_application_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        confirmed = _run_flow(tmp_path, monkeypatch, "skip", _plan("a", "b", "c"))
        assert confirmed is False
        stored = _stored_sequences(tmp_path)
        assert len(stored) == 1
        assert stored[0]["success_count"] == 0
        assert stored[0]["total_count"] == 1

    def test_ambiguous_only_auto_proceed_records_application_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ambiguous_only + all-confident (TTY): confirmation is skipped, but
        the plan sequence must still be recorded as application-only telemetry
        — the pre-routing ``_sequence_unattended`` flag cannot cover this case
        (step confidences unknown at context setup), and the instinct loop
        would otherwise starve under the ambiguous_only default.
        """

        def _no_prompt(*args: object, **kwargs: object) -> str:
            raise AssertionError("prompt must not fire on confident auto-proceed")

        plan = SimpleNamespace(
            steps=[SimpleNamespace(skill_id=s, confidence=0.9) for s in ("a", "b", "c")]
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: True))
        monkeypatch.setattr("vibesop.cli.main._safe_questionary_select", _no_prompt)
        monkeypatch.setattr("vibesop.cli.main.render_orchestration_result", MagicMock())
        router = SimpleNamespace(
            _config=SimpleNamespace(
                confirmation_mode="ambiguous_only", auto_select_threshold=0.6
            )
        )

        confirmed = _orchestration_confirmation_flow(
            _result(plan),
            yes=False,
            execute=False,
            json_output=False,
            console=MagicMock(),
            router=router,
            already_rendered=True,
        )

        assert confirmed is True
        stored = _stored_sequences(tmp_path)
        assert len(stored) == 1
        assert stored[0]["steps"] == ["a", "b", "c"]
        assert stored[0]["success_count"] == 0
        assert stored[0]["total_count"] == 1

    def test_single_fallback_records_application_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: True))
        monkeypatch.setattr(
            "vibesop.cli.main._safe_questionary_select",
            lambda message, choices, default="confirm": "single",
        )
        monkeypatch.setattr("vibesop.cli.main.render_orchestration_result", MagicMock())
        result = _result(_plan("a", "b", "c"))
        result.single_fallback = SimpleNamespace(skill_id="solo", confidence=0.9)

        confirmed = _orchestration_confirmation_flow(
            result,
            yes=False,
            execute=False,
            json_output=False,
            console=MagicMock(),
            router=_router(),
            already_rendered=True,
        )
        assert confirmed is False
        stored = _stored_sequences(tmp_path)
        assert len(stored) == 1
        assert stored[0]["success_count"] == 0

    def test_execute_records_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        confirmed = _run_flow(tmp_path, monkeypatch, "execute", _plan("a", "b", "c"), execute=True)
        assert confirmed is False  # guided mode takes over; plan accepted
        stored = _stored_sequences(tmp_path)
        assert len(stored) == 1
        assert stored[0]["success_count"] == 1

    def test_edit_proceed_records_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: True))
        monkeypatch.setattr(
            "vibesop.cli.main._safe_questionary_select",
            lambda message, choices, default="confirm": "edit",
        )
        monkeypatch.setattr(
            "vibesop.cli.main._safe_questionary_confirm",
            lambda message, default=True: True,
        )
        monkeypatch.setattr("vibesop.cli.main.render_orchestration_result", MagicMock())
        monkeypatch.setattr("vibesop.cli.main._edit_execution_plan", MagicMock(return_value=True))

        confirmed = _orchestration_confirmation_flow(
            _result(_plan("a", "b", "c")),
            yes=False,
            execute=False,
            json_output=False,
            console=MagicMock(),
            router=_router(),
            already_rendered=True,
        )
        assert confirmed is True
        stored = _stored_sequences(tmp_path)
        assert len(stored) == 1
        assert stored[0]["success_count"] == 1

    def test_edit_cancel_records_application_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: True))
        monkeypatch.setattr(
            "vibesop.cli.main._safe_questionary_select",
            lambda message, choices, default="confirm": "edit",
        )
        monkeypatch.setattr(
            "vibesop.cli.main._safe_questionary_confirm",
            lambda message, default=True: False,
        )
        monkeypatch.setattr("vibesop.cli.main.render_orchestration_result", MagicMock())
        monkeypatch.setattr("vibesop.cli.main._edit_execution_plan", MagicMock(return_value=True))

        confirmed = _orchestration_confirmation_flow(
            _result(_plan("a", "b", "c")),
            yes=False,
            execute=False,
            json_output=False,
            console=MagicMock(),
            router=_router(),
            already_rendered=True,
        )
        assert confirmed is False
        stored = _stored_sequences(tmp_path)
        assert len(stored) == 1
        assert stored[0]["success_count"] == 0

    def test_abort_records_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # questionary abort (Ctrl-C) returns None — not an explicit signal
        confirmed = _run_flow(tmp_path, monkeypatch, None, _plan("a", "b", "c"))
        assert confirmed is True
        assert _stored_sequences(tmp_path) == []

    def test_short_plan_is_noop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        confirmed = _run_flow(tmp_path, monkeypatch, "confirm", _plan("a", "b"))
        assert confirmed is True
        assert _stored_sequences(tmp_path) == []

    def test_none_plan_is_noop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        confirmed = _run_flow(tmp_path, monkeypatch, "confirm", None)
        assert confirmed is True
        assert _stored_sequences(tmp_path) == []

    def test_learner_failure_never_breaks_flow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _ExplodingLearner:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("disk full")

        monkeypatch.setattr("vibesop.core.instinct.learner.InstinctLearner", _ExplodingLearner)
        confirmed = _run_flow(tmp_path, monkeypatch, "confirm", _plan("a", "b", "c"))
        assert confirmed is True

    def test_edit_without_changes_records_application_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Editor applied no changes (modified falsy): plan never accepted →
        # application-only telemetry, symmetric with skip/single (M1).
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: True))
        monkeypatch.setattr(
            "vibesop.cli.main._safe_questionary_select",
            lambda message, choices, default="confirm": "edit",
        )
        confirm_mock = MagicMock()
        monkeypatch.setattr("vibesop.cli.main._safe_questionary_confirm", confirm_mock)
        monkeypatch.setattr("vibesop.cli.main.render_orchestration_result", MagicMock())
        monkeypatch.setattr("vibesop.cli.main._edit_execution_plan", MagicMock(return_value=False))

        confirmed = _orchestration_confirmation_flow(
            _result(_plan("a", "b", "c")),
            yes=False,
            execute=False,
            json_output=False,
            console=MagicMock(),
            router=_router(),
            already_rendered=True,
        )
        assert confirmed is False
        confirm_mock.assert_not_called()  # no "proceed?" for an unchanged plan
        stored = _stored_sequences(tmp_path)
        assert len(stored) == 1
        assert stored[0]["steps"] == ["a", "b", "c"]
        assert stored[0]["success_count"] == 0
        assert stored[0]["total_count"] == 1


class TestValidateModeRecording:
    """--validate + orchestrated: the confirmation flow must early-return so
    only the orchestrator records (application-only, success=False) — no
    interactive prompt, no double record (H1)."""

    def test_validate_skips_prompt_and_records_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # confirmation_mode="always" + TTY would prompt without the fix.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: True))
        select_mock = MagicMock()
        monkeypatch.setattr("vibesop.cli.main._safe_questionary_select", select_mock)
        monkeypatch.setattr("vibesop.cli.main.render_orchestration_result", MagicMock())

        confirmed = _orchestration_confirmation_flow(
            _result(_plan("a", "b", "c")),
            yes=False,
            execute=False,
            json_output=False,
            console=MagicMock(),
            router=_router(),
            already_rendered=True,
            validate=True,
        )
        assert confirmed is True
        select_mock.assert_not_called()
        assert _stored_sequences(tmp_path) == []

    def test_validate_run_records_once_application_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # End-to-end of the H1 invariant: the orchestrator records
        # success=False (route() flagged the run unattended for --validate),
        # then the confirmation flow early-returns without recording — a
        # single application-only record survives.
        from vibesop.core.instinct.learner import InstinctLearner

        monkeypatch.chdir(tmp_path)
        router_mock = MagicMock()
        router_mock._get_instinct_learner.return_value = InstinctLearner(
            storage_path=tmp_path / ".vibe" / "instincts.jsonl"
        )
        orch = Orchestrator(router_mock)
        context = SimpleNamespace(metadata={"_sequence_unattended": True})
        orch._record_plan_sequence(_QUERY, _plan("a", "b", "c"), context)

        monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: True))
        select_mock = MagicMock()
        monkeypatch.setattr("vibesop.cli.main._safe_questionary_select", select_mock)
        monkeypatch.setattr("vibesop.cli.main.render_orchestration_result", MagicMock())
        confirmed = _orchestration_confirmation_flow(
            _result(_plan("a", "b", "c")),
            yes=False,
            execute=False,
            json_output=False,
            console=MagicMock(),
            router=_router(),
            already_rendered=True,
            validate=True,
        )

        assert confirmed is True
        select_mock.assert_not_called()
        stored = _stored_sequences(tmp_path)
        assert len(stored) == 1  # no double record
        assert stored[0]["success_count"] == 0
        assert stored[0]["total_count"] == 1

    def test_handle_orchestrated_result_passes_validate_to_flow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from vibesop.cli.main import _handle_orchestrated_result

        flow = MagicMock(return_value=False)
        monkeypatch.setattr("vibesop.cli.main._orchestration_confirmation_flow", flow)

        _handle_orchestrated_result(
            _result(_plan("a", "b", "c")),
            MagicMock(),
            False,
            False,
            False,
            MagicMock(),
            validate=True,
        )
        assert flow.call_args.kwargs["validate"] is True


class TestOrchestratorUnattendedRecording:
    def _orchestrator(self) -> Orchestrator:
        return Orchestrator(MagicMock())

    def test_flagged_context_records_application_only(self) -> None:
        orch = self._orchestrator()
        context = SimpleNamespace(metadata={"_sequence_unattended": True})
        orch._record_plan_sequence(_QUERY, _plan("a", "b", "c"), context)
        learner = orch._router._get_instinct_learner.return_value
        learner.record_sequence.assert_called_once_with(
            steps=["a", "b", "c"], success=False, context=_QUERY
        )

    def test_unflagged_context_records_nothing(self) -> None:
        orch = self._orchestrator()
        context = SimpleNamespace(metadata={})
        orch._record_plan_sequence(_QUERY, _plan("a", "b", "c"), context)
        orch._router._get_instinct_learner.assert_not_called()

    def test_none_context_records_nothing(self) -> None:
        orch = self._orchestrator()
        orch._record_plan_sequence(_QUERY, _plan("a", "b", "c"), None)
        orch._router._get_instinct_learner.assert_not_called()

    def test_short_plan_records_nothing(self) -> None:
        orch = self._orchestrator()
        context = SimpleNamespace(metadata={"_sequence_unattended": True})
        orch._record_plan_sequence(_QUERY, _plan("a", "b"), context)
        orch._router._get_instinct_learner.assert_not_called()

    def test_learner_failure_swallowed(self) -> None:
        orch = self._orchestrator()
        orch._router._get_instinct_learner.side_effect = RuntimeError("boom")
        context = SimpleNamespace(metadata={"_sequence_unattended": True})
        # must not raise
        orch._record_plan_sequence(_QUERY, _plan("a", "b", "c"), context)


def _orchestrate_decision_interceptor() -> MagicMock:
    decision = MagicMock()
    decision.should_route = True
    decision.mode = InterceptionMode.ORCHESTRATE
    decision.query = _QUERY
    decision.reason = "orchestrate it"
    decision.analysis = None
    interceptor = MagicMock()
    interceptor.should_intercept.return_value = decision
    return interceptor


def _orchestrated_router() -> MagicMock:
    from vibesop.core.models import WorkflowPattern

    router = MagicMock()
    plan = SimpleNamespace(
        steps=[SimpleNamespace(skill_id=s) for s in ("a", "b", "c")],
        metadata={},
        workflow_pattern=WorkflowPattern.SEQUENTIAL,
    )
    result = SimpleNamespace(
        mode=SimpleNamespace(value="orchestrated"),
        execution_plan=plan,
        original_query=_QUERY,
        single_fallback=None,
        has_match=True,
    )
    router.orchestrate.return_value = result
    router._config = SimpleNamespace(confirmation_mode="always", auto_select_threshold=0.9)
    router.routing_config = SimpleNamespace(transparency="compact")
    return router


class TestRouteUnattendedFlag:
    @patch("vibesop.cli.main._handle_orchestrated_result", MagicMock())
    @patch("vibesop.cli.main.render_compact_orchestration", MagicMock())
    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_non_tty_run_sets_unattended_flag(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_stdin.isatty.return_value = False
        mock_interceptor_cls.return_value = _orchestrate_decision_interceptor()
        router = _orchestrated_router()
        mock_runtime_cls.return_value.router._router = router
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(app, ["route", _QUERY])

        assert result.exit_code == 0, result.output
        context = router.orchestrate.call_args.kwargs["context"]
        assert context.metadata["_sequence_unattended"] is True

    @patch("vibesop.cli.main._handle_orchestrated_result", MagicMock())
    @patch("vibesop.cli.main.render_compact_orchestration", MagicMock())
    @patch("vibesop.cli.progress.LiveOrchestrationCallbacks")
    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    def test_tty_interactive_run_does_not_set_flag(
        self,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_callbacks: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # CliRunner replaces sys.stdin during invoke (isatty always False), so
        # swap main's whole `sys` reference to simulate an interactive TTY.
        monkeypatch.setattr(
            "vibesop.cli.main.sys",
            SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True)),
        )
        mock_interceptor_cls.return_value = _orchestrate_decision_interceptor()
        router = _orchestrated_router()
        mock_runtime_cls.return_value.router._router = router
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(app, ["route", _QUERY])

        assert result.exit_code == 0, result.output
        context = router.orchestrate.call_args.kwargs["context"]
        assert "_sequence_unattended" not in context.metadata

    @patch("vibesop.cli.main.render_compact_orchestration", MagicMock())
    @patch("vibesop.cli.progress.LiveOrchestrationCallbacks")
    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    def test_validate_run_passes_validate_to_orchestrated_handler(
        self,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_callbacks: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # TTY + --validate: the unattended flag is set (orchestrator records
        # application-only) AND validate=True reaches the confirmation flow
        # so it early-returns instead of prompting (H1 plumbing).
        monkeypatch.setattr(
            "vibesop.cli.main.sys",
            SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True)),
        )
        mock_interceptor_cls.return_value = _orchestrate_decision_interceptor()
        router = _orchestrated_router()
        mock_runtime_cls.return_value.router._router = router
        handler = MagicMock()
        monkeypatch.setattr("vibesop.cli.main._handle_orchestrated_result", handler)
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(app, ["route", _QUERY, "--validate"])

        assert result.exit_code == 0, result.output
        assert handler.call_args.kwargs["validate"] is True
        context = router.orchestrate.call_args.kwargs["context"]
        assert context.metadata["_sequence_unattended"] is True


class TestLazyAssemblyTrigger:
    def test_enabled_by_default_calls_assemble(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))  # hermetic: ignore real ~/.vibe
        assemble = MagicMock()
        monkeypatch.setattr(
            "vibesop.core.instinct.tool_sequences.assemble_tool_sequences", assemble
        )
        _maybe_assemble_tool_sequences(tmp_path)
        assemble.assert_called_once_with(tmp_path)

    def test_disabled_skips_assembly(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("VIBE_SEQUENCES_ENABLED", "false")
        assemble = MagicMock()
        monkeypatch.setattr(
            "vibesop.core.instinct.tool_sequences.assemble_tool_sequences", assemble
        )
        _maybe_assemble_tool_sequences(tmp_path)
        assemble.assert_not_called()

    def test_uses_given_project_root_not_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # project_root is explicit (M2): a cwd elsewhere must not matter.
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        monkeypatch.setenv("HOME", str(tmp_path))
        assemble = MagicMock()
        monkeypatch.setattr(
            "vibesop.core.instinct.tool_sequences.assemble_tool_sequences", assemble
        )
        _maybe_assemble_tool_sequences(tmp_path)
        assemble.assert_called_once_with(tmp_path)

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_route_invokes_lazy_assembly(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_stdin.isatty.return_value = False
        mock_interceptor_cls.return_value = _orchestrate_decision_interceptor()
        router = _orchestrated_router()
        mock_runtime_cls.return_value.router._router = router
        monkeypatch.chdir(tmp_path)
        assemble = MagicMock()
        monkeypatch.setattr("vibesop.cli.main._maybe_assemble_tool_sequences", assemble)
        monkeypatch.setattr("vibesop.cli.main.render_compact_orchestration", MagicMock())
        monkeypatch.setattr("vibesop.cli.main._handle_orchestrated_result", MagicMock())

        result = CliRunner().invoke(app, ["route", _QUERY])

        assert result.exit_code == 0, result.output
        assemble.assert_called_once_with(tmp_path)

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_route_survives_assembly_failure(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_stdin.isatty.return_value = False
        mock_interceptor_cls.return_value = _orchestrate_decision_interceptor()
        router = _orchestrated_router()
        mock_runtime_cls.return_value.router._router = router
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "vibesop.cli.main._maybe_assemble_tool_sequences",
            MagicMock(side_effect=RuntimeError("boom")),
        )
        monkeypatch.setattr("vibesop.cli.main.render_compact_orchestration", MagicMock())
        monkeypatch.setattr("vibesop.cli.main._handle_orchestrated_result", MagicMock())

        result = CliRunner().invoke(app, ["route", _QUERY])

        assert result.exit_code == 0, result.output
