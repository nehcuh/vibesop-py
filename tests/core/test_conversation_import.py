"""Tests for ``vibesop.core.conversation_import``.

Covers parse_claude_jsonl (all content block shapes, idempotency, dedup,
max_history) against realistic inline fixtures modelled on the real Claude
Code transcript format at ``~/.claude/projects/<escaped>/<session>.jsonl``.
"""

from __future__ import annotations

import json
from pathlib import Path

from vibesop.core.conversation import ConversationContext
from vibesop.core.conversation_import import (
    _turn_hash,
    import_session,
    parse_claude_jsonl,
)


def _write_jsonl(path: Path, lines: list[dict]) -> Path:
    """Write a list of dict records as a jsonl file."""
    with path.open("w", encoding="utf-8") as f:
        for rec in lines:
            f.write(json.dumps(rec, ensure_ascii=False))
            f.write("\n")
    return path


# ──────────────────────────────────────────────────────────────────
# parse_claude_jsonl
# ──────────────────────────────────────────────────────────────────


def test_parse_user_and_assistant_string_content(tmp_path: Path) -> None:
    """Plain-string user prompt + plain-string assistant reply both parse."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {"type": "mode", "mode": "normal"},
            {
                "type": "user",
                "message": {"role": "user", "content": "hello world"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "hi there"},
                "timestamp": "2026-07-23T15:20:01.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    assert len(turns) == 2
    assert turns[0].role == "user"
    assert turns[0].query == "hello world"
    assert turns[0].content is None
    assert turns[1].role == "assistant"
    assert turns[1].query == ""
    assert turns[1].content == "hi there"


def test_parse_assistant_list_text_blocks_concatenated(tmp_path: Path) -> None:
    """Assistant content as a list of text blocks is joined with newline."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "first"},
                        {"type": "text", "text": "second"},
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    assert len(turns) == 1
    assert turns[0].content == "first\nsecond"


def test_parse_assistant_non_text_blocks_only_yields_empty_turn(tmp_path: Path) -> None:
    """Assistant with only tool_use/tool_result blocks still produces a turn."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}},
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    assert len(turns) == 1
    assert turns[0].role == "assistant"
    assert turns[0].content == ""


def test_parse_skips_non_user_assistant_lines(tmp_path: Path) -> None:
    """mode/permission-mode/attachment/ai-title/file-history-snapshot skipped."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {"type": "mode", "mode": "normal"},
            {"type": "permission-mode", "permissionMode": "auto"},
            {"type": "file-history-snapshot", "snapshot": {}},
            {"type": "attachment", "attachment": {}},
            {"type": "ai-title", "title": "x"},
            {
                "type": "user",
                "message": {"role": "user", "content": "real"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    assert len(turns) == 1
    assert turns[0].query == "real"


def test_parse_malformed_json_line_skipped(tmp_path: Path) -> None:
    """Broken JSON lines don't raise — they're skipped."""
    path = tmp_path / "s.jsonl"
    with path.open("w", encoding="utf-8") as f:
        f.write('{"type": "user", "message": {"role": "user", "content": "a"}, "timestamp": "2026-07-23T15:20:00.000Z"}\n')
        f.write("not valid json\n")
        f.write('{"type": "user", "message": {"role": "user", "content": "b"}, "timestamp": "2026-07-23T15:20:01.000Z"}\n')
    turns = parse_claude_jsonl(path)
    assert len(turns) == 2
    assert [t.query for t in turns] == ["a", "b"]


def test_parse_missing_timestamp_uses_zero(tmp_path: Path) -> None:
    """Missing timestamp yields 0.0 — turn still recorded."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [{"type": "user", "message": {"role": "user", "content": "x"}}],
    )
    turns = parse_claude_jsonl(src)
    assert len(turns) == 1
    assert turns[0].timestamp == 0.0


def test_parse_iso_with_z_suffix(tmp_path: Path) -> None:
    """ISO-8601 with trailing Z parses to a positive epoch."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "x"},
                "timestamp": "2026-07-23T15:20:00.312Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    assert turns[0].timestamp > 1_700_000_000.0


def test_parse_tz_naive_assumed_utc(tmp_path: Path) -> None:
    """Naive ISO timestamps treated as UTC (matches aggregator.py convention)."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "x"},
                "timestamp": "2026-07-23T15:20:00.000",  # no Z, no offset
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    # Same instant as the Z-suffixed version above
    expected = parse_claude_jsonl(
        _write_jsonl(
            tmp_path / "s2.jsonl",
            [
                {
                    "type": "user",
                    "message": {"role": "user", "content": "x"},
                    "timestamp": "2026-07-23T15:20:00.000Z",
                },
            ],
        )
    )[0].timestamp
    assert turns[0].timestamp == expected


def test_parse_missing_file_returns_empty(tmp_path: Path) -> None:
    """A non-existent source returns [] (OSError handled)."""
    turns = parse_claude_jsonl(tmp_path / "nope.jsonl")
    assert turns == []


# ──────────────────────────────────────────────────────────────────
# import_session
# ──────────────────────────────────────────────────────────────────


def test_import_creates_new_file(tmp_path: Path) -> None:
    src = _write_jsonl(
        tmp_path / "src.jsonl",
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "q1"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "a1"},
                "timestamp": "2026-07-23T15:20:01.000Z",
            },
        ],
    )
    storage = tmp_path / "conv"
    n = import_session(src, "mirror-claude-x", storage)
    assert n == 2
    assert (storage / "mirror-claude-x.json").exists()
    ctx = ConversationContext(conversation_id="mirror-claude-x", storage_dir=storage)
    turns = ctx.get_history()
    assert len(turns) == 2
    assert turns[0].role == "user"
    assert turns[0].query == "q1"
    assert turns[1].role == "assistant"
    assert turns[1].content == "a1"


def test_import_idempotent_second_run_zero(tmp_path: Path) -> None:
    """Re-importing the same source produces zero new turns."""
    src = _write_jsonl(
        tmp_path / "src.jsonl",
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "q1"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    storage = tmp_path / "conv"
    first = import_session(src, "c", storage)
    second = import_session(src, "c", storage)
    assert first == 1
    assert second == 0


def test_import_growing_session(tmp_path: Path) -> None:
    """Append a new line to the source, re-import → only new turn added."""
    src = tmp_path / "src.jsonl"
    _write_jsonl(
        src,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "q1"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    storage = tmp_path / "conv"
    first = import_session(src, "c", storage)
    assert first == 1

    # Append a fresh turn to the same jsonl
    with src.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "type": "user",
                    "message": {"role": "user", "content": "q2"},
                    "timestamp": "2026-07-23T15:21:00.000Z",
                }
            )
            + "\n"
        )
    second = import_session(src, "c", storage)
    assert second == 1
    ctx = ConversationContext(conversation_id="c", storage_dir=storage)
    queries = [t.query for t in ctx.get_history()]
    assert queries == ["q1", "q2"]


def test_import_preserves_existing_non_mirror_turns(tmp_path: Path) -> None:
    """Pre-existing user turns (e.g. from routing) survive a mirror import."""
    storage = tmp_path / "conv"
    ctx = ConversationContext(conversation_id="c", storage_dir=storage, max_history=200)
    ctx.add_turn("existing routing query", skill_id="some/skill")
    ctx.save()

    src = _write_jsonl(
        tmp_path / "src.jsonl",
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "mirror q"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    n = import_session(src, "c", storage)
    assert n == 1

    restored = ConversationContext(conversation_id="c", storage_dir=storage, max_history=200)
    turns = restored.get_history()
    # routing turn still there + mirror turn appended
    assert len(turns) == 2
    assert turns[0].query == "existing routing query"
    assert turns[0].skill_id == "some/skill"
    assert turns[1].query == "mirror q"


def test_import_respects_max_history(tmp_path: Path) -> None:
    """max_history=3 trims the front of a 10-line source."""
    lines = [
        {
            "type": "user",
            "message": {"role": "user", "content": f"q{i}"},
            "timestamp": f"2026-07-23T15:20:0{i}.000Z",
        }
        for i in range(10)
    ]
    src = _write_jsonl(tmp_path / "src.jsonl", lines)
    storage = tmp_path / "conv"
    n = import_session(src, "c", storage, max_history=3)
    assert n == 10  # all were new
    ctx = ConversationContext(conversation_id="c", storage_dir=storage, max_history=3)
    turns = ctx.get_history()
    assert len(turns) == 3
    # last 3 wins (q7, q8, q9)
    assert [t.query for t in turns] == ["q7", "q8", "q9"]


def test_turn_hash_stable_across_roles() -> None:
    """Hash changes when role, content, or timestamp differs."""
    from vibesop.core.conversation import ConversationTurn

    a = ConversationTurn(query="q", skill_id=None, timestamp=1.0, role="user")
    b = ConversationTurn(query="", skill_id=None, timestamp=1.0, role="assistant", content="q")
    c = ConversationTurn(query="q", skill_id=None, timestamp=2.0, role="user")
    d = ConversationTurn(query="other", skill_id=None, timestamp=1.0, role="user")
    assert _turn_hash(a) != _turn_hash(b)
    assert _turn_hash(a) != _turn_hash(c)
    assert _turn_hash(a) != _turn_hash(d)
    assert _turn_hash(a) == _turn_hash(
        ConversationTurn(query="q", skill_id=None, timestamp=1.0, role="user")
    )
