"""Tests for Claude Code adapter."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


class TestClaudeCodeHookRendering:
    """Tests for Claude Code hook script rendering.

    These tests verify that the vibesop-route.sh hook template renders
    correctly and contains all critical cross-platform and functional logic.
    Without them, macOS compatibility fixes (e.g., sha256sum → shasum)
    can silently regress.
    """

    @pytest.fixture
    def adapter(self):
        return ClaudeCodeAdapter()

    def test_route_hook_renders(self, adapter, tmp_path):
        """The route hook template renders and produces an executable file."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        hook_path = tmp_path / "hooks" / "vibesop-route.sh"
        assert hook_path.exists(), "vibesop-route.sh should be created"
        assert hook_path.stat().st_mode & 0o111, "Hook should be executable"
        result.add_file.assert_called_once_with(hook_path)
        result.add_warning.assert_not_called()

    def test_route_hook_has_cross_platform_hash(self, adapter, tmp_path):
        """Hook must include macOS (shasum) and Python fallback for hashing."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "shasum -a 256" in content, "macOS shasum fallback missing"
        assert "python3 -c" in content, "Python hash fallback missing"
        assert "sha256sum" in content, "Linux sha256sum path missing"

    def test_route_hook_has_slash_command_detection(self, adapter, tmp_path):
        """Hook must detect /vibe-* slash commands."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "vibe-" in content, "Slash command detection missing"
        assert "vibe route" in content, "vibe route call missing"

    def test_route_hook_has_conversation_id_passing(self, adapter, tmp_path):
        """Hook must pass --conversation to vibe route."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "--conversation" in content, "Conversation ID argument missing"
        assert "CONVERSATION_ID" in content, "Conversation ID variable missing"

    def test_route_hook_skips_short_queries(self, adapter, tmp_path):
        """Hook must skip empty or very short queries."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "-lt 10" in content, "Short-query guard missing"
        assert "echo '{}'" in content, "Empty JSON fallback missing"

    def test_route_hook_has_meta_query_guard(self, adapter, tmp_path):
        """Hook must skip meta queries about VibeSOP itself."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "vibe\\s+(route|skill|config)" in content, "Meta-query guard missing"

    def test_route_hook_has_explicit_override_detection(self, adapter, tmp_path):
        """Hook must detect explicit skill overrides like /skill or @skill."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "EXPLICIT SKILL" in content, "Explicit override output missing"
        assert "OVERRIDE" in content, "Override detection missing"
