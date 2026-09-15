"""Grok must not inherit Claude Code bash hooks (Windows WSL /bin/bash 127)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from vibesop.adapters.grok_build import (
    GrokBuildAdapter,
    apply_compat_claude_hooks_disabled,
    claude_hook_compat_is_disabled,
)
from vibesop.adapters.models import Manifest, ManifestMetadata


def _manifest() -> Manifest:
    return Manifest(
        metadata=ManifestMetadata(platform="grok-build", version="8.5.0"),
        skills=[],
    )


class TestApplyCompatClaudeHooksDisabled:
    def test_empty_writes_table(self) -> None:
        out = apply_compat_claude_hooks_disabled("")
        doc = tomllib.loads(out)
        assert doc["compat"]["claude"]["hooks"] is False

    def test_appends_to_unrelated_config(self) -> None:
        src = '[cli]\ninstaller = "npm"\n'
        out = apply_compat_claude_hooks_disabled(src)
        doc = tomllib.loads(out)
        assert doc["cli"]["installer"] == "npm"
        assert doc["compat"]["claude"]["hooks"] is False

    def test_flips_true_to_false(self) -> None:
        src = "[compat.claude]\nskills = true\nhooks = true\n"
        out = apply_compat_claude_hooks_disabled(src)
        doc = tomllib.loads(out)
        assert doc["compat"]["claude"]["hooks"] is False
        assert doc["compat"]["claude"]["skills"] is True

    def test_idempotent_when_already_false(self) -> None:
        src = "[compat.claude]\nhooks = false\n"
        assert apply_compat_claude_hooks_disabled(src) == src

    def test_inserts_hooks_into_existing_table(self) -> None:
        src = "[compat.claude]\nskills = true\n"
        out = apply_compat_claude_hooks_disabled(src)
        doc = tomllib.loads(out)
        assert doc["compat"]["claude"]["hooks"] is False
        assert doc["compat"]["claude"]["skills"] is True

    def test_does_not_touch_cursor_hooks(self) -> None:
        src = "[compat.cursor]\nhooks = true\n"
        out = apply_compat_claude_hooks_disabled(src)
        doc = tomllib.loads(out)
        assert doc["compat"]["cursor"]["hooks"] is True
        assert doc["compat"]["claude"]["hooks"] is False

    def test_dotted_assignment(self) -> None:
        src = "compat.claude.hooks = true\n"
        out = apply_compat_claude_hooks_disabled(src)
        doc = tomllib.loads(out)
        assert doc["compat"]["claude"]["hooks"] is False


class TestClaudeHookCompatIsDisabled:
    def test_missing_means_enabled(self) -> None:
        assert claude_hook_compat_is_disabled({}) is False
        assert claude_hook_compat_is_disabled({"compat": {"claude": {}}}) is False

    def test_explicit_false(self) -> None:
        assert claude_hook_compat_is_disabled({"compat": {"claude": {"hooks": False}}}) is True


class TestGrokBuildRenderMergesCompatOnlyOnHome:
    def test_dist_output_does_not_create_config_toml(self, tmp_path: Path) -> None:
        adapter = GrokBuildAdapter(project_root=tmp_path)
        out = tmp_path / "dist"
        result = adapter.render_config(_manifest(), out)
        assert result.success, result.errors
        assert not (out / "config.toml").exists()

    def test_deploy_home_merges_config_toml(self, tmp_path: Path) -> None:
        grok_home = tmp_path / "grok-home"
        grok_home.mkdir()
        (grok_home / "config.toml").write_text(
            '[cli]\ninstaller = "npm"\n\n[compat.claude]\nhooks = true\nskills = true\n',
            encoding="utf-8",
        )

        class _HomeAdapter(GrokBuildAdapter):
            @property
            def config_dir(self) -> Path:
                return grok_home

        adapter = _HomeAdapter(project_root=tmp_path)
        result = adapter.render_config(_manifest(), grok_home)
        assert result.success, result.errors
        doc = tomllib.loads((grok_home / "config.toml").read_text(encoding="utf-8"))
        assert doc["cli"]["installer"] == "npm"
        assert doc["compat"]["claude"]["hooks"] is False
        assert doc["compat"]["claude"]["skills"] is True
        assert (grok_home / "hooks" / "vibesop-route.json").exists()
