"""Simple integration tests for SkillManager."""

from __future__ import annotations

import pytest

from vibesop.core.skills.manager import SkillManager


class TestSkillManagerSimple:
    """Simple tests to verify integration."""

    def test_manager_has_executor(self) -> None:
        """Test that manager has executor instance."""
        manager = SkillManager()

        assert hasattr(manager, "_executor")
        assert manager._executor is not None

    def test_get_skill_definition_method_exists(self) -> None:
        """Test that get_skill_definition method exists."""
        manager = SkillManager()

        assert hasattr(manager, "get_skill_definition")
        assert callable(manager.get_skill_definition)

    def test_execute_skill_method_exists(self) -> None:
        """Test that execute_skill method exists."""
        manager = SkillManager()

        assert hasattr(manager, "execute_skill")
        assert callable(manager.execute_skill)

    def test_validate_skill_method_exists(self) -> None:
        """Test that validate_skill method exists."""
        manager = SkillManager()

        assert hasattr(manager, "validate_skill")
        assert callable(manager.validate_skill)

    def test_execute_disabled_returns_error(self) -> None:
        """Test that execution when disabled returns error."""
        manager = SkillManager(enable_execution=False)

        result = manager.execute_skill("any-skill", context={})

        assert result["success"] is False
        assert "disabled" in result["error"].lower()

    def test_backward_compatibility_list_skills(self) -> None:
        """Test that list_skills still works."""
        manager = SkillManager()

        skills = manager.list_skills()

        assert isinstance(skills, list)
        # Should have skills from various sources
        assert len(skills) > 0

    def test_backward_compatibility_get_info(self) -> None:
        """Test that get_skill_info still works."""
        manager = SkillManager()

        # Test with a skill we know exists
        info = manager.get_skill_info("gstack/freeze")

        assert info is not None
        assert "id" in info
        assert info["id"] == "gstack/freeze"

    def test_backward_compatibility_search(self) -> None:
        """Test that search_skills still works."""
        manager = SkillManager()

        results = manager.search_skills("gstack")

        assert isinstance(results, list)
        assert len(results) > 0

    def test_backward_compatibility_namespaces(self) -> None:
        """Test that get_namespaces still works."""
        manager = SkillManager()

        namespaces = manager.get_namespaces()

        assert isinstance(namespaces, list)
        assert "builtin" in namespaces
        assert "gstack" in namespaces

    def test_backward_compatibility_stats(self) -> None:
        """Test that get_stats still works."""
        manager = SkillManager()

        stats = manager.get_stats()

        assert "total_skills" in stats
        assert stats["total_skills"] > 0

    def test_new_methods_return_correct_structure(self) -> None:
        """Test that new methods return correct dictionary structure."""
        manager = SkillManager(enable_execution=False)

        # Test execute_skill returns correct structure
        result = manager.execute_skill("test", context={})
        assert "success" in result
        assert "skill_id" in result
        assert "error" in result

        # Test validate_skill returns correct structure
        validation = manager.validate_skill("test")
        assert "skill_id" in validation
        assert "is_valid" in validation
        assert "errors" in validation

    def test_get_skill_definition_returns_dict(self) -> None:
        """Test that get_skill_definition returns dict or None."""
        manager = SkillManager()

        # Non-existent skill should return None (not raise exception)
        result = manager.get_skill_definition("definitely-not-a-real-skill-xyz123")
        assert result is None
