"""Tests for CLI route() mode dispatch by InterceptionMode.

These tests verify that ``vibe route`` dispatches to the correct underlying
router method based on the IntentInterceptor decision:

- SINGLE -> router.route()
- SINGLE_AGENT -> router.route() with role-enriched context
- MULTI_AGENT_SQUAD -> router.orchestrate() with intent analysis metadata
- ORCHESTRATE -> router.orchestrate()
- SLASH_COMMAND -> SlashCommandExecutor (covered by existing e2e tests)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from vibesop.agent.runtime import InterceptionMode
from vibesop.cli.main import (
    _build_multi_agent_squad_context,
    _build_single_agent_context,
    _print_fallback,
    app,
)
from vibesop.core.matching import RoutingContext
from vibesop.core.models import IntentAnalysis


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_router() -> MagicMock:
    """Return a mock UnifiedRouter-like object with expected return values."""
    router = MagicMock()
    routing_result = MagicMock()
    routing_result.primary = MagicMock(skill_id="gstack-review")
    routing_result.alternatives = []
    routing_result.routing_path = []
    routing_result.layer_details = []
    routing_result.duration_ms = 0.0
    router.route.return_value = routing_result

    orch_result = MagicMock()
    orch_result.mode.value = "orchestrated"
    orch_result.execution_plan = None
    orch_result.primary = None
    orch_result.to_dict.return_value = {"mode": "orchestrated"}
    router.orchestrate.return_value = orch_result

    single_orch = MagicMock()
    single_orch.mode.value = "single"
    single_orch.execution_plan = None
    single_orch.primary = routing_result.primary
    single_orch.to_dict.return_value = {"mode": "single"}
    router._to_orchestration_result.return_value = single_orch
    return router


def _make_interceptor_mock(mode: InterceptionMode, *, analysis: Any = None) -> MagicMock:
    """Build a mocked IntentInterceptor returning the requested decision."""
    decision = MagicMock()
    decision.should_route = True
    decision.mode = mode
    decision.query = "test query"
    decision.reason = "test decision"
    decision.analysis = analysis

    interceptor = MagicMock()
    interceptor.should_intercept.return_value = decision
    return interceptor


class TestContextBuilders:
    """Unit tests for route-context enrichment helpers."""

    def test_single_agent_context_enriches_role_and_skills(self) -> None:
        analysis = IntentAnalysis(
            complexity="simple",
            suggested_roles=["architect"],
            per_agent_skills={"architect": ["system-design"]},
        )
        decision = MagicMock()
        decision.analysis = analysis

        base = RoutingContext(conversation_id="test-123")
        ctx = _build_single_agent_context(base, decision)

        assert ctx.interception_mode == "single_agent"
        assert ctx.role_context is not None
        assert ctx.role_context["role"] == "architect"
        assert ctx.role_context["allowed_skills"] == ["system-design"]
        assert "{skill_list}" in ctx.role_context["role_prompt"]
        assert ctx.metadata["intent_analysis"]["suggested_roles"] == ["architect"]
        assert ctx.metadata["_interception_mode"] == "single_agent"
        assert ctx.conversation_id == "test-123"

    def test_single_agent_context_degrades_when_no_analysis(self) -> None:
        decision = MagicMock()
        decision.analysis = None
        base = RoutingContext(conversation_id="test-123")
        ctx = _build_single_agent_context(base, decision)
        assert ctx is base

    def test_single_agent_context_degrades_when_no_roles(self) -> None:
        decision = MagicMock()
        decision.analysis = IntentAnalysis(complexity="simple", suggested_roles=[])
        base = RoutingContext(conversation_id="test-123")
        ctx = _build_single_agent_context(base, decision)
        assert ctx is base

    def test_multi_agent_squad_context_injects_analysis(self) -> None:
        analysis = IntentAnalysis(
            complexity="multi_agent",
            squad_needed=True,
            suggested_roles=["architect", "implementer"],
        )
        decision = MagicMock()
        decision.analysis = analysis
        base = RoutingContext(conversation_id="squad-123")

        ctx = _build_multi_agent_squad_context(base, decision)

        assert ctx.interception_mode == "multi_agent_squad"
        assert ctx.metadata["intent_analysis"]["squad_needed"] is True
        assert ctx.metadata["_interception_mode"] == "multi_agent_squad"
        assert ctx.conversation_id == "squad-123"

    def test_multi_agent_squad_context_without_analysis(self) -> None:
        decision = MagicMock()
        decision.analysis = None
        base = RoutingContext(conversation_id="squad-123")

        ctx = _build_multi_agent_squad_context(base, decision)

        assert ctx.interception_mode == "multi_agent_squad"
        assert ctx.conversation_id == "squad-123"
        assert "intent_analysis" not in ctx.metadata


class TestFallbackPrinter:
    """Unit tests for the fallback printer helper."""

    def test_print_fallback_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_fallback("hello", "too short", json_output=True)
        captured = capsys.readouterr()
        assert '"intercepted": false' in captured.out
        assert '"reason": "too short"' in captured.out
        assert '"query": "hello"' in captured.out


class TestRouteModeDispatch:
    """Integration tests for ``vibe route`` mode dispatch."""

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_single_mode_calls_route(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
    ) -> None:
        """SINGLE decision should call router.route() and skip orchestration."""
        mock_stdin.isatty.return_value = False
        mock_interceptor_cls.return_value = _make_interceptor_mock(InterceptionMode.SINGLE)
        mock_runtime_cls.return_value.router._router = mock_router

        result = cli_runner.invoke(app, ["route", "--json", "review my code"])

        assert result.exit_code == 0
        mock_router.route.assert_called_once()
        mock_router.orchestrate.assert_not_called()

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_single_agent_mode_calls_route_with_role_context(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
    ) -> None:
        """SINGLE_AGENT decision should call router.route() with enriched context."""
        mock_stdin.isatty.return_value = False
        analysis = IntentAnalysis(
            complexity="simple",
            suggested_roles=["architect"],
            per_agent_skills={"architect": ["system-design"]},
        )
        mock_interceptor_cls.return_value = _make_interceptor_mock(
            InterceptionMode.SINGLE_AGENT, analysis=analysis
        )
        mock_runtime_cls.return_value.router._router = mock_router

        result = cli_runner.invoke(app, ["route", "--json", "design a microservice"])

        assert result.exit_code == 0
        mock_router.route.assert_called_once()
        mock_router.orchestrate.assert_not_called()
        call_context = mock_router.route.call_args.kwargs.get("context")
        assert call_context is not None
        assert call_context.interception_mode == "single_agent"
        assert call_context.role_context["role"] == "architect"

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_multi_agent_squad_mode_calls_orchestrate(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
    ) -> None:
        """MULTI_AGENT_SQUAD decision should call router.orchestrate()."""
        mock_stdin.isatty.return_value = False
        analysis = IntentAnalysis(
            complexity="multi_agent",
            squad_needed=True,
            suggested_roles=["architect", "implementer", "reviewer"],
        )
        mock_interceptor_cls.return_value = _make_interceptor_mock(
            InterceptionMode.MULTI_AGENT_SQUAD, analysis=analysis
        )
        mock_runtime_cls.return_value.router._router = mock_router

        result = cli_runner.invoke(
            app, ["route", "--json", "design architecture, implement code, and review security"]
        )

        assert result.exit_code == 0
        mock_router.route.assert_not_called()
        mock_router.orchestrate.assert_called_once()
        call_context = mock_router.orchestrate.call_args.kwargs.get("context")
        assert call_context is not None
        assert call_context.interception_mode == "multi_agent_squad"
        assert call_context.metadata["intent_analysis"]["squad_needed"] is True

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_orchestrate_mode_calls_orchestrate(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
    ) -> None:
        """ORCHESTRATE decision should call router.orchestrate()."""
        mock_stdin.isatty.return_value = False
        mock_interceptor_cls.return_value = _make_interceptor_mock(InterceptionMode.ORCHESTRATE)
        mock_runtime_cls.return_value.router._router = mock_router

        result = cli_runner.invoke(app, ["route", "--json", "analyze and test"])

        assert result.exit_code == 0
        mock_router.route.assert_not_called()
        mock_router.orchestrate.assert_called_once()

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_none_mode_shows_fallback(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
    ) -> None:
        """NONE decision (should_route=False) should print fallback and exit cleanly."""
        mock_stdin.isatty.return_value = False
        interceptor = MagicMock()
        decision = MagicMock()
        decision.should_route = False
        decision.mode = InterceptionMode.NONE
        decision.query = "ok"
        decision.reason = "too short"
        decision.analysis = None
        interceptor.should_intercept.return_value = decision
        mock_interceptor_cls.return_value = interceptor
        mock_runtime_cls.return_value.router._router = mock_router

        result = cli_runner.invoke(app, ["route", "--json", "ok"])

        assert result.exit_code == 0
        assert '"intercepted": false' in result.output
        mock_router.route.assert_not_called()
        mock_router.orchestrate.assert_not_called()
