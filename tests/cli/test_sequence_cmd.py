"""Tests for ``vibe sequence record-tool|assemble`` and the purge integration.

record-tool is the Claude Code PostToolUse hook entry point: it must accept
the hook JSON on stdin, persist only (tool, ts, session) — never tool_input —
and always exit 0 so a broken event can never block the host agent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.sequence_cmd import app as sequence_app
from vibesop.cli.main import app as main_app
from vibesop.core.instinct.tool_sequences import cursor_path, sequences_path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke_record(runner: CliRunner, tmp_path: Path, stdin: str) -> object:
    return runner.invoke(
        sequence_app, ["record-tool", "--project-root", str(tmp_path)], input=stdin
    )


class TestRecordToolCommand:
    def test_valid_hook_json(self, runner: CliRunner, tmp_path: Path) -> None:
        payload = {
            "session_id": "sess-9",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /secret"},
            "hook_event_name": "PostToolUse",
        }
        result = _invoke_record(runner, tmp_path, json.dumps(payload))
        assert result.exit_code == 0
        entry = json.loads(sequences_path(tmp_path).read_text(encoding="utf-8").splitlines()[0])
        assert entry["tool"] == "Bash"
        assert entry["session"] == "sess-9"

    def test_no_tool_input_leak(self, runner: CliRunner, tmp_path: Path) -> None:
        secret = "aws_secret_access_key=AKIA1234567890"
        payload = {"tool_name": "Read", "tool_input": {"file_path": secret}}
        result = _invoke_record(runner, tmp_path, json.dumps(payload))
        assert result.exit_code == 0
        content = sequences_path(tmp_path).read_text(encoding="utf-8")
        assert secret not in content
        assert "tool_input" not in content

    def test_malformed_json_silent_exit_zero(self, runner: CliRunner, tmp_path: Path) -> None:
        result = _invoke_record(runner, tmp_path, "{not json")
        assert result.exit_code == 0
        assert not sequences_path(tmp_path).exists()

    def test_empty_stdin_silent_exit_zero(self, runner: CliRunner, tmp_path: Path) -> None:
        result = _invoke_record(runner, tmp_path, "")
        assert result.exit_code == 0
        assert not sequences_path(tmp_path).exists()

    def test_non_object_json_dropped(self, runner: CliRunner, tmp_path: Path) -> None:
        result = _invoke_record(runner, tmp_path, json.dumps(["Read", "Write"]))
        assert result.exit_code == 0
        assert not sequences_path(tmp_path).exists()

    def test_missing_tool_name_dropped(self, runner: CliRunner, tmp_path: Path) -> None:
        result = _invoke_record(runner, tmp_path, json.dumps({"session_id": "s"}))
        assert result.exit_code == 0
        assert not sequences_path(tmp_path).exists()

    def test_sequences_disabled_skips_capture(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VIBE_SEQUENCES_ENABLED", "false")
        monkeypatch.setenv("HOME", str(tmp_path))  # hermetic: ignore real ~/.vibe
        result = _invoke_record(
            runner, tmp_path, json.dumps({"tool_name": "Read", "session_id": "s"})
        )
        assert result.exit_code == 0
        assert not sequences_path(tmp_path).exists()


class TestRecordToolRootResolution:
    """gate33 pi MAJOR-3: without --project-root the capture must land in
    the host-provided project root (env var → payload workspaceRoot/cwd →
    process cwd), not wherever the hook happened to spawn."""

    def _invoke_no_flag(self, runner: CliRunner, stdin: str) -> object:
        return runner.invoke(sequence_app, ["record-tool"], input=stdin)

    def test_payload_workspace_root_wins_over_cwd(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        work = tmp_path / "proj"
        work.mkdir()
        monkeypatch.chdir(tmp_path)  # process cwd is NOT the project
        monkeypatch.delenv("GROK_WORKSPACE_ROOT", raising=False)
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        payload = {"toolName": "Edit", "workspaceRoot": str(work)}
        result = self._invoke_no_flag(runner, json.dumps(payload))
        assert result.exit_code == 0
        assert sequences_path(work).exists()
        assert not sequences_path(tmp_path).exists()

    def test_env_var_wins_over_payload(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_root = tmp_path / "env-proj"
        env_root.mkdir()
        monkeypatch.setenv("GROK_WORKSPACE_ROOT", str(env_root))
        monkeypatch.setenv("HOME", str(tmp_path))
        payload = {"toolName": "Edit", "workspaceRoot": str(tmp_path / "elsewhere")}
        result = self._invoke_no_flag(runner, json.dumps(payload))
        assert result.exit_code == 0
        assert sequences_path(env_root).exists()

    def test_cwd_is_last_resort(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        for var in ("GROK_WORKSPACE_ROOT", "CLAUDE_PROJECT_DIR"):
            monkeypatch.delenv(var, raising=False)
        result = self._invoke_no_flag(runner, json.dumps({"tool": "Bash"}))
        assert result.exit_code == 0
        assert sequences_path(tmp_path).exists()


class TestAssembleCommand:
    def test_assemble_feeds_learner(self, runner: CliRunner, tmp_path: Path) -> None:
        lines = [
            json.dumps({"tool": t, "ts": f"2026-07-18T10:0{i}:00+00:00", "session": "s"})
            for i, t in enumerate(["Read", "Edit", "Bash"])
        ]
        sequences_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        sequences_path(tmp_path).write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = runner.invoke(sequence_app, ["assemble", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Fed 1 tool sequence(s)" in result.output

        seq_file = tmp_path / ".vibe" / "sequences.jsonl"
        stored = [json.loads(line) for line in seq_file.read_text(encoding="utf-8").splitlines()]
        assert len(stored) == 1
        assert stored[0]["steps"] == ["Read", "Edit", "Bash"]
        assert stored[0]["total_count"] == 1
        assert stored[0]["success_count"] == 0  # application-only

        # Watermark advanced: a second assemble feeds nothing
        result = runner.invoke(sequence_app, ["assemble", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Fed 0 tool sequence(s)" in result.output

    def test_assemble_without_capture_file(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(sequence_app, ["assemble", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Fed 0 tool sequence(s)" in result.output


class TestStatusCommand:
    def test_no_capture_reports_never_captured(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(sequence_app, ["status", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "从未捕获或 hook 未更新" in result.output
        assert "不存在" in result.output  # capture file
        assert "无 cursor" in result.output

    def test_reports_age_sizes_rotation_and_watermark(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        from vibesop.core.instinct.tool_sequences import last_capture_path, rotated_path

        lines = [json.dumps({"tool": "Read", "ts": "t", "session": "s"})]
        sequences_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        sequences_path(tmp_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        size = sequences_path(tmp_path).stat().st_size
        rotated = rotated_path(tmp_path)
        rotated.write_text("{}\n", encoding="utf-8")
        rotated_size = rotated.stat().st_size  # CRLF on Windows → not a fixed 3
        cursor_path(tmp_path).write_text(json.dumps({"offset": size}), encoding="utf-8")
        from datetime import UTC, datetime

        epoch = int(datetime.now(UTC).timestamp()) - 300  # 5 minutes ago
        last_capture_path(tmp_path).write_text(f"{epoch}\n", encoding="utf-8")

        result = runner.invoke(sequence_app, ["status", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "last-capture:" in result.output
        assert "5 分钟前" in result.output  # age rendered
        assert f"{size} B" in result.output  # capture size
        assert "rotation:" in result.output and f"{rotated_size} B" in result.output
        assert "已装配到最新" in result.output

    def test_pending_bytes_reported(self, runner: CliRunner, tmp_path: Path) -> None:
        sequences_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        sequences_path(tmp_path).write_text(
            json.dumps({"tool": "Read", "ts": "t", "session": "s"}) + "\n", encoding="utf-8"
        )
        cursor_path(tmp_path).write_text(json.dumps({"offset": 0}), encoding="utf-8")

        result = runner.invoke(sequence_app, ["status", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "待装配" in result.output

    def test_corrupt_heartbeat_treated_as_never_captured(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        from vibesop.core.instinct.tool_sequences import last_capture_path

        last_capture_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        last_capture_path(tmp_path).write_text("not-an-epoch\n", encoding="utf-8")
        result = runner.invoke(sequence_app, ["status", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "从未捕获或 hook 未更新" in result.output


class TestDataPurgeToolSequences:
    def _seed(self, tmp_path: Path) -> None:
        sequences_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        sequences_path(tmp_path).write_text(
            json.dumps({"tool": "Read", "ts": "t", "session": None}) + "\n", encoding="utf-8"
        )
        cursor_path(tmp_path).write_text(json.dumps({"offset": 42}), encoding="utf-8")

    def test_purge_tool_sequences(self, runner: CliRunner, tmp_path: Path) -> None:
        self._seed(tmp_path)
        result = runner.invoke(
            main_app,
            [
                "data",
                "purge",
                "--tool-sequences",
                "--yes",
                "--project-root",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "tool-sequences: 2 file(s)" in result.output
        assert not sequences_path(tmp_path).exists()
        assert not cursor_path(tmp_path).exists()

    def test_purge_all_includes_tool_sequences(self, runner: CliRunner, tmp_path: Path) -> None:
        self._seed(tmp_path)
        result = runner.invoke(
            main_app,
            ["data", "purge", "--all", "--yes", "--project-root", str(tmp_path)],
        )
        assert result.exit_code == 0, result.output
        assert "tool-sequences:" in result.output
        assert not sequences_path(tmp_path).exists()
        assert not cursor_path(tmp_path).exists()
