"""Tests for all installers."""

import pytest
from pathlib import Path
import tempfile

from vibesop.installer import (
    VibeSOPInstaller,
    GstackInstaller,
    SuperpowersInstaller,
    SkillInstaller,
    InitSupport,
    QuickstartRunner,
)


class TestSkillInstaller:
    """Test SkillInstaller functionality."""

    def test_create_installer(self) -> None:
        """Test creating skill installer."""
        installer = SkillInstaller()
        assert installer is not None

    def test_list_skills_empty_project(self, tmp_path: Path) -> None:
        """Test listing skills in empty project."""
        installer = SkillInstaller()
        skills = installer.list_skills(tmp_path)

        assert isinstance(skills, list)
        assert len(skills) == 0

    def test_verify_skill_not_installed(self, tmp_path: Path) -> None:
        """Test verifying non-existent skill."""
        installer = SkillInstaller()
        result = installer.verify_skill("test-skill", tmp_path)

        assert result["skill_id"] == "test-skill"
        assert not result["installed"]


class TestInitSupport:
    """Test InitSupport functionality."""

    def test_create_init_support(self) -> None:
        """Test creating init support."""
        init_support = InitSupport()
        assert init_support is not None

    def test_init_project(self, tmp_path: Path) -> None:
        """Test initializing a project."""
        init_support = InitSupport()
        result = init_support.init_project(tmp_path, "claude-code")

        assert result["success"]
        assert len(result["created_dirs"]) > 0
        assert len(result["created_files"]) > 0

        # Verify directories created
        vibe_dir = tmp_path / ".vibe"
        assert vibe_dir.exists()
        assert (vibe_dir / "skills").exists()
        assert (vibe_dir / "config.yaml").exists()

    def test_verify_init(self, tmp_path: Path) -> None:
        """Test verifying project initialization."""
        init_support = InitSupport()

        # Before initialization
        result = init_support.verify_init(tmp_path)
        assert not result["initialized"]

        # Initialize
        init_support.init_project(tmp_path, "claude-code")

        # After initialization
        result = init_support.verify_init(tmp_path)
        assert result["initialized"]
        assert result["vibe_dir_exists"]
        assert result["config_exists"]


class TestGstackInstaller:
    """Test GstackInstaller functionality."""

    def test_create_installer(self) -> None:
        """Test creating gstack installer."""
        installer = GstackInstaller()
        assert installer is not None

    def test_verify_not_installed(self) -> None:
        """Test verifying gstack installation status."""
        installer = GstackInstaller()
        result = installer.verify()

        # May be installed or not - just verify structure
        assert result["path"] is not None
        assert isinstance(result["installed"], bool)
        assert "git_repo" in result


class TestSuperpowersInstaller:
    """Test SuperpowersInstaller functionality."""

    def test_create_installer(self) -> None:
        """Test creating superpowers installer."""
        installer = SuperpowersInstaller()
        assert installer is not None

    def test_verify_not_installed(self) -> None:
        """Test verifying superpowers installation status."""
        installer = SuperpowersInstaller()
        result = installer.verify()

        # May be installed or not - just verify structure
        assert result["path"] is not None
        assert isinstance(result["installed"], bool)
        assert "git_repo" in result


class TestQuickstartRunner:
    """Test QuickstartRunner functionality."""

    def test_create_runner(self) -> None:
        """Test creating quickstart runner."""
        runner = QuickstartRunner()
        assert runner is not None

    def test_supported_platforms(self) -> None:
        """Test getting supported platforms."""
        runner = QuickstartRunner()

        assert "claude-code" in runner._supported_platforms
        assert "opencode" in runner._supported_platforms

    def test_available_integrations(self) -> None:
        """Test getting available integrations."""
        runner = QuickstartRunner()

        assert "gstack" in runner._available_integrations
        assert "superpowers" in runner._available_integrations


class TestInstallerIntegration:
    """Integration tests for all installers."""

    def test_full_init_workflow(self, tmp_path: Path) -> None:
        """Test complete initialization workflow."""
        # Initialize project
        init_support = InitSupport()
        init_result = init_support.init_project(tmp_path, "claude-code")

        assert init_result["success"]

        # Verify initialization
        verify_result = init_support.verify_init(tmp_path)
        assert verify_result["initialized"]

    def test_skill_install_after_init(self, tmp_path: Path) -> None:
        """Test installing skill after initialization."""
        # Initialize project
        init_support = InitSupport()
        init_support.init_project(tmp_path, "claude-code")

        # Create a test skill
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text("# Test Skill\n\nA test skill.")

        # Install skill
        skill_installer = SkillInstaller()
        result = skill_installer.install_skill(skill_dir, tmp_path)

        # Note: This might fail due to missing dependencies, which is expected
        assert result["skill_id"] == "test-skill"
