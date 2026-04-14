"""Tests for vibe build command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


def _make_manifest():
    manifest = MagicMock()
    manifest.metadata.platform = "claude-code"
    manifest.metadata.version = "1.0.0"
    manifest.skills = []
    manifest.policies.behavior = {}
    return manifest


class TestBuildCommand:
    """Test suite for build command."""

    def test_build_invalid_target(self) -> None:
        """Test build with invalid target."""
        result = runner.invoke(app, ["build", "invalid-target"])
        assert result.exit_code == 1
        assert "Invalid target" in result.stdout

    def test_build_invalid_profile(self) -> None:
        """Test build with invalid profile."""
        result = runner.invoke(app, ["build", "claude-code", "--profile", "invalid"])
        assert result.exit_code == 1
        assert "Invalid profile" in result.stdout

    @patch("vibesop.cli.commands.build.ConfigRenderer")
    @patch("vibesop.cli.commands.build.ManifestBuilder")
    def test_build_success(self, mock_builder_cls, mock_renderer_cls, monkeypatch, tmp_path) -> None:
        """Test successful build."""
        monkeypatch.chdir(tmp_path)
        manifest = _make_manifest()
        mock_builder = MagicMock()
        mock_builder.build_from_registry.return_value = manifest
        mock_builder_cls.return_value = mock_builder

        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock(files_created=[str(tmp_path / "test.md")])
        mock_renderer_cls.return_value = mock_renderer

        result = runner.invoke(app, ["build", "claude-code"])
        assert result.exit_code == 0
        assert "Build complete" in result.stdout
        mock_builder.build_from_registry.assert_called_once_with(platform="claude-code")

    @patch("vibesop.cli.commands.build.ConfigRenderer")
    @patch("vibesop.cli.commands.build.ManifestBuilder")
    def test_build_with_overlay(self, mock_builder_cls, mock_renderer_cls, monkeypatch, tmp_path) -> None:
        """Test build with overlay file."""
        monkeypatch.chdir(tmp_path)
        overlay_file = tmp_path / "overlay.yaml"
        overlay_file.write_text("{}")

        manifest = _make_manifest()
        mock_builder = MagicMock()
        mock_builder.build.return_value = manifest
        mock_builder_cls.return_value = mock_builder

        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock(files_created=[])
        mock_renderer_cls.return_value = mock_renderer

        result = runner.invoke(app, ["build", "claude-code", "--overlay", str(overlay_file)])
        assert result.exit_code == 0
        assert "Applying overlay" in result.stdout
        mock_builder.build.assert_called_once_with(overlay_path=Path(str(overlay_file)), platform="claude-code")

    @patch("vibesop.cli.commands.build.ManifestBuilder")
    def test_build_verify(self, mock_builder_cls, monkeypatch, tmp_path) -> None:
        """Test build --verify."""
        monkeypatch.chdir(tmp_path)
        manifest = _make_manifest()
        mock_builder = MagicMock()
        mock_builder.build_from_registry.return_value = manifest
        mock_builder_cls.return_value = mock_builder

        result = runner.invoke(app, ["build", "claude-code", "--verify"])
        assert result.exit_code == 0
        assert "Verification Mode" in result.stdout
        assert "No files were written" in result.stdout

    @patch("vibesop.cli.commands.build.ManifestBuilder")
    def test_build_file_not_found(self, mock_builder_cls, monkeypatch, tmp_path) -> None:
        """Test build when FileNotFoundError is raised."""
        monkeypatch.chdir(tmp_path)
        mock_builder = MagicMock()
        mock_builder.build_from_registry.side_effect = FileNotFoundError("manifest.yaml missing")
        mock_builder_cls.return_value = mock_builder

        result = runner.invoke(app, ["build", "claude-code"])
        assert result.exit_code == 1
        assert "File not found" in result.stdout

    @patch("vibesop.cli.commands.build.ManifestBuilder")
    def test_build_value_error(self, mock_builder_cls, monkeypatch, tmp_path) -> None:
        """Test build when ValueError is raised."""
        monkeypatch.chdir(tmp_path)
        mock_builder = MagicMock()
        mock_builder.build_from_registry.side_effect = ValueError("Invalid config")
        mock_builder_cls.return_value = mock_builder

        result = runner.invoke(app, ["build", "claude-code"])
        assert result.exit_code == 1
        assert "Configuration error" in result.stdout

    @patch("vibesop.cli.commands.build.ConfigRenderer")
    @patch("vibesop.cli.commands.build.ManifestBuilder")
    def test_build_deployed_output(self, mock_builder_cls, mock_renderer_cls, monkeypatch, tmp_path) -> None:
        """Test build when output matches Claude Code deploy path."""
        monkeypatch.chdir(tmp_path)
        manifest = _make_manifest()
        mock_builder = MagicMock()
        mock_builder.build_from_registry.return_value = manifest
        mock_builder_cls.return_value = mock_builder

        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock(files_created=[])
        mock_renderer_cls.return_value = mock_renderer

        output_dir = tmp_path / "deploy"
        result = runner.invoke(app, ["build", "claude-code", "--output", str(output_dir)])
        assert result.exit_code == 0
        assert "Build complete" in result.stdout
        assert "Review generated files" in result.stdout

    @patch("vibesop.cli.commands.build.ConfigRenderer")
    @patch("vibesop.cli.commands.build.ManifestBuilder")
    def test_build_no_target_uses_default(self, mock_builder_cls, mock_renderer_cls, monkeypatch, tmp_path) -> None:
        """Test build without target uses default claude-code."""
        monkeypatch.chdir(tmp_path)
        manifest = _make_manifest()
        mock_builder = MagicMock()
        mock_builder.build_from_registry.return_value = manifest
        mock_builder_cls.return_value = mock_builder

        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock(files_created=[])
        mock_renderer_cls.return_value = mock_renderer

        result = runner.invoke(app, ["build"])
        assert result.exit_code == 0
        assert "No platform specified, using default" in result.stdout
        mock_builder.build_from_registry.assert_called_once_with(platform="claude-code")

    @patch("vibesop.cli.commands.build.ConfigRenderer")
    @patch("vibesop.cli.commands.build.ManifestBuilder")
    @patch("vibesop.cli.commands.build._get_configured_platform")
    def test_build_no_target_uses_config(self, mock_get_platform, mock_builder_cls, mock_renderer_cls, monkeypatch, tmp_path) -> None:
        """Test build without target uses configured platform."""
        monkeypatch.chdir(tmp_path)
        mock_get_platform.return_value = "opencode"

        manifest = _make_manifest()
        mock_builder = MagicMock()
        mock_builder.build_from_registry.return_value = manifest
        mock_builder_cls.return_value = mock_builder

        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock(files_created=[])
        mock_renderer_cls.return_value = mock_renderer

        result = runner.invoke(app, ["build"])
        assert result.exit_code == 0
        assert "Using configured platform: opencode" in result.stdout
        mock_builder.build_from_registry.assert_called_once_with(platform="opencode")

    @patch("vibesop.cli.commands.build.ConfigRenderer")
    @patch("vibesop.cli.commands.build.ManifestBuilder")
    def test_build_file_outside_cwd(self, mock_builder_cls, mock_renderer_cls, monkeypatch, tmp_path) -> None:
        """Test build when created file is outside current directory."""
        monkeypatch.chdir(tmp_path)
        manifest = _make_manifest()
        mock_builder = MagicMock()
        mock_builder.build_from_registry.return_value = manifest
        mock_builder_cls.return_value = mock_builder

        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock(files_created=["/absolute/path/to/file.md"])
        mock_renderer_cls.return_value = mock_renderer

        result = runner.invoke(app, ["build", "claude-code"])
        assert result.exit_code == 0
        assert "/absolute/path/to/file.md" in result.stdout

    @patch("vibesop.cli.commands.build.ConfigRenderer")
    @patch("vibesop.cli.commands.build.ManifestBuilder")
    def test_build_deploy_to_claude_dir(self, mock_builder_cls, mock_renderer_cls, monkeypatch, tmp_path) -> None:
        """Test build when output is ~/.claude."""
        monkeypatch.chdir(tmp_path)
        manifest = _make_manifest()
        mock_builder = MagicMock()
        mock_builder.build_from_registry.return_value = manifest
        mock_builder_cls.return_value = mock_builder

        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock(files_created=[])
        mock_renderer_cls.return_value = mock_renderer

        claude_dir = tmp_path / "home" / ".claude"
        claude_dir.mkdir(parents=True)
        # Patch Path.home to return our temp home
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = runner.invoke(app, ["build", "claude-code", "--output", str(claude_dir)])
        assert result.exit_code == 0
        assert "Deployed to Claude Code" in result.stdout

    @patch("vibesop.cli.commands.build.ManifestBuilder")
    def test_build_generic_exception(self, mock_builder_cls, monkeypatch, tmp_path) -> None:
        """Test build when generic exception is raised."""
        monkeypatch.chdir(tmp_path)
        mock_builder = MagicMock()
        mock_builder.build_from_registry.side_effect = RuntimeError("Unexpected failure")
        mock_builder_cls.return_value = mock_builder

        result = runner.invoke(app, ["build", "claude-code"])
        assert result.exit_code == 1
        assert "Build failed" in result.stdout

    def test_get_configured_platform_from_config(self, monkeypatch, tmp_path) -> None:
        """Test _get_configured_platform reads config.yaml."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".vibe"
        config_dir.mkdir()
        (config_dir / "config.yaml").write_text("platform: opencode\n")

        from vibesop.cli.commands.build import _get_configured_platform
        assert _get_configured_platform() == "opencode"
