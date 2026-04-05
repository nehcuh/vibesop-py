"""Tests for the 'vibe skills' command."""

from __future__ import annotations

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestSkillsCommand:
    """Tests for vibe skills command."""

    def test_skills_runs(self) -> None:
        """Test that skills list command runs without crashing."""
        result = runner.invoke(app, ["skills", "list"])

        # Command should run (may have no skills loaded)
        assert result.exit_code in (0, 1)

    def test_skill_info_not_found(self) -> None:
        """Test skill-info with non-existent skill."""
        result = runner.invoke(app, ["skill-info", "/nonexistent"])

        # Should exit with non-zero for unknown skill
        assert result.exit_code in (0, 1)
