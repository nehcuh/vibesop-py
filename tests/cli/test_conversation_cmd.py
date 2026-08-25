"""CLI tests for ``vibe conversation import-claude``.

Covers: file source happy path, missing source non-zero exit, auto-discovery
via HOME override, --all-sessions directory mode, and conversation-id
derivation from filename.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.conversation_cmd import _escape_cwd_as_project_dir, app

runner = CliRunner()

# Rich auto-highlights numbers and certain keywords when the env looks like a
# terminal (FORCE_COLOR / GITHUB_ACTIONS). Strip ANSI before asserting so the
# tests are CI-flake-proof regardless of env. Found by grok review 2026-07-24.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


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
    assert "Imported 2 new turns" in _strip_ansi(result.output)
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
    assert "does not exist" in _strip_ansi(result.output)


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


def test_import_claude_auto_discover_via_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty --source → newest jsonl from ~/.claude/projects/<escaped-cwd>/."""
    home = tmp_path / "home"
    # cwd-based escaped name = tmp_path with / → -
    escaped = _escape_cwd_as_project_dir(tmp_path)
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
    assert "Imported 1 new turns" in _strip_ansi(result.output)
    assert (storage / "mirror-claude-new.json").exists()
    # old not imported (no --all-sessions)
    assert not (storage / "mirror-claude-old.json").exists()


def test_import_claude_auto_discover_nothing_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto-discover with empty project dir → exit 1."""
    home = tmp_path / "home"
    escaped = _escape_cwd_as_project_dir(tmp_path)
    project_dir = home / ".claude" / "projects" / escaped
    project_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)

    result = runner.invoke(
        app,
        ["import-claude", "--storage-dir", str(tmp_path / "conv")],
    )
    assert result.exit_code != 0
    assert "no Claude jsonl found" in _strip_ansi(result.output)


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
    assert "2 session(s)" in _strip_ansi(result.output)


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
    assert "Imported 1 new turns" in _strip_ansi(first.output)
    second = runner.invoke(app, args)
    assert second.exit_code == 0
    assert "Imported 0 new turns" in _strip_ansi(second.output)


# ----------------------------------------------------------------------
# Phase 2 (Path-1 extension): --capture-depth flag + config fallback
# ----------------------------------------------------------------------


def _assistant_with_thinking(
    thinking: str, text: str, ts: str = "2026-07-23T15:20:00.000Z"
) -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": thinking},
                {"type": "text", "text": text},
            ],
        },
        "timestamp": ts,
    }


def test_import_claude_capture_depth_standard_by_default(tmp_path: Path) -> None:
    """No --capture-depth and no config → standard (thinking captured)."""
    src = _make_jsonl(
        tmp_path / "s.jsonl",
        [_assistant_with_thinking("pondering", "answer")],
    )
    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        ["import-claude", "--source", str(src), "--storage-dir", str(storage)],
    )
    assert result.exit_code == 0, result.output
    assert "capture_depth=standard" in _strip_ansi(result.output)
    conv = _read_conv(storage, "mirror-claude-s")
    assert conv["turns"][0]["thinking"] == "pondering"


def test_import_claude_capture_depth_minimal_flag_suppresses_thinking(tmp_path: Path) -> None:
    """--capture-depth minimal → thinking dropped."""
    src = _make_jsonl(
        tmp_path / "s.jsonl",
        [_assistant_with_thinking("secret", "answer")],
    )
    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        [
            "import-claude",
            "--source",
            str(src),
            "--storage-dir",
            str(storage),
            "--capture-depth",
            "minimal",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "capture_depth=minimal" in _strip_ansi(result.output)
    conv = _read_conv(storage, "mirror-claude-s")
    assert conv["turns"][0]["thinking"] is None


def test_import_claude_capture_depth_full_includes_tool_result_preview(tmp_path: Path) -> None:
    """--capture-depth full → tool_result.content_preview captured."""
    src = _make_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tu_1",
                            "is_error": False,
                            "content": "real output text",
                        },
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        [
            "import-claude",
            "--source",
            str(src),
            "--storage-dir",
            str(storage),
            "--capture-depth",
            "full",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "capture_depth=full" in _strip_ansi(result.output)
    conv = _read_conv(storage, "mirror-claude-s")
    assert conv["turns"][0]["tool_results"][0]["content_preview"] == "real output text"


def test_import_claude_capture_depth_config_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No --capture-depth, but config sets capture_depth=minimal → respected."""
    # Create .vibe/config.toml in the isolated cwd
    vibe_dir = tmp_path / ".vibe"
    vibe_dir.mkdir()
    (vibe_dir / "config.toml").write_text(
        '[conversation_mirror]\ncapture_depth = "minimal"\n',
        encoding="utf-8",
    )

    src = _make_jsonl(
        tmp_path / "s.jsonl",
        [_assistant_with_thinking("pondering", "answer")],
    )
    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        ["import-claude", "--source", str(src), "--storage-dir", str(storage)],
    )
    assert result.exit_code == 0, result.output
    assert "capture_depth=minimal" in _strip_ansi(result.output)
    conv = _read_conv(storage, "mirror-claude-s")
    assert conv["turns"][0]["thinking"] is None


def test_import_claude_cli_flag_overrides_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Config says minimal, CLI flag says full → full wins."""
    vibe_dir = tmp_path / ".vibe"
    vibe_dir.mkdir()
    (vibe_dir / "config.toml").write_text(
        '[conversation_mirror]\ncapture_depth = "minimal"\n',
        encoding="utf-8",
    )

    src = _make_jsonl(
        tmp_path / "s.jsonl",
        [_assistant_with_thinking("pondering", "answer")],
    )
    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        [
            "import-claude",
            "--source",
            str(src),
            "--storage-dir",
            str(storage),
            "--capture-depth",
            "full",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "capture_depth=full" in _strip_ansi(result.output)
    conv = _read_conv(storage, "mirror-claude-s")
    assert conv["turns"][0]["thinking"] == "pondering"


# ----------------------------------------------------------------------
# P1 fix (grok+pi review): --purge flag + thin-turn warning
# ----------------------------------------------------------------------


def _write_thin_mirror_file(storage: Path, cid: str = "s") -> None:
    """Simulate a pre-Path-1 mirror file: turns lack thinking/tool_calls keys."""
    storage.mkdir(parents=True, exist_ok=True)
    (storage / f"mirror-claude-{cid}.json").write_text(
        json.dumps(
            {
                "conversation_id": f"mirror-claude-{cid}",
                "turns": [
                    # Pre-Path-1 shape: only query/skill_id/timestamp/role/content.
                    # No thinking, tool_calls, tool_results, model, usage, stop_reason.
                    {"query": "old q", "skill_id": None, "timestamp": 1.0, "role": "user"}
                ],
                "last_activity": 1.0,
            }
        ),
        encoding="utf-8",
    )


def test_import_claude_warns_on_thin_turns_without_purge(tmp_path: Path) -> None:
    """Re-importing over a pre-Path-1 file prints the warning (no purge)."""
    src = _make_jsonl(
        tmp_path / "s.jsonl",
        [_assistant_with_thinking("rich thinking", "rich answer")],
    )
    storage = tmp_path / "conv"
    _write_thin_mirror_file(storage)

    result = runner.invoke(
        app,
        ["import-claude", "--source", str(src), "--storage-dir", str(storage)],
    )
    assert result.exit_code == 0, result.output
    assert "pre-Path-1 turns" in _strip_ansi(result.output)
    assert "--purge" in _strip_ansi(result.output)


def test_import_claude_purge_wipes_then_imports_clean(tmp_path: Path) -> None:
    """--purge deletes the thin file, then imports cleanly (no dups)."""
    src = _make_jsonl(
        tmp_path / "s.jsonl",
        [_assistant_with_thinking("rich thinking", "rich answer")],
    )
    storage = tmp_path / "conv"
    _write_thin_mirror_file(storage)
    # Sanity: thin file exists
    thin_path = storage / "mirror-claude-s.json"
    assert thin_path.exists()

    result = runner.invoke(
        app,
        [
            "import-claude",
            "--source",
            str(src),
            "--storage-dir",
            str(storage),
            "--purge",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Purged mirror-claude-s.json" in _strip_ansi(result.output)
    # No warning when --purge is set
    assert "pre-Path-1 turns" not in _strip_ansi(result.output)
    # File now has the rich turn only
    conv = _read_conv(storage, "mirror-claude-s")
    assert len(conv["turns"]) == 1
    assert conv["turns"][0]["thinking"] == "rich thinking"


def test_import_claude_no_warning_when_file_has_path1_fields(tmp_path: Path) -> None:
    """Files with Path-1 fields (even if all None) don't trigger the warning."""
    src = _make_jsonl(
        tmp_path / "s.jsonl",
        [_user("q2")],
    )
    storage = tmp_path / "conv"
    storage.mkdir(parents=True)
    # File already has Path-1 keys (even though values are None) — not thin.
    (storage / "mirror-claude-s.json").write_text(
        json.dumps(
            {
                "conversation_id": "mirror-claude-s",
                "turns": [
                    {
                        "query": "q1",
                        "skill_id": None,
                        "timestamp": 1.0,
                        "role": "user",
                        "thinking": None,  # key present → not thin
                        "tool_calls": None,
                        "tool_results": None,
                        "model": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["import-claude", "--source", str(src), "--storage-dir", str(storage)],
    )
    assert result.exit_code == 0, result.output
    assert "pre-Path-1" not in _strip_ansi(result.output)


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

    def test_conversation_id_falls_back_to_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
        assert (tmp_path / ".vibe" / "conversations" / "mirror-claude-env-session-99.json").exists()

    def test_conversation_id_falls_back_to_timestamp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
    def test_storage_lands_in_vibe_conversations_under_project_root(self, tmp_path: Path) -> None:
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


class TestAppendTurnMaxHistory:
    """P0 regression: live mirror MUST NOT truncate at ConversationContext's
    default of 10. The original ConversationContext default is tuned for
    routing hints; mirror use case needs the larger 200 default that
    batch-import uses. Found by pi review 2026-07-24."""

    def test_15_turns_all_preserved_default(self, tmp_path: Path) -> None:
        """Default config (no conversation_mirror.max_history) keeps all 15."""
        for i in range(15):
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "stress-sid",
                "prompt": f"turn-{i}",
            }
            result = runner.invoke(
                app,
                ["append-turn", "--project-root", str(tmp_path)],
                input=json.dumps(payload),
            )
            assert result.exit_code == 0, result.output
        conv = _read_conv(tmp_path / ".vibe" / "conversations", "mirror-claude-stress-sid")
        # CRITICAL: would be 10 if we forgot to override max_history
        assert len(conv["turns"]) == 15
        queries = [t["query"] for t in conv["turns"]]
        assert queries[0] == "turn-0"
        assert queries[-1] == "turn-14"

    def test_max_history_config_respected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """conversation_mirror.max_history=5 → only last 5 kept."""
        vibe_dir = tmp_path / ".vibe"
        vibe_dir.mkdir()
        (vibe_dir / "config.toml").write_text(
            "[conversation_mirror]\nmax_history = 5\n",
            encoding="utf-8",
        )
        for i in range(10):
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "cfg-sid",
                "prompt": f"t{i}",
            }
            result = runner.invoke(
                app,
                ["append-turn", "--project-root", str(tmp_path)],
                input=json.dumps(payload),
            )
            assert result.exit_code == 0, result.output
        conv = _read_conv(tmp_path / ".vibe" / "conversations", "mirror-claude-cfg-sid")
        assert len(conv["turns"]) == 5
        assert [t["query"] for t in conv["turns"]] == ["t5", "t6", "t7", "t8", "t9"]


# ──────────────────────────────────────────────────────────────────
# Sub-agent mirror (Phase 2)
# ──────────────────────────────────────────────────────────────────


def _make_subagent_tree(
    tmp_path: Path,
    *,
    session_id: str = "4c0b62ec-2a4b-435c-8088-a4d3be903f16",
    subagents: list[tuple[str, dict, list[dict]]],
) -> Path:
    """Lay out a Claude project dir with one session jsonl + N sub-agent jsonls.

    Mirrors the on-disk layout produced by Claude Code:

        <tmp>/proj/  <session>.jsonl
                     <session>/subagents/agent-<id>.jsonl
                     <session>/subagents/agent-<id>.meta.json
    """
    import os

    proj = tmp_path / "proj"
    proj.mkdir()
    main = proj / f"{session_id}.jsonl"
    _make_jsonl(main, [_user("kickoff"), _assistant("dispatching")])
    sub_dir = proj / session_id / "subagents"
    sub_dir.mkdir(parents=True)
    for idx, (agent_id, meta, lines) in enumerate(subagents):
        sub_jsonl = sub_dir / f"agent-{agent_id}.jsonl"
        _make_jsonl(sub_jsonl, lines)
        (sub_dir / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
        os.utime(sub_jsonl, (10.0 + idx, 10.0 + idx))
    return main


def test_import_claude_default_includes_subagents(tmp_path: Path) -> None:
    """Default invocation imports both main + each sub-agent transcript."""
    main = _make_subagent_tree(
        tmp_path,
        subagents=[
            (
                "a007cb9a1cdae69c4",
                {"agentType": "Explore", "description": "Map server"},
                [_user("explore"), _assistant("found it")],
            ),
            (
                "b0522f2c200b3bc06",
                {"agentType": "general-purpose", "description": "Adversary"},
                [_user("attack")],
            ),
        ],
    )
    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        ["import-claude", "--source", str(main), "--storage-dir", str(storage)],
    )
    assert result.exit_code == 0, result.output
    output = _strip_ansi(result.output)

    # Main conversation imported
    assert (storage / "mirror-claude-4c0b62ec-2a4b-435c-8088-a4d3be903f16.json").exists()
    # Two sub-agent conversations imported with derived ids.
    # ID format changed in Phase 2 P1 fix: <parent>-sub-<agentId> (no index/type)
    # so that mtime reorders / meta edits don't orphan old conversation files.
    sub1 = storage / "mirror-claude-4c0b62ec-2a4b-435c-8088-a4d3be903f16-sub-a007cb9a1cdae69c4.json"
    sub2 = storage / "mirror-claude-4c0b62ec-2a4b-435c-8088-a4d3be903f16-sub-b0522f2c200b3bc06.json"
    assert sub1.exists(), output
    assert sub2.exists(), output

    # Output reports sub-agent counts (Rich may line-wrap, so check fragments)
    assert "2 sub-agent transcript(s)" in output
    assert "sub-agent 1/2" in output and "sub-agent 2/2" in output
    assert "Explore — Map server" in output


def test_import_claude_no_include_subagents_skips_subagents(tmp_path: Path) -> None:
    """--no-include-subagents → only main transcript; no sub-agent files written."""
    main = _make_subagent_tree(
        tmp_path,
        subagents=[
            (
                "a007cb9a1cdae69c4",
                {"agentType": "Explore"},
                [_user("explore")],
            ),
        ],
    )
    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        [
            "import-claude",
            "--source",
            str(main),
            "--storage-dir",
            str(storage),
            "--no-include-subagents",
        ],
    )
    assert result.exit_code == 0, result.output
    output = _strip_ansi(result.output)
    assert "sub-agent turn(s)" not in output

    # Only main conversation file exists
    files = list(storage.glob("*.json"))
    assert len(files) == 1
    assert files[0].name.startswith("mirror-claude-4c0b62ec")


def test_import_claude_subagent_purge_wipes_subagent_files(tmp_path: Path) -> None:
    """--purge wipes both main + sub-agent conversations before re-import."""
    main = _make_subagent_tree(
        tmp_path,
        subagents=[
            (
                "a007cb9a1cdae69c4",
                {"agentType": "Explore", "description": "first"},
                [_user("v1")],
            ),
        ],
    )
    storage = tmp_path / "conv"
    args = ["import-claude", "--source", str(main), "--storage-dir", str(storage)]
    # First import creates the files
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    sub_file = (
        storage / "mirror-claude-4c0b62ec-2a4b-435c-8088-a4d3be903f16-sub-a007cb9a1cdae69c4.json"
    )
    assert sub_file.exists()
    # Manually add a stale turn to verify purge actually wipes (not just idempotent skip)
    sub_data = json.loads(sub_file.read_text(encoding="utf-8"))
    sub_data["turns"].append({"query": "STALE", "skill_id": None, "timestamp": 0.0})
    sub_file.write_text(json.dumps(sub_data), encoding="utf-8")

    # Re-import with --purge
    purge_result = runner.invoke(app, [*args, "--purge"])
    assert purge_result.exit_code == 0, purge_result.output
    purged_data = json.loads(sub_file.read_text(encoding="utf-8"))
    assert all(t.get("query") != "STALE" for t in purged_data["turns"])


def test_import_claude_subagent_no_subagents_dir_is_noop(tmp_path: Path) -> None:
    """Session with no subagents/ dir imports cleanly — no sub-agent lines in output."""
    # Build a main jsonl with no sibling <session>/ dir
    proj = tmp_path / "proj"
    proj.mkdir()
    main = proj / "sess.jsonl"
    _make_jsonl(main, [_user("hi")])

    storage = tmp_path / "conv"
    result = runner.invoke(
        app,
        ["import-claude", "--source", str(main), "--storage-dir", str(storage)],
    )
    assert result.exit_code == 0, result.output
    output = _strip_ansi(result.output)
    assert "sub-agent" not in output
    assert "0 sub-agent turn(s)" not in output  # the summary line is suppressed entirely
