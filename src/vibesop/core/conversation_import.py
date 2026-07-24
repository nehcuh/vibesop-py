"""Batch-import Claude Code transcript jsonl into a VibeSOP conversation file.

Phase 1 (Path B) of the conversation-mirror feature. Provides the parser
and bulk-import primitives used by ``vibe conversation import-claude``.

The Claude Code transcript format is verified by reading a real jsonl at
``~/.claude/projects/<escaped-cwd>/<session>.jsonl``. Each line is one of:
``mode``, ``permission-mode``, ``file-history-snapshot``, ``user``,
``assistant``, ``attachment``, ``ai-title``, ``last-prompt``, ``system``.
Only ``type == "user"`` and ``type == "assistant"`` produce turns; the rest
are skipped silently.

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

from vibesop.core.conversation import ConversationContext, ConversationTurn

logger = logging.getLogger(__name__)


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


def _extract_text(content: Any) -> str:
    """Flatten a Claude ``message.content`` value to a single string.

    - Plain string → returned as-is.
    - List of blocks → concatenate ``text`` blocks with ``"\\n"`` separator.
      Non-text blocks (tool_use, tool_result, image, thinking) contribute
      nothing, but the function returns ``""`` rather than failing so the
      caller can still record an empty-content turn (preserves conversation
      flow when an assistant response was tools-only).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def parse_claude_jsonl(path: Path) -> list[ConversationTurn]:
    """Stream a Claude Code transcript jsonl, return user+assistant turns.

    See module docstring for the format. Lines that fail to parse as JSON
    are logged at debug and skipped — never raise.
    """
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
                content = _extract_text(msg.get("content"))
                ts = _parse_timestamp(obj.get("timestamp"))
                if kind == "user":
                    turns.append(
                        ConversationTurn(
                            query=content,
                            skill_id=None,
                            timestamp=ts,
                            intent=None,
                            role="user",
                            content=None,
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
                            content=content,
                        )
                    )
    except OSError as exc:
        logger.debug("failed to read jsonl %s: %s", path, exc)
        return []
    return turns


def _turn_hash(turn: ConversationTurn) -> str:
    """Stable dedup key for a parsed turn.

    Uses ``role|content-or-query|timestamp`` — the same identity Claude's
    transcript assigns (uuid is in the line, but we mirror at message-text
    granularity, so re-importing an appended line is idempotent across
    re-runs).
    """
    payload = f"{turn.role}|{turn.content or turn.query}|{turn.timestamp}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def import_session(
    source: Path,
    conversation_id: str,
    storage_dir: Path,
    *,
    max_history: int = 200,
) -> int:
    """Bulk-import a Claude Code jsonl into a conversation file.

    Loads the existing ``ConversationContext`` at
    ``storage_dir / f"{conversation_id}.json"`` (or creates a new one),
    appends deduped parsed turns, and saves. Returns the count of NEW turns
    actually written.

    Idempotency: each parsed turn is hashed (``role|content|timestamp``).
    Turns whose hash already exists in the loaded context are skipped, so
    re-importing a growing session file produces zero duplicates.
    """
    parsed = parse_claude_jsonl(source)
    if not parsed:
        return 0

    ctx = ConversationContext(
        conversation_id=conversation_id,
        max_history=max_history,
        storage_dir=storage_dir,
    )
    existing = {_turn_hash(t) for t in ctx.get_history()}
    new_count = 0
    for turn in parsed:
        h = _turn_hash(turn)
        if h in existing:
            continue
        existing.add(h)
        ctx.add_turn(
            query=turn.query,
            skill_id=turn.skill_id,
            intent=turn.intent,
            role=turn.role,
            content=turn.content,
            timestamp=turn.timestamp,
        )
        new_count += 1
    return new_count
