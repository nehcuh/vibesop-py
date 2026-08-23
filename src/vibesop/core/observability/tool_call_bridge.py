"""Tool-call span bridge + route outcome signals (M12 M1).

Two jobs share one scan of the spans file (``.vibe/observability/spans.jsonl``,
or ``spans.dev.jsonl`` in dev/test contexts — same dev/prod selection as
``SpanWriter``, see ``_spans_filename``):

1. **Assembly bridge (producer of ``span_kind="tool_call"`` spans).**
   ``tool_call`` consumers already exist (``aggregator.get_skill_metrics``
   tool distribution, ``aggregator.get_pattern_sequences``,
   ``dag_rebuilder``) but nothing produced such spans. Meanwhile
   ``.vibe/tool_sequences.jsonl`` captures ``{"tool", "ts", "session"}``
   events from the host agent's PostToolUse hook. This bridge joins tool
   events to route spans and rewrites them as standard ``tool_call``
   spans appended to the same trace as their parent route span.

   Join strategy (design doc m12-product-design.md v3, gate15 裁定):
   - **session join first**: the agent path (``agent_runtime.handle_query``)
     stamps route spans with the real platform session UUID, which matches
     the hook event's ``session``. When several route spans share the
     session, the tool call belongs to the *latest route span started
     before the event* — tools execute after the routing decision that
     triggered them.
   - **time-window fallback**: events whose session matches nothing (or
     carries none) join to the UNIQUE route span within
     ``±JOIN_WINDOW_MINUTES`` of the event. Zero candidates → unmatched;
     more than one → ambiguous, refused (mis-attribution is worse than no
     attribution). Both counted in telemetry.
   - **CLI route spans are excluded from join candidacy entirely**:
     ``cli/main.py`` mints a fresh session UUID per invocation, so its
     session can never match a hook event, and letting CLI spans into the
     time-window fallback would risk mis-attaching agent tool calls to an
     unrelated ``vibe route`` that happened to run nearby.

2. **Outcome signals for route spans**, appended to
   ``.vibe/observability/route_outcomes.jsonl`` (one JSON per line;
   corrupt lines skipped on read, per project JSONL convention).

   Miss side (M1 slice):
   - explicit accept (``vibe instinct accept`` → routing_pending item with
     ``status="accepted"`` whose query matches the span) ≈ strong positive
   - re-ask (the span's ``task_id`` — full-text derived, truncation-safe —
     reappears on a LATER route span) ≈ weak negative
   - session completed without re-ask (a later different-task span in the
     same session, or the span is older than ``SESSION_COMPLETE_HOURS``)
     ≈ weak positive
   Spans with ``has_match`` missing (CLI error paths, pre-W5.0 spans) are
   "unknown" and never enter the miss pool (conservative direction);
   ``mode="not_intercepted"``/``"slash_command"`` spans are not routing
   attempts and are excluded too. CLI route spans (per-invocation session)
   are excluded as well — they could only ever decay into hollow
   expiry-based weak positives.

   Hit side (gate38 L2a): non-CLI spans with ``has_match is True`` get
   the mirror-image classification — the span's ``task_id`` reappearing
   on a LATER route span ≈ weak negative (``hit_reask_same_task_id``);
   a later different-task span in the same session ≈ weak positive
   (``hit_session_moved_on``); older than ``SESSION_COMPLETE_HOURS`` ≈
   weak positive (``hit_session_expired``). There is no explicit-accept
   channel for hits (accepted_queries is a miss-only signal). Hit rows
   add ``"side": "hit"`` and ``"population": "hook"`` so each row is
   self-describing; miss rows are NOT rewritten — readers default a
   missing ``side`` to ``"miss"`` and a missing ``population`` to
   ``"hook"`` (the miss pool is hook-path only too).

   Population disclosure (read before consuming EITHER side): both
   outcome populations are hook-path only — CLI spans are excluded on
   both sides — while the gate37 ``fire`` column (skill_health) counts
   CLI hits as well. The populations differ in coverage: NEVER combine
   outcomes with fires into a fire→success-rate ratio. Hit weak
   positives are even softer than miss ones — "the user never came
   back" after a hit may mean abandonment, not satisfaction. The first
   bridge run backfills ALL historical hits at once (write-once +
   span_id dedup keeps re-runs idempotent); ``hit_session_expired``
   dominates that backfill and is the weakest signal — filter by the
   ``hit_`` reason prefix when consuming.

   Cost: hit classification scans all route spans per hit, the same
   O(hits × spans) asymptotic as the miss side. The first run pays the
   full backfill at once, and per-run cost grows quadratically while
   spans.jsonl grows unbounded (rotation-coupling dependency recorded
   in gate38 §5). This is an offline assembly path — the 100µs hook
   hot-path budget is not involved.

   Outcome derivation lives HERE (assembly stage), not in the M2 scan
   stage: the bridge already pays a full spans.jsonl scan on every
   assembly run and runs on the same cadence as capture, so outcomes
   refresh incrementally for free. A scan-stage implementation would
   duplicate the span read and only update when someone runs clustering.

Idempotency: the bridge runs inside the single assembly reader's fan-out
(``assemble_tool_sequences`` — one shared cursor, per gate15: rotation
only resets the main cursor, multi-cursor semantics undefined), so events
normally arrive exactly once. A manual/cron re-run (``run_bridge``) may
re-feed the same events; already-processed ``(session, ts, tool)`` keys
are kept in ``.vibe/observability/tool_call_bridge_state.json`` and never
produce a second span. Outcome lines are deduped by ``span_id`` against
the outcomes file itself, so state-file loss cannot duplicate outcomes.

Privacy: tool_call spans carry ONLY the tool name — never arguments,
paths, or responses (same rule as the capture side).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vibesop.core.observability._span_fields import span_timestamp
from vibesop.core.observability.dev_detect import is_dev_environment
from vibesop.core.observability.models import Span
from vibesop.core.observability.span_writer import SpanWriter
from vibesop.core.observability.task_id import derive_task_id, normalize_query

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)

#: Time-window fallback half-width: an unmatched-session event joins to the
#: unique route span whose start is within this many minutes of the event.
JOIN_WINDOW_MINUTES = 30
#: A miss span older than this with no re-ask counts as "session completed".
SESSION_COMPLETE_HOURS = 24
#: Cap on remembered (session, ts, tool) keys; oldest are evicted FIFO.
MAX_SEEN_KEYS = 50_000

STATE_FILENAME = "tool_call_bridge_state.json"
OUTCOMES_FILENAME = "route_outcomes.jsonl"
BRIDGE_SOURCE = "tool_call_bridge"

#: metadata["query"] on route spans is truncated to this many chars by the
#: producers (agent_runtime.py / cli/main.py: ``query[:200]``).
SPAN_QUERY_MAX_CHARS = 200


def _spans_filename() -> str:
    """Dev/prod spans filename, mirroring SpanWriter's selection
    (span_writer.py:65 / skill_health.py:41-47). Unlike skill_health's
    ``spans_file_for`` there is NO exists-gate here: the bridge write side
    needs the path even when the file is missing."""
    return "spans.dev.jsonl" if is_dev_environment() else "spans.jsonl"


#: metadata markers of the CLI route path (cli/main.py) — excluded from join.
_CLI_PLATFORM = "vibe-cli"

ToolEvent = tuple[str, datetime | None, str | None]


@dataclass
class BridgeStats:
    """Telemetry for one bridge run."""

    bridged: int = 0
    dedup_skipped: int = 0
    joined_session: int = 0
    joined_window: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    outcomes_recorded: int = 0
    hit_outcomes_recorded: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class _RouteSpan:
    """Normalized view of one route span for joining / outcome derivation."""

    id: str
    trace_id: str
    session_id: str | None
    task_id: str | None
    agent_id: str | None
    project_id: str
    started_at: datetime | None
    is_cli: bool
    has_match: bool | None  # None = unknown (missing key)
    mode: str | None
    query: str  # metadata query (≤200 chars, may be truncated)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def bridge_entries(
    entries: Iterable[ToolEvent],
    project_root: str | Path,
) -> BridgeStats:
    """Join tool events to route spans, write tool_call spans + outcomes.

    Called from the single assembly reader's fan-out
    (``assemble_tool_sequences``) and safe to call directly for a manual
    re-run: processed event keys are remembered in the bridge state file.
    Never raises — telemetry must not break capture or assembly.
    """
    stats = BridgeStats()
    try:
        _run(list(entries), Path(project_root), stats)
    except Exception:
        logger.debug("tool-call bridge run failed", exc_info=True)
        stats.notes.append("bridge run failed; see debug log")
    return stats


def run_bridge(project_root: str | Path) -> BridgeStats:
    """Manual/cron entry: bridge ALL events currently in the capture log.

    Uses no cursor of its own (single-reader rule); re-processing is made
    safe by the (session, ts, tool) dedup keys in the bridge state file.
    Outcome derivation runs even when there is nothing new to bridge.

    NOTE (gate16b claude N3): state-file and outcome dedup are
    read-modify-write without a cross-process lock — safe today (assembly
    fan-out is the sole reader and this entry is manual-only), but a shared
    lock (project convention: fcntl + threading.Lock) is REQUIRED before
    this is ever put on a schedule or run concurrently with assembly.
    """
    from vibesop.core.instinct.tool_sequences import _parse_entries, sequences_path

    entries: list[ToolEvent] = []
    path = sequences_path(project_root)
    if path.exists():
        with path.open("rb") as f:
            entries = _parse_entries(f)
    return bridge_entries(entries, project_root)


# ---------------------------------------------------------------------------
# Bridge core
# ---------------------------------------------------------------------------


def _run(entries: list[ToolEvent], root: Path, stats: BridgeStats) -> None:
    spans_path = root / ".vibe" / "observability" / _spans_filename()
    route_spans = _load_route_spans(spans_path)
    state = _load_state(root / ".vibe" / "observability" / STATE_FILENAME)

    if entries and route_spans:
        _bridge_events(entries, route_spans, spans_path, state, stats)
    elif entries:
        # No route spans to join against. Still mark events seen: the
        # assembly cursor has already advanced past them, so an unmarked
        # event would be retried forever by manual re-runs.
        stats.notes.append("no route spans found; events left unbridged")
        seen = set(state["seen"])
        for ev in entries:
            key = _event_key(*ev)
            if key in seen:
                stats.dedup_skipped += 1
                continue
            state["seen"].append(key)
            seen.add(key)
            stats.unmatched += 1

    # Persist bridge state BEFORE outcome derivation (gate16b pi nit): if the
    # outcome append fails, unsaved dedup keys would let the next run emit
    # duplicate tool_call spans. Outcomes dedup against their own file, so
    # they tolerate re-runs; span emission does not.
    _save_state(root / ".vibe" / "observability" / STATE_FILENAME, state)
    _derive_outcomes(route_spans, root, stats)
    _derive_hit_outcomes(route_spans, root, stats)


def _bridge_events(
    entries: list[ToolEvent],
    route_spans: list[_RouteSpan],
    spans_path: Path,
    state: dict[str, Any],
    stats: BridgeStats,
) -> None:
    seen: set[str] = set(state["seen"])
    joinable = [rs for rs in route_spans if not rs.is_cli]
    by_session: dict[str, list[_RouteSpan]] = {}
    for rs in joinable:
        if rs.session_id:
            by_session.setdefault(rs.session_id, []).append(rs)
    window = timedelta(minutes=JOIN_WINDOW_MINUTES)
    writer = SpanWriter(storage_path=spans_path)

    for tool, ts, session in entries:
        key = _event_key(tool, ts, session)
        if key in seen:
            stats.dedup_skipped += 1
            continue
        state["seen"].append(key)
        seen.add(key)

        route, how = _join_one(ts, session, by_session, joinable, window)
        if route is None:
            if how == "ambiguous":
                stats.ambiguous += 1
            else:
                stats.unmatched += 1
            continue

        writer.write_span(_tool_call_span(tool, ts, session, route))
        stats.bridged += 1
        if how == "session":
            stats.joined_session += 1
        else:
            stats.joined_window += 1


def _join_one(
    ts: datetime | None,
    session: str | None,
    by_session: dict[str, list[_RouteSpan]],
    joinable: list[_RouteSpan],
    window: timedelta,
) -> tuple[_RouteSpan | None, str]:
    """Pick the parent route span for one event.

    Returns (span, "session"|"window") on success, (None, "unmatched") or
    (None, "ambiguous") otherwise.
    """
    if session and session in by_session:
        candidates = by_session[session]
        if ts is not None:
            preceding = [
                rs for rs in candidates if rs.started_at is not None and rs.started_at <= ts
            ]
            if preceding:
                return max(
                    preceding, key=lambda rs: rs.started_at or datetime.min.replace(tzinfo=UTC)
                ), "session"
            # Event predates every route span of its session (clock skew or
            # truncated span history): fall through to the window rule.
        elif len(candidates) == 1:
            return candidates[0], "session"

    if ts is None:
        return None, "unmatched"
    near = [
        rs for rs in joinable if rs.started_at is not None and abs(rs.started_at - ts) <= window
    ]
    if len(near) == 1:
        return near[0], "window"
    if len(near) > 1:
        return None, "ambiguous"
    return None, "unmatched"


def _tool_call_span(tool: str, ts: datetime | None, session: str | None, route: _RouteSpan) -> Span:
    """Build the bridged tool_call span. Tool name only — never arguments."""
    at = ts or datetime.now(UTC)
    span = Span(
        id=Span.new_id(),
        trace_id=route.trace_id,
        name=f"tool:{tool}",
        span_kind="tool_call",
        task_id=route.task_id,
        session_id=session or route.session_id,
        agent_id=route.agent_id,
        parent_span_id=route.id,
        status="ok",
        started_at=at,
        ended_at=at,  # hook events carry no duration; 0ms beats "running"
        metadata={"tool": tool, "source": BRIDGE_SOURCE},
        project_id=route.project_id,
    )
    return span


def _event_key(tool: str, ts: datetime | None, session: str | None) -> str:
    return f"{session or ''}|{ts.isoformat() if ts else ''}|{tool}"


# ---------------------------------------------------------------------------
# Route span loading
# ---------------------------------------------------------------------------


def _load_route_spans(spans_path: Path) -> list[_RouteSpan]:
    """Read route spans (span_kind=task, name starts with ``route:``).

    Fault-tolerant per project JSONL convention: corrupt lines are skipped.
    """
    if not spans_path.exists():
        return []
    spans: list[_RouteSpan] = []
    try:
        with spans_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rs = _as_route_span(record)
                if rs is not None:
                    spans.append(rs)
    except OSError:
        logger.debug("failed to read spans for bridging", exc_info=True)
    return spans


def _as_route_span(record: dict[str, Any]) -> _RouteSpan | None:
    if not isinstance(record, dict):
        return None
    if record.get("span_kind") != "task":
        return None
    name = record.get("name")
    if not isinstance(name, str) or not name.startswith("route:"):
        return None

    meta = record.get("metadata")
    if isinstance(meta, str):  # SpanWriter serialises metadata to a string
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}
    if not isinstance(meta, dict):
        meta = {}

    has_match_raw = meta.get("has_match")
    has_match = bool(has_match_raw) if has_match_raw is not None else None
    session_id = record.get("session_id")
    mode = meta.get("mode")
    query = meta.get("query")
    return _RouteSpan(
        id=str(record.get("id") or ""),
        trace_id=str(record.get("trace_id") or ""),
        session_id=session_id if isinstance(session_id, str) and session_id else None,
        task_id=record.get("task_id") if isinstance(record.get("task_id"), str) else None,
        agent_id=record.get("agent_id") if isinstance(record.get("agent_id"), str) else None,
        project_id=str(record.get("project_id") or "default"),
        started_at=_parse_dt(span_timestamp(record)),
        is_cli=(meta.get("platform") == _CLI_PLATFORM or meta.get("source") == "cli"),
        has_match=has_match,
        mode=mode if isinstance(mode, str) else None,
        query=query if isinstance(query, str) else "",
    )


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:  # matches aggregator's tz-naive guard (P1-2)
        dt = dt.replace(tzinfo=UTC)
    return dt


# ---------------------------------------------------------------------------
# Outcome signals
# ---------------------------------------------------------------------------


def _derive_outcomes(route_spans: list[_RouteSpan], root: Path, stats: BridgeStats) -> None:
    """Append newly-determinable miss outcomes to route_outcomes.jsonl.

    Dedup by span_id against the outcomes file itself (not the state file),
    so a lost state file can never duplicate an outcome line.

    Outcomes are WRITE-ONCE and never revised: a weak_positive from the
    24h-expiry heuristic is NOT overturned by a later re-ask. That is
    deliberate — these are weak prior signals, not labels. M2 (miss-cluster
    admission + precision metrics) must therefore NOT treat outcome rows as
    ground truth; recompute stronger evidence from raw spans where needed.
    """
    outcomes_path = root / ".vibe" / "observability" / OUTCOMES_FILENAME
    recorded = _load_recorded_span_ids(outcomes_path)

    misses = [rs for rs in route_spans if _is_miss(rs)]
    if not misses:
        return
    accepted_queries = _load_accepted_queries(root)
    now = datetime.now(UTC)
    session_complete_after = timedelta(hours=SESSION_COMPLETE_HOURS)

    new_lines: list[str] = []
    for miss in misses:
        if not miss.id or miss.id in recorded:
            continue
        outcome = _classify(miss, route_spans, accepted_queries, now, session_complete_after)
        if outcome is None:
            continue  # not yet determinable — retried on the next run
        kind, reason = outcome
        new_lines.append(
            json.dumps(
                {
                    "span_id": miss.id,
                    "trace_id": miss.trace_id,
                    "task_id": miss.task_id,
                    "session_id": miss.session_id,
                    "span_ts": miss.started_at.isoformat() if miss.started_at else None,
                    "outcome": kind,
                    "reason": reason,
                    "recorded_at": now.isoformat(),
                },
                ensure_ascii=False,
            )
        )
        recorded.add(miss.id)

    if not new_lines:
        return
    outcomes_path.parent.mkdir(parents=True, exist_ok=True)
    with outcomes_path.open("a", encoding="utf-8") as f:
        for line in new_lines:
            f.write(line + "\n")
    stats.outcomes_recorded += len(new_lines)


def _derive_hit_outcomes(route_spans: list[_RouteSpan], root: Path, stats: BridgeStats) -> None:
    """Append newly-determinable hit outcomes to route_outcomes.jsonl.

    Mirrors ``_derive_outcomes`` (miss side) exactly: same outcomes file,
    same WRITE-ONCE semantics, same span_id dedup against the outcomes
    file itself (never the state file), plain append, no new lock. Hit
    rows add ``"side": "hit"`` and ``"population": "hook"`` (gate38:
    row-level self-describing population); miss rows are NOT rewritten —
    readers default a missing ``side`` to ``"miss"`` and a missing
    ``population`` to ``"hook"`` (the miss pool is hook-path only too).

    These are weak PRIOR signals, not labels — the hit weak positives are
    softer than the miss ones (not returning ≠ satisfaction; see the
    module docstring's population disclosure).
    """
    outcomes_path = root / ".vibe" / "observability" / OUTCOMES_FILENAME
    recorded = _load_recorded_span_ids(outcomes_path)

    hits = [rs for rs in route_spans if _is_hit(rs)]
    if not hits:
        return
    now = datetime.now(UTC)
    session_complete_after = timedelta(hours=SESSION_COMPLETE_HOURS)

    new_lines: list[str] = []
    for hit in hits:
        if not hit.id or hit.id in recorded:
            continue
        outcome = _classify_hit(hit, route_spans, now, session_complete_after)
        if outcome is None:
            continue  # not yet determinable — retried on the next run
        kind, reason = outcome
        new_lines.append(
            json.dumps(
                {
                    "span_id": hit.id,
                    "trace_id": hit.trace_id,
                    "task_id": hit.task_id,
                    "session_id": hit.session_id,
                    "span_ts": hit.started_at.isoformat() if hit.started_at else None,
                    "outcome": kind,
                    "reason": reason,
                    "side": "hit",
                    "population": "hook",
                    "recorded_at": now.isoformat(),
                },
                ensure_ascii=False,
            )
        )
        recorded.add(hit.id)

    if not new_lines:
        return
    outcomes_path.parent.mkdir(parents=True, exist_ok=True)
    with outcomes_path.open("a", encoding="utf-8") as f:
        for line in new_lines:
            f.write(line + "\n")
    stats.hit_outcomes_recorded += len(new_lines)


def _is_miss(rs: _RouteSpan) -> bool:
    """Conservative miss rule: explicit has_match=False on a routed attempt.

    CLI route spans are excluded (same ``is_cli`` judgement as the join
    path): each CLI invocation mints its own session, so its misses could
    never show "session continued" evidence and would decay into hollow
    ``session_expired`` weak positives after 24h, polluting M2's precision
    metrics (gate16 pi nit).

    Cross-reference (gate17 claude nit 6):
    ``gold_detection.is_route_miss_span`` classifies misses for the M2
    discovery path and is DELIBERATELY looser — it does NOT exclude CLI
    spans or ``slash_command``. The divergence is intentional, not drift:
    THIS predicate feeds **outcome-signal derivation** (where one-shot
    CLI sessions are meaningless), while the scan predicate feeds
    **discovery candidates** (where a CLI miss is a legitimate signal).
    If you change one, re-read the other before deciding they should match.
    """
    if rs.is_cli:
        return False
    if rs.has_match is not False:  # True → hit; None → unknown, never a miss
        return False
    return rs.mode not in ("not_intercepted", "slash_command")


def _is_hit(rs: _RouteSpan) -> bool:
    """Conservative hit rule: explicit has_match=True on a routed attempt.

    Mirror of ``_is_miss`` (gate17 cross-reference convention: change one,
    re-read the other). CLI route spans are excluded for the same reason
    as on the miss side: each CLI invocation mints its own session, so its
    hits could never show "session moved on" evidence and would decay
    into hollow ``hit_session_expired`` weak positives after 24h. Spans
    with ``has_match`` missing are "unknown" and never enter the hit pool
    (conservative direction); ``mode="not_intercepted"``/``"slash_command"``
    spans are not routing attempts and are excluded too.
    """
    if rs.is_cli:
        return False
    if rs.has_match is not True:  # False → miss; None → unknown, never a hit
        return False
    return rs.mode not in ("not_intercepted", "slash_command")


def _classify(
    miss: _RouteSpan,
    route_spans: list[_RouteSpan],
    accepted_queries: list[str],
    now: datetime,
    session_complete_after: timedelta,
) -> tuple[str, str] | None:
    """Return (outcome, reason) or None when not yet determinable.

    Precedence: explicit accept (strong) > re-ask (weak neg) > completion
    (weak pos). A span with no re-ask and no completion evidence stays
    undecided and is re-evaluated on the next run.
    """
    if _matches_accepted(miss, accepted_queries):
        return "strong_positive", "explicit_accept"

    later_same_task = [
        rs
        for rs in route_spans
        if rs.task_id
        and miss.task_id
        and rs.task_id == miss.task_id
        and rs.id != miss.id
        and rs.started_at is not None
        and miss.started_at is not None
        and rs.started_at > miss.started_at
    ]
    if later_same_task:
        return "weak_negative", "reask_same_task_id"

    session_moved_on = any(
        rs.session_id
        and miss.session_id
        and rs.session_id == miss.session_id
        and rs.task_id != miss.task_id
        and rs.started_at is not None
        and miss.started_at is not None
        and rs.started_at > miss.started_at
        for rs in route_spans
    )
    if session_moved_on:
        return "weak_positive", "session_continued_without_reask"
    if miss.started_at is not None and now - miss.started_at > session_complete_after:
        return "weak_positive", "session_expired_without_reask"
    return None


def _classify_hit(
    hit: _RouteSpan,
    route_spans: list[_RouteSpan],
    now: datetime,
    session_complete_after: timedelta,
) -> tuple[str, str] | None:
    """Return (outcome, reason) or None when not yet determinable.

    Mirror of ``_classify`` minus the explicit-accept channel (accepted
    routing_pending queries are a miss-only signal — there is no accept
    path for hits). Reasons carry a ``hit_`` prefix so consumers can
    filter the two pools apart. Precedence: re-ask (weak neg) >
    completion (weak pos). A fresh hit with no completion evidence stays
    undecided and is re-evaluated on the next run.
    """
    later_same_task = [
        rs
        for rs in route_spans
        if rs.task_id
        and hit.task_id
        and rs.task_id == hit.task_id
        and rs.id != hit.id
        and rs.started_at is not None
        and hit.started_at is not None
        and rs.started_at > hit.started_at
    ]
    if later_same_task:
        return "weak_negative", "hit_reask_same_task_id"

    session_moved_on = any(
        rs.session_id
        and hit.session_id
        and rs.session_id == hit.session_id
        and rs.task_id != hit.task_id
        and rs.started_at is not None
        and hit.started_at is not None
        and rs.started_at > hit.started_at
        for rs in route_spans
    )
    if session_moved_on:
        return "weak_positive", "hit_session_moved_on"
    if hit.started_at is not None and now - hit.started_at > session_complete_after:
        return "weak_positive", "hit_session_expired"
    return None


def _matches_accepted(miss: _RouteSpan, accepted_queries: list[str]) -> bool:
    """Match a miss span against accepted routing_pending queries.

    Exact ``task_id`` equality first. The prefix fallback exists ONLY for
    the truncation case: span metadata queries are cut at 200 chars while
    pending stores up to 500, so a truncated span query is a genuine prefix
    of the full pending query. Gating on the truncation length matters —
    an ungated prefix check over-matches (gate16 claude nit: the short miss
    "run tests" would prefix-hit the accepted pending "run tests with
    coverage in ci" and earn a false strong_positive).
    """
    span_norm = normalize_query(miss.query)
    truncated = len(miss.query) >= SPAN_QUERY_MAX_CHARS
    for query in accepted_queries:
        if miss.task_id and derive_task_id(query) == miss.task_id:
            return True
        if truncated:
            pend_norm = normalize_query(query)
            if span_norm and pend_norm and pend_norm.startswith(span_norm):
                return True
    return False


def _load_accepted_queries(root: Path) -> list[str]:
    """Queries of routing_pending items with status="accepted" (explicit accept)."""
    path = root / ".vibe" / "instincts" / "routing_pending.jsonl"
    if not path.exists():
        return []
    queries: list[str] = []
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or data.get("status") != "accepted":
                continue
            query = data.get("query")
            if isinstance(query, str) and query.strip():
                queries.append(query)
    except OSError:
        logger.debug("failed to read routing_pending for outcomes", exc_info=True)
    return queries


def _load_recorded_span_ids(outcomes_path: Path) -> set[str]:
    if not outcomes_path.exists():
        return set()
    ids: set[str] = set()
    try:
        for raw_line in outcomes_path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            span_id = data.get("span_id") if isinstance(data, dict) else None
            if isinstance(span_id, str) and span_id:
                ids.add(span_id)
    except OSError:
        logger.debug("failed to read existing outcomes", exc_info=True)
    return ids


# ---------------------------------------------------------------------------
# Bridge state (event dedup keys)
# ---------------------------------------------------------------------------


def _load_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        seen = data.get("seen")
        if isinstance(seen, list):
            return {"seen": [k for k in seen if isinstance(k, str)]}
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return {"seen": []}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    from vibesop.utils.atomic_writer import write_text

    seen = state["seen"]
    if len(seen) > MAX_SEEN_KEYS:  # FIFO eviction of the oldest keys
        seen = seen[-MAX_SEEN_KEYS:]
    try:
        write_text(path, json.dumps({"seen": seen}))
    except OSError:
        logger.debug("failed to persist bridge state", exc_info=True)
