"""Tests for skill parser capabilities extraction."""

from __future__ import annotations

from pathlib import Path

from vibesop.core.skills.base import SkillMetadata
from vibesop.core.skills.parser import build_metadata


class TestCapabilitiesExtraction:
    """Test capabilities extraction from SKILL.md frontmatter."""

    def test_capabilities_list(self) -> None:
        """Parse capabilities from YAML list."""
        data = {
            "id": "test-skill",
            "name": "Test Skill",
            "description": "A test skill",
            "capabilities": ["plan", "design", "review"],
        }
        meta = build_metadata(data, "test-skill", Path("test"))
        assert meta.capabilities == ["plan", "design", "review"]

    def test_capabilities_string(self) -> None:
        """Parse capabilities from comma-separated string."""
        data = {
            "id": "test-skill",
            "name": "Test Skill",
            "description": "A test skill",
            "capabilities": "plan, design, review",
        }
        meta = build_metadata(data, "test-skill", Path("test"))
        assert meta.capabilities == ["plan", "design", "review"]

    def test_capabilities_missing(self) -> None:
        """Default to empty list when capabilities not present."""
        data = {
            "id": "test-skill",
            "name": "Test Skill",
            "description": "A test skill",
        }
        meta = build_metadata(data, "test-skill", Path("test"))
        assert meta.capabilities == []

    def test_skill_metadata_capabilities_field(self) -> None:
        """SkillMetadata dataclass accepts capabilities."""
        meta = SkillMetadata(
            id="test",
            name="Test",
            description="desc",
            intent="test intent",
            capabilities=["debug", "refactor"],
        )
        assert meta.capabilities == ["debug", "refactor"]
