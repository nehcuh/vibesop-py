"""Batch-import Claude Code transcript jsonl into a VibeSOP conversation file.

Phase 1 (Path B) of the conversation-mirror feature. Provides the parser
and bulk-import primitives used by ``vibe conversation import-claude``.

The Claude Code transcript format is verified by reading a real jsonl at
``~/.claude/projects/<escaped-cwd>/<session>.jsonl``. Each line is one of:
``mode``, ``permission-mode``, ``file-history-snapshot``, ``user``,
``assistant``, ``attachment``, ``ai-title``, ``last-prompt``, ``system``.
Only ``type == "user"`` and ``type == "assistant"`` produce turns; the rest
are skipped silently.

Block coverage (per Path-1 review):
- ``text``        → ``content`` (assistant) or ``query`` (user)
- ``thinking``    → ``thinking`` (only when ``capture_depth >= standard``)
- ``tool_use``    → ``tool_calls`` (id + name + sorted input KEYS, never values)
- ``tool_result`` → ``tool_results`` (tool_use_id + is_error always;
                    ``content_preview`` only when ``capture_depth == "full"``)

Per Claude Code transcript convention, ``tool_result`` blocks land on the
FOLLOWING user-role message — the parser preserves that placement rather
than trying to re-attach to the preceding assistant turn.

TODO(secret-redaction): Phase 2+ should add an opt-in secret-scrubber pass
over parsed content before persisting (e.g. API keys, tokens). Today we
trust Claude Code's own redaction of stdin/tool results; the mirror use
case is local-only. Tracked separately.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vibesop.core.conversation import ConversationContext, ConversationTurn, ToolCall, ToolResult

logger = logging.getLogger(__name__)

_CAPTURE_DEPTHS = ("minimal", "standard", "full")
_RESULT_PREVIEW_LIMIT = 200
_HASH_VERSION = "v2"


def _parse_timestamp(raw: Any) -> float:
    """Parse an ISO-8601 timestamp (with optional trailing ``Z``) to epoch float.

    Naive datetimes are assumed to be UTC (matches aggregator.py convention).
    Returns 0.0 when the value is missing or unparseable — preserves turn
    ordering while signalling the timestamp was bad.
    """
    if not raw or not isinstance(raw, str):
        return 0.0
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("unparseable timestamp %r — using 0.0", raw)
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def _coerce_capture_depth(value: str | None) -> str:
    """Validate / default the ``capture_depth`` knob.

    Accepts the three values defined in ``_CAPTURE_DEPTHS``. Unknown values
    fall back to ``"standard"`` (the documented default) with a debug log.
    """
    if value in _CAPTURE_DEPTHS:
        return value
    logger.debug("capture_depth=%r not in %s — using 'standard'", value, _CAPTURE_DEPTHS)
    return "standard"


def _extract_blocks(
    content: Any, *, capture_depth: str
) -> tuple[str, str | None, list[ToolCall], list[ToolResult]]:
    """Walk a Claude ``message.content`` value, returning per-block buckets.

    Returns ``(text, thinking, tool_calls, tool_results)``:

    - ``text``: newline-joined ``text`` blocks (empty string if none).
    - ``thinking``: newline-joined ``thinking`` blocks. ``None`` when
      ``capture_depth == "minimal"`` OR no thinking blocks present.
    - ``tool_calls``: ``ToolCall`` list (keys-only, never values). Empty
      when no ``tool_use`` blocks present. Populated for ``standard``+.
    - ``tool_results``: ``ToolResult`` list. ``tool_use_id`` + ``is_error``
      captured at ``standard``+; ``content_preview`` only at ``"full"``.

    For plain-string content (typical user prompts) returns
    ``(content, None, [], [])`` directly without per-block work.
    """
    if isinstance(content, str):
        return content, None, [], []

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    tool_results: list[ToolResult] = []

    if not isinstance(content, list):
        return "", None, [], []

    capture_thinking = capture_depth in ("standard", "full")
    capture_tools = capture_depth in ("standard", "full")
    capture_preview = capture_depth == "full"

    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            text = block.get("text")
            if isinstance(text, str):
                text_parts.append(text)
        elif btype == "thinking" and capture_thinking:
            thinking = block.get("thinking")
            if isinstance(thinking, str):
                thinking_parts.append(thinking)
        elif btype == "tool_use" and capture_tools:
            tool_id = block.get("id")
            tool_name = block.get("name") or "?"
            tool_input = block.get("input")
            keys = sorted(tool_input.keys()) if isinstance(tool_input, dict) else []
            if isinstance(tool_id, str):
                tool_calls.append(ToolCall(id=tool_id, name=str(tool_name), input_keys=keys))
        elif btype == "tool_result" and capture_tools:
            tool_use_id = block.get("tool_use_id")
            is_error = bool(block.get("is_error", False))
            preview: str | None = None
            if capture_preview:
                raw_content = block.get("content")
                preview = _truncate_tool_result(raw_content)
            if isinstance(tool_use_id, str):
                tool_results.append(
                    ToolResult(
                        tool_use_id=tool_use_id,
                        is_error=is_error,
                        content_preview=preview,
                    )
                )

    text = "\n".join(text_parts)
    thinking = "\n".join(thinking_parts) if thinking_parts else None
    return text, thinking, tool_calls, tool_results


def _truncate_tool_result(raw: Any) -> str | None:
    """Best-effort 200-char preview of a tool_result content field.

    ``content`` may be a string, a list of ``{type, text}`` blocks, or
    something else entirely. Returns ``None`` when no usable text exists.
    """
    if isinstance(raw, str):
        return raw[:_RESULT_PREVIEW_LIMIT]
    if isinstance(raw, list):
        parts: list[str] = []
        for item in raw:
            if isinstance(item, dict) and item.get("type") == "text":
                t = item.get("text")
                if isinstance(t, str):
                    parts.append(t)
        joined = "\n".join(parts)
        return joined[:_RESULT_PREVIEW_LIMIT] if joined else None
    return None


def _extract_usage(usage: Any) -> dict[str, int] | None:
    """Pull integer token counters from ``message.usage``.

    Returns ``None`` when the input isn't a dict or has no recognised keys.
    Only keeps keys whose values are ints — silently drops malformed entries.
    """
    if not isinstance(usage, dict):
        return None
    out: dict[str, int] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        val = usage.get(key)
        if isinstance(val, int):
            out[key] = val
    return out or None


def parse_claude_jsonl(
    path: Path,
    *,
    capture_depth: str = "standard",
) -> list[ConversationTurn]:
    """Stream a Claude Code transcript jsonl, return user+assistant turns.

    ``capture_depth``:
    - ``"minimal"``: text only (legacy behavior, pre-Path-1).
    - ``"standard"`` (default): + thinking + tool_calls (keys) + tool_results
      (id + is_error) + model + usage + stop_reason.
    - ``"full"``: + tool_result content_preview (200 chars).

    Lines that fail to parse as JSON are logged at debug and skipped — never raise.
    """
    depth = _coerce_capture_depth(capture_depth)
    turns: list[ConversationTurn] = []
    try:
        with path.open(encoding="utf-8") as f:
            for raw_line in f:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    logger.debug("skipping non-JSON line in %s", path)
                    continue
                if not isinstance(obj, dict):
                    continue
                kind = obj.get("type")
                if kind not in ("user", "assistant"):
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                text, thinking, tool_calls, tool_results = _extract_blocks(
                    msg.get("content"), capture_depth=depth
                )
                ts = _parse_timestamp(obj.get("timestamp"))
                model = msg.get("model") if isinstance(msg.get("model"), str) else None
                usage = _extract_usage(msg.get("usage"))
                stop_reason = (
                    msg.get("stop_reason") if isinstance(msg.get("stop_reason"), str) else None
                )
                if kind == "user":
                    # User turns: query = text; tool_results may also live here
                    # (Claude Code convention: assistant emits tool_use, the
                    # next user-role message carries tool_result blocks).
                    turns.append(
                        ConversationTurn(
                            query=text,
                            skill_id=None,
                            timestamp=ts,
                            intent=None,
                            role="user",
                            content=None,
                            thinking=None,
                            tool_calls=None,
                            tool_results=tool_results or None,
                            model=model,
                            usage=usage,
                            stop_reason=stop_reason,
                        )
                    )
                else:  # assistant
                    turns.append(
                        ConversationTurn(
                            query="",
                            skill_id=None,
                            timestamp=ts,
                            intent=None,
                            role="assistant",
                            content=text or None,
                            thinking=thinking,
                            tool_calls=tool_calls or None,
                            tool_results=None,
                            model=model,
                            usage=usage,
                            stop_reason=stop_reason,
                        )
                    )
    except OSError as exc:
        logger.debug("failed to read jsonl %s: %s", path, exc)
        return []
    return turns


def _turn_hash(turn: ConversationTurn) -> str:
    """Stable dedup key for a parsed turn.

    Versioned (``v2:``) so that re-importing a session after a Path-1
    upgrade doesn't collide with old ``v1`` hashes stored in pre-existing
    mirror files — old turns stay self-consistent, new turns get new
    hashes, and the user can purge + re-import to fully refresh.

    Hashed identity: ``role|content-or-query|thinking|tool_calls|tool_results|timestamp``.
    Model/usage/stop_reason deliberately excluded — they're metadata about
    the turn, not its identity (re-running the same prompt under a
    different model is still the "same" conversation turn for dedup).
    """
    tc_repr = (
        "|".join(f"{tc.id}:{tc.name}" for tc in turn.tool_calls) if turn.tool_calls else ""
    )
    tr_repr = (
        "|".join(f"{tr.tool_use_id}:{tr.is_error}" for tr in turn.tool_results)
        if turn.tool_results
        else ""
    )
    payload = "|".join(
        [
            turn.role,
            turn.content or turn.query,
            turn.thinking or "",
            tc_repr,
            tr_repr,
            f"{turn.timestamp}",
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{_HASH_VERSION}:{digest}"


def append_parsed_turns(
    parsed: list[ConversationTurn],
    conversation_id: str,
    storage_dir: Path,
    *,
    max_history: int = 200,
) -> tuple[int, int]:
    """Dedupe + append already-parsed turns to a conversation file.

    Returns ``(new_count, skipped_count)`` where ``skipped_count`` is the
    number of parsed turns whose hash matched an existing turn in the
    loaded context. Callers that want a single parse + both counts should
    use this directly; ``import_session`` is the file-path convenience
    wrapper.

    Idempotency contract: each parsed turn is hashed via ``_turn_hash``
    (v2). Pre-Path-1 mirror files contain "thin" turns
    (``thinking``/``tool_calls``/``tool_results`` all ``None``); upgrading
    and re-importing at ``standard`` depth produces "rich" turns whose
    hashes differ from the thin originals — resulting in duplicate
    appends. Detect this in the CLI layer (purge flag) rather than here.
    """
    if not parsed:
        return (0, 0)

    ctx = ConversationContext(
        conversation_id=conversation_id,
        max_history=max_history,
        storage_dir=storage_dir,
    )
    existing = {_turn_hash(t) for t in ctx.get_history()}
    new_count = 0
    skipped = 0
    for turn in parsed:
        h = _turn_hash(turn)
        if h in existing:
            skipped += 1
            continue
        existing.add(h)
        ctx.add_turn(
            query=turn.query,
            skill_id=turn.skill_id,
            intent=turn.intent,
            role=turn.role,
            content=turn.content,
            timestamp=turn.timestamp,
            thinking=turn.thinking,
            tool_calls=turn.tool_calls,
            tool_results=turn.tool_results,
            model=turn.model,
            usage=turn.usage,
            stop_reason=turn.stop_reason,
        )
        new_count += 1
    return (new_count, skipped)


def import_session(
    source: Path,
    conversation_id: str,
    storage_dir: Path,
    *,
    max_history: int = 200,
    capture_depth: str = "standard",
) -> int:
    """Bulk-import a Claude Code jsonl into a conversation file.

    Convenience wrapper: ``parse_claude_jsonl`` + ``append_parsed_turns``.
    Returns the count of NEW turns written. CLI callers that need both
    new + skipped counts (and want to avoid a double parse) should call
    the two helpers directly.

    Idempotency: see ``append_parsed_turns``. Old "thin" turns from
    pre-Path-1 mirror files hash differently from new "rich" turns —
    upgrading users should purge + re-import once.
    """
    parsed = parse_claude_jsonl(source, capture_depth=capture_depth)
    new_count, _skipped = append_parsed_turns(
        parsed, conversation_id, storage_dir, max_history=max_history
    )
    return new_count
