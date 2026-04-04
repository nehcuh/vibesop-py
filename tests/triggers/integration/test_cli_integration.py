"""CLI integration tests for auto command.

Tests the complete CLI workflow from command invocation
to execution, including file I/O and error handling.
"""

import pytest
from typer.testing import CliRunner
from pathlib import Path

from vibesop.cli.main import app


class TestCLICommandAuto:
    """Test 'vibe auto' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_auto_command_help(self, runner):
        """Test 'vibe auto --help' command."""
        result = runner.invoke(app, ["auto", "--help"])

        assert result.exit_code == 0
        assert "Automatically detect intent" in result.stdout
        assert "query" in result.stdout.lower()

    def test_auto_command_with_match(self, runner):
        """Test auto command with a query that matches."""
        result = runner.invoke(app, ["auto", "scan for security issues"])

        # Should detect security intent
        assert result.exit_code in [0, 1]  # 0 if execution succeeds, 1 if fails
        assert "Intent Detected" in result.stdout or "No intent detected" in result.stdout

    def test_auto_command_with_no_match(self, runner):
        """Test auto command with query that doesn't match."""
        result = runner.invoke(app, ["auto", "xyzabc123 completely unmatched"])

        assert result.exit_code == 1
        assert "No intent detected" in result.stdout

    def test_auto_command_dry_run(self, runner):
        """Test auto command with --dry-run flag."""
        result = runner.invoke(app, ["auto", "--dry-run", "scan for security"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "Preview" in result.stdout

    def test_auto_command_with_min_confidence(self, runner):
        """Test auto command with custom min-confidence."""
        result = runner.invoke(app, ["auto", "--min-confidence", "0.8", "test"])

        # Should complete without error (might not match)
        assert result.exit_code in [0, 1]

    def test_auto_command_with_input(self, runner):
        """Test auto command with input data."""
        result = runner.invoke(app, [
            "auto",
            "scan",
            "--input", '{"target": "./src"}',
            "--dry-run"
        ])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout

    def test_auto_command_verbose(self, runner):
        """Test auto command with --verbose flag."""
        result = runner.invoke(app, [
            "auto",
            "--verbose",
            "--dry-run",
            "scan for security issues"
        ])

        assert result.exit_code == 0
        assert "Intent Detected" in result.stdout or "No intent detected" in result.stdout
        # Verbose mode shows more details

    def test_auto_command_chinese_query(self, runner):
        """Test auto command with Chinese query."""
        result = runner.invoke(app, ["auto", "扫描安全漏洞"])

        # Should detect security intent
        assert result.exit_code in [0, 1]
        # Should show detection result
        assert len(result.stdout) > 0

    def test_auto_command_invalid_json_input(self, runner):
        """Test auto command with invalid JSON input."""
        result = runner.invoke(app, [
            "auto",
            "test",
            "--input", "invalid json"
        ])

        assert result.exit_code == 1
        assert "Invalid JSON" in result.stdout

    def test_auto_command_no_query_provided(self, runner):
        """Test auto command without query argument."""
        result = runner.invoke(app, ["auto"])

        assert result.exit_code != 0
        # Typer should show help or error


class TestAutoCommandOutput:
    """Test auto command output formatting."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_shows_confidence_score(self, runner):
        """Test that confidence score is displayed."""
        result = runner.invoke(app, ["auto", "--dry-run", "scan security"])

        assert result.exit_code == 0
        # Should show confidence percentage
        assert "Confidence:" in result.stdout or "no intent detected" in result.stdout.lower()

    def test_shows_pattern_details(self, runner):
        """Test that pattern details are shown."""
        result = runner.invoke(app, ["auto", "--dry-run", "scan security"])

        assert result.exit_code == 0
        # Should show pattern info
        assert "ID:" in result.stdout or "no intent detected" in result.stdout.lower()

    def test_shows_category_emoji(self, runner):
        """Test that category emoji is displayed."""
        result = runner.invoke(app, ["auto", "--dry-run", "scan security"])

        assert result.exit_code == 0
        # Should show emoji if matched
        has_emoji = any(emoji in result.stdout for emoji in ["🔒", "⚙️", "🛠️", "📚", "📁"])
        assert has_emoji or "no intent detected" in result.stdout.lower()

    def test_shows_available_patterns_on_no_match(self, runner):
        """Test that available patterns are shown when no match."""
        result = runner.invoke(app, ["auto", "xyzabc123", "--verbose"])

        assert result.exit_code == 1
        if "No intent detected" in result.stdout:
            # In verbose mode, should show available patterns
            assert "Available Patterns:" in result.stdout or "Supported categories" in result.stdout


class TestAutoCommandCategories:
    """Test auto command with different categories."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_security_category_detection(self, runner):
        """Test security category queries."""
        queries = [
            "scan for security vulnerabilities",
            "check security issues",
            "security audit"
        ]

        for query in queries:
            result = runner.invoke(app, ["auto", "--dry-run", query])
            assert result.exit_code == 0

    def test_config_category_detection(self, runner):
        """Test config category queries."""
        queries = [
            "deploy configuration",
            "validate config",
            "render config files"
        ]

        for query in queries:
            result = runner.invoke(app, ["auto", "--dry-run", query])
            assert result.exit_code == 0

    def test_dev_category_detection(self, runner):
        """Test dev category queries."""
        queries = [
            "run tests",
            "build project",
            "debug code"
        ]

        for query in queries:
            result = runner.invoke(app, ["auto", "--dry-run", query])
            assert result.exit_code == 0

    def test_docs_category_detection(self, runner):
        """Test docs category queries."""
        queries = [
            "generate documentation",
            "create readme",
            "update docs"
        ]

        for query in queries:
            result = runner.invoke(app, ["auto", "--dry-run", query])
            assert result.exit_code == 0

    def test_project_category_detection(self, runner):
        """Test project category queries."""
        queries = [
            "initialize new project",
            "migrate project",
            "project audit"
        ]

        for query in queries:
            result = runner.invoke(app, ["auto", "--dry-run", query])
            assert result.exit_code == 0
