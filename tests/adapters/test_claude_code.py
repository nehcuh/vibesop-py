"""Tests for Claude Code adapter."""

from pathlib import Path
from typing import ClassVar
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

    def test_route_hook_delegates_to_agent_runtime(self, adapter, tmp_path):
        """Hook must delegate to AgentRuntime.handle_query_for_hook via Python."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "AgentRuntime" in content, "AgentRuntime delegation missing"
        assert "handle_query_for_hook" in content, "handle_query_for_hook call missing"
        assert ("python3 -c" in content or "uv run python" in content), "Python invocation missing"

    def test_route_hook_has_slash_command_detection(self, adapter, tmp_path):
        """Hook must pass query to AgentRuntime (slash commands handled in Python)."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "vibe" in content, "vibe reference missing"
        # AgentRuntime handles slash commands, hook just delegates
        assert "from vibesop.agent.runtime import AgentRuntime" in content, (
            "AgentRuntime import missing"
        )

    def test_route_hook_passes_hook_config_params(self, adapter, tmp_path):
        """Hook must pass platform and hook config to AgentRuntime."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "hook_event_name=" in content, "hook_event_name param missing"
        assert "include_additional_context=" in content, "include_additional_context param missing"
        assert "no_match_message=" in content, "no_match_message param missing"
        assert "platform=" in content, "platform param missing"

    def test_route_hook_skips_empty_queries(self, adapter, tmp_path):
        """Hook must skip empty queries before calling Python."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "echo '{}'" in content, "Empty JSON fallback missing"
        assert "-z" in content, "Empty query check missing"

    def test_route_hook_parses_json_input(self, adapter, tmp_path):
        """Hook must parse JSON input for prompt field (with multi-agent fallbacks)."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        # Claude Code uses .prompt; some agents use .user_prompt / .query / .message.
        # Hook tries all in order via jq fallback chain.
        assert ".prompt" in content, "JSON .prompt parsing missing"
        assert "user_prompt" in content, "user_prompt fallback missing"
        assert "jq" in content, "jq JSON parsing missing"

    def test_route_hook_has_no_bash_routing_logic(self, adapter, tmp_path):
        """Hook must NOT contain duplicate routing logic — all in Python AgentRuntime."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        # These patterns were in the old 221-line bash hook and should now be absent
        assert "vibe route" not in content, "vibe route subprocess call should be removed"
        assert "OVERRIDE" not in content, "override detection should be in Python"
        assert "CONVERSATION_ID" not in content, "conversation ID should be in Python"
        assert "sha256sum" not in content, "hashing should be in Python"
        assert "shasum" not in content, "hashing should be in Python"
        assert "MODE=" not in content, "routing mode parsing should be in Python"
        assert "ALTERNATIVES_JSON" not in content, "alternatives parsing should be in Python"


class TestSkillContentRender:
    """Tests for _render_skill_content symlink preservation fix.

    Verifies that external pack skill symlinks are NOT overwritten
    by the thin Jinja2 template on subsequent builds.
    """

    def test_symlink_preserved_on_second_build(self, monkeypatch, tmp_path):
        """Symlink to installed pack must be preserved on re-build."""
        from vibesop.adapters.claude_code import ClaudeCodeAdapter
        from vibesop.adapters.models import Manifest, ManifestMetadata

        adapter = ClaudeCodeAdapter()
        output_dir = tmp_path / "output"
        skill_dir = output_dir / "skills" / "gstack-review"
        skill_dir.mkdir(parents=True)

        installed_dir = tmp_path / "installed"
        installed_dir.mkdir(parents=True)
        (installed_dir / "SKILL.md").write_text("# Full Review Skill\n\nExecute review flow.")

        monkeypatch.setattr(
            "vibesop.adapters._shared.is_pack_installed",
            lambda _: installed_dir,
        )

        class _Skill:
            id = "gstack/review"
            namespace = "gstack"
            name = "GStack Review"
            description = "Code review"
            version = "1.0"
            skill_type = "standard"
            tags: ClassVar[list[str]] = ["review"]
            trigger_when = "When asked to review code"

        skill = _Skill()
        meta = ManifestMetadata(
            platform="claude-code",
            version="5.3.2",
        )
        manifest = Manifest(
            metadata=meta,
            skills=[],
        )

        result = MagicMock()
        result.add_file = MagicMock()
        result.add_error = MagicMock()

        # First build: creates symlink
        adapter._render_skill_content(skill, skill_dir, manifest, result)
        assert skill_dir.is_symlink()
        assert skill_dir.resolve() == installed_dir.resolve()

        # Second build: symlink must be preserved
        adapter._render_skill_content(skill, skill_dir, manifest, result)
        assert skill_dir.is_symlink(), "Symlink was lost on second build"
        assert skill_dir.resolve() == installed_dir.resolve(), "Symlink target changed"

        content = (skill_dir / "SKILL.md").read_text()
        assert "Full Review Skill" in content, "Original content was overwritten"
        assert "Execute review flow" in content, "Original flow text missing"

    def test_no_pack_falls_back_to_template(self, monkeypatch, tmp_path):
        """Uninstalled external skills get template fallback."""
        from vibesop.adapters.claude_code import ClaudeCodeAdapter
        from vibesop.adapters.models import Manifest, ManifestMetadata

        adapter = ClaudeCodeAdapter()
        output_dir = tmp_path / "output"
        skill_dir = output_dir / "skills" / "unknown-skill"
        skill_dir.mkdir(parents=True)

        monkeypatch.setattr(
            "vibesop.adapters._shared.is_pack_installed",
            lambda _: None,
        )
        monkeypatch.setattr(
            adapter,
            "_find_skill_content",
            lambda _: None,
        )

        class _Skill:
            id = "unknown/skill"
            namespace = "unknown"
            name = "Unknown Skill"
            description = "Not installed"
            version = "1.0"
            skill_type = "standard"
            tags: ClassVar[list[str]] = []
            trigger_when = "never"

        meta = ManifestMetadata(
            platform="claude-code",
            version="5.3.2",
        )
        manifest = Manifest(
            metadata=meta,
            skills=[],
        )

        result = MagicMock()
        result.add_file = MagicMock()
        result.add_error = MagicMock()

        adapter._render_skill_content(_Skill(), skill_dir, manifest, result)
        skill_md = skill_dir / "SKILL.md"
        assert skill_md.exists(), "SKILL.md should exist from template fallback"
