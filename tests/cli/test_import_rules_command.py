"""Tests for vibe import-rules command."""

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestImportRulesCommand:
    """Test suite for import-rules command."""

    def test_import_rules_help(self) -> None:
        """Test import-rules help output."""
        result = runner.invoke(app, ["import-rules", "--help"])
        assert result.exit_code == 0
        assert "Import external legacy rules" in result.stdout

    def test_import_rules_dry_run(self) -> None:
        """Test import-rules --dry-run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rule_file = Path(tmpdir) / "rules.md"
            rule_file.write_text("# Team Rules\n\nBe nice.")

            result = runner.invoke(app, ["import-rules", str(rule_file), "--dry-run"])
            assert result.exit_code == 0
            assert "DRY RUN" in result.stdout
            assert "Be nice" in result.stdout

    def test_import_rules_success(self) -> None:
        """Test successful import to rules target."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rule_file = Path(tmpdir) / "rules.md"
            rule_file.write_text("# Team Rules\n\nBe nice.")

            result = runner.invoke(app, ["import-rules", str(rule_file), "--force"])
            assert result.exit_code == 0
            assert "Import Successful" in result.stdout
            assert "imported-rules.md" in result.stdout

    def test_import_rules_behavior_policies_target(self) -> None:
        """Test import to behavior-policies target."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rule_file = Path(tmpdir) / "rules.md"
            rule_file.write_text("# Behavior\n\nNo yelling.")

            result = runner.invoke(
                app,
                ["import-rules", str(rule_file), "--target", "behavior-policies", "--force"]
            )
            assert result.exit_code == 0
            assert "Import Successful" in result.stdout
            assert "imported.yaml" in result.stdout

    def test_import_rules_exists_no_force(self) -> None:
        """Test import fails when file exists and no --force."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rule_file = Path(tmpdir) / "rules.md"
            rule_file.write_text("# Team Rules")

            # First import creates the file
            runner.invoke(app, ["import-rules", str(rule_file), "--force"])

            # Second import without force should fail
            result = runner.invoke(app, ["import-rules", str(rule_file)])
            assert result.exit_code == 1
            assert "already exists" in result.stdout
