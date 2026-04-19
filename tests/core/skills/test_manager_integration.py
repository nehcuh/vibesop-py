"""Tests for enhanced SkillManager integration."""

from __future__ import annotations

import pytest

from vibesop.core.skills.manager import SkillManager


class TestSkillManagerIntegration:
    """Test SkillManager with external skill execution."""

    def test_init_with_execution_enabled(self) -> None:
        """Test initialization with execution enabled."""
        manager = SkillManager(enable_execution=True)

        assert manager._executor.enable_execution is True

    def test_init_with_execution_disabled(self) -> None:
        """Test initialization with execution disabled."""
        manager = SkillManager(enable_execution=False)

        assert manager._executor.enable_execution is False

    def test_get_skill_definition(self) -> None:
        """Test getting skill workflow definition."""
        manager = SkillManager()

        # First, list available skills to find one that exists
        skills = manager.list_skills()
        assert len(skills) > 0

        # Get definition for the first available skill
        skill_id = skills[0]["id"]
        result = manager.get_skill_definition(skill_id)

        assert result is not None
        assert "skill_id" in result
        assert "workflow" in result
        assert result["skill_id"] == skill_id
        assert "steps" in result["workflow"]

    def test_get_skill_definition_not_found(self) -> None:
        """Test getting definition for non-existent skill."""
        manager = SkillManager()

        result = manager.get_skill_definition("non-existent-skill")

        assert result is None

    def test_execute_skill_disabled(self) -> None:
        """Test execution when disabled."""
        manager = SkillManager(enable_execution=False)

        result = manager.execute_skill("test", context={})

        assert result["success"] is False
        assert "disabled" in result["error"].lower()

    def test_execute_skill_enabled(self) -> None:
        """Test execution when enabled."""
        manager = SkillManager(enable_execution=True)

        # Get a valid skill first
        skills = manager.list_skills()
        skill_id = skills[0]["id"]

        # Execute the skill
        result = manager.execute_skill(skill_id, context={"test": True})

        assert result["success"] is True
        assert result["skill_id"] == skill_id
        assert result["output"] is not None

    def test_validate_skill_valid(self) -> None:
        """Test validating a valid skill."""
        manager = SkillManager()

        # Get a valid skill first
        skills = manager.list_skills()
        skill_id = skills[0]["id"]

        result = manager.validate_skill(skill_id)

        assert result["skill_id"] == skill_id
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_skill_invalid(self) -> None:
        """Test validating an invalid skill."""
        manager = SkillManager()

        result = manager.validate_skill("non-existent-skill")

        assert result["skill_id"] == "non-existent-skill"
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    def test_list_skills_still_works(self) -> None:
        """Test that existing methods still work after integration."""
        manager = SkillManager()

        skills = manager.list_skills()

        assert isinstance(skills, list)
        assert len(skills) > 0
        assert any(s["id"] == "systematic-debugging" for s in skills)

    def test_get_skill_info_still_works(self) -> None:
        """Test that get_skill_info still works."""
        manager = SkillManager()

        info = manager.get_skill_info("systematic-debugging")

        assert info is not None
        assert info["id"] == "systematic-debugging"
        assert "name" in info

    def test_search_skills_still_works(self) -> None:
        """Test that search_skills still works."""
        manager = SkillManager()

        results = manager.search_skills("debug")

        assert isinstance(results, list)
        assert len(results) > 0
        assert any("debug" in r["id"].lower() or "debug" in r.get("description", "").lower() for r in results)

    def test_get_namespaces_still_works(self) -> None:
        """Test that get_namespaces still works."""
        manager = SkillManager()

        namespaces = manager.get_namespaces()

        assert isinstance(namespaces, list)
        assert "builtin" in namespaces

    def test_get_stats_still_works(self) -> None:
        """Test that get_stats still works."""
        manager = SkillManager()

        stats = manager.get_stats()

        assert "total_skills" in stats
        assert stats["total_skills"] > 0

    def test_integration_workflow(self) -> None:
        """Test complete integration workflow.

        This test demonstrates the typical workflow:
        1. List available skills
        2. Get skill definition
        3. Validate skill
        4. Execute skill (if enabled)
        """
        manager = SkillManager(enable_execution=True)

        # 1. List skills
        skills = manager.list_skills()
        assert len(skills) > 0

        # 2. Get skill definition for first skill
        first_skill_id = skills[0]["id"]
        definition = manager.get_skill_definition(first_skill_id)
        assert definition is not None

        # 3. Validate skill
        validation = manager.validate_skill(first_skill_id)
        assert validation["is_valid"] is True

        # 4. Execute skill
        execution = manager.execute_skill(first_skill_id, context={"test": True})
        assert execution["success"] is True

    def test_backward_compatibility(self) -> None:
        """Test that old API is still functional."""
        manager = SkillManager()

        # All old methods should work
        skills = manager.list_skills()
        info = manager.get_skill_info("systematic-debugging")
        results = manager.search_skills("test")
        namespaces = manager.get_namespaces()
        stats = manager.get_stats()

        assert len(skills) > 0
        assert info is not None
        assert isinstance(results, list)
        assert isinstance(namespaces, list)
        assert stats["total_skills"] > 0
