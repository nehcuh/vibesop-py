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
                    "content": [{"type": "thinking", "thinking": "t"}, {"type": "text", "text": "x"}],
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
