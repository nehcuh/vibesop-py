"""Tests for Skill Governance (Phase 3): enable/disable and scope enforcement."""


import pytest

from vibesop.core.routing.unified import UnifiedRouter
from vibesop.core.skills.config_manager import SkillConfigManager


@pytest.fixture
def router_with_skills(tmp_path):
    """Router with a local project skill and a builtin skill."""
    (tmp_path / ".vibe").mkdir()
    (tmp_path / ".vibe" / "skills").mkdir()

    # Create a local project skill
    local_skill_dir = tmp_path / ".vibe" / "skills" / "my-local-skill"
    local_skill_dir.mkdir(parents=True)
    (local_skill_dir / "SKILL.md").write_text(
        "---\nname: my-local-skill\nintent: Run local task\ntags: [run, local, task]\n---\n# My Local Skill\n",
        encoding="utf-8",
    )

    # Create a builtin skill in the temp project tree (simulating builtin)
    builtin_skill_dir = tmp_path / "core" / "skills" / "systematic-debugging"
    builtin_skill_dir.mkdir(parents=True)
    (builtin_skill_dir / "SKILL.md").write_text(
        "---\nname: systematic-debugging\nintent: Debug systematically\n---\n# Systematic Debugging\n",
        encoding="utf-8",
    )

    from vibesop.core.config.manager import ConfigManager

    manager = ConfigManager(project_root=tmp_path)
    router = UnifiedRouter(project_root=tmp_path, config=manager)
    router._config.enable_ai_triage = False
    return router


class TestSkillEnablement:
    """Test enable/disable filtering in routing."""

    @pytest.mark.slow
    def test_disabled_skill_excluded_from_routing(self, router_with_skills, tmp_path):
        """Skills with enabled=False should be excluded from candidates at discovery time."""
        # Disable the local skill
        SkillConfigManager.update_skill_config("my-local-skill", {"enabled": False})

        # Clear router cache so next route() reloads from SkillLoader
        router_with_skills._candidates_cache = None
        if hasattr(router_with_skills, "_skill_loader"):
            router_with_skills._skill_loader._skill_cache = {}

        # SkillLoader.discover_all() filters out disabled skills;
        # route() should therefore not match the disabled skill
        result = router_with_skills.route("!my-local-skill run local task")
        assert result.primary is None or result.primary.skill_id != "my-local-skill"

        # Clean up
        SkillConfigManager.update_skill_config("my-local-skill", {"enabled": True})

    def test_enabled_skill_included_in_routing(self, router_with_skills):
        """Skills with enabled=True (default) should be available."""
        # Use explicit syntax to bypass prefilter/levenshtein complexities in test
        result = router_with_skills.route("!my-local-skill run local task")
        assert result.primary is not None
        assert result.primary.skill_id == "my-local-skill"


class TestSkillScope:
    """Test project vs global scope filtering."""

    def test_project_scoped_skill_available_in_project(self, router_with_skills):
        """Project-scoped skills from the current project should be routable."""
        # Set local skill to project scope
        SkillConfigManager.update_skill_config("my-local-skill", {"scope": "project"})

        # Use explicit syntax to bypass prefilter/levenshtein complexities in test
        result = router_with_skills.route("!my-local-skill run local task")
        assert result.primary is not None
        assert result.primary.skill_id == "my-local-skill"

        # Clean up
        SkillConfigManager.update_skill_config("my-local-skill", {"scope": "global"})

    def test_project_scoped_skill_filtered_outside_project(self, tmp_path):
        """Project-scoped skills should be excluded when routing from a different project."""
        # Create two project roots
        project_a = tmp_path / "project_a"
        project_b = tmp_path / "project_b"
        (project_a / ".vibe" / "skills").mkdir(parents=True)
        (project_b / ".vibe").mkdir(parents=True)

        # Create a skill in project A
        skill_dir = project_a / ".vibe" / "skills" / "project-a-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: project-a-skill\nintent: Do project A thing\n---\n# Project A Skill\n",
            encoding="utf-8",
        )

        # Set it to project scope
        SkillConfigManager.update_skill_config("project-a-skill", {"scope": "project"})

        # Create router for project B - should not see project-a-skill
        from vibesop.core.config.manager import ConfigManager

        manager = ConfigManager(project_root=project_b)
        router_b = UnifiedRouter(project_root=project_b, config=manager)

        raw_candidates = router_b._get_candidates()
        {c["id"] for c in raw_candidates}

        # The skill may be discovered (if SkillLoader searches broadly),
        # but should be filtered at route time
        result = router_b.route("do project A thing")
        if result.primary:
            assert result.primary.skill_id != "project-a-skill"

        # Clean up
        SkillConfigManager.update_skill_config("project-a-skill", {"scope": "global"})

    def test_global_skill_always_available(self, router_with_skills):
        """Global-scoped skills should be available regardless of project."""
        # Builtin skills are global by default
        result = router_with_skills.route("!builtin/systematic-debugging debug systematically")
        assert result.primary is not None
        assert result.primary.skill_id == "builtin/systematic-debugging"


class TestSkillConfigDefaults:
    """Test SkillConfig default values."""

    def test_default_scope_is_global(self):
        """Default scope should be global so skills are universally available."""
        from vibesop.core.skills.config_manager import SkillConfig

        config = SkillConfig(skill_id="test-skill")
        assert config.scope == "global"
        assert config.enabled is True

    def test_default_enabled_is_true(self):
        """Default enabled should be True."""
        from vibesop.core.skills.config_manager import SkillConfig

        config = SkillConfig(skill_id="test-skill")
        assert config.enabled is True
