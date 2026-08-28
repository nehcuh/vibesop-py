"""Tests for Claude Code adapter."""

import json
import sys
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

from vibesop.adapters.claude_code import (
    ClaudeCodeAdapter,
    _rewrite_legacy_hook_entry,
    bash_hook_command,
)
from vibesop.adapters.models import Manifest
from vibesop.utils.hook_commands import parse_hook_script_command


class TestBashHookCommand:
    """Hook commands must be absolute POSIX under ``bash`` on every platform.

    Probed live on Claude Code 2.1.220 (2026-08-28): hooks spawn via
    ``bash -c`` with the session CWD, so config-relative ``hooks/x.sh``
    resolves against that CWD and 127s from any other directory.
    """

    def test_posix_path_is_unquoted_bash(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        script = tmp_path / "hooks" / "vibesop-route.sh"
        script.parent.mkdir()
        script.write_text("#!/bin/bash\n", encoding="utf-8")
        cmd = bash_hook_command(script)
        assert cmd.startswith("bash ")
        assert "\\" not in cmd
        assert cmd.endswith("vibesop-route.sh")

    def test_windows_command_is_absolute_posix_bash(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        script = tmp_path / "hooks" / "vibesop-route.sh"
        script.parent.mkdir()
        script.write_text("#!/bin/bash\n", encoding="utf-8")
        cmd = bash_hook_command(script)
        assert cmd == f"bash {script.resolve().as_posix()}"
        assert "\\" not in cmd
        assert "Program Files" not in cmd
        assert "bash.exe" not in cmd
        assert not cmd.startswith('"')


class TestRewriteLegacyHookEntry:
    """Rebuild must replace both backslash paths and Git-bash.exe wrappers."""

    @staticmethod
    def _entry(cmd: str) -> dict:
        return {"matcher": "", "hooks": [{"type": "command", "command": cmd}]}

    def test_extracts_script_from_backslash_bash_prefix(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        norm = parse_hook_script_command(r"bash C:\Users\HuChen\.claude\hooks/vibesop-route.sh")
        assert norm == "C:/Users/HuChen/.claude/hooks/vibesop-route.sh"

    def test_extracts_script_from_git_bash_wrapper(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        cmd = (
            '"C:/Program Files/Git/bin/bash.exe" '
            '"C:/Users/HuChen/.claude/hooks/vibesop-mirror-prompt.sh"'
        )
        norm = parse_hook_script_command(cmd)
        assert norm == "C:/Users/HuChen/.claude/hooks/vibesop-mirror-prompt.sh"

    def test_rewrites_git_bash_wrapper_on_windows(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        entry = self._entry(
            '"C:/Program Files/Git/bin/bash.exe" '
            '"C:/Users/HuChen/.claude/hooks/vibesop-mirror-prompt.sh"'
        )
        rewritten = _rewrite_legacy_hook_entry(entry)
        cmd = rewritten["hooks"][0]["command"]
        assert cmd == "bash C:/Users/HuChen/.claude/hooks/vibesop-mirror-prompt.sh"

    def test_rewrites_backslash_form_on_windows(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        entry = self._entry(r"bash C:\Users\h\.claude\hooks\vibesop-mirror-prompt.sh")
        rewritten = _rewrite_legacy_hook_entry(entry)
        assert (
            rewritten["hooks"][0]["command"]
            == "bash C:/Users/h/.claude/hooks/vibesop-mirror-prompt.sh"
        )

    def test_rewrites_bash_prefix_posix_form_on_windows(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        entry = self._entry("bash C:/Users/h/.claude/hooks/vibesop-mirror-prompt.sh")
        rewritten = _rewrite_legacy_hook_entry(entry)
        assert (
            rewritten["hooks"][0]["command"]
            == "bash C:/Users/h/.claude/hooks/vibesop-mirror-prompt.sh"
        )

    def test_rewrites_casefolded_tab_prefix_on_windows(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        entry = self._entry("BASH\tC:/Users/h/.claude/hooks/vibesop-mirror-prompt.sh")
        rewritten = _rewrite_legacy_hook_entry(entry)
        assert (
            rewritten["hooks"][0]["command"]
            == "bash C:/Users/h/.claude/hooks/vibesop-mirror-prompt.sh"
        )

    def test_rewrites_quoted_posix_one_token_on_windows(self, monkeypatch) -> None:
        """Quoted POSIX failed on pre-2.1 hosts (configDir+quote join)."""
        monkeypatch.setattr(sys, "platform", "win32")
        entry = self._entry('"C:/Users/HuChen/.claude/hooks/vibesop-tool-seq.sh"')
        rewritten = _rewrite_legacy_hook_entry(entry)
        assert rewritten["hooks"][0]["command"] == (
            "bash C:/Users/HuChen/.claude/hooks/vibesop-tool-seq.sh"
        )

    def test_rewrites_config_relative_form_on_windows(self, monkeypatch, tmp_path) -> None:
        """S51 canonical hooks/<name>.sh resolves against the session CWD on
        2.1.220 — with config_dir the rewrite upgrades it to the absolute
        path under that settings.json directory."""
        monkeypatch.setattr(sys, "platform", "win32")
        entry = self._entry("hooks/vibesop-mirror-prompt.sh")
        rewritten = _rewrite_legacy_hook_entry(entry, config_dir=tmp_path / ".claude")
        assert rewritten["hooks"][0]["command"] == (
            f"bash {(tmp_path / '.claude' / 'hooks' / 'vibesop-mirror-prompt.sh').as_posix()}"
        )

    def test_config_relative_form_without_config_dir_stays(self, monkeypatch) -> None:
        """No config_dir → no absolute target derivable → byte-identical."""
        monkeypatch.setattr(sys, "platform", "win32")
        entry = self._entry("hooks/vibesop-mirror-prompt.sh")
        rewritten = _rewrite_legacy_hook_entry(entry)
        assert rewritten["hooks"][0]["command"] == "hooks/vibesop-mirror-prompt.sh"

    def test_rewrites_quoted_spaced_home_on_windows(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        entry = self._entry(
            '"C:/Program Files/Git/bin/bash.exe" '
            '"C:/Users/First Last/.claude/hooks/vibesop-mirror-prompt.sh"'
        )
        rewritten = _rewrite_legacy_hook_entry(entry)
        assert rewritten["hooks"][0]["command"] == (
            "bash C:/Users/First Last/.claude/hooks/vibesop-mirror-prompt.sh"
        )

    def test_noop_quoted_posix_without_signal(self) -> None:
        entry = self._entry('bash "/abs/vibesop-route.sh"')
        rewritten = _rewrite_legacy_hook_entry(entry)
        assert rewritten["hooks"][0]["command"] == 'bash "/abs/vibesop-route.sh"'

    def test_noop_backtick_path(self) -> None:
        entry = self._entry('bash "/tmp/`id`/vibesop-route.sh"')
        rewritten = _rewrite_legacy_hook_entry(entry)
        assert rewritten["hooks"][0]["command"] == 'bash "/tmp/`id`/vibesop-route.sh"'

    def test_noop_win32_canonical_relative(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        entry = self._entry("hooks/vibesop-mirror-prompt.sh")
        rewritten = _rewrite_legacy_hook_entry(entry)
        assert rewritten["hooks"][0]["command"] == "hooks/vibesop-mirror-prompt.sh"

    def test_noop_mac_literal_backslash_posix_path(self) -> None:
        entry = self._entry("bash /Users/h/foo\\bar/vibesop-route.sh")
        rewritten = _rewrite_legacy_hook_entry(entry)
        assert rewritten["hooks"][0]["command"] == "bash /Users/h/foo\\bar/vibesop-route.sh"

    def test_noop_windows_form_on_mac(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        entry = self._entry(r"bash C:\Users\h\.claude\hooks\vibesop-route.sh")
        rewritten = _rewrite_legacy_hook_entry(entry)
        assert rewritten["hooks"][0]["command"] == (
            r"bash C:\Users\h\.claude\hooks\vibesop-route.sh"
        )


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
        if sys.platform != "win32":
            # Windows chmod only toggles read-only; hooks run via `bash <script>`.
            assert hook_path.stat().st_mode & 0o111, "Hook should be executable"
        result.add_file.assert_called_once_with(hook_path)
        result.add_warning.assert_not_called()

    def test_route_hook_delegates_to_agent_runtime(self, adapter, tmp_path):
        """Hook must delegate to AgentRuntime.handle_query_for_hook via Python."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text(encoding="utf-8")
        assert "AgentRuntime" in content, "AgentRuntime delegation missing"
        assert "handle_query_for_hook" in content, "handle_query_for_hook call missing"
        assert "handle_query_for_hook" in content
        assert "uv run python" in content or '"$@" -c' in content, "Python invocation missing"

    def test_route_hook_has_slash_command_detection(self, adapter, tmp_path):
        """Hook must pass query to AgentRuntime (slash commands handled in Python)."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text(encoding="utf-8")
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

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text(encoding="utf-8")
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

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text(encoding="utf-8")
        assert "echo '{}'" in content, "Empty JSON fallback missing"
        assert "-z" in content, "Empty query check missing"

    def test_route_hook_parses_json_input(self, adapter, tmp_path):
        """Hook must parse JSON input for prompt field (with multi-agent fallbacks)."""
        result = MagicMock()
        result.add_file = MagicMock()
        result.add_warning = MagicMock()

        adapter._render_route_hook(tmp_path, result)

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text(encoding="utf-8")
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

        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text(encoding="utf-8")
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

    def test_symlink_preserved_on_second_build(self, monkeypatch, tmp_path, symlink_supported):
        """Symlink to installed pack must be preserved on re-build."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
        from vibesop.adapters.claude_code import ClaudeCodeAdapter
        from vibesop.adapters.models import Manifest, ManifestMetadata

        adapter = ClaudeCodeAdapter()
        output_dir = tmp_path / "output"
        skill_dir = output_dir / "skills" / "gstack-review"
        skill_dir.mkdir(parents=True)

        installed_dir = tmp_path / "installed"
        installed_dir.mkdir(parents=True)
        (installed_dir / "SKILL.md").write_text(
            "# Full Review Skill\n\nExecute review flow.", encoding="utf-8"
        )

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
        adapter._render_skill_content(skill, skill_dir, result, manifest=manifest)
        assert skill_dir.is_symlink()
        assert skill_dir.resolve() == installed_dir.resolve()

        # Second build: symlink must be preserved
        adapter._render_skill_content(skill, skill_dir, result, manifest=manifest)
        assert skill_dir.is_symlink(), "Symlink was lost on second build"
        assert skill_dir.resolve() == installed_dir.resolve(), "Symlink target changed"

        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
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

        adapter._render_skill_content(_Skill(), skill_dir, result, manifest=manifest)
        skill_md = skill_dir / "SKILL.md"
        assert skill_md.exists(), "SKILL.md should exist from template fallback"


def _hook_entry(command: str) -> dict:
    """Build a settings.json hook entry matching Claude Code's schema."""
    return {"matcher": "", "hooks": [{"type": "command", "command": command}]}


class TestRouteHookLayerMutualExclusion:
    """gate41: user-level and project-level settings.json must not both
    register the vibesop-route.sh UserPromptSubmit hook (double span writes).
    """

    @pytest.fixture
    def home(self, monkeypatch, tmp_path):
        home = tmp_path / "fake_home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        # ntpath.expanduser ignores HOME — USERPROFILE wins on Windows
        monkeypatch.setenv("USERPROFILE", str(home))
        return home

    @pytest.fixture
    def project_root(self, tmp_path):
        root = tmp_path / "proj"
        root.mkdir()
        return root

    @staticmethod
    def _render(adapter, output_dir):
        result = adapter.create_render_result(success=True)
        adapter._render_settings_json(output_dir, MagicMock(), result)
        return result

    @staticmethod
    def _read_settings(path):
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _entries_with(hooks, marker):
        return [e for e in hooks if marker in json.dumps(e)]

    def test_project_build_strips_user_layer_route_hook(self, home, project_root):
        """Dual registration converges: other layer's route entries removed,
        mirror/PostToolUse/env preserved, warning names both paths."""
        user_dir = home / ".claude"
        (user_dir / "hooks").mkdir(parents=True)
        mirror_entry = _hook_entry(f"bash {user_dir}/hooks/vibesop-mirror-prompt.sh")
        post_tool_use = [_hook_entry(f"bash {user_dir}/hooks/vibesop-tool-seq.sh")]
        settings_path = user_dir / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "env": {"FOO": "1"},
                    "hooks": {
                        "UserPromptSubmit": [
                            _hook_entry(f"bash {user_dir}/hooks/vibesop-route.sh"),
                            mirror_entry,
                        ],
                        "PostToolUse": post_tool_use,
                    },
                }
            ),
            encoding="utf-8",
        )
        (user_dir / "hooks" / "vibesop-route.sh").write_text(
            '#!/bin/bash\nexport CLAUDE_SESSION_ID="$SESSION_ID"\n',
            encoding="utf-8",
        )

        adapter = ClaudeCodeAdapter(project_root=project_root)
        output_dir = project_root / ".claude"
        result = self._render(adapter, output_dir)

        updated = self._read_settings(settings_path)
        assert updated["hooks"]["UserPromptSubmit"] == [mirror_entry]
        assert updated["hooks"]["PostToolUse"] == post_tool_use
        assert updated["env"] == {"FOO": "1"}

        current_hooks = self._read_settings(output_dir / "settings.json")["hooks"][
            "UserPromptSubmit"
        ]
        assert len(self._entries_with(current_hooks, "vibesop-route.sh")) == 1

        assert len(result.warnings) == 1
        warning = result.warnings[0]
        assert str(settings_path) in warning
        assert str((output_dir / "settings.json").resolve()) in warning
        assert "forwards SESSION_ID" in warning

    def test_user_build_strips_project_layer_route_hook(self, home, project_root):
        """Symmetric: a user-level build cleans the project layer; emptied
        hooks keys are removed; stale script (no SESSION_ID) is reported."""
        proj_dir = project_root / ".claude"
        (proj_dir / "hooks").mkdir(parents=True)
        settings_path = proj_dir / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "model": "opus",
                    "hooks": {
                        "UserPromptSubmit": [_hook_entry(f"bash {proj_dir}/hooks/vibesop-route.sh")]
                    },
                }
            ),
            encoding="utf-8",
        )
        (proj_dir / "hooks" / "vibesop-route.sh").write_text(
            "#!/bin/bash\n# old template, no session forwarding\n",
            encoding="utf-8",
        )

        adapter = ClaudeCodeAdapter(project_root=project_root)
        result = self._render(adapter, home / ".claude")

        updated = self._read_settings(settings_path)
        assert "hooks" not in updated
        assert updated["model"] == "opus"
        assert len(result.warnings) == 1
        assert "does NOT forward SESSION_ID" in result.warnings[0]

    def test_single_layer_rebuild_is_idempotent(self, home, project_root):
        """Repeated builds never accumulate duplicate route entries."""
        adapter = ClaudeCodeAdapter(project_root=project_root)
        output_dir = project_root / ".claude"
        self._render(adapter, output_dir)
        result = self._render(adapter, output_dir)

        hooks = self._read_settings(output_dir / "settings.json")["hooks"]["UserPromptSubmit"]
        assert len(self._entries_with(hooks, "vibesop-route.sh")) == 1
        assert result.warnings == []

    def test_mirror_entry_preserved_and_not_duplicated(self, home, project_root, monkeypatch):
        """Merge semantics: the same-layer mirror entry survives rebuilds
        exactly once while the route entry is refreshed."""
        monkeypatch.setattr(
            ClaudeCodeAdapter,
            "_conversation_mirror_enabled",
            lambda self: True,
        )
        adapter = ClaudeCodeAdapter(project_root=project_root)
        output_dir = project_root / ".claude"
        self._render(adapter, output_dir)
        result = self._render(adapter, output_dir)

        hooks = self._read_settings(output_dir / "settings.json")["hooks"]["UserPromptSubmit"]
        assert len(self._entries_with(hooks, "vibesop-route.sh")) == 1
        assert len(self._entries_with(hooks, "vibesop-mirror-prompt.sh")) == 1
        assert result.warnings == []

    def test_other_layer_bad_json_does_not_crash(self, home, project_root):
        """Unparseable other-layer settings.json: warn, leave file untouched."""
        user_dir = home / ".claude"
        user_dir.mkdir(parents=True)
        settings_path = user_dir / "settings.json"
        settings_path.write_text("{not valid json", encoding="utf-8")

        adapter = ClaudeCodeAdapter(project_root=project_root)
        result = self._render(adapter, project_root / ".claude")

        assert settings_path.read_text(encoding="utf-8") == "{not valid json"
        assert any("Could not parse" in w for w in result.warnings)

    def test_warning_notes_missing_other_layer_script(self, home, project_root):
        """Warning reports when the other layer's route script is absent."""
        user_dir = home / ".claude"
        user_dir.mkdir(parents=True)
        (user_dir / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [_hook_entry(f"bash {user_dir}/hooks/vibesop-route.sh")]
                    }
                }
            ),
            encoding="utf-8",
        )

        adapter = ClaudeCodeAdapter(project_root=project_root)
        result = self._render(adapter, project_root / ".claude")

        assert len(result.warnings) == 1
        assert "not found" in result.warnings[0]


class TestRouteHookStripLayerGating:
    """gate41 impl-review MAJOR-1 (claude+pi): the strip must fire ONLY for
    the two real registration layers — a staging/dist build output must never
    touch the user's live registration."""

    @pytest.fixture
    def home(self, monkeypatch, tmp_path):
        home = tmp_path / "fake_home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        # ntpath.expanduser ignores HOME — USERPROFILE wins on Windows
        monkeypatch.setenv("USERPROFILE", str(home))
        return home

    @pytest.fixture
    def project_root(self, tmp_path):
        root = tmp_path / "proj"
        root.mkdir()
        return root

    def test_dist_output_does_not_strip_user_layer(self, home, project_root):
        user_dir = home / ".claude"
        (user_dir / "hooks").mkdir(parents=True)
        (user_dir / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [_hook_entry(f"bash {user_dir}/hooks/vibesop-route.sh")]
                    }
                }
            ),
            encoding="utf-8",
        )
        before = (user_dir / "settings.json").read_bytes()

        adapter = ClaudeCodeAdapter(project_root=project_root)
        result = adapter.create_render_result(success=True)
        # `vibe build claude-code` default staging output.
        adapter._render_settings_json(
            project_root / ".vibe" / "dist" / "claude-code", MagicMock(), result
        )

        assert (user_dir / "settings.json").read_bytes() == before
        assert result.warnings == []

    def test_arbitrary_output_dir_does_not_strip_either_layer(self, home, project_root):
        user_dir = home / ".claude"
        (user_dir / "hooks").mkdir(parents=True)
        (user_dir / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [_hook_entry(f"bash {user_dir}/hooks/vibesop-route.sh")]
                    }
                }
            ),
            encoding="utf-8",
        )
        before = (user_dir / "settings.json").read_bytes()

        adapter = ClaudeCodeAdapter(project_root=project_root)
        result = adapter.create_render_result(success=True)
        adapter._render_settings_json(project_root / "somewhere" / "else", MagicMock(), result)

        assert (user_dir / "settings.json").read_bytes() == before
        assert result.warnings == []


class TestDeployStripSymmetry:
    """gate41 impl-review MAJOR-2 (claude+pi): `vibe deploy` (user-level
    writer) must strip the project layer's route registration after copy."""

    def test_execute_deploy_strips_project_layer(self, monkeypatch, tmp_path):
        from vibesop.cli.commands import deploy

        # The autouse _isolated_home fixture (tests/conftest.py:253) patches
        # Path.home() at class level — deploy.py's layer check consults
        # Path.home(), so use it directly instead of env-HOME tricks.
        home = Path.home()
        monkeypatch.setitem(deploy.PLATFORM_DIRS, "claude-code", home / ".claude")

        project = tmp_path / "proj"
        source = project / ".vibe" / "dist" / "claude-code"
        source.mkdir(parents=True)
        (source / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            _hook_entry(f"bash {home}/.claude/hooks/vibesop-route.sh")
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        project_layer = project / ".claude"
        (project_layer / "hooks").mkdir(parents=True)
        (project_layer / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            _hook_entry(f"bash {project_layer}/hooks/vibesop-route.sh")
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.chdir(project)
        deploy.execute_deploy("claude-code")

        deployed = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
        assert "vibesop-route.sh" in json.dumps(deployed["hooks"]["UserPromptSubmit"])
        stripped = json.loads((project_layer / "settings.json").read_text(encoding="utf-8"))
        assert "vibesop-route.sh" not in json.dumps(stripped)


class TestDeployStripSkippedCopyGuard:
    """gate41 pi confirm NIT: when the destination settings.json copy is
    skipped (exists, no --force) and carries no route hook, the project
    layer must stay untouched — otherwise both layers end up unregistered."""

    def test_skip_copy_without_route_hook_leaves_project_layer(self, monkeypatch, tmp_path):
        from vibesop.cli.commands import deploy

        home = Path.home()  # autouse _isolated_home fixture
        monkeypatch.setitem(deploy.PLATFORM_DIRS, "claude-code", home / ".claude")

        project = tmp_path / "proj"
        source = project / ".vibe" / "dist" / "claude-code"
        source.mkdir(parents=True)
        (source / "settings.json").write_text(
            json.dumps({"hooks": {"UserPromptSubmit": [_hook_entry("bash x/vibesop-route.sh")]}}),
            encoding="utf-8",
        )
        # User layer settings.json already exists WITHOUT the route hook —
        # the copy loop skips it (no --force).
        user_dir = home / ".claude"
        user_dir.mkdir(parents=True)
        (user_dir / "settings.json").write_text(json.dumps({"model": "opus"}), encoding="utf-8")
        project_layer = project / ".claude"
        (project_layer / "hooks").mkdir(parents=True)
        (project_layer / "settings.json").write_text(
            json.dumps({"hooks": {"UserPromptSubmit": [_hook_entry("bash y/vibesop-route.sh")]}}),
            encoding="utf-8",
        )
        before = (project_layer / "settings.json").read_bytes()

        monkeypatch.chdir(project)
        deploy.execute_deploy("claude-code")

        assert (project_layer / "settings.json").read_bytes() == before
