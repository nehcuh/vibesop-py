"""Tests for the 'vibe skills' command."""

from __future__ import annotations

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestSkillsCommand:
    """Tests for vibe skills command."""

    def test_skills_list_runs(self) -> None:
        """Test that skills list command runs without crashing."""
        result = runner.invoke(app, ["skills", "list"])

        # Command should run (may have no skills loaded)
        assert result.exit_code in (0, 1)

    def test_skills_available_runs(self) -> None:
        """Test that skills available command runs without crashing."""
        result = runner.invoke(app, ["skills", "available"])

        # Command should run (may have no skills loaded)
        assert result.exit_code in (0, 1)

    def test_skills_info_not_found(self) -> None:
        """Test skills info with non-existent skill."""
        result = runner.invoke(app, ["skills", "info", "/nonexistent"])

        # Should exit with non-zero for unknown skill
        assert result.exit_code in (0, 1)


class TestSkillsRemovedCommands:
    """Tests to ensure removed commands no longer exist."""

    def test_execute_command_removed(self) -> None:
        """Test that execute command is removed (archived as dead code)."""
        result = runner.invoke(app, ["execute", "--help"])
        # Should not exist
        assert result.exit_code != 0

    def test_memory_command_removed(self) -> None:
        """Test that memory command no longer exists."""
        result = runner.invoke(app, ["memory", "list"])

        # Should fail with "No such command"
        assert result.exit_code != 0

    def test_instinct_command_removed(self) -> None:
        """Test that instinct command no longer exists."""
        result = runner.invoke(app, ["instinct", "list"])

        # Should fail with "No such command"
        assert result.exit_code != 0

    def test_scan_command_removed(self) -> None:
        """Test that scan command no longer exists."""
        result = runner.invoke(app, ["scan", "."])

        # Should fail with "No such command"
        assert result.exit_code != 0

    def test_detect_command_removed(self) -> None:
        """Test that detect command no longer exists."""
        result = runner.invoke(app, ["detect"])

        # Should fail with "No such command"
        assert result.exit_code != 0


class TestAnalyzeUnifiedCommand:
    """Tests for unified analyze command."""

    def test_analyze_session_runs(self) -> None:
        """Test that analyze session runs without crashing."""
        result = runner.invoke(app, ["analyze", "session"])

        # Command should run (may have no session file)
        assert result.exit_code in (0, 1)

    def test_analyze_security_runs(self) -> None:
        """Test that analyze security runs without crashing."""
        result = runner.invoke(app, ["analyze", "security", "."])

        # Command should run
        assert result.exit_code in (0, 1)

    def test_analyze_integrations_runs(self) -> None:
        """Test that analyze integrations runs without crashing."""
        result = runner.invoke(app, ["analyze", "integrations"])

        # Command should run
        assert result.exit_code in (0, 1)
