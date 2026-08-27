"""Tests for CLI route/orchestrate/decompose commands.

Covers the core CLI entry points for skill routing.

All routing is hermetic: the IntentInterceptor/AgentRuntime and
UnifiedRouter seams are stubbed (same pattern as
tests/cli/test_route_market_suggestion.py), so no test touches the
developer's live .vibe index, the HuggingFace embedding model, or the
network. State writes (missed-query inbox, routing counter, plan tracker)
are redirected to tmp_path via monkeypatch.chdir.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from vibesop.agent.runtime import InterceptionMode
from vibesop.cli.main import _extract_squad_from_result, _format_squad_summary, app
from vibesop.core.models import OrchestrationMode, OrchestrationResult, WorkflowPattern

runner = CliRunner()


class _FakeOrchestrateRouter:
    """UnifiedRouter stand-in for `vibe orchestrate` tests.

    The command builds its router from Path.cwd() — the developer's live
    .vibe index plus the HuggingFace embedding model (~10-50s load, and HF
    warnings leak into stdout, breaking JSON parsing). Return a controlled,
    stable result so these tests pin CLI plumbing (exit code, JSON shape),
    not live routing outcomes.
    """

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def orchestrate(self, query: str, context: object = None) -> OrchestrationResult:
        return OrchestrationResult(mode=OrchestrationMode.SINGLE, original_query=query)


class _FakeDecomposeRouter:
    """UnifiedRouter stand-in for `vibe decompose` tests.

    The real router reads the live skill catalog and may build an LLM
    client; here the decomposer gets no LLM (deterministic rule-based
    fallback) and an empty catalog (skill_id is always None).
    """

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.llm = None

    def build_decomposition_skills(self, query: str = "") -> list[str]:
        return []


def _routing_decision(query: str, mode: InterceptionMode) -> MagicMock:
    """Interceptor decision that always routes with the given mode."""
    decision = MagicMock()
    decision.should_route = True
    decision.mode = mode
    decision.query = query
    decision.reason = "route it"
    decision.analysis = None
    return decision


def _single_no_match_router() -> MagicMock:
    """UnifiedRouter-like mock whose single-route result is a stable no-match.

    Returns real OrchestrationResult objects (not MagicMocks) so JSON
    serialization and Rich renderers behave exactly as in production.
    """
    router = MagicMock()
    router.route.return_value = MagicMock(name="routing_result")
    router._to_orchestration_result.side_effect = lambda _rr, query: OrchestrationResult(
        mode=OrchestrationMode.SINGLE, original_query=query, duration_ms=1.0
    )
    router._config = SimpleNamespace(confirmation_mode="never", auto_select_threshold=0.9)
    router.routing_config = SimpleNamespace(transparency="full")
    return router


def _squad_router() -> MagicMock:
    """UnifiedRouter-like mock whose orchestrate() returns a fixed squad plan."""
    from vibesop.core.models import AgentRole, AgentSquad, ExecutionPlan, SquadStep

    squad = AgentSquad(
        squad_id="squad-test",
        roles=[AgentRole(role_id="architect", name="Architect", required_skills=["design"])],
        steps=[SquadStep(step_id="s1", role_id="architect", skill_ids=["design"])],
        execution_order=["s1"],
    )
    plan = ExecutionPlan(
        plan_id="plan-1",
        original_query="multi-agent query",
        workflow_pattern=WorkflowPattern.AGENT_SQUAD,
        metadata={"agent_squad": squad.to_dict()},
    )
    result = OrchestrationResult(
        mode=OrchestrationMode.ORCHESTRATED,
        original_query="multi-agent query",
        execution_plan=plan,
        duration_ms=1.0,
    )
    router = _single_no_match_router()
    router.orchestrate.return_value = result
    return router


def _patch_route_runtime(
    monkeypatch: pytest.MonkeyPatch,
    router: MagicMock,
    *,
    mode: InterceptionMode = InterceptionMode.SINGLE,
) -> None:
    """Patch the IntentInterceptor/AgentRuntime seam used by `vibe route`.

    route() imports both lazily inside the command body from
    vibesop.agent.runtime, so patching the attributes on that module
    intercepts construction.
    """
    interceptor = MagicMock()
    interceptor.should_intercept.side_effect = lambda query: _routing_decision(query, mode)
    monkeypatch.setattr("vibesop.agent.runtime.IntentInterceptor", lambda: interceptor)
    runtime = MagicMock()
    runtime.router._router = router
    monkeypatch.setattr("vibesop.agent.runtime.AgentRuntime", lambda **_kwargs: runtime)


class TestRouteCommand:
    """Test `vibe route` command."""

    @pytest.fixture(autouse=True)
    def _hermetic_runtime(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        # Redirect .vibe state writes (missed-query inbox, routing counter,
        # trace spans) to a tmp dir, then stub the routing boundary.
        monkeypatch.chdir(tmp_path)
        _patch_route_runtime(monkeypatch, _single_no_match_router())

    def test_route_basic_query(self) -> None:
        """Basic routing should return a result."""
        result = runner.invoke(app, ["route", "route my query"])
        assert result.exit_code == 0
        assert result.output

    def test_route_json_output(self) -> None:
        """JSON output should be valid JSON."""
        result = runner.invoke(app, ["route", "route my query", "--json"])
        assert result.exit_code == 0
        # Tolerate a status preamble (e.g. "Using default LLM ..." printed to
        # stdout when no explicit LLM is configured) — extract the JSON object.
        out = result.output
        data = json.loads(out[out.index("{") :])
        assert "mode" in data
        assert "primary" in data

    def test_route_with_yes_flag(self) -> None:
        """--yes flag should skip confirmation."""
        result = runner.invoke(app, ["route", "route my query", "--yes"])
        assert result.exit_code == 0

    def test_route_short_y_flag(self) -> None:
        """-y flag should skip confirmation."""
        result = runner.invoke(app, ["route", "route my query", "-y"])
        assert result.exit_code == 0

    def test_route_explain_flag(self) -> None:
        """--explain flag should show routing details."""
        result = runner.invoke(app, ["route", "route my query", "--explain"])
        assert result.exit_code == 0
        # Explain mode produces more verbose output
        assert len(result.output) > 0

    def test_route_no_match_query(self) -> None:
        """Queries with no match should still exit 0."""
        result = runner.invoke(app, ["route", "xyzabc123"])
        assert result.exit_code == 0


class TestOrchestrateCommand:
    """Test `vibe orchestrate` command."""

    @pytest.fixture(autouse=True)
    def _fake_router(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # orchestrate() imports UnifiedRouter lazily inside the command body,
        # so patching the attribute on vibesop.core.routing intercepts it.
        monkeypatch.setattr("vibesop.core.routing.UnifiedRouter", _FakeOrchestrateRouter)

    def test_orchestrate_basic(self) -> None:
        """Orchestrate should work for single-intent queries."""
        result = runner.invoke(app, ["orchestrate", "debug this"])
        assert result.exit_code == 0

    def test_orchestrate_json_output(self) -> None:
        """JSON output from orchestrate should be valid."""
        result = runner.invoke(app, ["orchestrate", "debug", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "mode" in data

    def test_orchestrate_multi_intent(self) -> None:
        """Orchestrate may return orchestrated mode for complex queries."""
        result = runner.invoke(app, ["orchestrate", "分析架构然后写测试"])
        assert result.exit_code == 0


class TestDecomposeCommand:
    """Test `vibe decompose` command."""

    @pytest.fixture(autouse=True)
    def _fake_router(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # decompose() imports UnifiedRouter lazily inside the command body,
        # so patching the attribute on vibesop.core.routing intercepts it.
        monkeypatch.setattr("vibesop.core.routing.UnifiedRouter", _FakeDecomposeRouter)

    def test_decompose_basic(self) -> None:
        """Decompose should return sub-tasks."""
        result = runner.invoke(app, ["decompose", "分析架构然后写测试"])
        assert result.exit_code == 0
        assert result.output

    def test_decompose_json_output(self) -> None:
        """JSON output from decompose should be valid."""
        result = runner.invoke(app, ["decompose", "debug then test", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Decompose returns a list of tasks or a dict
        assert isinstance(data, (list, dict))

    def test_decompose_json_includes_skill_id(self) -> None:
        """Each sub-task in JSON output exposes a skill_id field (str or null).

        P1-B: the decomposer is now fed the project skill catalog, so each task
        carries a skill_id (or explicit None) for downstream consumers.
        """
        result = runner.invoke(app, ["decompose", "debug then test", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)

        # data is {"query": ..., "sub_tasks": [...]}
        if isinstance(data, dict) and "sub_tasks" in data:
            for task in data["sub_tasks"]:
                assert "skill_id" in task
                assert task["skill_id"] is None or isinstance(task["skill_id"], str)


class TestRouteEdgeCases:
    """Edge cases for routing commands."""

    @pytest.fixture(autouse=True)
    def _hermetic_runtime(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.chdir(tmp_path)
        _patch_route_runtime(monkeypatch, _single_no_match_router())

    def test_route_empty_query(self) -> None:
        """Empty query should handle gracefully."""
        result = runner.invoke(app, ["route", ""])
        assert result.exit_code == 0

    def test_route_chinese_query(self) -> None:
        """Chinese queries should work."""
        result = runner.invoke(app, ["route", "帮我调试这个错误"])
        assert result.exit_code == 0

    def test_route_very_long_query(self) -> None:
        """Very long queries should not crash."""
        long_query = "debug " * 100
        result = runner.invoke(app, ["route", long_query])
        assert result.exit_code == 0


class TestRouteSquadDisplay:
    """Squad summary rendering for multi-agent queries."""

    def test_format_squad_summary_contains_roles_and_protocol(self) -> None:
        from vibesop.core.models import AgentRole, AgentSquad, SquadStep

        squad = AgentSquad(
            squad_id="squad-test",
            roles=[
                AgentRole(role_id="architect", name="Architect", required_skills=["design"]),
                AgentRole(role_id="red_team", name="Red Team", required_skills=["security"]),
            ],
            steps=[
                SquadStep(
                    step_id="arch",
                    role_id="architect",
                    agent_platform="claude-code",
                    skill_ids=["architecture-analysis", "design-doc"],
                ),
                SquadStep(
                    step_id="rt",
                    role_id="red_team",
                    agent_platform="claude-code",
                    skill_ids=["security-audit"],
                ),
            ],
            collaboration_protocol="review_gate",
            max_rounds=3,
            execution_order=["arch", "rt"],
        )

        summary = _format_squad_summary(squad)

        assert "Agent Squad" in summary
        assert "🏗️" in summary
        assert "🛡️" in summary
        assert "claude-code" in summary
        assert "architecture-analysis" in summary
        assert "security-audit" in summary
        assert "Protocol: review_gate" in summary
        assert "Max Rounds: 3" in summary
        assert "arch → rt → review" in summary

    def test_extract_squad_from_orchestration_result(self) -> None:
        from vibesop.core.models import (
            AgentRole,
            AgentSquad,
            ExecutionPlan,
            OrchestrationMode,
            OrchestrationResult,
            SquadStep,
        )

        squad = AgentSquad(
            squad_id="squad-test",
            roles=[AgentRole(role_id="architect", name="Architect", required_skills=["design"])],
            steps=[SquadStep(step_id="s1", role_id="architect", skill_ids=["design"])],
            execution_order=["s1"],
        )
        plan = ExecutionPlan(
            plan_id="plan-1",
            original_query="test",
            workflow_pattern=WorkflowPattern.AGENT_SQUAD,
            metadata={"agent_squad": squad.to_dict()},
        )
        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query="test",
            execution_plan=plan,
        )

        extracted = _extract_squad_from_result(result)
        assert extracted is not None
        assert extracted.squad_id == "squad-test"

    def test_extract_squad_returns_none_for_plain_result(self) -> None:
        from vibesop.core.models import OrchestrationMode, OrchestrationResult

        result = OrchestrationResult(
            mode=OrchestrationMode.SINGLE,
            original_query="test",
        )

        assert _extract_squad_from_result(result) is None

    def test_route_multi_agent_squad_query_renders_squad(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """A multi-agent query should render squad summary in CLI output."""
        monkeypatch.chdir(tmp_path)
        _patch_route_runtime(monkeypatch, _squad_router(), mode=InterceptionMode.MULTI_AGENT_SQUAD)
        result = runner.invoke(app, ["route", "multi-agent: 设计架构、实现代码、做安全审查"])
        assert result.exit_code == 0
        output = result.output
        # The fixture's squad renders deterministically — pin the exact block
        # (no OR-chain fallbacks that could mask a squad-rendering regression).
        assert "Agent Squad" in output
        assert "🏗️" in output  # architect role icon
        assert "Skills: design" in output
        assert "Protocol: sequential" in output


class TestRouteHookMode:
    """gate33 (pi NIT-6 / claude MAJOR-2): the grok route hook deployed
    ``vibe route --hook`` since e9b6f15, but the flag never existed — the
    grok-native routing hook was dead on arrival. These pin the now-real
    hook mode: stdin event JSON (snake AND camelCase) → query/session
    extraction → handle_query_for_hook envelope; always exit 0."""

    @pytest.fixture(autouse=True)
    def _stub_hook_runtime(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.chdir(tmp_path)
        captured: dict[str, Any] = {}

        class _StubRuntime:
            def __init__(self, **kwargs: Any) -> None:  # accepts project_root= etc.
                captured["init_kwargs"] = kwargs

            def handle_query_for_hook(self, query: str, **kwargs: Any) -> str:
                captured["query"] = query
                captured.update(kwargs)
                return '{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit"}}'

        monkeypatch.setattr("vibesop.agent.runtime.AgentRuntime", _StubRuntime)
        self.captured = captured  # type: ignore[attr-defined]

    def test_hook_mode_camelcase_grok_payload(self) -> None:
        payload = {"userPrompt": "帮我合并到 main 吧", "sessionId": "grok-sess-1"}
        result = runner.invoke(app, ["route", "--hook"], input=json.dumps(payload))
        assert result.exit_code == 0
        assert "hookSpecificOutput" in result.output
        assert self.captured["query"] == "帮我合并到 main 吧"  # type: ignore[attr-defined]
        assert self.captured["session_id"] == "grok-sess-1"  # type: ignore[attr-defined]
        assert self.captured["platform"] == "grok-build"  # type: ignore[attr-defined]
        # claude r2 NIT-1 / pi r2: the runtime is constructed with the
        # resolved project root (payload/env/cwd chain — here the cwd
        # fallback, Path(), since the payload carries no workspaceRoot).
        from pathlib import Path

        assert self.captured["init_kwargs"]["project_root"] == Path()  # type: ignore[attr-defined]

    def test_hook_mode_snake_case_payload(self) -> None:
        payload = {"query": "review this", "session_id": "claude-sess"}
        result = runner.invoke(app, ["route", "--hook"], input=json.dumps(payload))
        assert result.exit_code == 0
        assert self.captured["query"] == "review this"  # type: ignore[attr-defined]
        assert self.captured["session_id"] == "claude-sess"  # type: ignore[attr-defined]

    def test_hook_mode_empty_stdin_exits_zero_with_empty_envelope(self) -> None:
        result = runner.invoke(app, ["route", "--hook"], input="")
        assert result.exit_code == 0
        assert result.output.strip() == "{}"

    def test_hook_mode_plain_text_fallback(self) -> None:
        result = runner.invoke(app, ["route", "--hook"], input="plain query text")
        assert result.exit_code == 0
        assert self.captured["query"] == "plain query text"  # type: ignore[attr-defined]

    def test_explicit_platform_flag_beats_json_platform(self) -> None:
        payload = {"userPrompt": "x", "platform": "claude-code"}
        result = runner.invoke(
            app, ["route", "--hook", "--platform", "grok-build"], input=json.dumps(payload)
        )
        assert result.exit_code == 0
        assert self.captured["platform"] == "grok-build"  # type: ignore[attr-defined]

    def test_omitted_flag_reads_json_platform(self) -> None:
        payload = {"userPrompt": "x", "platform": "claude-code"}
        result = runner.invoke(app, ["route", "--hook"], input=json.dumps(payload))
        assert result.exit_code == 0
        assert self.captured["platform"] == "claude-code"  # type: ignore[attr-defined]

    def test_no_query_no_hook_errors(self) -> None:
        result = runner.invoke(app, ["route"])
        assert result.exit_code == 1
        assert "Missing argument QUERY" in result.output
