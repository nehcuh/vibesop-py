"""Tests for the conversation-mirror Claude Code hooks (Phase 2, Path A).

Covers both hook templates (UserPromptSubmit + SessionEnd), their
registration in the adapter's render/install artifacts, and the
``conversation_mirror.enabled`` opt-in switch (default false — unlike
``sequences.enabled`` which defaults true, because mirror captures user
prompts verbatim, which may contain secrets).
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


def _rendered_template(template_name: str, project_root: str | None = None) -> str:
    adapter = ClaudeCodeAdapter()
    env = adapter._get_template_env()
    template = env.get_template(template_name)
    if project_root is None:
        return template.render(version="8.0.0")
    return template.render(version="8.0.0", project_root=project_root)


def _rendered_prompt_hook(project_root: str | None = None) -> str:
    return _rendered_template("hooks/vibesop-mirror-prompt.sh.j2", project_root)


def _rendered_session_end_hook(project_root: str | None = None) -> str:
    return _rendered_template("hooks/vibesop-mirror-session-end.sh.j2", project_root)


def _hermetic_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, enabled: bool) -> None:
    """Isolate from real ~/.vibe and set the env-backed switch.

    The ConfigManager honors ``VIBE_<SECTION>_<KEY>`` env overrides, so we
    don't have to write a config file to tmp_path.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VIBE_CONVERSATION_MIRROR_ENABLED", "true" if enabled else "false")


class TestMirrorPromptHookTemplate:
    def test_posix_sh_shebang(self) -> None:
        content = _rendered_prompt_hook()
        assert content.startswith("#!/bin/sh")

    def test_invokes_append_turn(self) -> None:
        content = _rendered_prompt_hook()
        assert "vibe conversation append-turn" in content
        assert content.rstrip().endswith("exit 0")

    def test_no_jq_dependency_in_prompt_hook(self) -> None:
        # UserPromptSubmit payload is opaque; we pipe it through to the CLI.
        # Keeping jq out of this hook matches the tool-seq convention.
        content = _rendered_prompt_hook()
        assert "jq" not in content

    def test_sh_syntax_valid(self, tmp_path: Path) -> None:
        sh = shutil.which("sh")
        if sh is None:
            pytest.skip("sh not available")
        script = tmp_path / "vibesop-mirror-prompt.sh"
        script.write_text(_rendered_prompt_hook(), encoding="utf-8")
        result = subprocess.run([sh, "-n", str(script)], capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()

    def test_injected_project_root_deterministic(self) -> None:
        content = _rendered_prompt_hook("/tmp/my proj")
        assert "_MIRROR_ROOT='/tmp/my proj'" in content


class TestMirrorSessionEndHookTemplate:
    def test_posix_sh_shebang(self) -> None:
        content = _rendered_session_end_hook()
        assert content.startswith("#!/bin/sh")

    def test_invokes_import_claude(self) -> None:
        content = _rendered_session_end_hook()
        # Reuses Phase 1's import-claude subcommand rather than inventing a
        # new mode in append-turn — single source of truth for jsonl parsing.
        assert "vibe conversation import-claude" in content
        assert content.rstrip().endswith("exit 0")

    def test_passes_include_subagents_flag(self) -> None:
        """v3 Phase A Task 6 / grok+pi P0-3: the rendered hook MUST pass
        ``--include-subagents`` to ``vibe conversation import-claude`` so
        sub-agent transcripts get mirrored in the production path — without
        this flag, sub-agent import in production mirror path = 0%."""
        content = _rendered_session_end_hook()
        assert "--include-subagents" in content, (
            "session-end hook must pass --include-subagents to "
            "import-claude so sub-agent transcripts are mirrored"
        )

    def test_uses_jq_for_session_id_extraction(self) -> None:
        content = _rendered_session_end_hook()
        assert "jq" in content  # required for session_id field extraction
        assert "CLAUDE_SESSION_ID" in content  # env fallback

    def test_path_computation_logic(self) -> None:
        # Claude Code stores transcripts at ~/.claude/projects/<escaped>/<sid>.jsonl
        # where <escaped> is the absolute project dir with / -> -.
        content = _rendered_session_end_hook()
        assert ".claude/projects/" in content
        assert "sed 's#/#-#g'" in content
        assert "$_SESSION_ID.jsonl" in content

    def test_conversation_id_prefix_and_truncation(self) -> None:
        # Truncate to keep dashboard listings readable; prefix marks the
        # origin so mirror conversations are visually distinct from CLI ones.
        content = _rendered_session_end_hook()
        assert "mirror-claude-" in content
        assert "cut -c1-20" in content

    def test_sh_syntax_valid(self, tmp_path: Path) -> None:
        sh = shutil.which("sh")
        if sh is None:
            pytest.skip("sh not available")
        script = tmp_path / "vibesop-mirror-session-end.sh"
        script.write_text(_rendered_session_end_hook(), encoding="utf-8")
        result = subprocess.run([sh, "-n", str(script)], capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()


class TestAdapterRegistration:
    def test_render_config_includes_both_hooks_when_enabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hermetic_config(monkeypatch, tmp_path, enabled=True)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        output_dir = tmp_path / "out"

        result = adapter.render_config(_manifest(), output_dir)

        assert result.success, result.errors
        prompt_hook = output_dir / "hooks" / "vibesop-mirror-prompt.sh"
        session_end_hook = output_dir / "hooks" / "vibesop-mirror-session-end.sh"
        assert prompt_hook.exists()
        assert session_end_hook.exists()
        if sys.platform != "win32":
            assert prompt_hook.stat().st_mode & 0o111
            assert session_end_hook.stat().st_mode & 0o111

        settings = json.loads((output_dir / "settings.json").read_text(encoding="utf-8"))
        hooks = settings["hooks"]
        # UserPromptSubmit now has BOTH the route hook and the mirror hook.
        prompt_commands = [entry["hooks"][0]["command"] for entry in hooks["UserPromptSubmit"]]
        assert any("vibesop-route.sh" in c for c in prompt_commands)
        assert any("vibesop-mirror-prompt.sh" in c for c in prompt_commands)
        # SessionEnd is newly registered.
        session_end_commands = [entry["hooks"][0]["command"] for entry in hooks["SessionEnd"]]
        assert any("vibesop-mirror-session-end.sh" in c for c in session_end_commands)

    def test_render_config_omits_hooks_when_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Default (disabled) — mirrors capture nothing, prompts stay private.
        _hermetic_config(monkeypatch, tmp_path, enabled=False)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        output_dir = tmp_path / "out"

        result = adapter.render_config(_manifest(), output_dir)

        assert result.success, result.errors
        assert not (output_dir / "hooks" / "vibesop-mirror-prompt.sh").exists()
        assert not (output_dir / "hooks" / "vibesop-mirror-session-end.sh").exists()
        settings = json.loads((output_dir / "settings.json").read_text(encoding="utf-8"))
        # Route hook remains on UserPromptSubmit; mirror additions absent.
        prompt_commands = [
            entry["hooks"][0]["command"] for entry in settings["hooks"]["UserPromptSubmit"]
        ]
        assert any("vibesop-route.sh" in c for c in prompt_commands)
        assert not any("vibesop-mirror-prompt.sh" in c for c in prompt_commands)
        assert "SessionEnd" not in settings["hooks"]

    def test_render_config_disabled_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No env override at all → mirror must stay off (privacy default).
        monkeypatch.setenv("HOME", str(tmp_path))
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        output_dir = tmp_path / "out"

        result = adapter.render_config(_manifest(), output_dir)
        assert result.success, result.errors
        assert not (output_dir / "hooks" / "vibesop-mirror-prompt.sh").exists()
        settings = json.loads((output_dir / "settings.json").read_text(encoding="utf-8"))
        assert "SessionEnd" not in settings["hooks"]

    def test_injected_project_root_deterministic(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hermetic_config(monkeypatch, tmp_path, enabled=True)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        output_dir = tmp_path / "out"

        adapter.render_config(_manifest(), output_dir)

        expected_root = shlex.quote(str(output_dir.resolve().parent))
        prompt = (output_dir / "hooks" / "vibesop-mirror-prompt.sh").read_text(encoding="utf-8")
        session_end = (output_dir / "hooks" / "vibesop-mirror-session-end.sh").read_text(
            encoding="utf-8"
        )
        assert f"_MIRROR_ROOT={expected_root}" in prompt
        assert f"_MIRROR_ROOT={expected_root}" in session_end


class TestInstallHooks:
    def test_install_hooks_copies_both_templates_when_enabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hermetic_config(monkeypatch, tmp_path, enabled=True)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        config_dir = tmp_path / "claude-config"

        results = adapter.install_hooks(config_dir)

        assert results.get("vibesop-mirror-prompt") is True
        assert results.get("vibesop-mirror-session-end") is True
        assert (config_dir / "hooks" / "vibesop-mirror-prompt.sh").exists()
        assert (config_dir / "hooks" / "vibesop-mirror-session-end.sh").exists()
        if sys.platform != "win32":
            assert (config_dir / "hooks" / "vibesop-mirror-prompt.sh").stat().st_mode & 0o111
            assert (config_dir / "hooks" / "vibesop-mirror-session-end.sh").stat().st_mode & 0o111
        # Deterministic project root injection matches the render path.
        expected_root = shlex.quote(str(config_dir.resolve().parent))
        prompt = (config_dir / "hooks" / "vibesop-mirror-prompt.sh").read_text(encoding="utf-8")
        assert f"_MIRROR_ROOT={expected_root}" in prompt

    def test_install_hooks_disabled_skips_mirror(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hermetic_config(monkeypatch, tmp_path, enabled=False)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        config_dir = tmp_path / "claude-config"

        results = adapter.install_hooks(config_dir)

        assert "vibesop-mirror-prompt" not in results
        assert "vibesop-mirror-session-end" not in results
        assert not (config_dir / "hooks" / "vibesop-mirror-prompt.sh").exists()
        assert not (config_dir / "hooks" / "vibesop-mirror-session-end.sh").exists()
