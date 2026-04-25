"""End-to-end tests for Quick Commands (CLI --slash flag)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestQuickCommandsE2E:
    """Test Quick Commands through the CLI."""

    def test_vibe_help_quick_command(self) -> None:
        """Test /vibe-help command."""
        result = runner.invoke(app, ["route", "--slash", "/vibe-help"])

        assert result.exit_code == 0
        # The output should contain the help text for quick commands
        assert "Slash Commands" in result.stdout or "Quick Commands" in result.stdout
        assert "/vibe-route" in result.stdout
        assert "/vibe-install" in result.stdout

    def test_vibe_list_json_quick_command(self) -> None:
        """Test /vibe-list command with --json flag."""
        # Note: --json flag applies to the overall output formatting
        result = runner.invoke(app, ["route", "--slash", "--json", "/vibe-list"])

        assert result.exit_code == 0
        # Should be a valid JSON output. Note: we might need to handle raw newlines
        import re
        clean_json = re.sub(r'[\x00-\x1f]', '', result.stdout)
        data = json.loads(clean_json)
        assert "message" in data
        assert "Installed Skills" in data["message"]

    def test_vibe_analyze_quick_command(self) -> None:
        """Test /vibe-analyze command."""
        result = runner.invoke(app, ["route", "--slash", "/vibe-analyze"])

        assert result.exit_code == 0
        assert "Project type" in result.stdout
        assert "Tech stack" in result.stdout

    def test_invalid_quick_command(self) -> None:
        """Test an invalid quick command."""
        result = runner.invoke(app, ["route", "--slash", "/vibe-unknown"])

        # Fails with 1
        assert result.exit_code == 1
        assert "Unknown command:" in result.stdout

    def test_slash_flag_with_normal_query(self) -> None:
        """Test --slash flag with a non-slash query (should return error)."""
        result = runner.invoke(
            app,
            ["route", "--slash", "--yes", "--json", "help me debug this issue"],
        )

        assert result.exit_code == 1
        assert "must start with /vibe-" in result.stdout
