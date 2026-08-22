"""Tool-call sequence capture from host-agent hooks (P3: distillation data source).

Second data source of the skill-distillation loop (design doc §7.1, path ②):
a Claude Code ``PostToolUse`` hook pipes its event JSON to
``vibe sequence record-tool``, which appends a **minimal** entry — tool name,
timestamp, session id only, NEVER ``tool_input`` (paths, secrets) — to
``.vibe/tool_sequences.jsonl``. ``vibe sequence assemble`` (also lazy-triggered
from ``vibe route``) folds new entries into
``InstinctLearner.record_sequence(..., success=False)``: application-only
telemetry per the privacy rule — only explicit user confirmation (the
orchestration confirmation flow in ``cli/main.py``) may record success=True.

Files (all under ``<project_root>/.vibe/``, all covered by
``vibe data purge --tool-sequences``):

- ``tool_sequences.jsonl`` — one JSON object per line: ``{"tool", "ts", "session"}``
- ``tool_sequences.0.jsonl`` — single rotation of the capture log: when the
  live file exceeds ``MAX_CAPTURE_BYTES`` it is renamed aside (overwriting any
  older rotation) before the next append, capping total capture at ~2x the cap
- ``tool_sequences.cursor`` — JSON ``{"offset": <byte offset>}`` watermark so
  assembly never re-feeds already-processed entries
- ``tool_sequences.last`` — one epoch-seconds line written on every captured
  event (M12 M1 liveness signal; written by the shell hook template on the
  Claude Code / Kimi path and by ``record_tool_event`` itself on the pure-CLI
  Grok JSON-hook path — gate33; read by ``vibe sequence status``)

NOT covered by ``--tool-sequences`` (observability-domain files owned by
``core/observability/tool_call_bridge.py``, under ``.vibe/observability/``):
the bridged ``tool_call`` spans in ``spans.jsonl``, ``route_outcomes.jsonl``
and ``tool_call_bridge_state.json``. Purging them belongs with the
observability data, not with capture-log housekeeping.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from vibesop.core.instinct.learner import InstinctLearner

logger = logging.getLogger(__name__)

TOOL_SEQUENCES_FILENAME = "tool_sequences.jsonl"
ROTATED_FILENAME = "tool_sequences.0.jsonl"
CURSOR_FILENAME = "tool_sequences.cursor"
#: Liveness heartbeat written by the capture hook (one epoch-seconds line)
#: on every recorded event — the M1 "capture is alive" signal.
LAST_CAPTURE_FILENAME = "tool_sequences.last"
#: Session-less entries are split into a new group when the gap between two
#: consecutive events exceeds this window.
DEFAULT_WINDOW_MINUTES = 30
#: Mirrors InstinctLearner.record_sequence's own no-op threshold.
MIN_STEPS = 3
#: Capture-log size cap: the file is rotated aside before an append that would
#: grow it past this limit, so total on-disk capture stays ≤ ~2x this value.
MAX_CAPTURE_BYTES = 10 * 1024 * 1024  # 10 MB


def sequences_path(project_root: str | Path) -> Path:
    """Return the JSONL capture file path for *project_root*."""
    return Path(project_root) / ".vibe" / TOOL_SEQUENCES_FILENAME


def rotated_path(project_root: str | Path) -> Path:
    """Return the rotated capture file path for *project_root*."""
    return Path(project_root) / ".vibe" / ROTATED_FILENAME


def cursor_path(project_root: str | Path) -> Path:
    """Return the assembly watermark file path for *project_root*."""
    return Path(project_root) / ".vibe" / CURSOR_FILENAME


def last_capture_path(project_root: str | Path) -> Path:
    """Return the last-capture heartbeat path for *project_root*.

    Written on every captured event — by the shell-template hook
    (Claude Code / Kimi) or by ``record_tool_event`` itself on the
    pure-CLI path (Grok's JSON hook, gate33). A single line of epoch
    seconds. Absence means capture never fired (or the installed hook
    predates the liveness fix).
    """
    return Path(project_root) / ".vibe" / LAST_CAPTURE_FILENAME


def record_tool_event(payload: Mapping[str, Any], project_root: str | Path) -> bool:
    """Append one hook event to the capture log. Returns True when recorded.

    Extracts ONLY the tool name and session id from the hook payload.
    Field names: Claude Code / Kimi CLI use snake_case
    (``tool_name``/``session_id``); Grok Build's stdin envelope is
    camelCase throughout (``toolName``/``sessionId`` — grok's own
    hooks user guide, "camelCase input"; gate33 pi BLOCK-1: assuming
    Claude's shape for grok silently dropped 100% of events). Both
    casings (plus the bare ``tool`` key) are accepted. The timestamp is
    generated locally. ``tool_input``/``toolInput`` is never read beyond
    key lookup and never persisted. Events without a usable tool name are
    dropped. Rotates the log aside first when it exceeds
    ``MAX_CAPTURE_BYTES``.

    gate33 pi MAJOR-2: a successful record also rewrites the liveness
    heartbeat (``tool_sequences.last``, one epoch-seconds line) — the
    shell-template hooks do this themselves, and the pure-CLI path
    (grok's JSON hook) must satisfy the same contract or
    ``vibe sequence status`` would report a healthy capture as dead.
    """
    tool = payload.get("tool_name") or payload.get("tool") or payload.get("toolName")
    if not isinstance(tool, str) or not tool.strip():
        return False
    session = payload.get("session_id") or payload.get("sessionId")
    entry = {
        "tool": tool.strip(),
        "ts": datetime.now(UTC).isoformat(),
        "session": session.strip() if isinstance(session, str) and session.strip() else None,
    }
    path = sequences_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_oversized(path, project_root)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    try:
        last_capture_path(project_root).write_text(
            f"{datetime.now(UTC).timestamp():.0f}\n", encoding="utf-8"
        )
    except OSError:
        # Heartbeat is best-effort; the capture itself already landed.
        logger.debug("tool-sequence heartbeat write failed", exc_info=True)
    return True


def _rotate_if_oversized(path: Path, project_root: str | Path) -> None:
    """Rename an oversized capture log aside and reset the assembly watermark.

    Keeps at most one rotation (``tool_sequences.0.jsonl``, overwritten), so
    total capture stays bounded at ~2x ``MAX_CAPTURE_BYTES``. Entries not yet
    assembled at rotation time are discarded with the old file — the accepted
    cost of capping unbounded growth. The cursor is reset to 0 explicitly;
    the out-of-range fallback in ``assemble_tool_sequences`` would also zero
    a stale offset, so both paths stay compatible. Never raises: capture must
    not fail because housekeeping did.
    """
    try:
        if not path.exists() or path.stat().st_size <= MAX_CAPTURE_BYTES:
            return
        path.replace(rotated_path(project_root))  # overwrites any older rotation
        _write_cursor(cursor_path(project_root), 0)
    except OSError:
        logger.debug("tool-sequence rotation skipped", exc_info=True)


def assemble_tool_sequences(
    project_root: str | Path,
    *,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    min_steps: int = MIN_STEPS,
    learner: InstinctLearner | None = None,
) -> int:
    """Fold not-yet-assembled capture entries into the instinct learner.

    Groups new entries by ``session_id`` (session-less entries fall back to
    time-window splitting), and feeds every group of ≥ *min_steps* tool calls
    to ``record_sequence(steps, success=False)`` — application-only telemetry.
    Returns the number of sequences fed. Fault-tolerant: malformed lines are
    skipped, and the watermark advances past them so they are never retried.
    """
    data_path = sequences_path(project_root)
    if not data_path.exists():
        return 0

    size = data_path.stat().st_size
    offset = _read_cursor(cursor_path(project_root))
    if offset < 0 or offset > size:  # file rotated/purged since last assembly
        offset = 0
    if offset == size:
        return 0

    with data_path.open("rb") as f:
        f.seek(offset)
        # Stream line-by-line rather than reading one big block: the capture
        # log may be up to MAX_CAPTURE_BYTES. Splitting bytes on b"\n" is
        # UTF-8 safe (0x0A never occurs inside a multibyte sequence).
        entries = _parse_entries(f)

    # Advance-first watermark: a crash below must never double-feed entries.
    _write_cursor(cursor_path(project_root), size)

    # M12 M1: single-reader fan-out (gate15 claude 裁决) — this function is
    # the ONLY reader advancing the shared cursor, so the tool_call bridge
    # hooks in here rather than keeping a cursor of its own (rotation only
    # resets the main cursor; multi-cursor semantics are undefined). Bridge
    # failures must never break assembly.
    try:
        from vibesop.core.observability.tool_call_bridge import bridge_entries

        bridge_entries(entries, project_root)
    except Exception:
        logger.debug("tool-call bridge fan-out failed", exc_info=True)

    groups = [
        steps for steps in _group_sequences(entries, window_minutes) if len(steps) >= min_steps
    ]
    if not groups:
        return 0

    if learner is None:
        from vibesop.core.instinct.learner import InstinctLearner

        learner = InstinctLearner(storage_path=Path(project_root) / ".vibe" / "instincts.jsonl")
    fed = 0
    for steps in groups:
        learner.record_sequence(steps=steps, success=False, context="tool-sequence")
        fed += 1
    return fed


def clear_tool_sequences(project_root: str | Path) -> int:
    """Delete the capture log, its rotation, the watermark, and the liveness
    heartbeat (``vibe data purge``). Returns files removed.
    """
    removed = 0
    for path in (
        sequences_path(project_root),
        rotated_path(project_root),
        cursor_path(project_root),
        last_capture_path(project_root),
    ):
        if path.exists():
            path.unlink()
            removed += 1
    return removed


def _read_cursor(path: Path) -> int:
    """Read the byte-offset watermark; 0 when absent or corrupt."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        offset = data.get("offset", 0)
        return offset if isinstance(offset, int) else 0
    except (OSError, json.JSONDecodeError, AttributeError):
        return 0


def _write_cursor(path: Path, offset: int) -> None:
    from vibesop.utils.atomic_writer import write_text

    write_text(path, json.dumps({"offset": offset}))


def _parse_entries(lines: Iterable[bytes]) -> list[tuple[str, datetime | None, str | None]]:
    """Parse capture-log lines into (tool, timestamp, session) triples, skipping junk."""
    entries: list[tuple[str, datetime | None, str | None]] = []
    for raw in lines:
        stripped = raw.decode("utf-8", errors="replace").strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        tool = data.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            continue
        session = data.get("session")
        entries.append(
            (
                tool.strip(),
                _parse_ts(data.get("ts")),
                session if isinstance(session, str) and session else None,
            )
        )
    return entries


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Normalize tz-naive timestamps (hand-written/foreign capture data) to
    # UTC — record_tool_event always writes aware ISO, but a naive value
    # would otherwise raise TypeError downstream and abort a whole bridge
    # batch (gate16b claude N1).
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _group_sequences(
    entries: list[tuple[str, datetime | None, str | None]],
    window_minutes: int,
) -> list[list[str]]:
    """Group entries into tool-call sequences.

    Entries carrying a ``session_id`` group by session (arrival order
    preserved); session-less entries are split whenever the gap between two
    consecutive events exceeds *window_minutes*. Entries with unparseable
    timestamps stay in the current window group.
    """
    by_session: dict[str, list[str]] = {}
    sessionless: list[tuple[str, datetime | None]] = []
    for tool, ts, session in entries:
        if session:
            by_session.setdefault(session, []).append(tool)
        else:
            sessionless.append((tool, ts))

    groups = list(by_session.values())

    window = timedelta(minutes=window_minutes)
    current: list[str] = []
    last_ts: datetime | None = None
    for tool, ts in sessionless:
        if current and ts is not None and last_ts is not None and ts - last_ts > window:
            groups.append(current)
            current = []
        current.append(tool)
        if ts is not None:
            last_ts = ts
    if current:
        groups.append(current)

    return groups
