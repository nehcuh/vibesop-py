"""Tests for registry synchronization."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from vibesop.core.skills.registry_sync import RegistrySync


class TestRegistrySyncInit:
    """Test initialization."""

    def test_default_paths(self):
        sync = RegistrySync()
        assert sync.registry_path == Path("core/registry.yaml")
        assert sync.skills_dir == Path("core/skills")

    def test_custom_paths(self, tmp_path: Path):
        sync = RegistrySync(
            registry_path=tmp_path / "registry.yaml",
            skills_dir=tmp_path / "skills",
        )
        assert sync.registry_path == tmp_path / "registry.yaml"
        assert sync.skills_dir == tmp_path / "skills"


class TestLoadRegistry:
    """Test registry loading."""

    def test_load_existing_registry(self, tmp_path: Path):
        registry_file = tmp_path / "registry.yaml"
        registry_file.write_text("schema_version: 1\nskills: []\n")

        sync = RegistrySync(registry_path=registry_file)
        data = sync._load_registry()
        assert data["schema_version"] == 1
        assert data["skills"] == []

    def test_load_missing_registry(self, tmp_path: Path):
        sync = RegistrySync(registry_path=tmp_path / "missing.yaml")
        data = sync._load_registry()
        assert data["schema_version"] == 1
        assert data["skills"] == []

    def test_load_invalid_registry(self, tmp_path: Path):
        registry_file = tmp_path / "registry.yaml"
        registry_file.write_text("not a dict")

        sync = RegistrySync(registry_path=registry_file)
        data = sync._load_registry()
        assert data == {}


class TestDiscoverBuiltinSkills:
    """Test skill discovery."""

    def test_discover_empty_dir(self, tmp_path: Path):
        sync = RegistrySync(skills_dir=tmp_path)
        skills = sync._discover_builtin_skills()
        assert skills == {}

    def test_discover_with_skills(self, tmp_path: Path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test Skill\n")

        mock_meta = MagicMock()
        mock_meta.id = "test-skill"
        mock_meta.intent = "testing"
        mock_meta.description = "A test skill"

        sync = RegistrySync(skills_dir=tmp_path)
        with patch("vibesop.core.skills.registry_sync.parse_skill_md", return_value=mock_meta):
            skills = sync._discover_builtin_skills()

        assert "test-skill" in skills
        assert skills["test-skill"] == mock_meta

    def test_discover_skips_non_directories(self, tmp_path: Path):
        (tmp_path / "not-a-dir.txt").write_text("hello")
        sync = RegistrySync(skills_dir=tmp_path)
        skills = sync._discover_builtin_skills()
        assert skills == {}

    def test_discover_skips_missing_skill_md(self, tmp_path: Path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        sync = RegistrySync(skills_dir=tmp_path)
        skills = sync._discover_builtin_skills()
        assert skills == {}

    def test_discover_none_meta(self, tmp_path: Path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test\n")

        sync = RegistrySync(skills_dir=tmp_path)
        with patch("vibesop.core.skills.registry_sync.parse_skill_md", return_value=None):
            skills = sync._discover_builtin_skills()

        assert "test-skill" in skills
        assert skills["test-skill"] is None


class TestSync:
    """Test sync operation."""

    def test_sync_adds_new_skills(self, tmp_path: Path):
        registry_file = tmp_path / "registry.yaml"
        registry_file.write_text("schema_version: 1\nskills: []\n")

        skill_dir = tmp_path / "skills" / "new-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# New Skill\n")

        mock_meta = MagicMock()
        mock_meta.id = "new-skill"
        mock_meta.intent = "do something"
        mock_meta.description = "A new skill"

        sync = RegistrySync(registry_path=registry_file, skills_dir=tmp_path / "skills")
        with patch("vibesop.core.skills.registry_sync.parse_skill_md", return_value=mock_meta):
            report = sync.sync()

        assert "new-skill" in report["added"]
        assert report["total"] == 1

    def test_sync_updates_changed_intent(self, tmp_path: Path):
        registry_file = tmp_path / "registry.yaml"
        registry_file.write_text(
            "schema_version: 1\nskills:\n  - id: existing\n    namespace: builtin\n    intent: old intent\n"
        )

        skill_dir = tmp_path / "skills" / "existing"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Existing\n")

        mock_meta = MagicMock()
        mock_meta.id = "existing"
        mock_meta.intent = "new intent"
        mock_meta.description = ""

        sync = RegistrySync(registry_path=registry_file, skills_dir=tmp_path / "skills")
        with patch("vibesop.core.skills.registry_sync.parse_skill_md", return_value=mock_meta):
            report = sync.sync()

        assert "existing" in report["updated"]

    def test_sync_preserves_non_builtin(self, tmp_path: Path):
        registry_file = tmp_path / "registry.yaml"
        registry_file.write_text(
            "schema_version: 1\nskills:\n  - id: external\n    namespace: external\n"
        )

        sync = RegistrySync(registry_path=registry_file, skills_dir=tmp_path / "skills")
        with patch.object(sync, "_discover_builtin_skills", return_value={}):
            report = sync.sync()

        assert "external" not in report["added"]
        assert report["total"] == 1

    def test_sync_unchanged(self, tmp_path: Path):
        registry_file = tmp_path / "registry.yaml"
        registry_file.write_text(
            "schema_version: 1\nskills:\n  - id: same\n    namespace: builtin\n    intent: same\n"
        )

        skill_dir = tmp_path / "skills" / "same"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Same\n")

        mock_meta = MagicMock()
        mock_meta.id = "same"
        mock_meta.intent = "same"
        mock_meta.description = ""

        sync = RegistrySync(registry_path=registry_file, skills_dir=tmp_path / "skills")
        with patch("vibesop.core.skills.registry_sync.parse_skill_md", return_value=mock_meta):
            report = sync.sync()

        assert "same" in report["unchanged"]
