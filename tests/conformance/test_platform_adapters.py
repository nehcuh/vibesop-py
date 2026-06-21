"""Conformance tests: platform adapter compliance.

Verifies that all 5 platform adapters produce valid, structurally correct
output following their integration mode (file-based, hook-based, sdk-based).
"""

from __future__ import annotations

from pathlib import Path

from vibesop.adapters import (
    ClaudeCodeAdapter,
    CursorAdapter,
    FileBasedAdapter,
    HookBasedAdapter,
    KimiCliAdapter,
    OpenCodeAdapter,
    PiCodingAgentAdapter,
    PlatformAdapter,
    SdkBasedAdapter,
)
from vibesop.adapters.models import Manifest, ManifestMetadata


def _manifest_for(platform):
    return Manifest(
        metadata=ManifestMetadata(platform=platform, version="1.0.0"),
        skills=[],
    )


class TestAdapterHierarchy:
    """Verify adapter inheritance follows the 3-mode reference architecture."""

    def test_claude_code_inherits_hook_based(self):
        assert issubclass(ClaudeCodeAdapter, HookBasedAdapter)
        assert issubclass(ClaudeCodeAdapter, PlatformAdapter)

    def test_opencode_inherits_file_based(self):
        assert issubclass(OpenCodeAdapter, FileBasedAdapter)
        assert issubclass(OpenCodeAdapter, PlatformAdapter)

    def test_cursor_inherits_file_based(self):
        assert issubclass(CursorAdapter, FileBasedAdapter)
        assert issubclass(CursorAdapter, PlatformAdapter)

    def test_kimi_cli_inherits_file_based(self):
        assert issubclass(KimiCliAdapter, FileBasedAdapter)
        assert issubclass(KimiCliAdapter, PlatformAdapter)

    def test_pi_inherits_sdk_based(self):
        assert issubclass(PiCodingAgentAdapter, SdkBasedAdapter)
        assert issubclass(PiCodingAgentAdapter, PlatformAdapter)

    def test_sdk_based_is_platform_adapter(self):
        assert issubclass(SdkBasedAdapter, PlatformAdapter)

    def test_hook_based_is_platform_adapter(self):
        assert issubclass(HookBasedAdapter, PlatformAdapter)

    def test_file_based_is_platform_adapter(self):
        assert issubclass(FileBasedAdapter, PlatformAdapter)


class TestClaudeCodeConformance:
    """Claude Code adapter (hook-based) produces compliant output."""

    def test_render_config_only_succeeds(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        manifest = _manifest_for("claude-code")
        result = adapter.render_config_only(manifest, tmp_path)
        assert result.success, f"Errors: {result.errors}"

    def test_creates_core_files(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter.render_config_only(_manifest_for("claude-code"), tmp_path)
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / "rules" / "routing.md").exists()
        assert (tmp_path / "rules" / "behaviors.md").exists()
        assert (tmp_path / "hooks" / "vibesop-route.sh").exists()
        assert (tmp_path / "hooks" / "vibesop-track.sh").exists()

    def test_hook_script_is_executable(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter.render_config_only(_manifest_for("claude-code"), tmp_path)
        hook = tmp_path / "hooks" / "vibesop-route.sh"
        assert hook.stat().st_mode & 0o111

    def test_hook_delegates_to_agent_runtime(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter.render_config_only(_manifest_for("claude-code"), tmp_path)
        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "AgentRuntime" in content
        assert "handle_query_for_hook" in content

    def test_hook_has_no_vibe_route_subprocess(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter.render_config_only(_manifest_for("claude-code"), tmp_path)
        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "vibe route" not in content

    def test_settings_json_has_hook_config(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter.render_config_only(_manifest_for("claude-code"), tmp_path)
        settings = tmp_path / "settings.json"
        assert settings.exists()
        import json

        data = json.loads(settings.read_text())
        assert "hooks" in data
        assert "UserPromptSubmit" in data["hooks"]


class TestOpenCodeConformance:
    """OpenCode adapter (file-based) produces compliant output."""

    def test_render_config_only_succeeds(self, tmp_path):
        adapter = OpenCodeAdapter()
        result = adapter.render_config_only(_manifest_for("opencode"), tmp_path)
        assert result.success, f"Errors: {result.errors}"

    def test_creates_core_files(self, tmp_path):
        adapter = OpenCodeAdapter()
        adapter.render_config_only(_manifest_for("opencode"), tmp_path)
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / "hooks" / "vibesop-route.sh").exists()
        assert (tmp_path / "vibesop-env.sh").exists()

    def test_hook_delegates_to_agent_runtime(self, tmp_path):
        adapter = OpenCodeAdapter()
        adapter.render_config_only(_manifest_for("opencode"), tmp_path)
        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "AgentRuntime" in content

    def test_env_script_is_executable(self, tmp_path):
        adapter = OpenCodeAdapter()
        adapter.render_config_only(_manifest_for("opencode"), tmp_path)
        env = tmp_path / "vibesop-env.sh"
        assert env.stat().st_mode & 0o111


class TestCursorConformance:
    """Cursor adapter (file-based) produces compliant output."""

    def test_render_config_only_succeeds(self, tmp_path):
        adapter = CursorAdapter()
        result = adapter.render_config_only(_manifest_for("cursor"), tmp_path)
        assert result.success, f"Errors: {result.errors}"

    def test_creates_hook_script(self, tmp_path):
        adapter = CursorAdapter()
        adapter.render_config_only(_manifest_for("cursor"), tmp_path)
        assert (tmp_path / "hooks" / "vibesop-route.sh").exists()


class TestKimiCliConformance:
    """Kimi CLI adapter (file-based, TOML config) produces compliant output."""

    def test_render_config_only_succeeds(self, tmp_path):
        adapter = KimiCliAdapter()
        result = adapter.render_config_only(_manifest_for("kimi-cli"), tmp_path)
        assert result.success, f"Errors: {result.errors}"

    def test_creates_toml_config(self, tmp_path):
        adapter = KimiCliAdapter()
        adapter.render_config_only(_manifest_for("kimi-cli"), tmp_path)
        assert (tmp_path / "config.toml").exists()

    def test_toml_config_has_hooks_section(self, tmp_path):
        adapter = KimiCliAdapter()
        adapter.render_config_only(_manifest_for("kimi-cli"), tmp_path)
        content = (tmp_path / "config.toml").read_text()
        assert "[[hooks]]" in content
        assert "vibesop-route" in content

    def test_hook_delegates_to_agent_runtime(self, tmp_path):
        adapter = KimiCliAdapter()
        adapter.render_config_only(_manifest_for("kimi-cli"), tmp_path)
        content = (tmp_path / "hooks" / "vibesop-route.sh").read_text()
        assert "AgentRuntime" in content


class TestPiCodingAgentConformance:
    """Pi Coding Agent adapter (SDK-based pattern) produces compliant output."""

    def test_render_config_succeeds(self, tmp_path):
        adapter = PiCodingAgentAdapter(project_root=tmp_path)
        result = adapter.render_config(_manifest_for("pi"), tmp_path)
        assert result.success, f"Errors: {result.errors}"

    def test_creates_expected_output_files(self, tmp_path):
        adapter = PiCodingAgentAdapter(project_root=tmp_path)
        adapter.render_config(_manifest_for("pi"), tmp_path)
        # Pi writes docs/, extensions/, prompts/, skills/ to output_dir
        assert (tmp_path / "docs").is_dir()
        assert (tmp_path / "extensions").is_dir()
        assert (tmp_path / "prompts").is_dir()

    def test_creates_extension_files(self, tmp_path):
        adapter = PiCodingAgentAdapter(project_root=tmp_path)
        adapter.render_config(_manifest_for("pi"), tmp_path)
        assert (tmp_path / "extensions" / "vibesop-route.ts").exists()
        assert (tmp_path / "extensions" / "vibesop-track.ts").exists()


class TestSharedTemplateUsage:
    """All adapters use the shared vibesop-route.sh.j2 template."""

    def test_all_hook_scripts_use_same_template_source(self):
        from vibesop.adapters._shared import render_route_hook

        claude = render_route_hook(platform="claude-code", platform_name="Claude Code")
        opencode = render_route_hook(platform="opencode", platform_name="OpenCode")
        kimi = render_route_hook(platform="kimi-cli", platform_name="Kimi CLI")

        for result in [claude, opencode, kimi]:
            assert result.startswith("#!/bin/bash")
            assert "AgentRuntime" in result

    def test_platform_outputs_are_different(self):
        from vibesop.adapters._shared import render_route_hook

        claude = render_route_hook(platform="claude-code", platform_name="Claude Code")
        opencode = render_route_hook(platform="opencode", platform_name="OpenCode")
        assert "Claude Code" in claude
        assert "OpenCode" in opencode
        assert claude != opencode


class TestRenderResultConformance:
    """RenderResult API is consistent across all adapters."""

    def test_file_tracking(self):
        from vibesop.adapters.models import RenderResult

        result = RenderResult(success=True)
        result.add_file(Path("/tmp/test.txt"))
        assert result.file_count == 1

    def test_error_tracking(self):
        from vibesop.adapters.models import RenderResult

        result = RenderResult(success=True)
        result.add_error("Something went wrong")
        assert len(result.errors) == 1
        assert "Something went wrong" in result.errors

    def test_warning_tracking(self):
        from vibesop.adapters.models import RenderResult

        result = RenderResult(success=True)
        result.add_warning("Non-critical issue")
        assert result.success
        assert len(result.warnings) == 1
