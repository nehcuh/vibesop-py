"""Tests for vibe deploy command."""

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestDeployCommand:
    """Test suite for deploy command."""

    def test_deploy_help(self) -> None:
        """Test deploy help output."""
        result = runner.invoke(app, ["deploy", "--help"])
        assert result.exit_code == 0
        assert "Deploy configuration" in result.stdout

    def test_deploy_dry_run(self) -> None:
        """Test deploy dry-run mode."""
        result = runner.invoke(app, ["deploy", "claude-code", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "Preview" in result.stdout

    def test_deploy_missing_source(self) -> None:
        """Test deploy with missing source directory."""
        result = runner.invoke(
            app,
            ["deploy", "claude-code", "--source", "/nonexistent/path"]
        )
        # Exit code 1 or 2 is acceptable (error or usage error)
        assert result.exit_code in (1, 2)

    def test_deploy_with_custom_source(self) -> None:
        """Test deploy with custom source directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            (source / "test.txt").write_text("test")

            result = runner.invoke(
                app,
                ["deploy", "claude-code", "--source", str(source), "--dry-run"]
            )
            assert result.exit_code == 0
            assert str(source) in result.stdout
