"""Tests for ``vibesop.core.conversation_import``.

Covers parse_claude_jsonl (all content block shapes, idempotency, dedup,
max_history) against realistic inline fixtures modelled on the real Claude
Code transcript format at ``~/.claude/projects/<escaped>/<session>.jsonl``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vibesop.core.conversation import ConversationContext
from vibesop.core.conversation_import import (
    _turn_hash,
    import_session,
    parse_claude_jsonl,
)

if TYPE_CHECKING:
    import pytest


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
    """Assistant with only tool_use blocks: content=None, tool_calls populated."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "tu_1", "name": "Bash", "input": {"cmd": "ls"}},
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    assert len(turns) == 1
    assert turns[0].role == "assistant"
    assert turns[0].content is None
    assert turns[0].tool_calls is not None
    assert len(turns[0].tool_calls) == 1
    assert turns[0].tool_calls[0].id == "tu_1"
    assert turns[0].tool_calls[0].name == "Bash"
    assert turns[0].tool_calls[0].input_keys == ["cmd"]


# ──────────────────────────────────────────────────────────────────
# Path-1 extension: thinking / tool_use / tool_result / model / usage
# ──────────────────────────────────────────────────────────────────


def test_parse_thinking_captured_at_standard_depth(tmp_path: Path) -> None:
    """Assistant thinking block is captured when capture_depth >= standard."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "Pondering options"},
                        {"type": "text", "text": "Here is the answer"},
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)  # default depth = standard
    assert turns[0].thinking == "Pondering options"
    assert turns[0].content == "Here is the answer"


def test_parse_thinking_suppressed_at_minimal_depth(tmp_path: Path) -> None:
    """capture_depth='minimal' drops thinking blocks (legacy behavior)."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "secret"},
                        {"type": "text", "text": "answer"},
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src, capture_depth="minimal")
    assert turns[0].thinking is None
    assert turns[0].content == "answer"
    assert turns[0].tool_calls is None


def test_parse_tool_use_keys_only_never_values(tmp_path: Path) -> None:
    """Privacy: tool_use input KEYS captured, VALUES never."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tu_42",
                            "name": "Edit",
                            "input": {"file_path": "/secret", "old_string": "x", "new_string": "y"},
                        },
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    tc = turns[0].tool_calls[0]
    assert tc.id == "tu_42"
    assert tc.name == "Edit"
    # Sorted keys only — no values leak
    assert tc.input_keys == ["file_path", "new_string", "old_string"]


def test_parse_tool_result_on_following_user_message(tmp_path: Path) -> None:
    """Claude Code convention: tool_result blocks land on the next user message."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "running"},
                        {"type": "tool_use", "id": "tu_1", "name": "Bash", "input": {}},
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tu_1",
                            "is_error": False,
                            "content": "ok",
                        },
                    ],
                },
                "timestamp": "2026-07-23T15:20:01.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    assert len(turns) == 2
    # Assistant turn: tool_use recorded, no tool_results
    assert turns[0].role == "assistant"
    assert turns[0].tool_calls is not None
    assert turns[0].tool_results is None
    # Following user turn: tool_result recorded under tool_results
    assert turns[1].role == "user"
    assert turns[1].tool_results is not None
    assert len(turns[1].tool_results) == 1
    assert turns[1].tool_results[0].tool_use_id == "tu_1"
    assert turns[1].tool_results[0].is_error is False
    # Default depth = standard → no content_preview
    assert turns[1].tool_results[0].content_preview is None


def test_parse_tool_result_error_flag_always_captured(tmp_path: Path) -> None:
    """is_error is captured even at standard depth (no preview)."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tu_9",
                            "is_error": True,
                            "content": "Command failed",
                        },
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    tr = turns[0].tool_results[0]
    assert tr.is_error is True
    assert tr.content_preview is None  # standard depth


def test_parse_tool_result_preview_only_at_full_depth(tmp_path: Path) -> None:
    """content_preview requires capture_depth='full'; truncates to 200 chars."""
    long_text = "x" * 500
    src = _write_jsonl(
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
                            "content": long_text,
                        },
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    full = parse_claude_jsonl(src, capture_depth="full")
    standard = parse_claude_jsonl(src, capture_depth="standard")
    assert len(full[0].tool_results[0].content_preview) == 200
    assert standard[0].tool_results[0].content_preview is None


def test_parse_tool_result_list_content_shape(tmp_path: Path) -> None:
    """tool_result.content as list of {type: text} blocks is concatenated + truncated."""
    src = _write_jsonl(
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
                            "content": [
                                {"type": "text", "text": "line1"},
                                {"type": "text", "text": "line2"},
                            ],
                        },
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src, capture_depth="full")
    assert turns[0].tool_results[0].content_preview == "line1\nline2"


def test_parse_model_usage_stop_reason_captured(tmp_path: Path) -> None:
    """Envelope model/usage/stop_reason are captured at standard depth."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hi"}],
                    "model": "claude-sonnet-4-6",
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_creation_input_tokens": 10,
                        "cache_read_input_tokens": 5,
                    },
                    "stop_reason": "end_turn",
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    assert turns[0].model == "claude-sonnet-4-6"
    assert turns[0].usage == {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 10,
        "cache_read_input_tokens": 5,
    }
    assert turns[0].stop_reason == "end_turn"


def test_parse_usage_drops_non_int_keys(tmp_path: Path) -> None:
    """Malformed usage entries are silently dropped, not the whole dict."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "x"}],
                    "usage": {"input_tokens": 5, "bogus": "nope", "output_tokens": "bad"},
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src)
    assert turns[0].usage == {"input_tokens": 5}


def test_capture_depth_unknown_falls_back_to_standard(tmp_path: Path) -> None:
    """Bogus capture_depth value logs + falls back to standard (never raises)."""
    src = _write_jsonl(
        tmp_path / "s.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "t"},
                        {"type": "text", "text": "x"},
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    turns = parse_claude_jsonl(src, capture_depth="bogus")
    assert turns[0].thinking == "t"  # standard behavior applied


# ──────────────────────────────────────────────────────────────────
# Hash v2 — idempotency contract after Path-1
# ──────────────────────────────────────────────────────────────────


def test_turn_hash_includes_thinking_and_tool_calls() -> None:
    """Adding thinking/tool_calls to an otherwise-identical turn yields a new hash."""
    from vibesop.core.conversation import ConversationTurn, ToolCall

    base = ConversationTurn(query="", skill_id=None, timestamp=1.0, role="assistant", content="hi")
    with_thinking = ConversationTurn(
        query="",
        skill_id=None,
        timestamp=1.0,
        role="assistant",
        content="hi",
        thinking="Pondering",
    )
    with_tool = ConversationTurn(
        query="",
        skill_id=None,
        timestamp=1.0,
        role="assistant",
        content="hi",
        tool_calls=[ToolCall(id="tu_1", name="Bash", input_keys=["cmd"])],
    )
    assert _turn_hash(base) != _turn_hash(with_thinking)
    assert _turn_hash(base) != _turn_hash(with_tool)
    assert _turn_hash(with_thinking) != _turn_hash(with_tool)


def test_turn_hash_includes_tool_results() -> None:
    """User turns distinguished by their tool_result set, not just query/timestamp."""
    from vibesop.core.conversation import ConversationTurn, ToolResult

    base = ConversationTurn(query="", skill_id=None, timestamp=1.0, role="user")
    with_result = ConversationTurn(
        query="",
        skill_id=None,
        timestamp=1.0,
        role="user",
        tool_results=[ToolResult(tool_use_id="tu_1", is_error=False)],
    )
    assert _turn_hash(base) != _turn_hash(with_result)


def test_turn_hash_has_v2_prefix() -> None:
    """All hashes start with 'v2:' for migration detection."""
    from vibesop.core.conversation import ConversationTurn

    h = _turn_hash(ConversationTurn(query="q", skill_id=None, timestamp=1.0))
    assert h.startswith("v2:")


def test_turn_hash_excludes_model_and_usage() -> None:
    """Re-running the same prompt under a different model is the same turn for dedup."""
    from vibesop.core.conversation import ConversationTurn

    a = ConversationTurn(
        query="",
        skill_id=None,
        timestamp=1.0,
        role="assistant",
        content="hi",
        model="m1",
        usage={"input_tokens": 1},
    )
    b = ConversationTurn(
        query="",
        skill_id=None,
        timestamp=1.0,
        role="assistant",
        content="hi",
        model="m2",
        usage={"input_tokens": 999},
    )
    assert _turn_hash(a) == _turn_hash(b)


# ──────────────────────────────────────────────────────────────────
# import_session — plumbs new fields through
# ──────────────────────────────────────────────────────────────────


def test_import_session_writes_thinking_and_tool_calls(tmp_path: Path) -> None:
    """New fields survive all the way to disk via ConversationContext.add_turn."""
    src = _write_jsonl(
        tmp_path / "src.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "hmm"},
                        {
                            "type": "tool_use",
                            "id": "tu_1",
                            "name": "Read",
                            "input": {"file_path": "/a"},
                        },
                        {"type": "text", "text": "done"},
                    ],
                    "model": "claude-x",
                    "stop_reason": "end_turn",
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    storage = tmp_path / "conv"
    n = import_session(src, "c", storage)
    assert n == 1
    ctx = ConversationContext(conversation_id="c", storage_dir=storage)
    turns = ctx.get_history()
    assert turns[0].thinking == "hmm"
    assert turns[0].tool_calls is not None
    assert turns[0].tool_calls[0].name == "Read"
    assert turns[0].model == "claude-x"
    assert turns[0].stop_reason == "end_turn"


def test_import_session_accepts_capture_depth(tmp_path: Path) -> None:
    """import_session threads capture_depth through to parser."""
    src = _write_jsonl(
        tmp_path / "src.jsonl",
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
                            "content": "preview text",
                        },
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    storage = tmp_path / "conv"
    # full → preview captured
    import_session(src, "full", storage, capture_depth="full")
    ctx_full = ConversationContext(conversation_id="full", storage_dir=storage)
    assert ctx_full.get_history()[0].tool_results[0].content_preview == "preview text"

    # standard → no preview
    import_session(src, "standard", storage, capture_depth="standard")
    ctx_std = ConversationContext(conversation_id="standard", storage_dir=storage)
    assert ctx_std.get_history()[0].tool_results[0].content_preview is None


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
        f.write(
            '{"type": "user", "message": {"role": "user", "content": "a"}, "timestamp": "2026-07-23T15:20:00.000Z"}\n'
        )
        f.write("not valid json\n")
        f.write(
            '{"type": "user", "message": {"role": "user", "content": "b"}, "timestamp": "2026-07-23T15:20:01.000Z"}\n'
        )
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


# ──────────────────────────────────────────────────────────────────
# Sub-agent discovery + import (Phase 2)
# ──────────────────────────────────────────────────────────────────


def _write_subagent_tree(
    tmp_path: Path,
    *,
    session_id: str = "4c0b62ec-2a4b-435c-8088-a4d3be903f16",
    main_lines: list[dict] | None = None,
    subagents: list[tuple[str, dict, list[dict]]] | None = None,
) -> Path:
    """Lay out a Claude Code project dir with sub-agent transcripts.

    ``subagents`` is a list of ``(agent_id_hex, meta_dict, transcript_lines)``
    tuples. Writes the canonical paths:

        <escaped>/  <session>.jsonl
                    <session>/subagents/agent-<id>.jsonl
                    <session>/subagents/agent-<id>.meta.json

    Returns the path to the main session jsonl.
    """
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    main_path = project_dir / f"{session_id}.jsonl"
    _write_jsonl(
        main_path,
        main_lines
        or [
            {
                "type": "user",
                "message": {"role": "user", "content": "hi"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            }
        ],
    )

    if subagents:
        sub_dir = project_dir / session_id / "subagents"
        sub_dir.mkdir(parents=True)
        for idx, (agent_id, meta, lines) in enumerate(subagents):
            sub_jsonl = sub_dir / f"agent-{agent_id}.jsonl"
            _write_jsonl(sub_jsonl, lines)
            (sub_dir / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
            # Force ascending mtimes so discover_subagents returns spawn order.
            import os

            os.utime(sub_jsonl, (10.0 + idx, 10.0 + idx))
    return main_path


def test_discover_subagents_empty_when_no_dir(tmp_path: Path) -> None:
    """No subagents/ dir → empty list, no error."""
    from vibesop.core.conversation_import import discover_subagents

    main = tmp_path / "sess.jsonl"
    _write_jsonl(
        main,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "x"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            }
        ],
    )
    assert discover_subagents(main) == []


def test_discover_subagents_pairs_jsonl_with_meta(tmp_path: Path) -> None:
    """Each agent-<id>.jsonl is paired with its sibling .meta.json."""
    from vibesop.core.conversation_import import discover_subagents

    main = _write_subagent_tree(
        tmp_path,
        subagents=[
            (
                "a007cb9a1cdae69c4",
                {"agentType": "Explore", "description": "Map server", "toolUseId": "call_1"},
                [
                    {
                        "type": "user",
                        "message": {"role": "user", "content": "go"},
                        "timestamp": "2026-07-23T15:20:00.000Z",
                    }
                ],
            ),
            (
                "b0522f2c200b3bc06",
                {"agentType": "general-purpose", "description": "Adversary", "toolUseId": "call_2"},
                [
                    {
                        "type": "user",
                        "message": {"role": "user", "content": "attack"},
                        "timestamp": "2026-07-23T15:21:00.000Z",
                    }
                ],
            ),
        ],
    )
    records = discover_subagents(main)
    assert len(records) == 2
    # Sorted by mtime ascending (spawn order)
    assert records[0].agent_id == "a007cb9a1cdae69c4"
    assert records[0].meta["agentType"] == "Explore"
    assert records[0].meta["description"] == "Map server"
    assert records[1].agent_id == "b0522f2c200b3bc06"


def test_discover_subagents_handles_missing_meta(tmp_path: Path) -> None:
    """agent-<id>.jsonl without .meta.json still discovered — meta is empty dict."""
    from vibesop.core.conversation_import import discover_subagents

    main = _write_subagent_tree(
        tmp_path,
        subagents=[
            ("a007cb9a1cdae69c4", {}, []),  # meta dict empty → don't write meta.json
        ],
    )
    # Manually remove the meta.json that _write_subagent_tree wrote (since
    # we passed an empty meta dict it still wrote "{}" — delete for this test).
    meta_path = main.parent / main.stem / "subagents" / "agent-a007cb9a1cdae69c4.meta.json"
    meta_path.unlink()

    records = discover_subagents(main)
    assert len(records) == 1
    assert records[0].meta == {}


def test_discover_subagents_ignores_orphan_meta(tmp_path: Path) -> None:
    """meta.json without matching transcript is skipped silently."""
    from vibesop.core.conversation_import import discover_subagents

    main = _write_subagent_tree(tmp_path, subagents=[])
    sub_dir = main.parent / main.stem / "subagents"
    sub_dir.mkdir(parents=True)
    (sub_dir / "agent-orphanforsure0000.meta.json").write_text(
        json.dumps({"agentType": "Explore"}), encoding="utf-8"
    )
    records = discover_subagents(main)
    assert records == []


def test_parse_subagent_meta_returns_none_for_missing(tmp_path: Path) -> None:
    from vibesop.core.conversation_import import parse_subagent_meta

    assert parse_subagent_meta(tmp_path / "nope.json") is None


def test_parse_subagent_meta_returns_none_for_invalid_json(tmp_path: Path) -> None:
    from vibesop.core.conversation_import import parse_subagent_meta

    bad = tmp_path / "bad.meta.json"
    bad.write_text("{not json", encoding="utf-8")
    assert parse_subagent_meta(bad) is None


# ──────────────────────────────────────────────────────────────────
# parent_conversation_id join contract (v3 Phase A Task 6 / P0-3)
# ──────────────────────────────────────────────────────────────────


def test_import_subagent_writes_parent_conversation_id(tmp_path: Path) -> None:
    """v3 Phase A Task 6 / grok+pi P0-3: sub-agent conversation metadata
    must include ``parent_conversation_id`` (resolved mirror-claude-* id)
    so the DAG rebuilder can JOIN child.parent_conversation_id ==
    parent.conversation_id.

    Background: ``parent_session`` (raw path.stem) does NOT match the
    parent's mirror conversation id (``mirror-claude-{session[:20]}``),
    so JOIN by parent_session alone always misses.
    """
    from vibesop.core.conversation_import import (
        discover_subagents,
        import_subagent,
    )

    main = _write_subagent_tree(
        tmp_path,
        subagents=[
            (
                "a007cb9a1cdae69c4",
                {"agentType": "Explore", "description": "Map server"},
                [
                    {
                        "type": "user",
                        "message": {"role": "user", "content": "go"},
                        "timestamp": "2026-07-23T15:20:00.000Z",
                    }
                ],
            ),
        ],
    )
    record = discover_subagents(main)[0]

    # Parent conversation_id is the resolved mirror id (truncated + prefixed)
    parent_conv_id = "mirror-claude-abc123def456"
    sub_cid = "mirror-claude-abc123def456-sub-a007cb9a1cdae69c4"

    storage_dir = tmp_path / "conversations"
    import_subagent(
        record,
        sub_cid,
        storage_dir,
        parent_session_id=main.stem,  # raw session id (legacy)
        parent_conversation_id=parent_conv_id,  # resolved (new)
    )

    # Read sub-agent conversation file and verify both keys are persisted
    import json as _json

    sub_file = storage_dir / f"{sub_cid}.json"
    assert sub_file.exists(), f"sub-agent conversation not written: {sub_file}"
    data = _json.loads(sub_file.read_text())
    meta = data.get("metadata", {})
    assert meta.get("parent_conversation_id") == parent_conv_id, (
        f"parent_conversation_id missing or wrong: {meta}"
    )
    # Legacy parent_session is still written (raw path.stem) for backward compat
    assert meta.get("parent_session") == main.stem


def test_import_subagent_parent_conversation_id_optional(tmp_path: Path) -> None:
    """When parent_conversation_id is None (older callers), metadata should
    not contain the key — backward compat for code paths not yet migrated."""
    from vibesop.core.conversation_import import (
        discover_subagents,
        import_subagent,
    )

    main = _write_subagent_tree(
        tmp_path,
        subagents=[
            (
                "b0522f2c200b3bc06",
                {"agentType": "general-purpose"},
                [
                    {
                        "type": "user",
                        "message": {"role": "user", "content": "x"},
                        "timestamp": "2026-07-23T15:20:00.000Z",
                    }
                ],
            ),
        ],
    )
    record = discover_subagents(main)[0]
    storage_dir = tmp_path / "conversations"

    import_subagent(
        record,
        "sub-conv-no-parent",
        storage_dir,
        parent_session_id=main.stem,
        # parent_conversation_id omitted (default None)
    )

    import json as _json

    sub_file = storage_dir / "sub-conv-no-parent.json"
    data = _json.loads(sub_file.read_text())
    meta = data.get("metadata", {})
    assert "parent_conversation_id" not in meta, (
        f"parent_conversation_id should be absent when not passed: {meta}"
    )


def test_derive_subagent_conversation_id_stable_and_readable(tmp_path: Path) -> None:
    """Identity = parent + agent_id; stable across mtime/meta changes."""
    from vibesop.core.conversation_import import (
        SubagentRecord,
        derive_subagent_conversation_id,
    )

    record = SubagentRecord(
        jsonl_path=Path("x"),
        agent_id="a007cb9a1cdae69c4",
        meta={"agentType": "Explore", "description": "Map server"},
    )
    cid = derive_subagent_conversation_id("mirror-claude-4c0b62ec", record)
    # Identity no longer carries index or agentType — both can mutate across
    # re-imports (mtime reorders, meta edits). Found by grok+pi review.
    assert cid == "mirror-claude-4c0b62ec-sub-a007cb9a1cdae69c4"
    # Same inputs → same id (idempotent re-import)
    assert cid == derive_subagent_conversation_id("mirror-claude-4c0b62ec", record)


def test_derive_subagent_conversation_id_ignores_type_changes() -> None:
    """agentType / description edits must NOT change id (would orphan old file).

    This is the regression grok+pi flagged: previously id embedded agentType,
    so any meta correction (description filled in, type relabeled) orphaned
    the old conversation file.
    """
    from vibesop.core.conversation_import import (
        SubagentRecord,
        derive_subagent_conversation_id,
    )

    base_record = SubagentRecord(
        jsonl_path=Path("x"),
        agent_id="a007cb9a1cdae69c4",
        meta={"agentType": "Explore", "description": "first"},
    )
    reordered = SubagentRecord(
        jsonl_path=Path("x"),
        agent_id="a007cb9a1cdae69c4",
        meta={"agentType": "general-purpose", "description": "edited later"},
    )
    parent = "mirror-claude-sess"
    base_id = derive_subagent_conversation_id(parent, base_record)
    # Different agentType / description (meta corrected after first import)
    assert derive_subagent_conversation_id(parent, reordered) == base_id


def test_derive_subagent_conversation_id_sanitizes_path_traversal() -> None:
    """agentId containing '/' or '..' cannot escape storage_dir.

    Found by grok+pi review: _slugify_agent_type only truncated, leaving
    '/' intact. Defense-in-depth even though Claude Code emits hex today.
    """
    from vibesop.core.conversation_import import (
        SubagentRecord,
        derive_subagent_conversation_id,
    )

    malicious = SubagentRecord(
        jsonl_path=Path("x"),
        agent_id="../../etc/passwd",
        meta={},
    )
    cid = derive_subagent_conversation_id("mirror-claude-x", malicious)
    # No '/', no '..', only path-safe chars
    assert "/" not in cid
    assert ".." not in cid
    # Resulting filename stays a single segment under storage_dir
    assert cid.count("/") == 0


def test_import_subagent_writes_metadata_and_turns(tmp_path: Path) -> None:
    """import_subagent persists agentType/description in metadata + turns in file."""
    from vibesop.core.conversation_import import (
        SubagentRecord,
        import_subagent,
    )

    storage = tmp_path / "conv"
    sub_jsonl = tmp_path / "agent.jsonl"
    _write_jsonl(
        sub_jsonl,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "go"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "model": "claude-sonnet-4-6",
                    "content": [
                        {"type": "thinking", "thinking": "planning"},
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Read",
                            "input": {"file_path": "/x"},
                        },
                        {"type": "text", "text": "done"},
                    ],
                },
                "timestamp": "2026-07-23T15:20:01.000Z",
            },
        ],
    )
    record = SubagentRecord(
        jsonl_path=sub_jsonl,
        agent_id="a007cb9a1cdae69c4",
        meta={"agentType": "Explore", "description": "Map server", "toolUseId": "call_x"},
    )
    n = import_subagent(
        record,
        "mirror-claude-sess-sub1-Explore-a007cb9a",
        storage,
        parent_session_id="sess",
    )
    assert n == 2  # one user + one assistant turn

    ctx = ConversationContext(
        conversation_id="mirror-claude-sess-sub1-Explore-a007cb9a",
        storage_dir=storage,
    )
    # Metadata persisted
    assert ctx.metadata["agent_type"] == "Explore"
    assert ctx.metadata["description"] == "Map server"
    assert ctx.metadata["parent_session"] == "sess"
    assert ctx.metadata["tool_use_id"] == "call_x"
    assert ctx.metadata["agent_id"] == "a007cb9a1cdae69c4"
    assert ctx.metadata["is_subagent"] is True
    # Turns parsed
    turns = ctx.get_history()
    assert len(turns) == 2
    assert turns[1].thinking == "planning"
    assert turns[1].tool_calls is not None and turns[1].tool_calls[0].name == "Read"
    assert turns[1].model == "claude-sonnet-4-6"


def test_import_subagent_idempotent_on_rerun(tmp_path: Path) -> None:
    """Running import_subagent twice on the same transcript → 0 new turns."""
    from vibesop.core.conversation_import import (
        SubagentRecord,
        import_subagent,
    )

    storage = tmp_path / "conv"
    sub_jsonl = tmp_path / "agent.jsonl"
    _write_jsonl(
        sub_jsonl,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "go"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            }
        ],
    )
    record = SubagentRecord(
        jsonl_path=sub_jsonl,
        agent_id="a007cb9a1cdae69c4",
        meta={"agentType": "Explore"},
    )
    cid = "mirror-claude-sess-sub1-Explore-a007cb9a"
    assert import_subagent(record, cid, storage, parent_session_id="sess") == 1
    assert import_subagent(record, cid, storage, parent_session_id="sess") == 0


def test_import_subagent_respects_capture_depth(tmp_path: Path) -> None:
    """minimal depth skips thinking/tool_calls even on sub-agent transcripts."""
    from vibesop.core.conversation_import import (
        SubagentRecord,
        import_subagent,
    )

    storage = tmp_path / "conv"
    sub_jsonl = tmp_path / "agent.jsonl"
    _write_jsonl(
        sub_jsonl,
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "hidden"},
                        {"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
                        {"type": "text", "text": "ok"},
                    ],
                },
                "timestamp": "2026-07-23T15:20:00.000Z",
            },
        ],
    )
    record = SubagentRecord(jsonl_path=sub_jsonl, agent_id="abc", meta={})
    import_subagent(
        record,
        "c-min",
        storage,
        parent_session_id="p",
        capture_depth="minimal",
    )
    ctx = ConversationContext(conversation_id="c-min", storage_dir=storage)
    turns = ctx.get_history()
    assert len(turns) == 1
    assert turns[0].thinking is None
    assert turns[0].tool_calls is None


# ──────────────────────────────────────────────────────────────────
# Phase 2 P1 regressions (grok + pi review)
# ──────────────────────────────────────────────────────────────────


def test_import_subagent_persists_metadata_on_zero_new_turns(tmp_path: Path) -> None:
    """Re-import with 0 new turns (all duplicates) still writes updated metadata.

    Found by grok+pi review: previously ``import_subagent`` only saved via
    ``add_turn``, so when every parsed turn hashed as duplicate the new
    metadata (e.g. corrected description) never landed on disk.
    """
    from vibesop.core.conversation_import import (
        SubagentRecord,
        import_subagent,
    )

    storage = tmp_path / "conv"
    sub_jsonl = tmp_path / "agent.jsonl"
    _write_jsonl(
        sub_jsonl,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "x"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            }
        ],
    )

    # First import with empty description
    record_v1 = SubagentRecord(
        jsonl_path=sub_jsonl,
        agent_id="abc",
        meta={"agentType": "Explore", "description": ""},
    )
    import_subagent(record_v1, "c1", storage, parent_session_id="p")
    ctx1 = ConversationContext(conversation_id="c1", storage_dir=storage)
    assert ctx1.metadata.get("description") in (None, "")

    # Re-import with corrected description (same transcript → all dupes)
    record_v2 = SubagentRecord(
        jsonl_path=sub_jsonl,
        agent_id="abc",
        meta={"agentType": "Explore", "description": "Map server"},
    )
    new = import_subagent(record_v2, "c1", storage, parent_session_id="p")
    assert new == 0  # all turns were duplicates

    # Reload from disk — metadata update must have persisted
    ctx2 = ConversationContext(conversation_id="c1", storage_dir=storage)
    assert ctx2.metadata.get("description") == "Map server"


def test_import_subagent_persists_metadata_on_empty_transcript(tmp_path: Path) -> None:
    """Sub-agent with no user/assistant turns still gets a metadata-only file.

    Found by grok review (issue 8): previously ``if not parsed: return 0``
    skipped saving, leaving the dashboard blind to the sub-agent.
    """
    from vibesop.core.conversation_import import (
        SubagentRecord,
        import_subagent,
    )

    storage = tmp_path / "conv"
    sub_jsonl = tmp_path / "agent.jsonl"
    # Only non-user/assistant lines → parse_claude_jsonl returns []
    _write_jsonl(
        sub_jsonl,
        [
            {"type": "mode", "mode": "normal"},
            {"type": "attachment", "attachment": {}},
        ],
    )
    record = SubagentRecord(
        jsonl_path=sub_jsonl,
        agent_id="abc",
        meta={"agentType": "Explore", "description": "no turns yet"},
    )
    new = import_subagent(record, "c1", storage, parent_session_id="p")
    assert new == 0

    # File must still exist + carry metadata (so dashboard lists the sub-agent)
    ctx = ConversationContext(conversation_id="c1", storage_dir=storage)
    assert ctx.metadata["agent_type"] == "Explore"
    assert ctx.metadata["description"] == "no turns yet"
    assert ctx.metadata["is_subagent"] is True


def test_discover_subagents_does_not_raise_on_unreadable_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Permission errors during iterdir return [] rather than crashing CLI.

    Found by grok review (issue 6): docstring promised "never raises" but
    iterdir could raise on race or permission error.
    """
    from vibesop.core.conversation_import import discover_subagents

    main = _write_subagent_tree(
        tmp_path,
        subagents=[
            (
                "abc123",
                {"agentType": "Explore"},
                [
                    {
                        "type": "user",
                        "message": {"role": "user", "content": "go"},
                        "timestamp": "2026-07-23T15:20:00.000Z",
                    }
                ],
            ),
        ],
    )

    # Patch Path.iterdir to raise only when scanning the subagents dir.
    # Scoped monkeypatch — pytest's own tmp_path cleanup uses ``unlink`` /
    # ``stat``, not ``iterdir``, so this is safe within the test body.
    original_iterdir = Path.iterdir

    def raising_iterdir(self: Path) -> Any:
        if self.name == "subagents":
            raise PermissionError("denied")
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", raising_iterdir)
    records = discover_subagents(main)
    assert records == []


def test_discover_subagents_handles_stat_race(tmp_path: Path) -> None:
    """If jsonl vanishes between listing and stat, sort uses mtime=0 (no crash).

    Found by grok review (issue 6): mid-scan unlink could raise
    FileNotFoundError during the sort key evaluation. Verified via a
    direct call to the internal sort-key helper rather than monkey-patching
    Path.stat (which would break pytest's tmp_path cleanup).
    """
    from vibesop.core.conversation_import import SubagentRecord, _sort_key_safe

    # Vanished jsonl — Path.stat raises FileNotFoundError (subclass of OSError)
    vanished = tmp_path / "does-not-exist.jsonl"
    record = SubagentRecord(jsonl_path=vanished, agent_id="abc123", meta={})
    # Must not raise; mtime falls back to 0.0
    mtime, aid = _sort_key_safe(record)
    assert mtime == 0.0
    assert aid == "abc123"


def test_subagent_id_scheme_dropped_old_format_orphans(
    tmp_path: Path,
) -> None:
    """Re-import after mtime reorder must NOT produce duplicate conversation files.

    End-to-end regression for grok+pi finding: previously the id embedded
    spawn index, so the same agent could land in two different files across
    re-imports. With the new scheme (id = parent + agent_id only), the file
    is reused.
    """
    from vibesop.core.conversation_import import (
        SubagentRecord,
        derive_subagent_conversation_id,
        import_subagent,
    )

    storage = tmp_path / "conv"
    sub_jsonl = tmp_path / "agent.jsonl"
    _write_jsonl(
        sub_jsonl,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "x"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            }
        ],
    )
    record = SubagentRecord(
        jsonl_path=sub_jsonl,
        agent_id="a007cb9a1cdae69c4",
        meta={"agentType": "Explore", "description": "first"},
    )
    parent = "mirror-claude-sess"

    # Simulate two re-import passes — id must be the same (no spawn-index dependence)
    cid_a = derive_subagent_conversation_id(parent, record)
    cid_b = derive_subagent_conversation_id(parent, record)
    assert cid_a == cid_b, "id must be deterministic"

    # Both imports land in the same file → no orphan
    import_subagent(record, cid_a, storage, parent_session_id="sess")
    files_before = sorted(p.name for p in storage.glob("*.json"))
    import_subagent(record, cid_b, storage, parent_session_id="sess")
    files_after = sorted(p.name for p in storage.glob("*.json"))
    assert files_before == files_after


def test_path_traversal_safe_agent_id_cannot_escape_storage(
    tmp_path: Path,
) -> None:
    """A crafted agentId (e.g. '../../etc/passwd') cannot write outside storage_dir.

    Found by grok+pi review: slugify must strip '/' and '..' before the
    id is joined into a filesystem path.
    """
    from vibesop.core.conversation_import import (
        SubagentRecord,
        import_subagent,
    )

    storage = tmp_path / "conv"
    storage.mkdir()
    sub_jsonl = tmp_path / "agent.jsonl"
    _write_jsonl(
        sub_jsonl,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "x"},
                "timestamp": "2026-07-23T15:20:00.000Z",
            }
        ],
    )
    malicious = SubagentRecord(
        jsonl_path=sub_jsonl,
        agent_id="../../etc/passwd",
        meta={},
    )

    # Must not raise and must not create files outside storage_dir
    import_subagent(malicious, "mirror-claude-x", storage, parent_session_id="p")

    # All written files live INSIDE storage_dir (no traversal)
    for written in storage.rglob("*.json"):
        assert storage in written.parents or written.parent == storage
    # Specifically, no /etc/passwd-related file was created
    assert not (tmp_path / "etc").exists()
    assert not (tmp_path / "passwd").exists()


# ──────────────────────────────────────────────────────────────────
# ConversationContext metadata persistence
# ──────────────────────────────────────────────────────────────────


def test_conversation_context_persists_metadata(tmp_path: Path) -> None:
    """metadata dict round-trips through save/load."""
    ctx = ConversationContext(
        conversation_id="c1",
        storage_dir=tmp_path / "conv",
        metadata={"agent_type": "Explore", "is_subagent": True},
    )
    ctx.add_turn(query="hi", skill_id=None, intent=None, role="user")
    # Reload from disk via a fresh instance — caller-supplied metadata=None
    # so the stored metadata is adopted.
    ctx2 = ConversationContext(conversation_id="c1", storage_dir=tmp_path / "conv")
    assert ctx2.metadata["agent_type"] == "Explore"
    assert ctx2.metadata["is_subagent"] is True


def test_conversation_context_caller_metadata_wins(tmp_path: Path) -> None:
    """When caller passes metadata, it overrides what's on disk (re-import case)."""
    storage = tmp_path / "conv"
    ctx = ConversationContext(
        conversation_id="c1",
        storage_dir=storage,
        metadata={"agent_type": "Old"},
    )
    ctx.add_turn(query="hi", skill_id=None, intent=None, role="user")

    ctx2 = ConversationContext(
        conversation_id="c1",
        storage_dir=storage,
        metadata={"agent_type": "New"},
    )
    assert ctx2.metadata["agent_type"] == "New"


def test_conversation_context_no_metadata_backward_compat(tmp_path: Path) -> None:
    """Pre-Path-2 files (no metadata key) load cleanly with empty metadata."""
    storage = tmp_path / "conv"
    storage.mkdir()
    # Hand-write a minimal pre-Path-2 conversation file.
    (storage / "c1.json").write_text(
        json.dumps(
            {
                "conversation_id": "c1",
                "turns": [],
                "last_activity": 0.0,
            }
        ),
        encoding="utf-8",
    )
    ctx = ConversationContext(conversation_id="c1", storage_dir=storage)
    assert ctx.metadata == {}
