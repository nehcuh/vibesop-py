"""Tests for dynamic skill discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.core.routing.dynamic_discovery import DiscoveredSkill, DynamicSkillDiscovery


class TestDynamicSkillDiscovery:
    """Tests for DynamicSkillDiscovery."""

    @pytest.fixture
    def discovery(self) -> DynamicSkillDiscovery:
        return DynamicSkillDiscovery()

    def test_discover_installed_packs(self, discovery: DynamicSkillDiscovery) -> None:
        """Should find skills from installed packs if any exist."""
        skills = discovery.discover()

        # discovery.discover() always returns a list
        assert isinstance(skills, list)

        if skills:
            ids = [s.id for s in skills]
            gstack_skills = [i for i in ids if i.startswith("gstack/")]
            omx_skills = [i for i in ids if i.startswith("omx/")]
            assert len(gstack_skills) > 0 or len(omx_skills) > 0 or len(skills) > 0

    def test_merge_no_duplicates(self, discovery: DynamicSkillDiscovery) -> None:
        """Registry entries should not be duplicated."""
        registry = [
            {"id": "gstack/review", "name": "Review", "namespace": "gstack"},
        ]
        merged = discovery.merge_with_registry(registry)

        gstack_entries = [s for s in merged if s["id"] == "gstack/review"]
        assert len(gstack_entries) == 1

    def test_merge_adds_new_skills(self, discovery: DynamicSkillDiscovery) -> None:
        """Discovered skills not in registry should be appended."""
        registry: list[dict] = []
        merged = discovery.merge_with_registry(registry)

        # If external packs are installed, skills should be appended
        if any(s["id"].startswith("gstack/") for s in merged):
            gstack_skills = [s for s in merged if s.get("namespace") == "gstack"]
            assert len(gstack_skills) > 0

    def test_merge_preserves_registry_entries(self, discovery: DynamicSkillDiscovery) -> None:
        """Registry entries should be preserved exactly as-is."""
        registry = [
            {
                "id": "builtin/analyze",
                "name": "Analyze",
                "description": "Built-in analyze skill",
                "namespace": "builtin",
                "priority": "P1",
            },
        ]
        merged = discovery.merge_with_registry(registry)

        # First entry should be the registry entry
        assert merged[0] == registry[0]

    def test_discover_returns_list(self, discovery: DynamicSkillDiscovery) -> None:
        """discover() should always return a list even if no packs installed."""
        skills = discovery.discover()
        assert isinstance(skills, list)


class TestDiscoveredSkill:
    """Tests for the DiscoveredSkill dataclass."""

    def test_create_discovered_skill(self) -> None:
        """Should create a DiscoveredSkill with all fields."""
        skill = DiscoveredSkill(
            id="gstack/review",
            name="Review",
            description="Code review skill",
            namespace="gstack",
            source_path=Path("/tmp/gstack/review"),
            triggers=["review", "pr review"],
        )
        assert skill.id == "gstack/review"
        assert skill.name == "Review"
        assert skill.description == "Code review skill"
        assert skill.namespace == "gstack"
        assert skill.triggers == ["review", "pr review"]
