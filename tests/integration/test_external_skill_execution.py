"""Integration tests for external skill execution.

Tests that external skills from superpowers, gstack, etc. can be
loaded, instantiated, and executed through the SkillManager.
"""

import pytest
from pathlib import Path

from vibesop.core.skills.manager import SkillManager
from vibesop.core.skills.loader import SkillLoader
from vibesop.core.skills.external_loader import ExternalSkillLoader


class TestExternalSkillIntegration:
    """Test external skill loading and execution."""

    def test_external_skills_discovered(self):
        """Test that external skills are discovered from ~/.claude/skills/."""
        loader = SkillLoader(enable_external=True, require_audit=True)
        skills = loader.discover_all()

        # Should find external skills
        external_skills = {k: v for k, v in skills.items() if v.external_metadata is not None}

        # We expect at least some external skills to be found
        # (depending on what's installed in ~/.claude/skills/)
        print(f"\nDiscovered {len(external_skills)} external skills")
        for skill_id in sorted(external_skills.keys()):
            print(f"  - {skill_id}")

        # The test passes if we can discover without errors
        # Actual number depends on user's environment
        assert len(skills) > 0

    def test_skill_manager_lists_external_skills(self):
        """Test that SkillManager lists external skills."""
        manager = SkillManager()
        skills = manager.list_skills()

        # Find external skills
        external = [
            s for s in skills if s.get("namespace") in ["external", "superpowers", "gstack"]
        ]

        print(f"\nSkillManager found {len(external)} external skills")
        for skill in external[:5]:  # Show first 5
            print(f"  - {skill['id']} ({skill['namespace']})")

        # Should have external skills if they are installed
        if external:
            assert all("id" in s for s in external)
            assert all("namespace" in s for s in external)

    def test_external_skill_instantiation(self):
        """Test that external skills can be instantiated."""
        manager = SkillManager()

        # Try to instantiate some common external skills
        test_skills = [
            "systematic-debugging",
            "experience-evolution",
            "planning-with-files",
        ]

        instantiated = []
        for skill_id in test_skills:
            skill = manager.get_skill_instance(skill_id)
            if skill:
                instantiated.append(skill_id)
                print(f"✅ Instantiated: {skill_id}")

        # At least some should be instantiable
        assert len(instantiated) > 0, "Should be able to instantiate external skills"

    def test_gstack_skills_loaded(self):
        """Test that gstack skills are loaded if installed."""
        loader = SkillLoader(enable_external=True)
        skills = loader.discover_all()

        gstack_skills = {k: v for k, v in skills.items() if k.startswith("gstack/")}

        print(f"\nFound {len(gstack_skills)} gstack skills")
        for skill_id in sorted(gstack_skills.keys()):
            skill = gstack_skills[skill_id]
            assert skill.external_metadata is not None
            print(f"  ✅ {skill_id}")

    def test_superpowers_skills_loaded(self):
        """Test that superpowers skills are loaded if installed."""
        loader = SkillLoader(enable_external=True)
        skills = loader.discover_all()

        superpowers_skills = {k: v for k, v in skills.items() if k.startswith("superpowers/")}

        print(f"\nFound {len(superpowers_skills)} superpowers skills")
        for skill_id in sorted(superpowers_skills.keys()):
            skill = superpowers_skills[skill_id]
            assert skill.external_metadata is not None
            print(f"  ✅ {skill_id}")

    def test_external_skill_security_audit(self):
        """Test that external skills pass security audit."""
        loader = SkillLoader(enable_external=True, require_audit=True)
        skills = loader.discover_all()

        external_skills = {k: v for k, v in skills.items() if v.external_metadata is not None}

        # All loaded external skills should be safe
        for skill_id, skill in external_skills.items():
            if skill.external_metadata:
                assert skill.external_metadata.is_safe, (
                    f"Skill {skill_id} should pass security audit"
                )

    def test_skill_manager_get_skill_info(self):
        """Test getting skill info for external skills."""
        manager = SkillManager()

        # Get info for an external skill
        info = manager.get_skill_info("systematic-debugging")

        if info:
            assert info["id"] == "systematic-debugging"
            assert "name" in info
            assert "namespace" in info
            print(f"\nSkill info: {info}")

    def test_loader_without_external_skills(self):
        """Test that loader works when external skills are disabled."""
        loader = SkillLoader(enable_external=False)
        skills = loader.discover_all()

        # Should only have local skills
        external = {k: v for k, v in skills.items() if v.external_metadata is not None}
        assert len(external) == 0, "Should not load external skills when disabled"


class TestExternalSkillLoader:
    """Test ExternalSkillLoader directly."""

    def test_discover_external_skills(self):
        """Test discovering external skills."""
        loader = ExternalSkillLoader(require_audit=True)
        skills = loader.discover_all()

        print(f"\nExternalSkillLoader discovered {len(skills)} skills")
        for skill_id in sorted(skills.keys())[:5]:
            skill = skills[skill_id]
            print(f"  - {skill_id} (safe: {skill.is_safe})")

        # All should have audit results
        for skill in skills.values():
            assert skill.audit_result is not None

    def test_get_supported_packs(self):
        """Test getting information about supported packs."""
        loader = ExternalSkillLoader()
        packs = loader.get_supported_packs()

        print(f"\nSupported packs:")
        for name, info in packs.items():
            status = "installed" if info["installed"] else "not installed"
            print(f"  - {name}: {status}")
            if info["installed"]:
                print(f"    Path: {info['path']}")

        # Should list superpowers and gstack
        assert "superpowers" in packs
        assert "gstack" in packs
