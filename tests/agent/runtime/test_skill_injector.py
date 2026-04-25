"""Tests for SkillInjector."""

from __future__ import annotations

from unittest.mock import patch

from vibesop.agent.runtime.skill_injector import (
    InjectionMethod,
    PlatformType,
    SkillInjector,
)
from vibesop.core.models import ExecutionMode, ExecutionPlan, ExecutionStep


class TestSkillInjector:
    """Test skill content injection across platforms."""

    def test_claude_code_injection(self, tmp_path) -> None:
        injector = SkillInjector(project_root=tmp_path)

        # Mock skill content
        skill_content = "# Test Skill\n\nThis is a test skill."
        with patch.object(injector, "_load_skill_content", return_value=skill_content):
            result = injector.inject_single_skill("test/skill", PlatformType.CLAUDE_CODE)

        assert result.method == InjectionMethod.ADDITIONAL_CONTEXT
        assert result.skill_id == "test/skill"
        payload_dict = result.payload
        assert isinstance(payload_dict, dict)
        assert "ACTIVE SKILL" in payload_dict["additionalContext"]
        assert "test/skill" in payload_dict["additionalContext"]
        assert skill_content in payload_dict["additionalContext"]

    def test_opencode_injection(self, tmp_path) -> None:
        injector = SkillInjector(project_root=tmp_path)

        skill_content = "# Test Skill\n\nWorkflow steps here."
        with patch.object(injector, "_load_skill_content", return_value=skill_content):
            result = injector.inject_single_skill("test/skill", PlatformType.OPENCODE)

        assert result.method == InjectionMethod.SYSTEM_PROMPT
        assert "<vibesop-skill" in result.payload
        assert "test/skill" in result.payload

    def test_kimi_cli_instruction(self, tmp_path) -> None:
        injector = SkillInjector(project_root=tmp_path)

        with patch.object(injector, "_load_skill_content", return_value="content"):
            result = injector.inject_single_skill("gstack/review", PlatformType.KIMI_CLI)

        assert result.method == InjectionMethod.INSTRUCTION
        assert "gstack-review" in result.payload
        assert "SKILL.md" in result.payload
        assert "读取" in result.payload

    def test_generic_injection(self, tmp_path) -> None:
        injector = SkillInjector(project_root=tmp_path)

        skill_content = "# Generic Skill"
        with patch.object(injector, "_load_skill_content", return_value=skill_content):
            result = injector.inject_single_skill("test/skill", PlatformType.GENERIC)

        assert result.method == InjectionMethod.TEXT
        assert "=== SKILL: test/skill ===" in result.payload

    def test_truncation(self, tmp_path) -> None:
        injector = SkillInjector(project_root=tmp_path)
        injector.MAX_INJECT_LENGTH = 50

        long_content = "A" * 100
        with patch.object(injector, "_load_skill_content", return_value=long_content):
            result = injector.inject_single_skill("test/skill", PlatformType.CLAUDE_CODE)

        assert result.truncated
        # Content should be truncated to MAX_INJECT_LENGTH (50 in test)
        payload_dict = result.payload
        assert len(payload_dict["additionalContext"]) < 200  # includes wrapper

    def test_execution_plan_claude_code(self, tmp_path) -> None:
        injector = SkillInjector(project_root=tmp_path)

        plan = ExecutionPlan(
            plan_id="test-plan",
            original_query="analyze and optimize",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="superpowers-architect",
                    intent="Analyze architecture",
                    input_query="Analyze the architecture",
                    output_as="analysis",
                ),
                ExecutionStep(
                    step_id="s2",
                    step_number=2,
                    skill_id="superpowers-optimize",
                    intent="Optimize performance",
                    input_query="Optimize based on analysis",
                    output_as="optimization",
                    dependencies=["s1"],
                ),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

        result = injector.inject_execution_plan(plan, PlatformType.CLAUDE_CODE)

        assert result.method == InjectionMethod.ADDITIONAL_CONTEXT
        assert "Execution Plan" in str(result.payload)
        assert "superpowers-architect" in str(result.payload)
        assert "superpowers-optimize" in str(result.payload)

    def test_execution_plan_kimi_cli(self, tmp_path) -> None:
        injector = SkillInjector(project_root=tmp_path)

        plan = ExecutionPlan(
            plan_id="test-plan",
            original_query="test query",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="skill-a",
                    intent="Do A",
                    input_query="Do A",
                ),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

        result = injector.inject_execution_plan(plan, PlatformType.KIMI_CLI)

        assert result.method == InjectionMethod.INSTRUCTION
        assert "步骤" in result.payload
        assert "skill-a" in result.payload

    def test_load_skill_from_core_skills(self, tmp_path) -> None:
        injector = SkillInjector(project_root=tmp_path)

        # Create a mock skill file
        skill_dir = tmp_path / "core" / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Test Skill from core")

        content = injector._load_skill_content("test-skill")
        assert "Test Skill from core" in content

    def test_load_skill_not_found(self, tmp_path) -> None:
        injector = SkillInjector(project_root=tmp_path)

        content = injector._load_skill_content("nonexistent/skill")
        assert "Skill content not found" in content
        assert "nonexistent/skill" in content
