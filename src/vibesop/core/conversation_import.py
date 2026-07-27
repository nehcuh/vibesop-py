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

Sub-agent transcripts (Phase 2): Claude Code stores each Task-tool spawn
under ``<session-id>/subagents/agent-<id>.jsonl`` with a sibling
``agent-<id>.meta.json`` containing ``agentType`` / ``description`` /
``toolUseId``. Each sub-agent transcript uses the same line schema as the
parent (with extra ``isSidechain: true`` + ``agentId`` fields), so
``parse_claude_jsonl`` parses them unchanged. ``discover_subagents``
enumerates these for the CLI; ``import_subagent`` wires one into its own
mirror conversation so the dashboard surfaces the sub-agent's internal
thinking/tool_calls/tool_results that the parent transcript never sees.

TODO(secret-redaction): Phase 2+ should add an opt-in secret-scrubber pass
over parsed content before persisting (e.g. API keys, tokens). Today we
trust Claude Code's own redaction of stdin/tool results; the mirror use
case is local-only. Tracked separately.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vibesop.core.conversation import ConversationContext, ConversationTurn, ToolCall, ToolResult

logger = logging.getLogger(__name__)

_CAPTURE_DEPTHS = ("minimal", "standard", "full")
_RESULT_PREVIEW_LIMIT = 200
_HASH_VERSION = "v2"

# Sub-agent transcript files live alongside the main session jsonl under a
# ``<session-id>/subagents/`` directory. Claude Code today emits hex agentIds
# (no dashes), but the format isn't a hard contract — accept any non-dot
# run so future identifiers don't silently get dropped from the mirror.
# ``_sanitize_for_path`` defends against traversal regardless of charset.
_SUBAGENT_RE = re.compile(r"^agent-(?P<agent_id>[^.]+)\.jsonl$")
_SUBAGENT_META_RE = re.compile(r"^agent-(?P<agent_id>[^.]+)\.meta\.json$")


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
    metadata: dict[str, Any] | None = None,
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

    ``metadata`` (when supplied) is written onto the
    ``ConversationContext`` (caller-wins over stored). Even when every
    parsed turn hashes as duplicate, the metadata is persisted to disk so
    re-importing with updated meta (e.g. a corrected description) doesn't
    silently no-op. Found by grok+pi review (originally only saved via
    ``add_turn`` → 0-new-turn re-import dropped meta updates on the floor).
    """
    if not parsed:
        return (0, 0)

    ctx = ConversationContext(
        conversation_id=conversation_id,
        max_history=max_history,
        storage_dir=storage_dir,
        metadata=metadata,
    )
    new_count, skipped = _append_dedup_turns(ctx, parsed)
    # Force a save when nothing else triggered one — guarantees metadata
    # updates land on disk even for the all-duplicates re-import path.
    if new_count == 0 and metadata:
        ctx.save()
    return (new_count, skipped)


def _append_dedup_turns(
    ctx: ConversationContext, parsed: list[ConversationTurn]
) -> tuple[int, int]:
    """Append ``parsed`` to ``ctx`` skipping hash-duplicates of existing turns.

    Shared by the parent-transcript path (``append_parsed_turns``) and the
    sub-agent path (``import_subagent``) so dedupe semantics stay in one
    place — found by grok+pi review (previously two near-verbatim copies
    that would drift if ``_turn_hash`` ever revved again).
    """
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


# ----------------------------------------------------------------------
# Sub-agent transcript discovery + import (Phase 2)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class SubagentRecord:
    """One Claude Code sub-agent transcript discovered on disk.

    ``jsonl_path`` points to ``agent-<id>.jsonl`` (same line schema as the
    parent session). ``agent_id`` is the hex hash Claude Code assigns.
    ``meta`` carries ``agentType`` / ``description`` / ``toolUseId`` from
    the sibling ``.meta.json`` — empty dict when meta is missing or
    unreadable (sub-agent still importable, just less well-labeled).
    """

    jsonl_path: Path
    agent_id: str
    meta: dict[str, Any]


def parse_subagent_meta(meta_path: Path) -> dict[str, Any] | None:
    """Parse a Claude Code ``agent-*.meta.json`` file.

    Returns the dict unchanged on success (keys observed in the wild:
    ``agentType``, ``description``, ``toolUseId``). Returns ``None`` when
    the file is missing, unreadable, or doesn't decode to a dict — caller
    should still be able to import the sub-agent transcript without meta.
    """
    if not meta_path.exists():
        return None
    try:
        with meta_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("failed to read subagent meta %s: %s", meta_path, exc)
        return None
    return data if isinstance(data, dict) else None


def _sort_key_safe(record: SubagentRecord) -> tuple[float, str]:
    """Sort sub-agent records by ``(mtime, agent_id)`` with OSError fallback.

    Pulled out of ``discover_subagents`` so the safety contract (mid-scan
    unlink → mtime=0.0, never raises) is unit-testable directly. Found by
    grok review (issue 6): the original inline sort key could raise
    ``FileNotFoundError`` / ``PermissionError`` if a file vanished between
    the directory listing and the stat call.
    """
    try:
        mtime = record.jsonl_path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (mtime, record.agent_id)


def discover_subagents(session_jsonl: Path) -> list[SubagentRecord]:
    """Enumerate sub-agent transcripts for a given main session jsonl.

    Claude Code writes sub-agent transcripts to a sibling directory named
    after the session: ``<session-stem>/subagents/agent-<id>.jsonl`` with
    a ``agent-<id>.meta.json`` sibling. This helper scans that directory
    and returns records ordered by jsonl mtime (ascending — matches the
    order the parent agent spawned them).

    Returns an empty list when the ``subagents/`` directory doesn't exist
    (no Task tool was used in the session) or is unreadable. Best-effort
    throughout: any I/O error during listing or stat returns either a
    partial result or an empty list rather than raising — the mirror is a
    read-only, opt-in convenience feature and must never crash the CLI.
    Found by grok/pi review (originally documented as "never raises" but
    could raise on ``PermissionError`` / mid-scan ``FileNotFoundError``).
    """
    subagents_dir = session_jsonl.parent / session_jsonl.stem / "subagents"
    if not subagents_dir.is_dir():
        return []

    # Pair each agent-<id>.jsonl with its .meta.json (meta is best-effort).
    by_agent_id: dict[str, dict[str, Any]] = {}
    try:
        entries = list(subagents_dir.iterdir())
    except OSError as exc:
        logger.debug("subagents dir unreadable %s: %s", subagents_dir, exc)
        return []
    for entry in entries:
        if not entry.is_file():
            continue
        name = entry.name
        m = _SUBAGENT_RE.match(name)
        if m:
            aid = m.group("agent_id")
            by_agent_id.setdefault(aid, {})["jsonl"] = entry
            continue
        mm = _SUBAGENT_META_RE.match(name)
        if mm:
            aid = mm.group("agent_id")
            by_agent_id.setdefault(aid, {})["meta_path"] = entry

    records: list[SubagentRecord] = []
    for aid, bundle in by_agent_id.items():
        jsonl_path = bundle.get("jsonl")
        if not isinstance(jsonl_path, Path):
            continue  # orphan meta.json without a transcript — skip
        meta_path = bundle.get("meta_path")
        meta = parse_subagent_meta(meta_path) if isinstance(meta_path, Path) else {}
        records.append(SubagentRecord(jsonl_path=jsonl_path, agent_id=aid, meta=meta or {}))

    # Sort by transcript mtime so the dashboard list reflects spawn order.
    # Tiebreaker by agent_id so the order is deterministic across runs even
    # when two transcripts share an mtime (HFS+/ext3 1s granularity) — found
    # by pi review. Without this the same agent could land under a different
    # ``index`` on re-import and produce a stale orphan conversation file.
    records.sort(key=_sort_key_safe)
    return records


_PATH_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _sanitize_for_path(value: str | None, *, fallback: str, max_len: int = 64) -> str:
    """Reduce a free-form external string to a path-component-safe slug.

    Used for any value that flows from a Claude Code transcript/meta into a
    filesystem path via ``conversation_id``. Strips ``/``, ``..``, spaces,
    quotes, and any other character that could let the value escape
    ``storage_dir`` when ``_file_path`` joins it back. Collapses runs of
    stripped chars to a single ``-`` so the slug stays readable.

    Found by grok+pi review: the original ``_slugify_agent_type`` only
    truncated, leaving ``/`` intact — a crafted ``agentType`` (or any
    future field that surfaces in the id) could traverse out of
    ``storage_dir``. Defense-in-depth: callers should also avoid putting
    free-form values into ids, but this guarantees safety even if they do.
    """
    if not isinstance(value, str) or not value.strip():
        return fallback
    slug = _PATH_SAFE_RE.sub("-", value.strip()).strip("-")
    if not slug:
        return fallback
    return slug[:max_len]


def derive_subagent_conversation_id(
    parent_conversation_id: str,
    record: SubagentRecord,
) -> str:
    """Build a stable, filesystem-safe id for a sub-agent's mirror conversation.

    Format: ``<parent_conv_id>-sub-<sanitized_agent_id>``

    Identity comes from ``parent_conv_id`` + ``agent_id`` only — both are
    stable across re-imports (mtime reorders, meta edits, capture-depth
    upgrades). Previously the id embedded a 1-based spawn ``index`` and
    the agentType; both mutated across runs and orphaned old conversation
    files. Found by grok+pi review.

    ``agent_id`` is sanitized defensively — Claude Code emits hex today,
    but we don't want to assume that forever. ``_sanitize_for_path``
    strips ``/``, ``..``, etc. so a malformed id can't traverse out of
    ``storage_dir`` via ``_file_path``.
    """
    aid_slug = _sanitize_for_path(record.agent_id, fallback="unknown")
    return f"{parent_conversation_id}-sub-{aid_slug}"


def import_subagent(
    record: SubagentRecord,
    conversation_id: str,
    storage_dir: Path,
    parent_session_id: str,
    *,
    max_history: int = 200,
    capture_depth: str = "standard",
    parent_conversation_id: str | None = None,
) -> int:
    """Import one sub-agent transcript into its own mirror conversation.

    Same parser + dedupe semantics as ``import_session``. The conversation
    file gets a ``metadata`` block on disk recording ``agent_type`` /
    ``description`` / ``parent_session`` / ``parent_conversation_id`` /
    ``tool_use_id`` so the dashboard can render the sub-agent's role
    alongside its internal turns.

    Returns the count of NEW turns written (skipped duplicates don't count).

    Two parent keys are written deliberately (v3 Phase A Task 6 / grok+pi P0-3):
    - ``parent_session`` = the raw Claude Code session id (``path.stem``).
      Legacy field; kept so older dashboards still render.
    - ``parent_conversation_id`` = the resolved mirror conversation id
      (e.g. ``mirror-claude-abc123``). This is the JOIN key the v3 DAG
      rebuilder uses to walk parent ↔ sub-agent conversations across
      process boundaries — ``contextvars`` does NOT cross processes.

    Metadata persistence: even when ``parsed`` is empty OR every turn is a
    hash duplicate, the caller-supplied metadata is still written to disk.
    This matters because ``.meta.json`` may be corrected after a first
    import (description / agentType filled in) — without the forced save
    the re-import would no-op silently and the dashboard would keep
    showing stale metadata. Found by grok+pi review.
    """
    parsed = parse_claude_jsonl(record.jsonl_path, capture_depth=capture_depth)

    metadata = {
        "agent_type": record.meta.get("agentType"),
        "description": record.meta.get("description"),
        "parent_session": parent_session_id,
        "parent_conversation_id": parent_conversation_id,
        "tool_use_id": record.meta.get("toolUseId"),
        "agent_id": record.agent_id,
        "is_subagent": True,
    }
    # Strip None values so the persisted metadata stays compact — dashboard
    # treats absent keys the same as None.
    metadata = {k: v for k, v in metadata.items() if v is not None}

    ctx = ConversationContext(
        conversation_id=conversation_id,
        storage_dir=storage_dir,
        max_history=max_history,
        metadata=metadata,
    )
    if not parsed:
        # Empty transcript but metadata is meaningful (sub-agent existed,
        # just emitted no user/assistant turns yet). Persist so the
        # dashboard still lists it. Found by grok review (issue 8).
        ctx.save()
        return 0

    new_count, _skipped = _append_dedup_turns(ctx, parsed)
    if new_count == 0:
        # All turns were duplicates — still refresh metadata on disk so
        # updated descriptions / agentType land. Found by grok+pi review.
        ctx.save()
    return new_count
