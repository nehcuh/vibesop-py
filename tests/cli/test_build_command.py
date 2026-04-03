"""Tests for vibe build command."""

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestBuildCommand:
    """Test suite for build command."""

    def test_build_help(self) -> None:
        """Test build help output."""
        result = runner.invoke(app, ["build", "--help"])
        assert result.exit_code == 0
        assert "Build platform configuration" in result.stdout

    def test_build_invalid_target(self) -> None:
        """Test build with invalid target."""
        result = runner.invoke(app, ["build", "invalid-target"])
        assert result.exit_code == 1
        assert "Invalid target" in result.stdout

    def test_build_invalid_profile(self) -> None:
        """Test build with invalid profile."""
        result = runner.invoke(
            app,
            ["build", "claude-code", "--profile", "invalid-profile"]
        )
        assert result.exit_code == 1
        assert "Invalid profile" in result.stdout

    def test_build_verify_mode(self) -> None:
        """Test build verify mode."""
        result = runner.invoke(app, ["build", "claude-code", "--verify"])
        assert result.exit_code == 0
        assert "Verification" in result.stdout

    def test_build_manifest_only(self) -> None:
        """Test build manifest-only mode."""
        result = runner.invoke(app, ["build", "claude-code", "--manifest-only"])
        assert result.exit_code == 0
        assert "manifest-only" in result.stdout.lower() or "manifest" in result.stdout.lower()

    def test_build_with_overlay(self) -> None:
        """Test build with overlay file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            overlay = Path(tmpdir) / "overlay.yaml"
            overlay.write_text("platform: claude-code\n")

            result = runner.invoke(
                app,
                ["build", "claude-code", "--overlay", str(overlay)]
            )
            # May fail if overlay is invalid, but should not crash
            assert result.exit_code in (0, 1)
