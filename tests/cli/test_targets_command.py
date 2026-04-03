"""Tests for vibe targets command."""

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestTargetsCommand:
    """Test suite for targets command."""

    def test_targets_help(self) -> None:
        """Test targets help output."""
        result = runner.invoke(app, ["targets", "--help"])
        assert result.exit_code == 0
        assert "List available platform targets" in result.stdout

    def test_targets_default(self) -> None:
        """Test targets default output."""
        result = runner.invoke(app, ["targets"])
        assert result.exit_code == 0
        assert "Available Targets" in result.stdout or "targets" in result.stdout.lower()

    def test_targets_verbose(self) -> None:
        """Test targets with verbose output."""
        result = runner.invoke(app, ["targets", "--verbose"])
        assert result.exit_code == 0

    def test_targets_installed_only(self) -> None:
        """Test targets with --installed filter."""
        result = runner.invoke(app, ["targets", "--installed"])
        assert result.exit_code == 0

    def test_targets_json(self) -> None:
        """Test targets JSON output."""
        result = runner.invoke(app, ["targets", "--json"])
        assert result.exit_code == 0
        # Should contain JSON output
        assert "{" in result.stdout or "[]" in result.stdout or "error" in result.stdout.lower()
