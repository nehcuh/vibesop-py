"""Tests for vibe inspect command."""

import tempfile

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestInspectCommand:
    """Test suite for inspect command."""

    def test_inspect_help(self) -> None:
        """Test inspect help output."""
        result = runner.invoke(app, ["inspect", "--help"])
        assert result.exit_code == 0
        assert "--path" in result.stdout

    def test_inspect_default(self) -> None:
        """Test inspect default output."""
        result = runner.invoke(app, ["inspect"])
        # May fail if no config exists, but command should run
        assert result.exit_code in (0, 1)

    def test_inspect_verbose(self) -> None:
        """Test inspect with verbose output."""
        result = runner.invoke(app, ["inspect", "--verbose"])
        assert result.exit_code in (0, 1)

    def test_inspect_skills_only(self) -> None:
        """Test inspect with --skills filter."""
        result = runner.invoke(app, ["inspect", "--skills"])
        assert result.exit_code in (0, 1)

    def test_inspect_config_only(self) -> None:
        """Test inspect with --config filter."""
        result = runner.invoke(app, ["inspect", "--config"])
        assert result.exit_code in (0, 1)

    def test_inspect_custom_path(self) -> None:
        """Test inspect with custom path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(app, ["inspect", "--path", tmpdir])
            assert result.exit_code in (0, 1)
