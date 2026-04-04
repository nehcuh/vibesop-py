"""Tests for the 'vibe skills' command."""

from __future__ import annotations

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestSkillsCommand:
    """Tests for vibe skills command."""

    def test_skills_lists_available(self) -> None:
        """Test that skills command lists available skills."""
        with patch("vibesop.cli.main.SkillManager") as mock_manager:
            mock_instance = Mock()
            mock_instance.list_skills.return_value = [
                Mock(id="/review", name="Code Review", description="Review code"),
                Mock(id="/debug", name="Debug", description="Debug issues"),
            ]
            mock_manager.return_value = mock_instance

            result = runner.invoke(app, ["skills"])

            assert result.exit_code == 0
            assert "review" in result.stdout.lower()

    def test_skill_info(self) -> None:
        """Test skill-info command shows details."""
        with patch("vibesop.cli.main.SkillManager") as mock_manager:
            mock_instance = Mock()
            mock_instance.get_skill.return_value = Mock(
                id="/review",
                name="Code Review",
                description="Review code for issues",
                trigger_when=["review", "audit"],
            )
            mock_manager.return_value = mock_instance

            result = runner.invoke(app, ["skill-info", "/review"])

            assert result.exit_code == 0
            assert "Code Review" in result.stdout
