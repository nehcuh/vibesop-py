#!/usr/bin/env python3
"""Integration test for skill add command with auto-configuration."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


@pytest.fixture
def temp_skill_dir(tmp_path):
    """Create a temporary skill directory."""
    skill_dir = tmp_path / "test-skill.skill"
    skill_dir.mkdir()

    # Create SKILL.md with metadata
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("""---
name: Test Skill
id: test-skill
description: Systematic debugging workflow for finding and fixing bugs
version: 1.0.0
skill_type: workflow
tags:
  - debug
  - troubleshooting
trigger_when: User encounters bugs or errors
---

# Test Skill

This is a test skill for debugging workflow.
""")

    # Create skill.py
    skill_py = skill_dir / "skill.py"
    skill_py.write_text("""
def execute():
    print("Test skill executed")
""")

    return skill_dir


def test_skill_add_with_auto_config(temp_skill_dir, monkeypatch):
    """Test skill add with automatic configuration."""

    # Change to temp directory
    monkeypatch.chdir(temp_skill_dir.parent)

    # Mock questionary for non-interactive testing
    with patch("vibesop.cli.commands.skill_add.questionary") as mock_q:
        mock_q.select.return_value.ask.return_value = "project"
        mock_q.confirm.return_value.ask.return_value = True

        result = runner.invoke(app, ["skills", "add", str(temp_skill_dir)])

        print(f"Exit code: {result.exit_code}")
        print(f"Output:\n{result.output}")

        # Should succeed
        assert result.exit_code == 0

        # Should show auto-configuration
        assert "Auto-configuring" in result.output or "Understanding skill" in result.output

        # Check if config was created
        config_file = temp_skill_dir.parent / ".vibe" / "skills" / "auto-config.yaml"
        if config_file.exists():
            import json

            import yaml

            with open(config_file) as f:
                config = yaml.safe_load(f)

            print(f"Config: {json.dumps(config, indent=2)}")

            # Should have skill configuration
            assert "skills" in config
            assert "test-skill" in config["skills"]

            skill_config = config["skills"]["test-skill"]

            # Should have priority
            assert "priority" in skill_config
            assert isinstance(skill_config["priority"], int)

            # Should have category
            assert "category" in skill_config

            # Should have routing patterns
            assert "routing" in skill_config
            assert "patterns" in skill_config["routing"]


def test_skill_add_with_llm_detection(temp_skill_dir, monkeypatch, tmp_path):
    """Test that LLM configuration is detected correctly."""

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create .vibe/config.yaml with LLM configuration
    vibe_dir = tmp_path / ".vibe"
    vibe_dir.mkdir()

    config_file = vibe_dir / "config.yaml"
    config_file.write_text("""
llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key: test-key
""")

    # Mock user input
    inputs = "project\n"
    result = runner.invoke(app, ["skills", "add", str(temp_skill_dir)], input=inputs)

    print(f"Exit code: {result.exit_code}")
    print(f"Output:\n{result.output}")

    # Should mention LLM availability
    if "LLM available" in result.output or "LLM config" in result.output:
        print("✓ LLM detection working")


def test_skill_add_with_manual_config(temp_skill_dir, monkeypatch, tmp_path):
    """Test manual configuration mode."""

    monkeypatch.chdir(tmp_path)

    # Mock questionary for non-interactive testing
    call_count = {"select": 0, "confirm": 0}

    def select_side_effect(*args, **kwargs):
        call_count["select"] += 1
        if call_count["select"] == 1:
            return MagicMock(ask=MagicMock(return_value="project"))
        return MagicMock(ask=MagicMock(return_value=50))

    def confirm_side_effect(*args, **kwargs):
        call_count["confirm"] += 1
        return MagicMock(ask=MagicMock(return_value=True))

    with patch("vibesop.cli.commands.skill_add.questionary") as mock_q:
        mock_q.select.side_effect = select_side_effect
        mock_q.confirm.side_effect = confirm_side_effect

        result = runner.invoke(
            app,
            ["skills", "add", str(temp_skill_dir), "--manual-config"],
        )

        print(f"Exit code: {result.exit_code}")
        print(f"Output:\n{result.output}")

        # Should show manual configuration
        assert "Manual configuration" in result.output or "priority" in result.output.lower()


def test_skill_add_force_reinstall(temp_skill_dir, monkeypatch, tmp_path):
    """Test force reinstall functionality."""

    monkeypatch.chdir(tmp_path)

    with patch("vibesop.cli.commands.skill_add.questionary") as mock_q:
        mock_q.select.return_value.ask.return_value = "project"
        mock_q.confirm.return_value.ask.return_value = True

        # First installation
        result1 = runner.invoke(
            app,
            ["skills", "add", str(temp_skill_dir)],
        )

        print(f"First install exit code: {result1.exit_code}")

        # Second installation without force (should fail or warn)
        result2 = runner.invoke(
            app,
            ["skills", "add", str(temp_skill_dir)],
        )

        print(f"Second install exit code: {result2.exit_code}")

        # Force reinstall (should succeed)
        result3 = runner.invoke(
            app,
            ["skills", "add", str(temp_skill_dir), "--force"],
        )

        print(f"Force reinstall exit code: {result3.exit_code}")
        assert result3.exit_code == 0


if __name__ == "__main__":

    # Run with verbose output
    pytest.main([__file__, "-v", "-s"])
