"""Tests for omx/ CLI integration."""

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.omx import app as omx_app

runner = CliRunner()


def test_omx_list():
    """Test omx list shows all 7 methodologies."""
    result = runner.invoke(omx_app, ["list"])
    assert result.exit_code == 0
    assert "deep-interview" in result.output
    assert "ralph" in result.output
    assert "ralplan" in result.output
    assert "team" in result.output
    assert "ultrawork" in result.output
    assert "autopilot" in result.output
    assert "ultraqa" in result.output


def test_omx_interview_dry_run():
    """Test omx interview dry run."""
    result = runner.invoke(omx_app, ["interview", "build app", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry Run" in result.output


def test_omx_ralph_dry_run():
    """Test omx ralph dry run."""
    result = runner.invoke(omx_app, ["ralph", "implement feature", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry Run" in result.output


def test_omx_plan_dry_run():
    """Test omx plan dry run."""
    result = runner.invoke(omx_app, ["plan", "design auth", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry Run" in result.output


def test_omx_team_dry_run():
    """Test omx team dry run."""
    result = runner.invoke(omx_app, ["team", "parallel tasks", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry Run" in result.output


def test_omx_ultrawork_dry_run():
    """Test omx ultrawork dry run."""
    result = runner.invoke(omx_app, ["ultrawork", "batch tasks", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry Run" in result.output


def test_omx_autopilot_dry_run():
    """Test omx autopilot dry run."""
    result = runner.invoke(omx_app, ["autopilot", "build feature", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry Run" in result.output


def test_omx_ultraqa_dry_run():
    """Test omx ultraqa dry run."""
    result = runner.invoke(omx_app, ["ultraqa", "test website", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry Run" in result.output
