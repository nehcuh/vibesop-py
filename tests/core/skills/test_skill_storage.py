"""Tests for SkillStorage."""

from pathlib import Path

import pytest

from vibesop.core.skills.storage import (
    SkillManifest,
    SkillSource,
    SkillStorage,
    get_storage,
    install_skill_from_project,
    link_all_to_platform,
)


class TestSkillSource:
    """Test SkillSource dataclass."""

    def test_creation(self):
        src = SkillSource(type="local", path="/path")
        assert src.type == "local"
        assert src.path == "/path"
        assert src.version is None
        assert src.ref is None


class TestSkillManifest:
    """Test SkillManifest dataclass."""

    def test_creation(self):
        src = SkillSource(type="local", path="/path")
        manifest = SkillManifest(
            id="test",
            name="Test",
            description="Desc",
            version="1.0.0",
            source=src,
            installed_at="2024-01-01",
            checksum="abc123",
        )
        assert manifest.id == "test"
        assert manifest.checksum == "abc123"


class TestSkillStoragePaths:
    """Test path resolution."""

    def test_get_skill_path(self):
        storage = SkillStorage(dry_run=True)
        path = storage.get_skill_path("test-skill")
        assert path.name == "test-skill"
        assert "skills" in str(path)

    def test_get_platform_skill_path_valid(self):
        storage = SkillStorage(dry_run=True)
        path = storage.get_platform_skill_path("test", "claude-code")
        assert path.name == "test"
        assert ".claude" in str(path)

    def test_get_platform_skill_path_invalid(self):
        storage = SkillStorage(dry_run=True)
        with pytest.raises(ValueError, match="Unknown platform"):
            storage.get_platform_skill_path("test", "unknown")


class TestSkillStorageDryRun:
    """Test dry-run mode operations."""

    def test_install_skill_dry_run(self, tmp_path: Path):
        storage = SkillStorage(dry_run=True)
        source = tmp_path / "source"
        source.mkdir()
        (source / "SKILL.md").write_text("# Test")

        success, msg = storage.install_skill("test-skill", source)
        assert success is True
        assert "Would install" in msg

    def test_install_skill_missing_source(self, tmp_path: Path):
        storage = SkillStorage(dry_run=False)
        success, msg = storage.install_skill("test", tmp_path / "missing")
        assert success is False
        assert "not found" in msg.lower()

    def test_link_to_platform_dry_run(self, tmp_path: Path):
        storage = SkillStorage(dry_run=True)
        # Create skill in central storage so existence check passes
        skill_path = storage.get_skill_path("test")
        skill_path.mkdir(parents=True, exist_ok=True)
        success, msg = storage.link_to_platform("test", "claude-code")
        assert success is True
        assert "Would link" in msg

    def test_link_to_platform_unknown(self):
        storage = SkillStorage(dry_run=True)
        success, msg = storage.link_to_platform("test", "unknown")
        assert success is False
        assert "Unknown platform" in msg

    def test_unlink_from_platform_nothing_to_unlink(self, tmp_path: Path):
        storage = SkillStorage(dry_run=True)
        success, msg = storage.unlink_from_platform("test", "claude-code")
        assert success is True
        assert "Nothing to unlink" in msg

    def test_remove_skill_dry_run(self, tmp_path: Path):
        storage = SkillStorage(dry_run=True)
        # Create skill in central storage so existence check passes
        skill_path = storage.get_skill_path("test")
        skill_path.mkdir(parents=True, exist_ok=True)
        success, msg = storage.remove_skill("test")
        assert success is True
        assert "Would remove" in msg


class TestSkillStorageReal:
    """Test real filesystem operations."""

    def test_install_skill(self, tmp_path: Path):
        # Override central dir to tmp_path
        storage = SkillStorage(dry_run=False)
        original_dir = storage.CENTRAL_SKILLS_DIR
        storage.CENTRAL_SKILLS_DIR = tmp_path / "central"

        source = tmp_path / "source"
        source.mkdir()
        (source / "SKILL.md").write_text("# Test Skill")

        try:
            success, _msg = storage.install_skill("test-skill", source)
            assert success is True
            assert (storage.get_skill_path("test-skill") / "SKILL.md").exists()
        finally:
            storage.CENTRAL_SKILLS_DIR = original_dir

    def test_skill_exists(self, tmp_path: Path):
        storage = SkillStorage(dry_run=False)
        original_dir = storage.CENTRAL_SKILLS_DIR
        storage.CENTRAL_SKILLS_DIR = tmp_path / "central"

        try:
            assert storage.skill_exists("missing") is False
            skill_path = storage.get_skill_path("test")
            skill_path.mkdir(parents=True)
            (skill_path / "SKILL.md").write_text("# Test")
            assert storage.skill_exists("test") is True
        finally:
            storage.CENTRAL_SKILLS_DIR = original_dir

    def test_list_skills_empty(self, tmp_path: Path):
        storage = SkillStorage(dry_run=False)
        original_dir = storage.CENTRAL_SKILLS_DIR
        storage.CENTRAL_SKILLS_DIR = tmp_path / "central"

        try:
            skills = storage.list_skills()
            assert skills == {}
        finally:
            storage.CENTRAL_SKILLS_DIR = original_dir

    def test_remove_skill_real(self, tmp_path: Path):
        storage = SkillStorage(dry_run=False)
        original_dir = storage.CENTRAL_SKILLS_DIR
        storage.CENTRAL_SKILLS_DIR = tmp_path / "central"

        source = tmp_path / "source"
        source.mkdir()
        (source / "SKILL.md").write_text("# Test")

        try:
            storage.install_skill("test", source)
            assert storage.skill_exists("test") is True
            success, _msg = storage.remove_skill("test")
            assert success is True
            assert storage.skill_exists("test") is False
        finally:
            storage.CENTRAL_SKILLS_DIR = original_dir

    def test_remove_skill_not_found(self, tmp_path: Path):
        storage = SkillStorage(dry_run=False)
        original_dir = storage.CENTRAL_SKILLS_DIR
        storage.CENTRAL_SKILLS_DIR = tmp_path / "central"

        try:
            success, msg = storage.remove_skill("missing")
            assert success is False
            assert "not found" in msg.lower()
        finally:
            storage.CENTRAL_SKILLS_DIR = original_dir


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_get_storage(self):
        storage = get_storage()
        assert isinstance(storage, SkillStorage)
        assert storage.dry_run is False

    def test_install_skill_from_project_no_source(self, tmp_path: Path):
        success, msg = install_skill_from_project("missing", project_root=tmp_path)
        assert success is False
        assert "not found" in msg.lower()

    def test_link_all_to_platform_no_skills(self, tmp_path: Path):
        installed, linked, _messages = link_all_to_platform("claude-code", project_root=tmp_path)
        assert installed == 0
        assert linked == 0
