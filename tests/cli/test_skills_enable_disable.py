"""Tests for CLI skill enable/disable commands."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestSkillEnableCommand:
    """Test `vibe skills enable` command."""

    @patch("vibesop.cli.commands.skills_cmd.SkillConfigManager")
    @patch("vibesop.cli.commands.skills_cmd.SkillManager")
    def test_enable_existing_skill(self, mock_manager_cls, mock_config_mgr_cls):
        """Enable should update config for an existing skill."""
        mock_manager = MagicMock()
        mock_manager.get_skill_info.return_value = {"id": "my-skill", "name": "My Skill"}
        mock_manager_cls.return_value = mock_manager

        mock_config = MagicMock()
        mock_config.enabled = False
        mock_config_mgr_cls.get_skill_config.return_value = mock_config

        result = runner.invoke(app, ["skills", "enable", "my-skill"])

        assert result.exit_code == 0
        mock_config_mgr_cls.update_skill_config.assert_called_once_with(
            "my-skill", {"enabled": True}
        )
        assert "enabled" in result.output.lower()

    @patch("vibesop.cli.commands.skills_cmd.SkillManager")
    def test_enable_nonexistent_skill(self, mock_manager_cls):
        """Enable should fail for a non-existent skill."""
        mock_manager = MagicMock()
        mock_manager.get_skill_info.return_value = None
        mock_manager_cls.return_value = mock_manager

        result = runner.invoke(app, ["skills", "enable", "nonexistent-skill"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @patch("vibesop.cli.commands.skills_cmd.SkillConfigManager")
    @patch("vibesop.cli.commands.skills_cmd.SkillManager")
    def test_enable_already_enabled(self, mock_manager_cls, mock_config_mgr_cls):
        """Enable should warn if skill is already enabled."""
        mock_manager = MagicMock()
        mock_manager.get_skill_info.return_value = {"id": "my-skill", "name": "My Skill"}
        mock_manager_cls.return_value = mock_manager

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config_mgr_cls.get_skill_config.return_value = mock_config

        result = runner.invoke(app, ["skills", "enable", "my-skill"])

        assert result.exit_code == 0
        assert "already enabled" in result.output.lower()
        mock_config_mgr_cls.update_skill_config.assert_not_called()


class TestSkillDisableCommand:
    """Test `vibe skills disable` command."""

    @patch("vibesop.cli.commands.skills_cmd.SkillConfigManager")
    @patch("vibesop.cli.commands.skills_cmd.SkillManager")
    def test_disable_existing_skill(self, mock_manager_cls, mock_config_mgr_cls):
        """Disable should update config for an existing skill."""
        mock_manager = MagicMock()
        mock_manager.get_skill_info.return_value = {"id": "my-skill", "name": "My Skill"}
        mock_manager_cls.return_value = mock_manager

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config_mgr_cls.get_skill_config.return_value = mock_config

        result = runner.invoke(app, ["skills", "disable", "my-skill"])

        assert result.exit_code == 0
        mock_config_mgr_cls.update_skill_config.assert_called_once_with(
            "my-skill", {"enabled": False}
        )
        assert "disabled" in result.output.lower()

    @patch("vibesop.cli.commands.skills_cmd.SkillManager")
    def test_disable_nonexistent_skill(self, mock_manager_cls):
        """Disable should fail for a non-existent skill."""
        mock_manager = MagicMock()
        mock_manager.get_skill_info.return_value = None
        mock_manager_cls.return_value = mock_manager

        result = runner.invoke(app, ["skills", "disable", "nonexistent-skill"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @patch("vibesop.cli.commands.skills_cmd.SkillConfigManager")
    @patch("vibesop.cli.commands.skills_cmd.SkillManager")
    def test_disable_already_disabled(self, mock_manager_cls, mock_config_mgr_cls):
        """Disable should warn if skill is already disabled."""
        mock_manager = MagicMock()
        mock_manager.get_skill_info.return_value = {"id": "my-skill", "name": "My Skill"}
        mock_manager_cls.return_value = mock_manager

        mock_config = MagicMock()
        mock_config.enabled = False
        mock_config_mgr_cls.get_skill_config.return_value = mock_config

        result = runner.invoke(app, ["skills", "disable", "my-skill"])

        assert result.exit_code == 0
        assert "already disabled" in result.output.lower()
        mock_config_mgr_cls.update_skill_config.assert_not_called()
