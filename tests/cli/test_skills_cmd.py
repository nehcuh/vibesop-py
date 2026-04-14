"""Tests for vibe skills subcommands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestSkillsList:
    """Tests for vibe skills list."""

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_list_simple(self, mock_storage_cls) -> None:
        mock_storage = MagicMock()
        mock_storage.list_skills.return_value = {"skill-a": MagicMock(), "skill-b": MagicMock()}
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "list"])
        assert result.exit_code == 0
        assert "Installed Skills" in result.stdout
        assert "skill-a" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_list_all(self, mock_storage_cls) -> None:
        mock_storage = MagicMock()
        manifest = MagicMock()
        manifest.name = "Skill A"
        manifest.version = "1.0"
        manifest.source.type = "builtin"
        manifest.source.version = None
        manifest.installed_at = "2024-01-01T00:00:00"
        mock_storage.list_skills.return_value = {"skill-a": manifest}
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "list", "--all"])
        assert result.exit_code == 0
        assert "Installed Skills" in result.stdout or "Skill A" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_list_platform(self, mock_storage_cls) -> None:
        mock_storage = MagicMock()
        mock_storage.PLATFORM_SKILLS_DIRS = {"claude-code": Path("/tmp/claude")}
        mock_storage.get_linked_skills.return_value = ["skill-a"]
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "list", "--platform", "claude-code"])
        assert result.exit_code == 0
        assert "Skills linked to claude-code" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_list_unknown_platform(self, mock_storage_cls) -> None:
        mock_storage = MagicMock()
        mock_storage.PLATFORM_SKILLS_DIRS = {}
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "list", "--platform", "unknown"])
        assert result.exit_code == 1
        assert "Unknown platform" in result.stdout


class TestSkillsInstall:
    """Tests for vibe skills install."""

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_install_from_url(self, mock_storage_cls) -> None:
        mock_storage = MagicMock()
        mock_storage.install_from_remote.return_value = (True, "Installed from URL")
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "install", "my-skill", "--url", "https://example.com/skill.tar.gz"])
        assert result.exit_code == 0
        assert "Installed from URL" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_install_from_source(self, mock_storage_cls, tmp_path) -> None:
        mock_storage = MagicMock()
        mock_storage.install_skill.return_value = (True, "Installed from source")
        mock_storage_cls.return_value = mock_storage

        source_dir = tmp_path / "my-skill"
        source_dir.mkdir()
        result = runner.invoke(app, ["skills", "install", "my-skill", "--source", str(source_dir)])
        assert result.exit_code == 0
        assert "Installed from source" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_install_not_found(self, mock_storage_cls, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "install", "missing-skill"])
        assert result.exit_code == 1
        assert "Skill not found in project" in result.stdout


class TestSkillsLinkUnlink:
    """Tests for vibe skills link and unlink."""

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_link_success(self, mock_storage_cls) -> None:
        mock_storage = MagicMock()
        mock_storage.link_to_platform.return_value = (True, "Linked")
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "link", "my-skill", "claude-code"])
        assert result.exit_code == 0
        assert "Linked" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_link_failure(self, mock_storage_cls) -> None:
        mock_storage = MagicMock()
        mock_storage.link_to_platform.return_value = (False, "Already linked")
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "link", "my-skill", "claude-code"])
        assert result.exit_code == 1
        assert "Already linked" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_unlink_success(self, mock_storage_cls) -> None:
        mock_storage = MagicMock()
        mock_storage.unlink_from_platform.return_value = (True, "Unlinked")
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "unlink", "my-skill", "claude-code"])
        assert result.exit_code == 0
        assert "Unlinked" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_unlink_failure(self, mock_storage_cls) -> None:
        mock_storage = MagicMock()
        mock_storage.unlink_from_platform.return_value = (False, "Not linked")
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "unlink", "my-skill", "claude-code"])
        assert result.exit_code == 1
        assert "Not linked" in result.stdout


class TestSkillsRemove:
    """Tests for vibe skills remove."""

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_remove_success(self, mock_storage_cls, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)
        mock_storage = MagicMock()
        mock_storage.PLATFORM_SKILLS_DIRS = {"claude-code": tmp_path / "claude"}
        mock_storage.remove_skill.return_value = (True, "Removed")
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "remove", "my-skill"])
        assert result.exit_code == 0
        assert "Removed" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_remove_linked_without_flag(self, mock_storage_cls, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)
        platform_dir = tmp_path / "claude"
        platform_dir.mkdir()
        skill_link = platform_dir / "my-skill"
        skill_link.symlink_to("/dev/null")

        mock_storage = MagicMock()
        mock_storage.PLATFORM_SKILLS_DIRS = {"claude-code": platform_dir}
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "remove", "my-skill"])
        assert result.exit_code == 1
        assert "Skill is linked to" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_remove_with_unlink_all(self, mock_storage_cls, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)
        mock_storage = MagicMock()
        mock_storage.PLATFORM_SKILLS_DIRS = {"claude-code": tmp_path / "claude"}
        mock_storage.remove_skill.return_value = (True, "Removed")
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "remove", "my-skill", "--unlink-all"])
        assert result.exit_code == 0
        assert "Removed" in result.stdout


class TestSkillsStatus:
    """Tests for vibe skills status."""

    @patch("vibesop.cli.commands.skills_cmd.SkillStorage")
    def test_status(self, mock_storage_cls, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)
        mock_storage = MagicMock()
        mock_storage.CENTRAL_SKILLS_DIR = tmp_path / ".skills"
        mock_storage.CENTRAL_SKILLS_DIR.mkdir()
        mock_storage.list_skills.return_value = {}
        mock_storage.PLATFORM_SKILLS_DIRS = {"claude-code": tmp_path / "claude"}
        mock_storage.get_linked_skills.return_value = []
        mock_storage_cls.return_value = mock_storage

        result = runner.invoke(app, ["skills", "status"])
        assert result.exit_code == 0
        assert "Skill Storage Status" in result.stdout


class TestSkillsAvailable:
    """Tests for vibe skills available."""

    @patch("vibesop.cli.commands.skills_cmd.SkillManager")
    def test_available_empty(self, mock_mgr_cls) -> None:
        mock_mgr = MagicMock()
        mock_mgr.list_skills.return_value = []
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(app, ["skills", "available"])
        assert result.exit_code == 0
        assert "No skills found" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillManager")
    def test_available_with_skills(self, mock_mgr_cls) -> None:
        mock_mgr = MagicMock()
        mock_mgr.list_skills.return_value = [
            {"id": "debug", "name": "Debug", "description": "Debug skill", "namespace": "builtin"},
        ]
        mock_mgr.get_stats.return_value = {"namespaces": ["builtin"]}
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(app, ["skills", "available"])
        assert result.exit_code == 0
        assert "Available Skills" in result.stdout
        assert "debug" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillManager")
    def test_available_verbose(self, mock_mgr_cls) -> None:
        mock_mgr = MagicMock()
        mock_mgr.list_skills.return_value = [
            {"id": "debug", "name": "Debug", "description": "Debug skill", "namespace": "builtin", "type": "prompt", "tags": ["dev"], "source": "builtin"},
        ]
        mock_mgr.get_stats.return_value = {"namespaces": ["builtin"]}
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(app, ["skills", "available", "--verbose"])
        assert result.exit_code == 0
        assert "Debug skill" in result.stdout


class TestSkillsInfo:
    """Tests for vibe skills info."""

    @patch("vibesop.cli.commands.skills_cmd.SkillManager")
    def test_info_found(self, mock_mgr_cls) -> None:
        mock_mgr = MagicMock()
        mock_mgr.get_skill_info.return_value = {
            "id": "debug",
            "name": "Debug Skill",
            "type": "prompt",
            "namespace": "builtin",
            "version": "1.0.0",
            "author": "Test",
            "source": "builtin",
            "description": "A debug skill",
            "intent": "Debug things",
            "tags": ["dev"],
            "source_file": "/tmp/debug.md",
        }
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(app, ["skills", "info", "debug"])
        assert result.exit_code == 0
        assert "Debug Skill" in result.stdout
        assert "Debug things" in result.stdout

    @patch("vibesop.cli.commands.skills_cmd.SkillManager")
    def test_info_not_found(self, mock_mgr_cls) -> None:
        mock_mgr = MagicMock()
        mock_mgr.get_skill_info.return_value = None
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(app, ["skills", "info", "missing"])
        assert result.exit_code == 1
        assert "Skill not found" in result.stdout
