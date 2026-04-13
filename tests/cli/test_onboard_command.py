"""Tests for vibe onboard command."""

from unittest.mock import patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestOnboardCommand:
    """Test suite for onboard command."""

    @patch("vibesop.installer.init_support.InitSupport.init_project")
    def test_onboard_full(self, mock_init) -> None:
        """Test full onboarding flow."""
        mock_init.return_value = {"success": True, "created_files": []}

        result = runner.invoke(app, ["onboard"])
        assert result.exit_code == 0
        assert "Welcome to VibeSOP" in result.stdout
        assert "Onboarding complete" in result.stdout
        assert "Step 3: Deploy" in result.stdout
        assert "Step 4: Integrations" in result.stdout
        mock_init.assert_called_once()

    @patch("vibesop.installer.init_support.InitSupport.init_project")
    def test_onboard_skip_deploy(self, mock_init) -> None:
        """Test onboarding with --skip-deploy."""
        mock_init.return_value = {"success": True, "created_files": []}

        result = runner.invoke(app, ["onboard", "--skip-deploy"])
        assert result.exit_code == 0
        assert "Onboarding complete" in result.stdout
        assert "Step 3: Deploy" in result.stdout
        assert "skipped" in result.stdout

    @patch("vibesop.installer.init_support.InitSupport.init_project")
    def test_onboard_skip_integrations(self, mock_init) -> None:
        """Test onboarding with --skip-integrations."""
        mock_init.return_value = {"success": True, "created_files": []}

        result = runner.invoke(app, ["onboard", "--skip-integrations"])
        assert result.exit_code == 0
        assert "Onboarding complete" in result.stdout
        assert "Step 4: Integrations" in result.stdout
        assert "skipped" in result.stdout

    @patch("vibesop.installer.init_support.InitSupport.init_project")
    def test_onboard_init_failure(self, mock_init) -> None:
        """Test onboarding when initialization fails."""
        mock_init.return_value = {"success": False, "errors": ["Permission denied"]}

        result = runner.invoke(app, ["onboard"])
        assert result.exit_code == 1
        assert "Initialization failed" in result.stdout
