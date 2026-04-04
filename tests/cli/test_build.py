"""Tests for the 'vibe build' command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestBuildCommand:
    """Tests for vibe build command."""

    def test_build_claude_code(self, tmp_path: Path) -> None:
        """Test build command for claude-code platform."""
        with patch("vibesop.cli.commands.build.ConfigRenderer") as mock_renderer:
            mock_instance = Mock()
            mock_instance.render.return_value = Mock(
                files_written=[
                    tmp_path / "CLAUDE.md",
                    tmp_path / "rules" / "behaviors.md",
                ],
                total_files=2,
                total_size=1024,
            )
            mock_renderer.return_value = mock_instance

            result = runner.invoke(app, ["build", "claude-code", "--output", str(tmp_path)])

            assert result.exit_code == 0

    def test_build_opencode(self, tmp_path: Path) -> None:
        """Test build command for opencode platform."""
        with patch("vibesop.cli.commands.build.ConfigRenderer") as mock_renderer:
            mock_instance = Mock()
            mock_instance.render.return_value = Mock(
                files_written=[tmp_path / "config.yaml"],
                total_files=1,
                total_size=512,
            )
            mock_renderer.return_value = mock_instance

            result = runner.invoke(app, ["build", "opencode", "--output", str(tmp_path)])

            assert result.exit_code == 0

    def test_build_verify_only(self) -> None:
        """Test build command with --verify flag."""
        with patch("vibesop.cli.commands.build.ConfigRenderer") as mock_renderer:
            mock_instance = Mock()
            mock_instance.verify.return_value = Mock(is_valid=True, errors=[])
            mock_renderer.return_value = mock_instance

            result = runner.invoke(app, ["build", "claude-code", "--verify"])

            assert result.exit_code == 0

    def test_build_invalid_platform(self) -> None:
        """Test build command with invalid platform."""
        result = runner.invoke(app, ["build", "nonexistent-platform"])

        assert result.exit_code != 0
