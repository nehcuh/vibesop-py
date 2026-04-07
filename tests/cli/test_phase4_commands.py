"""Tests for Phase 4 commands (worktree, route validation, import-rules).

Note:
- The worktree command is deprecated and moved to legacy.
- route-select was removed in v4.0.0 (use 'vibe route' instead).
- route-cmd validate is now 'vibe route --validate'.

Tests require VIBESOP_ENABLE_LEGACY=1 to run legacy command tests.
"""

import os

from typer.testing import CliRunner

from vibesop.cli.main import app

# Enable legacy commands for testing
os.environ["VIBESOP_ENABLE_LEGACY"] = "1"

runner = CliRunner()


class TestWorktreeCommand:
    """Test suite for worktree command."""

    def test_worktree_help(self) -> None:
        """Test worktree help output."""
        result = runner.invoke(app, ["worktree", "--help"])
        assert result.exit_code == 0
        assert "worktree" in result.stdout.lower()

    def test_worktree_list(self) -> None:
        """Test worktree list action."""
        result = runner.invoke(app, ["worktree", "list"])
        assert result.exit_code == 0  # May fail if no git, but command runs


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
