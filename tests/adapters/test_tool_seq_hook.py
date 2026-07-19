"""Tests for the P3 Claude Code PostToolUse tool-sequence hook.

Covers the hook template (POSIX sh, no jq dependency, never blocks the host),
its registration in the adapter's render/install artifacts, and the
``sequences.enabled`` switch gating installation.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vibesop.adapters.claude_code import ClaudeCodeAdapter
from vibesop.adapters.models import Manifest, ManifestMetadata


def _manifest() -> Manifest:
    return Manifest(
        metadata=ManifestMetadata(platform="claude-code", version="8.0.0"),
        skills=[],
    )


def _rendered_hook(project_root: str | None = None) -> str:
    adapter = ClaudeCodeAdapter()
    env = adapter._get_template_env()
    template = env.get_template("hooks/vibesop-tool-seq.sh.j2")
    if project_root is None:
        return template.render(version="8.0.0")
    return template.render(version="8.0.0", project_root=project_root)


def _hermetic_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, enabled: bool) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))  # ignore real ~/.vibe config
    monkeypatch.setenv("VIBE_SEQUENCES_ENABLED", "true" if enabled else "false")


class TestToolSeqHookTemplate:
    def test_posix_sh_no_jq(self) -> None:
        content = _rendered_hook()
        assert content.startswith("#!/bin/sh")
        assert "jq" not in content  # no jq dependency (route hook convention)
        assert "vibe sequence record-tool" in content
        assert content.rstrip().endswith("exit 0")  # never blocks Claude Code

    def test_no_tool_input_capture(self) -> None:
        # The hook pipes the raw hook JSON to record-tool untouched; the
        # minimal-field extraction lives in the CLI (tested separately). The
        # script itself must never parse tool_input — only comments may
        # mention it.
        for line in _rendered_hook().splitlines():
            if "tool_input" in line:
                assert line.lstrip().startswith("#"), line

    def test_sh_syntax_valid(self, tmp_path: Path) -> None:
        sh = shutil.which("sh")
        if sh is None:
            pytest.skip("sh not available")
        script = tmp_path / "vibesop-tool-seq.sh"
        script.write_text(_rendered_hook(), encoding="utf-8")
        result = subprocess.run([sh, "-n", str(script)], capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()

    def test_hook_exits_zero_on_empty_input(self, tmp_path: Path) -> None:
        sh = shutil.which("sh")
        if sh is None:
            pytest.skip("sh not available")
        script = tmp_path / "vibesop-tool-seq.sh"
        script.write_text(_rendered_hook(), encoding="utf-8")
        result = subprocess.run(
            [sh, str(script)], input=b"", capture_output=True, cwd=tmp_path, check=False
        )
        assert result.returncode == 0

    def test_injected_project_root_is_deterministic_seq_root(self) -> None:
        # Render-time root wins over the directory-crawl fallback chain (M3);
        # shellquote keeps paths with spaces a single shell token.
        content = _rendered_hook("/tmp/my proj")
        assert "_SEQ_ROOT='/tmp/my proj'" in content

    def test_missing_project_root_renders_empty_and_keeps_fallback(self) -> None:
        content = _rendered_hook()
        assert "_SEQ_ROOT=''" in content
        # fallback chain preserved: crawl result, then CLAUDE_PROJECT_DIR/PWD
        assert '[ -z "$_SEQ_ROOT" ] && _SEQ_ROOT="$_VIBESOP_PROJECT_ROOT"' in content
        assert '[ -z "$_SEQ_ROOT" ] && _SEQ_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"' in content


class TestAdapterRegistration:
    def test_render_config_includes_hook_and_post_tool_use(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hermetic_config(monkeypatch, tmp_path, enabled=True)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        output_dir = tmp_path / "out"

        result = adapter.render_config(_manifest(), output_dir)

        assert result.success, result.errors
        hook = output_dir / "hooks" / "vibesop-tool-seq.sh"
        assert hook.exists()
        if sys.platform != "win32":
            # Windows chmod only toggles read-only; hooks run via `bash <script>`.
            assert hook.stat().st_mode & 0o111  # executable
        # deterministic project root injected at render time (M3): the hook
        # lives in <output_dir>/hooks/, so the root is output_dir's parent —
        # mirroring the script's own `_HOOK_DIR/../..` convention.
        hook_content = hook.read_text(encoding="utf-8")
        expected_root = shlex.quote(str(output_dir.resolve().parent))
        assert f"_SEQ_ROOT={expected_root}" in hook_content
        settings = json.loads((output_dir / "settings.json").read_text(encoding="utf-8"))
        post_tool_use = settings["hooks"]["PostToolUse"]
        command = post_tool_use[0]["hooks"][0]["command"]
        assert "vibesop-tool-seq.sh" in command

    def test_render_config_disabled_omits_hook(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hermetic_config(monkeypatch, tmp_path, enabled=False)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        output_dir = tmp_path / "out"

        result = adapter.render_config(_manifest(), output_dir)

        assert result.success, result.errors
        assert not (output_dir / "hooks" / "vibesop-tool-seq.sh").exists()
        settings = json.loads((output_dir / "settings.json").read_text(encoding="utf-8"))
        assert "PostToolUse" not in settings.get("hooks", {})

    def test_install_hooks_includes_tool_seq(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hermetic_config(monkeypatch, tmp_path, enabled=True)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        config_dir = tmp_path / "claude-config"

        results = adapter.install_hooks(config_dir)

        assert results.get("vibesop-tool-seq") is True
        hook = config_dir / "hooks" / "vibesop-tool-seq.sh"
        assert hook.exists()
        if sys.platform != "win32":
            # Windows chmod only toggles read-only; hooks run via `bash <script>`.
            assert hook.stat().st_mode & 0o111
        expected_root = shlex.quote(str(config_dir.resolve().parent))
        assert f"_SEQ_ROOT={expected_root}" in hook.read_text(encoding="utf-8")

    def test_install_hooks_disabled_skips_tool_seq(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hermetic_config(monkeypatch, tmp_path, enabled=False)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        config_dir = tmp_path / "claude-config"

        results = adapter.install_hooks(config_dir)

        assert "vibesop-tool-seq" not in results
        assert not (config_dir / "hooks" / "vibesop-tool-seq.sh").exists()
