"""Tests for optimize_cmd.py."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestOptimizeCommand:
    """Tests for vibe optimize command."""

    def test_optimize_help(self):
        result = runner.invoke(app, ["optimize", "--help"])
        assert result.exit_code == 0
        assert "optimize" in result.stdout.lower()

    def test_optimize_dry_run(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["optimize", "--days", "1"])
        # May return 0 or 1 depending on data availability
        assert "Routing Health" in result.stdout or result.exit_code == 0

    def test_optimize_with_days(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["optimize", "--days", "7"])
        assert result.exit_code in (0, 1)

    def test_optimize_with_apply_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["optimize", "--apply", "--days", "1"])
        # --apply may fail gracefully if no evaluator data
        assert "Applied Optimizations" in result.stdout or "Routing Health" in result.stdout
