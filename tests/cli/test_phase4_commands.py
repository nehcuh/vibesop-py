"""Tests for Phase 4 commands (route validation, import-rules).

Note:
- The worktree command has been removed in v4.1.0.
- route-select was removed in v4.0.0 (use 'vibe route' instead).
- route-cmd validate is now 'vibe route --validate'.
"""

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestRouteSelectCommand:
    """Test suite for route-select command (deprecated)."""

    def test_route_select_removed(self) -> None:
        """Test that route-select command was removed."""
        result = runner.invoke(app, ["route-cmd", "select", "--help"])
        # Command should not exist anymore (exit code 2 for typer usage error)
        assert result.exit_code != 0


class TestRouteValidateCommand:
    """Test suite for route validation (now via --validate flag)."""

    def test_route_validate_help(self) -> None:
        """Test route --validate help output."""
        result = runner.invoke(app, ["route", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.stdout.lower()

    def test_route_validate_default(self) -> None:
        """Test route --validate with query."""
        result = runner.invoke(app, ["route", "test query", "--validate"])
        assert result.exit_code == 0

    def test_route_validate_short_flag(self) -> None:
        """Test route --validate with short flag."""
        result = runner.invoke(app, ["route", "test", "-V"])
        assert result.exit_code == 0

    def test_route_explain_flag(self) -> None:
        """Test route --explain shows decision report."""
        result = runner.invoke(app, ["route", "test query", "--explain"])
        assert result.exit_code == 0
        assert "Routing Decision Report" in result.stdout

    def test_route_explain_short_flag(self) -> None:
        """Test route --explain with short flag."""
        result = runner.invoke(app, ["route", "test", "-e"])
        assert result.exit_code == 0
        assert "Routing Decision Report" in result.stdout


class TestRouteSlashCommands:
    """Test suite for slash command handling in vibe route."""

    def test_route_slash_help(self) -> None:
        """Test /vibe-help executed via vibe route."""
        result = runner.invoke(app, ["route", "/vibe-help"])
        assert result.exit_code == 0
        assert "/vibe-route" in result.stdout
        assert "/vibe-install" in result.stdout

    def test_route_slash_list(self) -> None:
        """Test /vibe-list executed via vibe route."""
        result = runner.invoke(app, ["route", "/vibe-list"])
        assert result.exit_code == 0
        assert "Installed Skills" in result.stdout or "No installed skills" in result.stdout

    def test_route_slash_unknown(self) -> None:
        """Test unknown /vibe-* command returns error."""
        result = runner.invoke(app, ["route", "/vibe-unknown"])
        assert result.exit_code == 1
        assert "Unknown command" in result.stdout

    def test_route_slash_help_json(self) -> None:
        """Test /vibe-help with --json output."""
        result = runner.invoke(app, ["route", "/vibe-help", "--json"])
        assert result.exit_code == 0
        assert '"success"' in result.stdout
        assert '"message"' in result.stdout


class TestImportRulesCommand:
    """Test suite for import-rules command."""

    def test_import_rules_help(self) -> None:
        """Test import-rules help output."""
        result = runner.invoke(app, ["import-rules", "--help"])
        assert result.exit_code == 0
        assert "import" in result.stdout.lower()

    def test_import_rules_no_file(self) -> None:
        """Test import-rules without file."""
        result = runner.invoke(app, ["import-rules"])
        assert result.exit_code != 0  # Requires file argument
