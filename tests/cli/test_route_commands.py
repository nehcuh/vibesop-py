"""Tests for CLI route/orchestrate/decompose commands.

Covers the core CLI entry points for skill routing.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from vibesop.cli.main import app

if TYPE_CHECKING:
    pass

runner = CliRunner()


class TestRouteCommand:
    """Test `vibe route` command."""

    def test_route_basic_query(self) -> None:
        """Basic routing should return a result."""
        result = runner.invoke(app, ["route", "debug this error"])
        assert result.exit_code == 0
        assert result.output

    def test_route_json_output(self) -> None:
        """JSON output should be valid JSON."""
        result = runner.invoke(app, ["route", "debug", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "mode" in data
        assert "primary" in data

    def test_route_with_yes_flag(self) -> None:
        """--yes flag should skip confirmation."""
        result = runner.invoke(app, ["route", "debug", "--yes"])
        assert result.exit_code == 0

    def test_route_short_y_flag(self) -> None:
        """-y flag should skip confirmation."""
        result = runner.invoke(app, ["route", "debug", "-y"])
        assert result.exit_code == 0

    def test_route_explain_flag(self) -> None:
        """--explain flag should show routing details."""
        result = runner.invoke(app, ["route", "debug", "--explain"])
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
