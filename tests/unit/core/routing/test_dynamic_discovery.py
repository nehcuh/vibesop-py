"""Tests for DynamicSkillDiscovery — external skill discovery and registry merging."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from vibesop.core.routing.dynamic_discovery import DiscoveredSkill, DynamicSkillDiscovery


class TestDiscoveredSkill:
    """Test the DiscoveredSkill dataclass."""

    def test_dataclass_creation(self) -> None:
        skill = DiscoveredSkill(
            id="gstack/review",
            name="Review",
            description="Code review skill",
            namespace="gstack",
            source_path=Path("/skills/gstack/review"),
            triggers=["review code", "code review"],
        )
        assert skill.id == "gstack/review"
        assert skill.namespace == "gstack"
        assert skill.triggers == ["review code", "code review"]


class TestDynamicSkillDiscovery:
    """Test DynamicSkillDiscovery discover and merge methods."""

    def setup_method(self) -> None:
        """Reset singleton loader before each test."""
        DynamicSkillDiscovery._loader = None

    def teardown_method(self) -> None:
        """Reset singleton loader after each test."""
        DynamicSkillDiscovery._loader = None

    def _make_meta(
        self, name: str = "Skill", description: str = "", install_path: Path | None = None
    ) -> Any:
        """Factory for mock ExternalSkillMetadata-like objects."""
        meta = MagicMock()
        meta.base_metadata.name = name
        meta.base_metadata.description = description
        meta.install_path = install_path
        return meta

    def test_discover_empty(self) -> None:
        """No installed skills → empty list."""
        with patch("vibesop.core.skills.external_loader.ExternalSkillLoader") as MockLoader:
            MockLoader.return_value.discover_all.return_value = {}
            discovery = DynamicSkillDiscovery()
            result = discovery.discover()
            assert result == []

    def test_discover_skips_invalid_id(self) -> None:
        """Skills without '/' in ID are skipped."""
        with patch("vibesop.core.skills.external_loader.ExternalSkillLoader") as MockLoader:
            MockLoader.return_value.discover_all.return_value = {
                "nonslash": self._make_meta(),
                "": self._make_meta(),
            }
            discovery = DynamicSkillDiscovery()
            result = discovery.discover()
            assert result == []

    def test_discover_basic(self, tmp_path: Path) -> None:
        """Valid skill discovered with correct namespace split."""
        skill_dir = tmp_path / "gstack" / "review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Review\n", encoding="utf-8")

        with patch("vibesop.core.skills.external_loader.ExternalSkillLoader") as MockLoader:
            MockLoader.return_value.discover_all.return_value = {
                "gstack/review": self._make_meta(
                    name="Review Skill",
                    description="Reviews code",
                    install_path=skill_dir,
                ),
            }
            discovery = DynamicSkillDiscovery()
            result = discovery.discover()

        assert len(result) == 1
        assert result[0].id == "gstack/review"
        assert result[0].name == "Review Skill"
        assert result[0].namespace == "gstack"
        assert result[0].source_path == skill_dir

    def test_discover_uses_skill_name_fallback(self, tmp_path: Path) -> None:
        """When meta.name is empty, uses skill_name from ID."""
        skill_dir = tmp_path / "pack" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# My Skill\n", encoding="utf-8")

        with patch("vibesop.core.skills.external_loader.ExternalSkillLoader") as MockLoader:
            MockLoader.return_value.discover_all.return_value = {
                "pack/my-skill": self._make_meta(name="", install_path=skill_dir),
            }
            discovery = DynamicSkillDiscovery()
            result = discovery.discover()

        assert result[0].name == "my-skill"

    def test_discover_extracts_triggers(self, tmp_path: Path) -> None:
        """Trigger phrases extracted from SKILL.md frontmatter."""
        skill_dir = tmp_path / "gstack" / "review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ntriggers:\n  - review code\n  - audit code\n---\n# Review\n",
            encoding="utf-8",
        )

        with patch("vibesop.core.skills.external_loader.ExternalSkillLoader") as MockLoader:
            MockLoader.return_value.discover_all.return_value = {
                "gstack/review": self._make_meta(install_path=skill_dir),
            }
            discovery = DynamicSkillDiscovery()
            result = discovery.discover()

        assert result[0].triggers == ["review code", "audit code"]

    def test_discover_missing_skill_md(self, tmp_path: Path) -> None:
        """Missing SKILL.md results in empty triggers."""
        skill_dir = tmp_path / "gstack" / "review"
        skill_dir.mkdir(parents=True)
        # No SKILL.md written

        with patch("vibesop.core.skills.external_loader.ExternalSkillLoader") as MockLoader:
            MockLoader.return_value.discover_all.return_value = {
                "gstack/review": self._make_meta(install_path=skill_dir),
            }
            discovery = DynamicSkillDiscovery()
            result = discovery.discover()

        assert result[0].triggers == []

    def test_discover_no_install_path(self) -> None:
        """None install_path handled gracefully."""
        with patch("vibesop.core.skills.external_loader.ExternalSkillLoader") as MockLoader:
            MockLoader.return_value.discover_all.return_value = {
                "gstack/review": self._make_meta(install_path=None),
            }
            discovery = DynamicSkillDiscovery()
            result = discovery.discover()

        assert len(result) == 1
        assert result[0].source_path == Path()
        assert result[0].triggers == []

    def test_singleton_loader(self) -> None:
        """Loader is cached as class-level singleton."""
        with patch("vibesop.core.skills.external_loader.ExternalSkillLoader") as MockLoader:
            instance = MockLoader.return_value
            instance.discover_all.return_value = {}

            d1 = DynamicSkillDiscovery()
            d1.discover()
            assert DynamicSkillDiscovery._loader is instance

            d2 = DynamicSkillDiscovery()
            d2.discover()
            # Second call should reuse the same loader instance
            MockLoader.assert_called_once()

    def test_merge_with_registry_empty(self) -> None:
        """Merging empty registry with no discoveries → empty."""
        with patch.object(DynamicSkillDiscovery, "discover", return_value=[]):
            discovery = DynamicSkillDiscovery()
            result = discovery.merge_with_registry([])
            assert result == []

    def test_merge_with_registry_adds_discovered(self) -> None:
        """Discovered skills not in registry are appended."""
        discovered = [
            DiscoveredSkill(
                id="gstack/review",
                name="Review",
                description="Code review",
                namespace="gstack",
                source_path=Path("/skills/review"),
                triggers=["review"],
            ),
        ]
        with patch.object(DynamicSkillDiscovery, "discover", return_value=discovered):
            discovery = DynamicSkillDiscovery()
            result = discovery.merge_with_registry([{"id": "builtin/debug", "name": "Debug"}])

        assert len(result) == 2
        assert result[0]["id"] == "builtin/debug"
        assert result[1]["id"] == "gstack/review"
        assert result[1]["entrypoint"] == "external"
        assert result[1]["priority"] == "P3"
        assert result[1]["triggers"] == ["review"]

    def test_merge_skips_existing(self) -> None:
        """Registry entries take precedence over discovered skills."""
        discovered = [
            DiscoveredSkill(
                id="builtin/debug",
                name="Discovered Debug",
                description="",
                namespace="builtin",
                source_path=Path(),
                triggers=[],
            ),
        ]
        registry = [{"id": "builtin/debug", "name": "Registry Debug"}]
        with patch.object(DynamicSkillDiscovery, "discover", return_value=discovered):
            discovery = DynamicSkillDiscovery()
            result = discovery.merge_with_registry(registry)

        assert len(result) == 1
        assert result[0]["name"] == "Registry Debug"

    def test_merge_preserves_registry_order(self) -> None:
        """Registry entries remain first in the merged list."""
        discovered = [
            DiscoveredSkill(
                id="gstack/a",
                name="A",
                description="",
                namespace="gstack",
                source_path=Path(),
                triggers=[],
            ),
            DiscoveredSkill(
                id="gstack/b",
                name="B",
                description="",
                namespace="gstack",
                source_path=Path(),
                triggers=[],
            ),
        ]
        registry = [{"id": "builtin/x", "name": "X"}]
        with patch.object(DynamicSkillDiscovery, "discover", return_value=discovered):
            discovery = DynamicSkillDiscovery()
            result = discovery.merge_with_registry(registry)

        assert [r["id"] for r in result] == ["builtin/x", "gstack/a", "gstack/b"]
