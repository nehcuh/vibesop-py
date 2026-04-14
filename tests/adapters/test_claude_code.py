"""Tests for Claude Code adapter."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from vibesop.adapters.claude_code import ClaudeCodeAdapter
from vibesop.adapters.models import Manifest


class TestClaudeCodeAdapter:
    """Tests for ClaudeCodeAdapter."""

    def test_platform_name(self) -> None:
        adapter = ClaudeCodeAdapter()
        assert adapter.platform_name == "claude-code"

    def test_config_dir(self) -> None:
        adapter = ClaudeCodeAdapter()
        assert adapter.config_dir == Path("~/.claude").expanduser()

    def test_get_template_env_caching(self) -> None:
        adapter = ClaudeCodeAdapter()
        env1 = adapter._get_template_env()
        env2 = adapter._get_template_env()
        assert env1 is env2

    @patch.object(ClaudeCodeAdapter, "validate_manifest")
    def test_render_config_success(self, mock_validate, monkeypatch, tmp_path) -> None:
        """Test render_config successful path."""
        monkeypatch.chdir(tmp_path)
        adapter = ClaudeCodeAdapter()
        mock_validate.return_value = []

        manifest = MagicMock()
        manifest.skills = []
        manifest.policies.behavior = {}
        result = adapter.render_config(manifest, tmp_path / "output")

        assert result.success is True

    @patch.object(ClaudeCodeAdapter, "validate_manifest")
    def test_render_config_invalid_manifest(self, mock_validate, tmp_path) -> None:
        """Test render_config with invalid manifest."""
        adapter = ClaudeCodeAdapter()
        mock_validate.return_value = ["Missing platform"]

        manifest = MagicMock(spec=Manifest)
        result = adapter.render_config(manifest, tmp_path / "output")

        assert result.success is False
        assert "Missing platform" in result.errors
