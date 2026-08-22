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

    def test_claude_project_dir_wins_over_render_time_root(self) -> None:
        # M12 gate15 BLOCK-2 root cause: a globally-installed hook renders
        # with project_root=$HOME, so captures scattered into ~/.vibe. The
        # working project (CLAUDE_PROJECT_DIR) must take precedence; the
        # render-time root is the deterministic fallback for project-local
        # installs. shellquote keeps paths with spaces a single shell token.
        content = _rendered_hook("/tmp/my proj")
        assert '_SEQ_ROOT="${CLAUDE_PROJECT_DIR:-}"' in content
        assert "[ -z \"$_SEQ_ROOT\" ] && _SEQ_ROOT='/tmp/my proj'" in content

    def test_missing_project_root_renders_empty_and_keeps_fallback(self) -> None:
        content = _rendered_hook()
        assert "[ -z \"$_SEQ_ROOT\" ] && _SEQ_ROOT=''" in content
        # fallback chain preserved: crawl result, then cwd
        assert '[ -z "$_SEQ_ROOT" ] && _SEQ_ROOT="$_VIBESOP_PROJECT_ROOT"' in content
        assert '[ -z "$_SEQ_ROOT" ] && _SEQ_ROOT="$PWD"' in content

    def test_failure_not_swallowed_and_liveness_signal(self) -> None:
        # M12: failures append to a capped local log instead of vanishing;
        # successful captures refresh a one-line epoch liveness file.
        content = _rendered_hook()
        assert "hook_errors.log" in content
        assert "tool_sequences.last" in content
        assert "65536" in content  # log size cap
        assert "date +%s" in content  # liveness timestamp
        # the old silent-death pattern is gone
        assert ">/dev/null 2>&1 || true" not in content


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


class TestToolSeqHookBehavior:
    """Execute the rendered hook with fake PostToolUse payloads (M12).

    Uses a stub ``vibe`` binary on PATH so the tests stay hermetic. ``HOME``
    is redirected so the real ``~/.local/bin/vibe`` never shadows the stub.
    """

    PAYLOAD = b'{"session_id":"sess-1","tool_name":"Read","cwd":"/tmp/work"}'

    def _setup(self, tmp_path: Path, vibe_body: str) -> dict[str, str]:
        sh = shutil.which("sh")
        if sh is None:
            pytest.skip("sh not available")
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        (fake_bin / "vibe").write_text(f"#!/bin/sh\n{vibe_body}\n", encoding="utf-8")
        (fake_bin / "vibe").chmod(0o755)
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        work = tmp_path / "work"
        work.mkdir(exist_ok=True)
        script = tmp_path / "vibesop-tool-seq.sh"
        # Empty render-time root: exercises the runtime fallback chain.
        script.write_text(_rendered_hook(""), encoding="utf-8")
        env = {
            "HOME": str(home),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "CLAUDE_PROJECT_DIR": str(work),
        }
        return {"script": str(script), "env": env, "work": str(work), "cwd": str(work)}

    def _run(self, setup: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["sh", setup["script"]],
            input=self.PAYLOAD,
            capture_output=True,
            # Hermetic cwd: from the repo checkout the template's crawl would
            # find the real vibesop pyproject and the uv fallback would run
            # the real CLI. From tmp_path the crawl finds nothing.
            cwd=setup["cwd"],
            env=setup["env"],
            timeout=60,
            check=False,
        )

    def test_success_updates_last_capture_and_stays_silent(self, tmp_path: Path) -> None:
        setup = self._setup(tmp_path, "exit 0")
        result = self._run(setup)
        assert result.returncode == 0
        assert result.stdout == b""  # hooks must never write to stdout
        vibe_dir = Path(setup["work"]) / ".vibe"
        last = vibe_dir / "tool_sequences.last"
        assert last.exists()
        assert last.read_text(encoding="utf-8").strip().isdigit()
        assert not (vibe_dir / "hook_errors.log").exists()

    def test_failure_writes_capped_error_log_and_exits_zero(self, tmp_path: Path) -> None:
        setup = self._setup(tmp_path, "echo boom >&2; exit 3")
        result = self._run(setup)
        assert result.returncode == 0  # never blocks the host agent
        assert result.stdout == b""
        vibe_dir = Path(setup["work"]) / ".vibe"
        errlog = vibe_dir / "hook_errors.log"
        assert errlog.exists()
        text = errlog.read_text(encoding="utf-8")
        assert "rc=3" in text
        assert "boom" in text
        assert not (vibe_dir / "tool_sequences.last").exists()

    def test_missing_vibe_and_uv_logs_rc127(self, tmp_path: Path) -> None:
        setup = self._setup(tmp_path, "exit 0")
        # Remove the stub vibe and any uv from PATH: the crawl fallback finds
        # no vibesop checkout under tmp_path, so rc=127 must be logged.
        (tmp_path / "bin" / "vibe").unlink()
        result = self._run(setup)
        assert result.returncode == 0
        errlog = Path(setup["work"]) / ".vibe" / "hook_errors.log"
        assert errlog.exists()
        assert "rc=127" in errlog.read_text(encoding="utf-8")

    def test_error_log_is_capped(self, tmp_path: Path) -> None:
        setup = self._setup(tmp_path, "echo boom >&2; exit 3")
        vibe_dir = Path(setup["work"]) / ".vibe"
        vibe_dir.mkdir()
        errlog = vibe_dir / "hook_errors.log"
        errlog.write_text(
            ("old-line-" + "x" * 90 + "\n") * 1000, encoding="utf-8"
        )  # ~97KB > 64KB cap
        result = self._run(setup)
        assert result.returncode == 0
        lines = errlog.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 201  # 200 kept + 1 new
        assert any("rc=3" in line for line in lines)

    def test_claude_project_dir_wins_over_render_time_root(self, tmp_path: Path) -> None:
        # Stub records its argv; CLAUDE_PROJECT_DIR (set in _setup) must beat
        # the render-time root for --project-root.
        args_file = tmp_path / "vibe-args"
        setup = self._setup(tmp_path, f'printf \'%s\' "$*" > "{args_file}"\nexit 0')
        # Re-render with a bogus render-time root that must NOT win.
        Path(setup["script"]).write_text(_rendered_hook("/should/not/win"), encoding="utf-8")
        result = self._run(setup)
        assert result.returncode == 0
        assert f"--project-root {setup['work']}" in args_file.read_text(encoding="utf-8")


class TestGrokBuildToolSeqHook:
    """gate33: Grok Build adapter deploys a PostToolUse tool-sequence
    capture hook as a JSON hook (no shell script — the adapter's stated
    Windows-native property) calling the existing cross-platform
    ``vibe sequence record-tool`` entry."""

    def _grok_manifest(self) -> Manifest:
        return Manifest(
            metadata=ManifestMetadata(platform="grok-build", version="8.0.0"),
            skills=[],
        )

    def test_render_config_includes_tool_seq_hook(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hermetic_config(monkeypatch, tmp_path, enabled=True)
        from vibesop.adapters.grok_build import GrokBuildAdapter

        adapter = GrokBuildAdapter(project_root=tmp_path)
        output_dir = tmp_path / "out"

        result = adapter.render_config(self._grok_manifest(), output_dir)

        assert result.success, result.errors
        hook_file = output_dir / "hooks" / "vibesop-tool-seq.json"
        assert hook_file.exists()
        config = json.loads(hook_file.read_text(encoding="utf-8"))
        post_tool_use = config["hooks"]["PostToolUse"]
        entry = post_tool_use[0]["hooks"][0]
        assert entry["type"] == "command"
        assert entry["command"] == "vibe sequence record-tool"
        assert entry["timeout"] == 10
        # Empty matcher = capture ALL tools (behavior evidence needs the
        # full sequence, not just edits).
        assert post_tool_use[0]["matcher"] == ""
        # Observation-only: no statusMessage — capture stays invisible.
        assert "statusMessage" not in entry

    def test_render_config_disabled_omits_tool_seq_hook(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hermetic_config(monkeypatch, tmp_path, enabled=False)
        from vibesop.adapters.grok_build import GrokBuildAdapter

        adapter = GrokBuildAdapter(project_root=tmp_path)
        output_dir = tmp_path / "out"

        result = adapter.render_config(self._grok_manifest(), output_dir)

        assert result.success, result.errors
        assert not (output_dir / "hooks" / "vibesop-tool-seq.json").exists()
        # The route hook is unaffected by the sequences switch.
        assert (output_dir / "hooks" / "vibesop-route.json").exists()

    def test_capture_end_to_end_via_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The command the hook invokes actually records a GROK-SHAPED
        (camelCase — gate33 pi BLOCK-1) PostToolUse payload: the capture
        log gains exactly one minimal entry (tool + ts + session — never
        toolInput) plus the liveness heartbeat (pi MAJOR-2)."""
        vibe = shutil.which("vibe")
        if vibe is None:
            pytest.skip("vibe binary not on PATH")
        _hermetic_config(monkeypatch, tmp_path, enabled=True)
        work = tmp_path / "proj"
        work.mkdir()
        # The real grok stdin envelope (per grok's hooks user guide):
        # camelCase keys, plus cwd/workspaceRoot the CLI uses as the
        # project-root fallback (pi MAJOR-3).
        payload = {
            "hookEventName": "post_tool_use",
            "sessionId": "grok-session-1",
            "cwd": str(work),
            "workspaceRoot": str(work),
            "toolName": "search_replace",
            "toolInput": {"file_path": "/secret/should-not-leak"},
        }
        result = subprocess.run(
            [vibe, "sequence", "record-tool"],
            check=False,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=tmp_path,  # deliberately NOT the project dir — the payload
            # workspaceRoot must win over the process cwd (pi MAJOR-3)
            timeout=30,
        )
        assert result.returncode == 0
        log = work / ".vibe" / "tool_sequences.jsonl"
        assert log.exists(), "camelCase payload must be recorded (gate33 pi BLOCK-1)"
        entry = json.loads(log.read_text(encoding="utf-8").strip())
        assert entry["tool"] == "search_replace"
        assert entry["session"] == "grok-session-1"
        assert "tool_input" not in entry
        assert "toolInput" not in entry
        # Liveness heartbeat written by the pure-CLI path (pi MAJOR-2).
        heartbeat = work / ".vibe" / "tool_sequences.last"
        assert heartbeat.exists()
        assert heartbeat.read_text(encoding="utf-8").strip().isdigit()
