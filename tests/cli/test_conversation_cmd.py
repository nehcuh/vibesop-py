"""CLI tests for ``vibe conversation import-claude``.

Covers: file source happy path, missing source non-zero exit, auto-discovery
via HOME override, --all-sessions directory mode, and conversation-id
derivation from filename.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.conversation_cmd import app

runner = CliRunner()


def _make_jsonl(path: Path, lines: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for rec in lines:
            f.write(json.dumps(rec, ensure_ascii=False))
            f.write("\n")
    return path


def _user(content: str, ts: str = "2026-07-23T15:20:00.000Z") -> dict:
    return {"type": "user", "message": {"role": "user", "content": content}, "timestamp": ts}


def _assistant(content: str, ts: str = "2026-07-23T15:20:01.000Z") -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": content},
        "timestamp": ts,
    }


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run each test from a tmp cwd so .vibe/conversations resolves locally."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_import_claude_file_happy_path(tmp_path: Path) -> None:
    src = _make_jsonl(
        tmp_path / "sess.jsonl",
        [_user("hello"), _assistant("world")],
    )
    result = runner.invoke(
        app,
        [
            "import-claude",
            "--source",
            str(src),
            "--storage-dir",
            str(tmp_path / "conv"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Imported 2 new turns" in result.output
    assert (tmp_path / "conv" / "mirror-claude-sess.json").exists()


def test_import_claude_missing_source_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "import-claude",
            "--source",
            str(tmp_path / "nonexistent.jsonl"),
            "--storage-dir",
            str(tmp_path / "conv"),
        ],
    )
    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_import_claude_conversation_id_derived_from_filename(tmp_path: Path) -> None:
    """Empty --conversation-id → mirror-claude-<stem>."""
    src = _make_jsonl(
        tmp_path / "88e80ab9-a1609072a787.jsonl",
        [_user("hi")],
    )
    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        ["import-claude", "--source", str(src), "--storage-dir", str(storage)],
    )
    assert result.exit_code == 0, result.output
    assert (storage / "mirror-claude-88e80ab9-a1609072a787.json").exists()


def test_import_claude_auto_discover_via_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty --source → newest jsonl from ~/.claude/projects/<escaped-cwd>/."""
    home = tmp_path / "home"
    # cwd-based escaped name = tmp_path with / → -
    escaped = str(tmp_path).replace("/", "-")
    project_dir = home / ".claude" / "projects" / escaped
    project_dir.mkdir(parents=True)
    # Two jsonls — auto-discover picks the newest (by mtime)
    old_path = project_dir / "old.jsonl"
    new_path = project_dir / "new.jsonl"
    _make_jsonl(old_path, [_user("older")])
    _make_jsonl(new_path, [_user("newer")])
    # Force newer mtime on new_path
    import os

    os.utime(old_path, (1.0, 1.0))
    os.utime(new_path, (2.0, 2.0))

    monkeypatch.setattr(Path, "home", lambda: home)

    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        ["import-claude", "--storage-dir", str(storage)],
    )
    assert result.exit_code == 0, result.output
    assert "Imported 1 new turns" in result.output
    assert (storage / "mirror-claude-new.json").exists()
    # old not imported (no --all-sessions)
    assert not (storage / "mirror-claude-old.json").exists()


def test_import_claude_auto_discover_nothing_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto-discover with empty project dir → exit 1."""
    home = tmp_path / "home"
    escaped = str(tmp_path).replace("/", "-")
    project_dir = home / ".claude" / "projects" / escaped
    project_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)

    result = runner.invoke(
        app,
        ["import-claude", "--storage-dir", str(tmp_path / "conv")],
    )
    assert result.exit_code != 0
    assert "no Claude jsonl found" in result.output


def test_import_claude_all_sessions_directory_mode(tmp_path: Path) -> None:
    """--source=<dir> --all-sessions imports each jsonl separately."""
    src_dir = tmp_path / "sessions"
    src_dir.mkdir()
    _make_jsonl(src_dir / "a.jsonl", [_user("a")])
    _make_jsonl(src_dir / "b.jsonl", [_user("b"), _assistant("b-r")])

    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        [
            "import-claude",
            "--source",
            str(src_dir),
            "--storage-dir",
            str(storage),
            "--all-sessions",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (storage / "mirror-claude-a.json").exists()
    assert (storage / "mirror-claude-b.json").exists()
    assert "2 session(s)" in result.output


def test_import_claude_directory_default_picks_only_newest(tmp_path: Path) -> None:
    """Without --all-sessions, --source=<dir> imports only the newest jsonl."""
    src_dir = tmp_path / "sessions"
    src_dir.mkdir()
    old = _make_jsonl(src_dir / "old.jsonl", [_user("old")])
    new = _make_jsonl(src_dir / "new.jsonl", [_user("new")])
    import os

    os.utime(old, (1.0, 1.0))
    os.utime(new, (2.0, 2.0))

    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        [
            "import-claude",
            "--source",
            str(src_dir),
            "--storage-dir",
            str(storage),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (storage / "mirror-claude-new.json").exists()
    assert not (storage / "mirror-claude-old.json").exists()


def test_import_claude_idempotent_re_run(tmp_path: Path) -> None:
    """Running twice on the same source returns 0 new on the second pass."""
    src = _make_jsonl(tmp_path / "s.jsonl", [_user("once")])
    storage = tmp_path / "conv"
    args = ["import-claude", "--source", str(src), "--storage-dir", str(storage)]
    first = runner.invoke(app, args)
    assert first.exit_code == 0
    assert "Imported 1 new turns" in first.output
    second = runner.invoke(app, args)
    assert second.exit_code == 0
    assert "Imported 0 new turns" in second.output


# ----------------------------------------------------------------------
# Phase 2 (Path A): ``vibe conversation append-turn`` — real-time hook entry
# ----------------------------------------------------------------------


def _read_conv(storage: Path, cid: str) -> dict:
    return json.loads((storage / f"{cid}.json").read_text(encoding="utf-8"))


class TestAppendTurnUserPrompt:
    def test_user_prompt_submit_appends_user_turn(self, tmp_path: Path) -> None:
        storage = tmp_path / ".vibe" / "conversations"
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "abc123",
            "prompt": "hello world",
        }
        result = runner.invoke(
            app,
            ["append-turn", "--project-root", str(tmp_path)],
            input=json.dumps(payload),
        )
        assert result.exit_code == 0, result.output
        conv = _read_conv(storage, "mirror-claude-abc123")
        assert len(conv["turns"]) == 1
        turn = conv["turns"][0]
        assert turn["query"] == "hello world"
        assert turn["role"] == "user"
        assert turn["content"] is None

    def test_user_prompt_accepts_alias_keys(self, tmp_path: Path) -> None:
        # Robust to upstream schema drift: prompt | user_prompt | query |
        # message | text. We exercise two aliases here.
        storage = tmp_path / ".vibe" / "conversations"
        for key in ("user_prompt", "query", "message", "text"):
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": f"sid-{key}",
                key: f"v-{key}",
            }
            result = runner.invoke(
                app,
                ["append-turn", "--project-root", str(tmp_path)],
                input=json.dumps(payload),
            )
            assert result.exit_code == 0, result.output
        # Each alias produced its own conversation file.
        for key in ("user_prompt", "query", "message", "text"):
            conv = _read_conv(storage, f"mirror-claude-sid-{key}")
            assert conv["turns"][0]["query"] == f"v-{key}"


class TestAppendTurnPostToolUse:
    def test_post_tool_use_appends_tool_turn_with_keys_only(self, tmp_path: Path) -> None:
        """CRITICAL privacy: tool turn stores ``ToolName(arg1, arg2)``,
        never the values — even when those values are present in the
        payload's ``tool_input``."""
        storage = tmp_path / ".vibe" / "conversations"
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sid-tool",
            "tool_name": "Bash",
            "tool_input": {
                "command": "rm -rf /",  # sensitive value
                "cwd": "/secret/path",  # sensitive value
            },
        }
        result = runner.invoke(
            app,
            ["append-turn", "--project-root", str(tmp_path)],
            input=json.dumps(payload),
        )
        assert result.exit_code == 0, result.output
        conv = _read_conv(storage, "mirror-claude-sid-tool")
        assert len(conv["turns"]) == 1
        turn = conv["turns"][0]
        assert turn["role"] == "tool"
        assert turn["query"] == ""
        # Keys present, alphabetized.
        assert turn["content"] == "Bash(command, cwd)"

    def test_tool_input_values_never_persisted(self, tmp_path: Path) -> None:
        """Even when payload contains values, the stored file MUST NOT
        contain them anywhere — defense in depth."""
        secret_value = "SUPER_SECRET_TOKEN_42"
        another_secret = "/Users/me/.ssh/id_rsa"
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sid-priv",
            "tool_name": "Write",
            "tool_input": {
                "file_path": another_secret,
                "content": secret_value,
            },
        }
        result = runner.invoke(
            app,
            ["append-turn", "--project-root", str(tmp_path)],
            input=json.dumps(payload),
        )
        assert result.exit_code == 0, result.output
        conv_file = tmp_path / ".vibe" / "conversations" / "mirror-claude-sid-priv.json"
        raw = conv_file.read_text(encoding="utf-8")
        assert secret_value not in raw
        assert another_secret not in raw
        # Only the keys.
        assert "file_path" in raw
        assert "content" in raw

    def test_tool_input_with_no_args_renders_empty(self, tmp_path: Path) -> None:
        storage = tmp_path / ".vibe" / "conversations"
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sid-noargs",
            "tool_name": "ExitPlanMode",
            "tool_input": {},
        }
        result = runner.invoke(
            app,
            ["append-turn", "--project-root", str(tmp_path)],
            input=json.dumps(payload),
        )
        assert result.exit_code == 0, result.output
        conv = _read_conv(storage, "mirror-claude-sid-noargs")
        assert conv["turns"][0]["content"] == "ExitPlanMode()"


class TestAppendTurnFailOpen:
    def test_malformed_stdin_exits_zero(self, tmp_path: Path) -> None:
        # Hook contract: never block the host agent.
        result = runner.invoke(
            app,
            ["append-turn", "--project-root", str(tmp_path)],
            input="not valid json {{{",
        )
        assert result.exit_code == 0
        # Nothing written.
        assert not (tmp_path / ".vibe" / "conversations").exists() or not list(
            (tmp_path / ".vibe" / "conversations").glob("*.json")
        )

    def test_empty_stdin_exits_zero(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["append-turn", "--project-root", str(tmp_path)],
            input="",
        )
        assert result.exit_code == 0

    def test_unknown_event_silently_skipped(self, tmp_path: Path) -> None:
        """Events we don't handle (e.g. Notification) are dropped silently —
        no exception, no file written."""
        payload = {
            "hook_event_name": "Notification",
            "session_id": "sid-unhandled",
            "message": "irrelevant",
        }
        result = runner.invoke(
            app,
            ["append-turn", "--project-root", str(tmp_path)],
            input=json.dumps(payload),
        )
        assert result.exit_code == 0
        conv_file = tmp_path / ".vibe" / "conversations" / "mirror-claude-sid-unhandled.json"
        assert not conv_file.exists()


class TestAppendTurnConversationId:
    def test_conversation_id_derived_from_session_id(self, tmp_path: Path) -> None:
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "deadbeef-cafe-babe",  # > 20 chars
            "prompt": "hi",
        }
        result = runner.invoke(
            app,
            ["append-turn", "--project-root", str(tmp_path)],
            input=json.dumps(payload),
        )
        assert result.exit_code == 0, result.output
        # Prefix + truncate to 20 chars.
        expected = "mirror-claude-deadbeef-cafe-babe"[: len("mirror-claude-") + 20]
        assert (tmp_path / ".vibe" / "conversations" / f"{expected}.json").exists()

    def test_conversation_id_falls_back_to_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_SESSION_ID", "env-session-99")
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "from-env",
        }
        result = runner.invoke(
            app,
            ["append-turn", "--project-root", str(tmp_path)],
            input=json.dumps(payload),
        )
        assert result.exit_code == 0, result.output
        assert (
            tmp_path / ".vibe" / "conversations" / "mirror-claude-env-session-99.json"
        ).exists()

    def test_conversation_id_falls_back_to_timestamp(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # No session_id, no env → mirror-<unix-ts>
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "lonely",
        }
        result = runner.invoke(
            app,
            ["append-turn", "--project-root", str(tmp_path)],
            input=json.dumps(payload),
        )
        assert result.exit_code == 0, result.output
        files = list((tmp_path / ".vibe" / "conversations").glob("mirror-*.json"))
        assert len(files) == 1
        assert files[0].stem.startswith("mirror-")
        # mirror-claude- prefix only applied when session-derived.
        assert not files[0].stem.startswith("mirror-claude-")


class TestAppendTurnStorageDefault:
    def test_storage_lands_in_vibe_conversations_under_project_root(
        self, tmp_path: Path
    ) -> None:
        # --project-root controls where .vibe/ lives; without it, cwd is used.
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "loc-test",
            "prompt": "x",
        }
        result = runner.invoke(
            app,
            ["append-turn", "--project-root", str(tmp_path)],
            input=json.dumps(payload),
        )
        assert result.exit_code == 0, result.output
        # Storage lives at <project_root>/.vibe/conversations/, NOT cwd's .vibe.
        assert (tmp_path / ".vibe" / "conversations" / "mirror-claude-loc-test.json").exists()

