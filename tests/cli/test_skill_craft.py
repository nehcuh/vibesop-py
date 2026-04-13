"""Tests for vibe skill-craft command."""

import json
from pathlib import Path

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestSkillCraftCommand:
    """Test suite for skill-craft command."""

    def test_unknown_action(self) -> None:
        """Test skill-craft with invalid action."""
        result = runner.invoke(app, ["skill-craft", "invalid"])
        assert result.exit_code == 1
        assert "Unknown action" in result.stdout

    def test_create_no_name(self) -> None:
        """Test skill-craft create without --name exits with hint."""
        result = runner.invoke(app, ["skill-craft", "create"])
        assert result.exit_code == 0
        assert "Skipping interactive mode" in result.stdout

    def test_create_with_name(self, monkeypatch, tmp_path) -> None:
        """Test skill-craft create with --name creates file."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["skill-craft", "create", "--name", "My Skill", "--description", "Does things"])
        assert result.exit_code == 0
        assert "Skill created" in result.stdout
        assert (tmp_path / ".vibe" / "skills" / "my-skill.md").exists()

    def test_create_with_output(self, monkeypatch, tmp_path) -> None:
        """Test skill-craft create with custom output directory."""
        monkeypatch.chdir(tmp_path)
        out_dir = tmp_path / "custom"
        result = runner.invoke(app, ["skill-craft", "create", "--name", "Test", "--output", str(out_dir)])
        assert result.exit_code == 0
        assert (out_dir / "test.md").exists()

    def test_templates(self) -> None:
        """Test skill-craft templates lists templates."""
        result = runner.invoke(app, ["skill-craft", "templates"])
        assert result.exit_code == 0
        assert "debug" in result.stdout
        assert "review - Code review" in result.stdout

    def test_from_missing_source(self) -> None:
        """Test skill-craft from without source file."""
        result = runner.invoke(app, ["skill-craft", "from"])
        assert result.exit_code == 1
        assert "Source file required" in result.stdout

    def test_from_valid_json(self, monkeypatch, tmp_path) -> None:
        """Test skill-craft from with valid session JSON."""
        monkeypatch.chdir(tmp_path)
        session_file = tmp_path / "session.json"
        session_file.write_text(json.dumps({"messages": [{"role": "user", "content": "review my code"}]}))

        result = runner.invoke(app, ["skill-craft", "from", str(session_file)])
        assert result.exit_code == 0
        assert "Found 1 patterns" in result.stdout
        assert "Code Review" in result.stdout

    def test_from_no_patterns(self, monkeypatch, tmp_path) -> None:
        """Test skill-craft from with empty messages."""
        monkeypatch.chdir(tmp_path)
        session_file = tmp_path / "session.json"
        session_file.write_text(json.dumps({"messages": []}))

        result = runner.invoke(app, ["skill-craft", "from", str(session_file)])
        assert result.exit_code == 0
        assert "No clear patterns detected" in result.stdout

    def test_from_invalid_json(self, monkeypatch, tmp_path) -> None:
        """Test skill-craft from with invalid JSON."""
        monkeypatch.chdir(tmp_path)
        session_file = tmp_path / "session.json"
        session_file.write_text("not json")

        result = runner.invoke(app, ["skill-craft", "from", str(session_file)])
        assert result.exit_code == 1
        assert "Invalid JSON file" in result.stdout
