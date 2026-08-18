"""Junk-query guard coverage for the decompose entry points.

The junk guard (_is_junk_query in vibesop.core.routing.unified) rejects
harness-injected markup (e.g. <system-reminder> blocks) by PREFIX after
lstrip. route() and _single_skill_route() were already guarded; these tests
pin the same semantics at the three decompose entry points:

- ``vibe decompose`` CLI command (vibesop.cli.main.decompose)
- ``AgentRouter.decompose()`` (vibesop.agent)
- ``AgentRouter.build_plan()`` auto-decompose branch (vibesop.agent)
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from vibesop.agent import AgentRouter
from vibesop.cli.main import app
from vibesop.core.orchestration import SubTask, TaskDecomposer

runner = CliRunner()

JUNK_QUERY = "  <system-reminder>Auto permission mode is active</system-reminder>"
# Marker present but NOT at the prefix — a legitimate query discussing the
# marker must not be killed (prefix, not substring, semantics).
DISCUSSION_QUERY = "explain what <system-reminder> blocks do in this repo"
NORMAL_QUERY = "debug the failing login test"


@pytest.fixture()
def decompose_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record TaskDecomposer.decompose calls; return one canned sub-task."""
    calls: list[str] = []

    def fake_decompose(self: TaskDecomposer, query: str, skills: object = None) -> list[SubTask]:
        calls.append(query)
        return [SubTask(intent="debug", query=query, skill_id=None)]

    monkeypatch.setattr(TaskDecomposer, "decompose", fake_decompose)
    return calls


class TestCliDecomposeJunkGuard:
    def test_junk_query_rejected(self, decompose_spy: list[str]) -> None:
        result = runner.invoke(app, ["decompose", JUNK_QUERY])
        assert result.exit_code == 0
        assert "harness-injected markup" in result.output
        # No decomposition happened at all.
        assert decompose_spy == []

    def test_junk_query_json_output(self, decompose_spy: list[str]) -> None:
        result = runner.invoke(app, ["decompose", JUNK_QUERY, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["sub_tasks"] == []
        assert decompose_spy == []

    def test_normal_query_not_rejected(self, decompose_spy: list[str]) -> None:
        result = runner.invoke(app, ["decompose", NORMAL_QUERY, "--json"])
        assert result.exit_code == 0
        assert "harness-injected markup" not in result.output
        data = json.loads(result.output)
        assert len(data["sub_tasks"]) == 1
        assert decompose_spy == [NORMAL_QUERY]

    def test_normal_query_json_output_parseable_for_long_query(
        self, decompose_spy: list[str]
    ) -> None:
        """Pin: --json output must survive json.loads even for long queries.

        Rich's console.print wraps at terminal width and would insert a raw
        newline inside a JSON string value; the decompose command therefore
        emits JSON via plain print() (same channel as route --json).
        """
        long_query = "debug the failing login test " + "with verbose tracing " * 6
        result = runner.invoke(app, ["decompose", long_query, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["query"] == long_query
        assert len(data["sub_tasks"]) == 1

    def test_marker_discussion_query_not_rejected(self, decompose_spy: list[str]) -> None:
        result = runner.invoke(app, ["decompose", DISCUSSION_QUERY, "--json"])
        assert result.exit_code == 0
        assert "harness-injected markup" not in result.output
        assert decompose_spy == [DISCUSSION_QUERY]


class TestAgentDecomposeJunkGuard:
    def test_junk_query_returns_empty(self, tmp_path, decompose_spy: list[str]) -> None:
        agent = AgentRouter(project_root=tmp_path)
        assert agent.decompose(JUNK_QUERY) == []
        assert decompose_spy == []

    def test_normal_query_decomposes(self, tmp_path, decompose_spy: list[str]) -> None:
        agent = AgentRouter(project_root=tmp_path)
        sub_tasks = agent.decompose(NORMAL_QUERY)
        assert len(sub_tasks) == 1
        assert sub_tasks[0]["intent"] == "debug"
        assert decompose_spy == [NORMAL_QUERY]

    def test_marker_discussion_query_not_killed(self, tmp_path, decompose_spy: list[str]) -> None:
        agent = AgentRouter(project_root=tmp_path)
        sub_tasks = agent.decompose(DISCUSSION_QUERY)
        assert len(sub_tasks) == 1
        assert decompose_spy == [DISCUSSION_QUERY]


class TestAgentBuildPlanJunkGuard:
    def test_junk_query_plans_from_empty_decomposition(
        self, tmp_path, decompose_spy: list[str]
    ) -> None:
        agent = AgentRouter(project_root=tmp_path)
        plan = agent.build_plan(JUNK_QUERY)
        assert plan["steps"] == []
        assert decompose_spy == []

    def test_normal_query_auto_decomposes(self, tmp_path, decompose_spy: list[str]) -> None:
        agent = AgentRouter(project_root=tmp_path)
        agent.build_plan(NORMAL_QUERY)
        assert decompose_spy == [NORMAL_QUERY]
