"""Tests for vibe quickstart command."""

from unittest.mock import MagicMock

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestQuickstartCommand:
    """Test suite for quickstart command."""

    def test_quickstart_help(self) -> None:
        """Test quickstart help output."""
        result = runner.invoke(app, ["quickstart", "--help"])
        assert result.exit_code == 0
        assert "Run interactive setup wizard" in result.stdout

    def test_quickstart_force_success(self, monkeypatch) -> None:
        """Test quickstart --force with successful runner."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = {
            "success": True,
            "steps_completed": ["init", "config"],
        }
        monkeypatch.setattr(
            "vibesop.cli.commands.quickstart.QuickstartRunner",
            lambda: mock_runner,
        )

        result = runner.invoke(app, ["quickstart", "--force"])
        assert result.exit_code == 0
        assert "Quickstart complete" in result.stdout
        assert "init" in result.stdout

    def test_quickstart_force_failure(self, monkeypatch) -> None:
        """Test quickstart --force with failed runner."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = {
            "success": False,
            "errors": ["config missing"],
        }
        monkeypatch.setattr(
            "vibesop.cli.commands.quickstart.QuickstartRunner",
            lambda: mock_runner,
        )

        result = runner.invoke(app, ["quickstart", "--force"])
        assert result.exit_code == 1
        assert "Quickstart failed" in result.stdout
        assert "config missing" in result.stdout

    def test_quickstart_interactive_success(self, monkeypatch) -> None:
        """Test quickstart interactive mode with successful runner."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = {"success": True}
        monkeypatch.setattr(
            "vibesop.cli.commands.quickstart.QuickstartRunner",
            lambda: mock_runner,
        )

        result = runner.invoke(app, ["quickstart"])
        assert result.exit_code == 0
        assert "Setup complete" in result.stdout
        assert "Welcome to VibeSOP" in result.stdout

    def test_quickstart_interactive_failure(self, monkeypatch) -> None:
        """Test quickstart interactive mode with failed runner."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = {"success": False}
        monkeypatch.setattr(
            "vibesop.cli.commands.quickstart.QuickstartRunner",
            lambda: mock_runner,
        )

        result = runner.invoke(app, ["quickstart"])
        assert result.exit_code == 1
        assert "Setup failed" in result.stdout
