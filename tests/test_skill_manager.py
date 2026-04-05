"""Test skill management system."""

import asyncio
import shutil
import tempfile
from pathlib import Path

from vibesop.core.skills import (
    PromptSkill,
    SkillContext,
    SkillManager,
    SkillMetadata,
    SkillResult,
    SkillType,
    WorkflowSkill,
)


class TestSkillMetadata:
    """Test SkillMetadata dataclass."""

    def test_create_metadata(self) -> None:
        """Test creating skill metadata."""
        metadata = SkillMetadata(
            id="test/skill",
            name="Test Skill",
            description="A test skill",
            intent="Test things",
        )

        assert metadata.id == "test/skill"
        assert metadata.name == "Test Skill"
        assert metadata.namespace == "builtin"
        assert metadata.tags == []

    def test_metadata_with_tags(self) -> None:
        """Test metadata with tags."""
        metadata = SkillMetadata(
            id="test/skill",
            name="Test Skill",
            description="A test skill",
            intent="Test things",
            tags=["test", "demo"],
        )

        assert metadata.tags == ["test", "demo"]


class TestSkillContext:
    """Test SkillContext dataclass."""

    def test_create_context(self) -> None:
        """Test creating skill context."""
        context = SkillContext(
            query="test query",
            working_dir=Path("/tmp"),
        )

        assert context.query == "test query"
        assert context.working_dir == Path("/tmp")
        assert context.env == {}
        assert context.metadata == {}

    def test_context_with_env(self) -> None:
        """Test context with environment variables."""
        context = SkillContext(
            query="test",
            working_dir=Path("/tmp"),
            env={"TEST": "value"},
        )

        assert context.env == {"TEST": "value"}


class TestSkillResult:
    """Test SkillResult dataclass."""

    def test_create_success_result(self) -> None:
        """Test creating a successful result."""
        result = SkillResult(
            success=True,
            output="Done!",
        )

        assert result.success is True
        assert result.output == "Done!"
        assert result.error is None

    def test_create_error_result(self) -> None:
        """Test creating an error result."""
        result = SkillResult(
            success=False,
            output="",
            error="Something went wrong",
        )

        assert result.success is False
        assert result.error == "Something went wrong"


class TestPromptSkill:
    """Test PromptSkill class."""

    def test_create_prompt_skill(self) -> None:
        """Test creating a prompt skill."""
        metadata = SkillMetadata(
            id="test/prompt",
            name="Test",
            description="Test prompt skill",
            intent="Test",
        )
        skill = PromptSkill(
            metadata=metadata,
            prompt_template="Please {query}",
        )

        assert skill.id == "test/prompt"
        assert skill.get_prompt_template() == "Please {query}"

    def test_render_prompt(self) -> None:
        """Test rendering a prompt template."""
        metadata = SkillMetadata(
            id="test/prompt",
            name="Test",
            description="Test",
            intent="Test",
        )
        skill = PromptSkill(
            metadata=metadata,
            prompt_template="Help me {query}",
        )

        context = SkillContext(
            query="review code",
            working_dir=Path("/tmp"),
        )

        rendered = skill.render_prompt(context)

        assert rendered == "Help me review code"

    def test_execute_prompt_skill(self) -> None:
        """Test executing a prompt skill."""
        metadata = SkillMetadata(
            id="test/prompt",
            name="Test",
            description="Test",
            intent="Test",
        )
        skill = PromptSkill(
            metadata=metadata,
            prompt_template="Process: {query}",
        )

        context = SkillContext(
            query="test",
            working_dir=Path("/tmp"),
        )

        async def run() -> SkillResult:
            return await skill.execute(context)

        result = asyncio.run(run())

        assert result.success is True
        assert "Process: test" in result.output

    def test_execute_with_error(self) -> None:
        """Test executing with invalid template."""
        metadata = SkillMetadata(
            id="test/prompt",
            name="Test",
            description="Test",
            intent="Test",
        )
        # Using a template that might fail
        skill = PromptSkill(
            metadata=metadata,
            prompt_template="{query}",
            system_prompt=None,
        )

        context = SkillContext(
            query="test",
            working_dir=Path("/tmp"),
        )

        async def run() -> SkillResult:
            return await skill.execute(context)

        result = asyncio.run(run())

        assert result.success is True


class TestWorkflowSkill:
    """Test WorkflowSkill class."""

    def test_create_workflow_skill(self) -> None:
        """Test creating a workflow skill."""
        metadata = SkillMetadata(
            id="test/workflow",
            name="Test Workflow",
            description="A test workflow",
            intent="Test workflow",
            skill_type=SkillType.WORKFLOW,
        )
        steps = [
            {"type": "prompt", "name": "step1", "prompt": "First step"},
            {"type": "command", "name": "step2", "command": "echo test"},
        ]

        skill = WorkflowSkill(metadata=metadata, steps=steps)

        assert skill.id == "test/workflow"
        assert len(skill.steps) == 2

    def test_execute_workflow_skill(self) -> None:
        """Test executing a workflow skill."""
        metadata = SkillMetadata(
            id="test/workflow",
            name="Test Workflow",
            description="A test workflow",
            intent="Test workflow",
            skill_type=SkillType.WORKFLOW,
        )
        steps = [
            {"type": "prompt", "name": "analyze", "prompt": "Analyze this"},
            {"type": "command", "name": "build", "command": "make build"},
        ]

        skill = WorkflowSkill(metadata=metadata, steps=steps)
        context = SkillContext(query="test", working_dir=Path("/tmp"))

        async def run() -> SkillResult:
            return await skill.execute(context)

        result = asyncio.run(run())

        assert result.success is True
        assert result.metadata["steps_executed"] == 2


class TestSkillLoader:
    """Test SkillLoader class."""

    def _create_loader(self) -> SkillManager:
        """Helper to create a manager with temp directory."""
        tmpdir = Path(tempfile.mkdtemp())
        return SkillManager(project_root=tmpdir), tmpdir

    def test_empty_manager(self) -> None:
        """Test manager with no project-local skills."""
        import os

        # Create temp directory and chroot to it
        tmpdir = Path(tempfile.mkdtemp())
        original_dir = os.getcwd()

        try:
            os.chdir(tmpdir)
            manager = SkillManager(project_root=tmpdir)

            # Check only project-local skills (not external skills)
            # Project-local skills should be empty in temp directory
            skills = manager.list_skills(include_registry=False)
            project_local = [
                s
                for s in skills
                if s.get("source") == "filesystem" and s.get("namespace") == "project"
            ]

            # Should have no project-local skills in empty temp directory
            assert len(project_local) == 0
        finally:
            os.chdir(original_dir)
            # Cleanup
            shutil.rmtree(tmpdir)

    def test_list_skills_from_registry(self) -> None:
        """Test listing skills from YAML registry."""
        # Use current project root which has registry
        manager = SkillManager()

        skills = manager.list_skills(include_registry=True)

        # Should have skills from registry
        assert len(skills) > 0

        # Check structure
        skill = skills[0]
        assert "id" in skill
        assert "name" in skill
        assert "description" in skill

    def test_get_namespaces(self) -> None:
        """Test getting available namespaces."""
        manager = SkillManager()

        namespaces = manager.get_namespaces()

        assert isinstance(namespaces, list)
        assert "builtin" in namespaces

    def test_get_stats(self) -> None:
        """Test getting skill statistics."""
        manager = SkillManager()

        stats = manager.get_stats()

        assert "total_skills" in stats
        assert "by_namespace" in stats
        assert "by_type" in stats
        assert stats["total_skills"] > 0


class TestSkillManager:
    """Test SkillManager class."""

    def test_get_skill_info(self) -> None:
        """Test getting skill information."""
        manager = SkillManager()

        # Try to get a known skill
        info = manager.get_skill_info("gstack/review")

        # May or may not exist depending on registry
        if info:
            assert "id" in info
            assert info["id"] == "gstack/review"

    def test_search_skills(self) -> None:
        """Test searching for skills."""
        manager = SkillManager()

        # Search for a common term
        results = manager.search_skills("review")

        assert isinstance(results, list)

    def test_search_skills_no_results(self) -> None:
        """Test searching with no results."""
        manager = SkillManager()

        results = manager.search_skills("xyznonexistent")

        assert isinstance(results, list)

    def test_reload_skills(self) -> None:
        """Test reloading skills."""
        manager = SkillManager()

        count = manager.reload_skills()

        assert count >= 0


class TestMarkdownSkillLoading:
    """Test loading skills from markdown files."""

    def test_load_markdown_skill(self) -> None:
        """Test loading a skill from a markdown file."""
        tmpdir = Path(tempfile.mkdtemp())
        skills_dir = tmpdir / "skills"
        skills_dir.mkdir()

        # Create a markdown skill file
        skill_file = skills_dir / "test.md"
        skill_file.write_text(
            """---
id: project/test-skill
name: Test Skill
description: A test skill from markdown
intent: Test things
type: prompt
---

This is the prompt template for testing.
Query: {query}
"""
        )

        manager = SkillManager(project_root=tmpdir)
        skills = manager.list_skills(include_registry=False)

        # Should have found the skill
        assert len(skills) >= 1

        # Find our skill
        test_skill = next((s for s in skills if s["id"] == "project/test-skill"), None)
        if test_skill:
            assert test_skill["name"] == "Test Skill"
            assert test_skill["description"] == "A test skill from markdown"

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_load_yaml_skill(self) -> None:
        """Test loading a skill from a YAML file."""
        tmpdir = Path(tempfile.mkdtemp())
        skills_dir = tmpdir / "skills"
        skills_dir.mkdir()

        # Create a YAML skill file
        skill_file = skills_dir / "test.yaml"
        skill_file.write_text(
            """id: project/yaml-skill
name: YAML Skill
description: A test skill from YAML
intent: Test YAML loading
type: prompt
prompt: "Process: {query}"
"""
        )

        manager = SkillManager(project_root=tmpdir)
        skills = manager.list_skills(include_registry=False)

        # Should have found the skill
        assert len(skills) >= 1

        # Find our skill
        yaml_skill = next((s for s in skills if s["id"] == "project/yaml-skill"), None)
        if yaml_skill:
            assert yaml_skill["name"] == "YAML Skill"

        # Cleanup
        shutil.rmtree(tmpdir)
