"""Tests for Phase 4 commands (worktree, route-select, route-validate, import-rules)."""

from typer.testing import CliRunner

from vibesop.cli.main import app

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
    """Test suite for route-select command."""

    def test_route_select_help(self) -> None:
        """Test route-select help output."""
        result = runner.invoke(app, ["route-select", "--help"])
        assert result.exit_code == 0
        assert "select" in result.stdout.lower()

    def test_route_select_with_query(self) -> None:
        """Test route-select with query."""
        result = runner.invoke(app, ["route-select", "test query"])
        assert result.exit_code == 0
        assert "test query" in result.stdout.lower() or "test" in result.stdout.lower()


class TestRouteValidateCommand:
    """Test suite for route-validate command."""

    def test_route_validate_help(self) -> None:
        """Test route-validate help output."""
        result = runner.invoke(app, ["route-validate", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.stdout.lower()

    def test_route_validate_default(self) -> None:
        """Test route-validate default."""
        result = runner.invoke(app, ["route-validate"])
        assert result.exit_code == 0

    def test_route_validate_with_pattern(self) -> None:
        """Test route-validate with pattern."""
        result = runner.invoke(app, ["route-validate", "--pattern", "test"])
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
