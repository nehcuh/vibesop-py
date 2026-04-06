"""Tests for execute CLI command."""

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.execute import app as execute_app

runner = CliRunner()


def test_execute_list_command():
    """Test that execute list shows available skills."""
    result = runner.invoke(execute_app, ["list"])
    assert result.exit_code == 0


def test_execute_nonexistent_skill():
    """Test executing a non-existent skill shows error."""
    result = runner.invoke(execute_app, ["execute", "nonexistent-skill", "test query"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_execute_dry_run():
    """Test dry run shows what would be executed."""
    result = runner.invoke(
        execute_app, ["execute", "systematic-debugging", "debug error", "--dry-run"]
    )
    assert result.exit_code == 0
    assert "Dry Run" in result.output


def test_execute_with_namespace():
    """Test executing omx/ skill shows correct info in dry run."""
    result = runner.invoke(execute_app, ["execute", "omx/deep-interview", "build app", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry Run" in result.output
