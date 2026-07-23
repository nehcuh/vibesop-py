"""Tests for the pre-session-end hook (instinct learning loop closure).

Regression for the gap surfaced on 2026-07-23: the hook template called
``vibe auto-analyze-session`` (a command that doesn't exist), and the
``claude_code.py:install_hooks()`` wrote a totally different inline no-op
hook that just printed "Session ending at $(date)". Neither fired the
instinct loop.

These tests pin the fix by checking the actual content that
``ClaudeCodeAdapter.install_hooks()`` writes to disk.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vibesop.adapters.claude_code import ClaudeCodeAdapter


def _hermetic_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


class TestInstallHooksContent:
    """``ClaudeCodeAdapter.install_hooks()`` writes a hook that actually
    invokes real vibe subcommands — no more inline no-op stub."""

    def test_install_hooks_writes_real_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hermetic_config(monkeypatch, tmp_path)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        config_dir = tmp_path / "claude-config"

        results = adapter.install_hooks(config_dir)

        assert results.get("pre-session-end") is True
        hook = config_dir / "hooks" / "pre-session-end.sh"
        assert hook.exists()
        content = hook.read_text(encoding="utf-8")

        # Must call the real commands, not the dead reference
        assert "vibe analyze session" in content
        assert "vibe instinct eval" in content
        assert "auto-analyze-session" not in content

        # Must be executable on POSIX
        if sys.platform != "win32":
            assert hook.stat().st_mode & 0o111

    def test_install_hooks_not_just_a_log_line(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: the old install_hooks() wrote a hook whose body was
        essentially ``echo "Session ending at $(date)"`` — a no-op. The
        new hook must actually invoke vibe subcommands."""
        _hermetic_config(monkeypatch, tmp_path)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        config_dir = tmp_path / "claude-config"

        adapter.install_hooks(config_dir)
        content = (config_dir / "hooks" / "pre-session-end.sh").read_text("utf-8")

        # Count actual vibe invocations (not strings inside echo).
        real_calls = [
            line for line in content.splitlines()
            if ("vibe analyze" in line or "vibe instinct" in line)
            and not line.lstrip().startswith("#")
            and not line.lstrip().startswith('echo "')
        ]
        assert len(real_calls) >= 2, (
            f"Expected ≥2 real vibe invocations, got {len(real_calls)}:\n{content}"
        )

    def test_hook_syntax_valid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hook must be syntactically valid bash (sh -n)."""
        _hermetic_config(monkeypatch, tmp_path)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        config_dir = tmp_path / "claude-config"
        adapter.install_hooks(config_dir)
        hook = config_dir / "hooks" / "pre-session-end.sh"

        sh = shutil.which("sh")
        if sh is None:
            pytest.skip("sh not available")
        result = subprocess.run([sh, "-n", str(hook)], capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()

    def test_hook_exits_zero_when_vibe_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hook must tolerate vibe not being on PATH (exit 0, never block)."""
        _hermetic_config(monkeypatch, tmp_path)
        adapter = ClaudeCodeAdapter(project_root=tmp_path)
        config_dir = tmp_path / "claude-config"
        adapter.install_hooks(config_dir)
        hook = config_dir / "hooks" / "pre-session-end.sh"

        bash = shutil.which("bash")
        if bash is None:
            pytest.skip("bash not available")

        # PATH without vibe → "vibe not found" branch → exit 0.
        result = subprocess.run(
            [bash, str(hook)],
            capture_output=True,
            cwd=tmp_path,
            check=False,
            env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        )
        assert result.returncode == 0, result.stderr.decode()
        assert b"not found" in result.stdout.lower() or b"skipping" in result.stdout.lower()
