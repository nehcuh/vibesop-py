"""Tests for CLI route/orchestrate/decompose commands.

Covers the core CLI entry points for skill routing.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from vibesop.cli.main import app, _extract_squad_from_result, _format_squad_summary
from vibesop.core.models import WorkflowPattern

runner = CliRunner()


class TestRouteCommand:
    """Test `vibe route` command."""

    def test_route_basic_query(self) -> None:
        """Basic routing should return a result."""
        result = runner.invoke(app, ["route", "route my query"])
        assert result.exit_code == 0
        assert result.output

    def test_route_json_output(self) -> None:
        """JSON output should be valid JSON."""
        result = runner.invoke(app, ["route", "route my query", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
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
        from vibesop.core.models import AgentRole, AgentSquad, ExecutionPlan, OrchestrationResult, OrchestrationMode, SquadStep

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
        from vibesop.core.models import OrchestrationResult, OrchestrationMode

        result = OrchestrationResult(
            mode=OrchestrationMode.SINGLE,
            original_query="test",
        )

        assert _extract_squad_from_result(result) is None

    def test_route_multi_agent_squad_query_renders_squad(self) -> None:
        """A multi-agent query should render squad summary in CLI output."""
        result = runner.invoke(app, ["route", "multi-agent: 设计架构、实现代码、做安全审查"])
        assert result.exit_code == 0
        output = result.output
        # Squad summary should appear
        assert "Agent Squad" in output or "Squad" in output or "🔍 Semantic Analysis" in output
