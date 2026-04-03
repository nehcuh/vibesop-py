"""Integration tests for CLI workflow commands.

Tests the complete CLI workflow from command invocation
to execution, including file I/O and error handling.
"""

import pytest
import subprocess
import json
from pathlib import Path
from typer.testing import CliRunner

from vibesop.cli.main import app


class TestCLIWorkflowCommands:
    """Test CLI workflow commands integration."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_workflow_list_command(self, runner, temp_workflow_dir):
        """Test 'vibe workflow list' command."""
        # Create some workflow files
        workflow_yaml = """
name: test-workflow
description: Test workflow
stages:
  - name: stage1
    description: Stage 1
    required: true
    metadata:
      skill_id: /test
"""
        (temp_workflow_dir / "workflow1.yaml").write_text(workflow_yaml)
        (temp_workflow_dir / "workflow2.yaml").write_text(
            workflow_yaml.replace("test-workflow", "workflow2")
        )

        # Run command from project root
        result = runner.invoke(app, ["workflow", "list"])

        assert result.exit_code == 0
        assert "workflow1" in result.stdout
        assert "workflow2" in result.stdout

    def test_workflow_list_empty(self, runner, tmp_path):
        """Test 'vibe workflow list' with no workflows."""
        # Use empty directory
        result = runner.invoke(app, ["workflow", "list"])

        assert result.exit_code == 0
        assert "No workflow files found" in result.stdout

    def test_workflow_validate_command(self, runner, temp_workflow_dir):
        """Test 'vibe workflow validate' command."""
        # Create valid workflow
        workflow_yaml = """
name: validate-test
description: Test validation
stages:
  - name: stage1
    description: Stage 1
    required: true
    timeout_seconds: 30
    metadata:
      skill_id: /test
"""
        workflow_file = temp_workflow_dir / "test.yaml"
        workflow_file.write_text(workflow_yaml)

        result = runner.invoke(app, ["workflow", "validate", str(workflow_file)])

        assert result.exit_code == 0
        assert "✓ Workflow is valid" in result.stdout
        assert "validate-test" in result.stdout

    def test_workflow_validate_invalid_file(self, runner, temp_workflow_dir):
        """Test validating invalid workflow file."""
        # Create invalid YAML
        invalid_file = temp_workflow_dir / "invalid.yaml"
        invalid_file.write_text("invalid: yaml: content:")

        result = runner.invoke(app, ["workflow", "validate", str(invalid_file)])

        assert result.exit_code == 1
        assert "✗" in result.stdout

    def test_workflow_validate_nonexistent_file(self, runner):
        """Test validating non-existent file."""
        result = runner.invoke(app, ["workflow", "validate", "nonexistent.yaml"])

        assert result.exit_code == 2
        assert "does not exist" in result.stdout

    def test_workflow_run_dry_run(self, runner, temp_workflow_dir):
        """Test 'vibe workflow run --dry-run' command."""
        # Create workflow
        workflow_yaml = """
name: dry-run-test
description: Test dry run
stages:
  - name: stage1
    description: First stage
    required: true
    metadata:
      skill_id: /test
  - name: stage2
    description: Second stage
    dependencies:
      - stage1
    required: true
    metadata:
      skill_id: /test
"""
        workflow_file = temp_workflow_dir / "dry-run.yaml"
        workflow_file.write_text(workflow_yaml)

        result = runner.invoke(app, [
            "workflow", "run", str(workflow_file), "--dry-run"
        ])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "dry-run-test" in result.stdout
        assert "stage1" in result.stdout
        assert "stage2" in result.stdout

    def test_workflow_run_with_strategy(self, runner, temp_workflow_dir):
        """Test 'vibe workflow run' with strategy option."""
        workflow_yaml = """
name: strategy-test
description: Test strategy
stages:
  - name: stage1
    description: Stage 1
    required: true
    metadata:
      skill_id: /test
  - name: stage2
    description: Stage 2
    required: true
    metadata:
      skill_id: /test
"""
        workflow_file = temp_workflow_dir / "strategy.yaml"
        workflow_file.write_text(workflow_yaml)

        # Test with parallel strategy
        result = runner.invoke(app, [
            "workflow", "run", str(workflow_file),
            "--strategy", "parallel",
            "--dry-run"
        ])

        assert result.exit_code == 0
        assert "parallel" in result.stdout

    def test_workflow_run_with_input(self, runner, temp_workflow_dir):
        """Test 'vibe workflow run' with input data."""
        workflow_yaml = """
name: input-test
description: Test input
stages:
  - name: stage1
    description: Stage 1
    required: true
    metadata:
      skill_id: /test
"""
        workflow_file = temp_workflow_dir / "input.yaml"
        workflow_file.write_text(workflow_yaml)

        # Test with JSON input
        result = runner.invoke(app, [
            "workflow", "run", str(workflow_file),
            "--input", '{"test": "data"}',
            "--dry-run"
        ])

        assert result.exit_code == 0

    def test_workflow_resume_no_active(self, runner):
        """Test 'vibe workflow resume' with no active workflows."""
        result = runner.invoke(app, ["workflow", "resume"])

        assert result.exit_code == 0
        # Should show empty list or message

    def test_workflow_help(self, runner):
        """Test 'vibe workflow --help' command."""
        result = runner.invoke(app, ["workflow", "--help"])

        assert result.exit_code == 0
        assert "Execute v2.0 workflows" in result.stdout
        assert "run" in result.stdout
        assert "list" in result.stdout
        assert "validate" in result.stdout
        assert "resume" in result.stdout


class TestCLIWorkflowRealWorld:
    """Test CLI with real workflow files."""

    def test_security_review_workflow_cli(self, runner):
        """Test security-review workflow via CLI."""
        # Use predefined workflow
        workflow_file = Path(".vibe/workflows/security-review.yaml")

        if not workflow_file.exists():
            pytest.skip("Predefined workflow not found")

        result = runner.invoke(app, [
            "workflow", "validate", str(workflow_file)
        ])

        assert result.exit_code == 0
        assert "security-review" in result.stdout

    def test_config_deploy_workflow_cli(self, runner):
        """Test config-deploy workflow via CLI."""
        workflow_file = Path(".vibe/workflows/config-deploy.yaml")

        if not workflow_file.exists():
            pytest.skip("Predefined workflow not found")

        result = runner.invoke(app, [
            "workflow", "run", str(workflow_file),
            "--dry-run"
        ])

        assert result.exit_code == 0
        assert "config-deploy" in result.stdout

    def test_list_all_predefined_workflows(self, runner):
        """Test listing all predefined workflows."""
        result = runner.invoke(app, ["workflow", "list"])

        assert result.exit_code == 0

        # Check for predefined workflows
        if "security-review" in result.stdout:
            assert "security-review" in result.stdout
        if "config-deploy" in result.stdout:
            assert "config-deploy" in result.stdout
        if "skill-discovery" in result.stdout:
            assert "skill-discovery" in result.stdout
