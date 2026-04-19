"""Tests for ExternalSkillExecutor."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from vibesop.core.exceptions import SkillNotFoundError
from vibesop.core.skills.base import SkillDefinition
from vibesop.core.skills.executor import (
    ExternalSkillExecutor,
    SecurityViolationError,
    SkillExecutionError,
    SkillResult,
)
from vibesop.core.skills.workflow import (
    ExecutionContext,
    StepType,
    Workflow,
    WorkflowStep,
)

# Get project root for tests
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()


class TestSkillResult:
    """Test SkillResult model."""

    def test_to_dict_success(self) -> None:
        """Test converting successful result to dict."""
        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test workflow",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Test step",
                    instruction="Do something",
                )
            ],
        )

        result = SkillResult(
            success=True,
            skill_id="test",
            workflow=workflow,
            output="Success",
            execution_time=100.0,
        )

        data = result.to_dict()

        assert data["success"] is True
        assert data["skill_id"] == "test"
        assert data["workflow"]["skill_id"] == "test"
        assert data["output"] == "Success"
        assert data["error"] is None
        assert data["execution_time_ms"] == 100.0

    def test_to_dict_failure(self) -> None:
        """Test converting failed result to dict."""
        result = SkillResult(
            success=False,
            skill_id="test",
            error="Something went wrong",
            execution_time=50.0,
        )

        data = result.to_dict()

        assert data["success"] is False
        assert data["skill_id"] == "test"
        assert data["workflow"] is None
        assert data["output"] is None
        assert data["error"] == "Something went wrong"


class TestExternalSkillExecutor:
    """Test ExternalSkillExecutor."""

    def test_init_default(self) -> None:
        """Test initialization with defaults."""
        executor = ExternalSkillExecutor(project_root=PROJECT_ROOT)

        assert executor.enable_execution is True
        assert executor.execution_timeout == 30.0

    def test_init_custom(self) -> None:
        """Test initialization with custom settings."""
        executor = ExternalSkillExecutor(
            enable_execution=False,
            execution_timeout=60.0,
        )

        assert executor.enable_execution is False
        assert executor.execution_timeout == 60.0

    def test_get_skill_definition_builtin(self) -> None:
        """Test getting definition for built-in skill."""
        executor = ExternalSkillExecutor(project_root=PROJECT_ROOT)

        # Use a built-in skill that should exist
        result = executor.get_skill_definition("builtin/systematic-debugging")

        assert result.success is True
        assert result.skill_id == "builtin/systematic-debugging"
        assert result.workflow is not None
        assert len(result.workflow.steps) > 0
        assert result.execution_time >= 0

    def test_get_skill_definition_not_found(self) -> None:
        """Test getting definition for non-existent skill."""
        executor = ExternalSkillExecutor(project_root=PROJECT_ROOT)

        with pytest.raises(SkillNotFoundError):
            executor.get_skill_definition("non-existent-skill")

    def test_get_skill_definition_external(self) -> None:
        """Test getting definition for external skill."""
        # Create a temporary external skill
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()

            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(
                """---
name: Test Skill
description: A test skill
---

# Test Skill

This is a test skill.

## Steps

1. First step
   Do something first

2. Second step
   Do something second
""",
                encoding="utf-8",
            )

            # Create executor and get definition
            executor = ExternalSkillExecutor(project_root=tmpdir)

            # Mock the loader to find our test skill
            with patch.object(executor._loader, "get_skill") as mock_get:
                from vibesop.core.skills.base import SkillMetadata
                from vibesop.core.skills.loader import LoadedSkill

                mock_get.return_value = LoadedSkill(
                    metadata=SkillMetadata(
                        id="test-skill",
                        name="Test Skill",
                        description="A test skill",
                        intent="Test",
                        namespace="test",
                        version="1.0.0",
                    ),
                    content="",
                    source_file=skill_md,
                )

                # Mock the auditor to return safe result
                with patch.object(executor._auditor, "audit_skill_file") as mock_audit:
                    from vibesop.security.skill_auditor import AuditResult

                    mock_audit.return_value = AuditResult(
                        is_safe=True,
                        threats=[],
                        reason="Safe",
                    )

                    result = executor.get_skill_definition("test-skill")

                    assert result.success is True
                    assert result.skill_id == "test-skill"
                    assert result.workflow is not None
                    assert len(result.workflow.steps) >= 2

    def test_execute_skill_disabled(self) -> None:
        """Test executing skill when execution is disabled."""
        executor = ExternalSkillExecutor(enable_execution=False)

        with pytest.raises(RuntimeError, match="execution is disabled"):
            executor.execute_skill("test", context={})

    def test_execute_skill_success(self) -> None:
        """Test successful skill execution."""
        executor = ExternalSkillExecutor(enable_execution=True)

        # Mock get_skill_definition
        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test workflow",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Test step",
                    instruction="Do something",
                )
            ],
        )

        with patch.object(executor, "get_skill_definition") as mock_get:
            mock_get.return_value = SkillResult(
                success=True,
                skill_id="test",
                workflow=workflow,
            )

            result = executor.execute_skill("test", context={"x": 1})

            assert result.success is True
            assert result.skill_id == "test"
            assert result.output is not None
            assert result.error is None

    def test_execute_skill_definition_error(self) -> None:
        """Test execution when getting definition fails."""
        executor = ExternalSkillExecutor(enable_execution=True)

        with patch.object(executor, "get_skill_definition") as mock_get:
            mock_get.return_value = SkillResult(
                success=False,
                skill_id="test",
                error="Failed to get definition",
            )

            with pytest.raises(SkillExecutionError):
                executor.execute_skill("test", context={})

    def test_validate_skill_valid(self) -> None:
        """Test validating a valid skill."""
        executor = ExternalSkillExecutor(project_root=PROJECT_ROOT)

        # Mock get_skill_definition
        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test workflow",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Test step",
                    instruction="Do something",
                )
            ],
        )

        with patch.object(executor, "get_skill_definition") as mock_get:
            mock_get.return_value = SkillResult(
                success=True,
                skill_id="test",
                workflow=workflow,
            )

            is_valid, errors = executor.validate_skill("test")

            assert is_valid is True
            assert len(errors) == 0

    def test_validate_skill_invalid(self) -> None:
        """Test validating an invalid skill."""
        executor = ExternalSkillExecutor(project_root=PROJECT_ROOT)

        with patch.object(executor, "get_skill_definition") as mock_get:
            mock_get.return_value = SkillResult(
                success=False,
                skill_id="test",
                error="Skill not found",
            )

            is_valid, errors = executor.validate_skill("test")

            assert is_valid is False
            assert len(errors) > 0

    def test_list_executable_skills(self) -> None:
        """Test listing executable skills."""
        executor = ExternalSkillExecutor(project_root=PROJECT_ROOT)

        skills = executor.list_executable_skills()

        assert isinstance(skills, list)
        assert len(skills) > 0
        # Check for either builtin or superpowers namespace
        assert any("systematic-debugging" in skill for skill in skills)


class TestSecurity:
    """Test security features."""

    def test_security_audit_failure(self) -> None:
        """Test that security audit failures block execution."""
        executor = ExternalSkillExecutor(project_root=PROJECT_ROOT)

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_file = Path(tmpdir) / "SKILL.md"
            skill_file.write_text("unsafe content", encoding="utf-8")

            # Mock the loader and auditor
            with patch.object(executor._loader, "get_skill") as mock_get:
                from vibesop.core.skills.base import SkillMetadata
                from vibesop.core.skills.loader import LoadedSkill

                mock_get.return_value = LoadedSkill(
                    metadata=SkillMetadata(
                        id="malicious",
                        name="Malicious",
                        description="Malicious skill",
                        intent="Harm",
                        namespace="test",
                        version="1.0.0",
                    ),
                    content="",
                    source_file=skill_file,
                )

                with patch.object(executor._auditor, "audit_skill_file") as mock_audit:
                    from vibesop.security.skill_auditor import AuditResult

                    mock_audit.return_value = AuditResult(
                        is_safe=False,
                        threats=[{"type": "prompt_injection", "severity": "high"}],
                        reason="Security audit failed",
                    )

                    with pytest.raises(SecurityViolationError):
                        executor.get_skill_definition("malicious")
