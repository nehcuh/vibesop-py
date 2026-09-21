"""Skill-consumption five-segment ledger (F2 lane, 2026-09-21).

Why this exists
---------------
R6 measured a weak model scoring 22/25 while skill content **never entered
its context** (routing 2/2 no-match, 0 SKILL.md reads; the strong-model R5
control read 80 SKILL.md files on the same task). Read against R5's 23.5/25
the two numbers look like "weak model + skills ≈ strong model" — the
near-equivalence is an artifact of not accounting for consumption. The
paper's recommendation #3 (``docs/research/2026-09-09-agent-skills-paper.md``)
is to record *selected / read / applicable / executed / accepted* separately;
research-survey §7 F2 turns that into the product rule **consumption
evidence comes before scoring**. This module is that ledger.

Five segments, one honest answer each
-------------------------------------
Every row carries the same envelope per segment: ``{"state": <value|null>,
"reason": <str|null>, ...}``. A ``null`` state always ships a non-null
``reason`` — an honest hole must say why it is a hole.

``selected``      LANDED. Derived from the route span the producers already
                  write (``metadata.has_match`` / ``skill_id`` /
                  ``top_skills`` / ``demoted_skill_id`` / ``mode``). ``yes``
                  requires a real skill id: ``has_match=true`` with an empty
                  or ``fallback-llm`` id is reported as ``null`` +
                  ``hit_without_real_skill_id``, never as a hit.
``read``          ALWAYS ``null`` today (``no_harness_receipt``). No producer
                  records "the SKILL.md body entered the model's context",
                  and ``.vibe/tool_sequences.jsonl`` is name-only by privacy
                  rule (never ``tool_input``, so never a path). Two PROXY
                  fields ship inside the segment and are never promoted to
                  ``state``: ``injection_attempted`` (hook path + a real hit
                  ⇒ the body was handed to the harness) and
                  ``read_like_tool_calls``/``tools`` (bridged ``tool_call``
                  spans parented to this route span). R6 is the reason for
                  the strictness: its 10 read-like calls all targeted
                  ``TASK.md`` and its own artifacts — reading a file is not
                  reading the skill.
``applicable``    ALWAYS ``null`` (``not_observable``). No harness reports
                  "the agent judged this skill applicable"; guessing from
                  keywords/similarity would smuggle an unvalidated heuristic
                  into the ledger.
``executed``      ALWAYS ``null`` (``no_step_receipt``). Plan step results
                  (``plan.steps[*].verification_result``) never reach span
                  metadata. Tool activity is not step execution.
``accepted``      ALWAYS ``null`` (``no_verification_receipt``). The
                  ``builtin/verify-result`` verdict lives in the plan, not in
                  any ``.vibe/`` artifact, and ``route_outcomes.jsonl`` rows
                  are explicitly weak priors, not labels.

Alignment contract for a later round (kept, not wired): once a producer
writes ``metadata["verification_result"]`` (``{"status": "pass"|"fail"|
"blocked", "skill_id": ...}``) onto the route span, ``accepted`` maps
``pass → "yes"``, ``fail``/``blocked`` → ``"no"``, missing → today's null.
That field feeds the ledger only — never an exit code, CI job, or promote
decision.

Storage
-------
``<project_root>/.vibe/observability/skill_consumption.jsonl`` — one row per
route span, JSONL, plus a single rotation aside
(``skill_consumption.0.jsonl``, overwritten) once the live file passes
``MAX_LEDGER_BYTES``. No dev/prod variant, mirroring
``route_outcomes.jsonl`` (only ``spans.jsonl`` has a dev twin). Readers union
live + rotated with live winning per ``span_id``.

Rows are **upserted**, not append-once: the consumption facts for one route
span keep growing while its tool calls get bridged, so a write-once row would
freeze the half-assembled state. A row is rewritten only when its content
actually changes (``recorded_at`` is preserved from the first write), so a
no-op re-run touches nothing. Rows whose route span has since rotated out of
``spans.jsonl`` are preserved verbatim.

Privacy: the ledger never stores query text. The join key is
``task_id`` (``sha1(normalize(query))[:16]``, pure derivation); tool names
come from ``tool_call`` spans, which by construction carry no arguments,
paths, or responses. ``session_id`` is kept (session-level queries need it;
``route_outcomes.jsonl`` set the precedent).

Non-goals (do not relax)
------------------------
Report-only factual accounting. No rates, no ratios, no percentages, no
grades, no disposition advice — the ledger must never be read as a success
rate, a merge gate, or a routing-threshold input. It does not touch matching
scores, injection bodies, or the promote "lamp is not a gate" semantics.

Usage:
    from vibesop.core.observability.skill_consumption import consumption_report

    result = consumption_report(Path(".vibe/observability/skill_consumption.jsonl"))
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vibesop.core.observability._span_fields import span_timestamp
from vibesop.core.observability.dev_detect import is_dev_environment
from vibesop.core.observability.route_observe import parse_window
from vibesop.utils.atomic_writer import write_text

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

logger = logging.getLogger(__name__)

SCHEMA = "vibesop.observability.skill_consumption"
SCHEMA_VERSION = 1

LEDGER_FILENAME = "skill_consumption.jsonl"
ROTATED_FILENAME = "skill_consumption.0.jsonl"
#: Live ledger size cap; crossing it rotates the file aside (one generation).
MAX_LEDGER_BYTES = 8 * 1024 * 1024

#: Route spans are ``span_kind="task"`` records whose name carries this prefix.
ROUTE_SPAN_PREFIX = "route:"
#: CLI route spans are marked with this platform (mirror of
#: ``tool_call_bridge._CLI_PLATFORM`` — keep the two in lockstep; the CLI mints
#: a fresh session per invocation and never injects a skill body, which is why
#: ``read.evidence.injection_attempted`` is pinned ``False`` for them).
CLI_PLATFORM = "vibe-cli"
#: PlanBuilder's no-match sentinel — a routed step id that is not a skill.
FALLBACK_SENTINEL = "fallback-llm"
#: Modes that are not routing attempts (same exclusion as the bridge's pools).
NON_ATTEMPT_MODES = ("not_intercepted", "slash_command")
#: Conservative read-tool allowlist (case-insensitive). Anything outside it is
#: still reported in ``tools`` — the consumer judges, not this list.
READ_LIKE_TOOLS = frozenset({"read", "read_file", "readfile", "view", "view_file"})
#: Ordered routing snapshot cap, same as the producers' ``top_skills[:3]``.
MAX_SKILL_IDS = 3

# Reason codes (stable strings — pinned by tests).
R_MISSING_HAS_MATCH = "missing_has_match"
R_NON_BOOLEAN_HAS_MATCH = "non_boolean_has_match"
R_HIT_WITHOUT_SKILL = "hit_without_real_skill_id"
R_NO_HARNESS_RECEIPT = "no_harness_receipt"
R_NOT_OBSERVABLE = "not_observable"
R_NO_STEP_RECEIPT = "no_step_receipt"
R_NO_VERIFICATION_RECEIPT = "no_verification_receipt"

UNREADABLE_LEDGER = "unreadable_ledger"

RAW_COUNTS_NOTE = (
    "raw counts only: this ledger records what happened to skill consumption, "
    "not whether skills helped (no rates, no success score, not a gate)"
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def ledger_paths(project_root: str | Path) -> tuple[Path, Path]:
    """(live ledger, rotation aside) under ``<root>/.vibe/observability/``."""
    directory = Path(project_root) / ".vibe" / "observability"
    return directory / LEDGER_FILENAME, directory / ROTATED_FILENAME


def spans_path_for(project_root: str | Path) -> Path:
    """This project's spans file, mirroring SpanWriter's dev/prod selection.

    Unlike ``skill_health.spans_file_for`` there is NO exists-gate: the
    derivation needs the path even when the file is absent.
    """
    filename = "spans.dev.jsonl" if is_dev_environment() else "spans.jsonl"
    return Path(project_root) / ".vibe" / "observability" / filename


# ---------------------------------------------------------------------------
# Row derivation (pure)
# ---------------------------------------------------------------------------


def _decode_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """``metadata`` as a dict: dict (``Span.to_dict``) or JSON string (writer)."""
    raw = record.get("metadata")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        if isinstance(decoded, dict):
            return decoded
    return {}


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _is_cli_span(meta: dict[str, Any]) -> bool:
    """CLI route spans carry the dual markers (``platform`` / ``source``)."""
    return meta.get("platform") == CLI_PLATFORM or meta.get("source") == "cli"


def is_routing_attempt(record: dict[str, Any]) -> bool:
    """True for a route span that represents an actual routing attempt.

    Same exclusion as the bridge's miss/hit pools: ``not_intercepted`` /
    ``slash_command`` spans are not routing attempts, so the ledger writes no
    row for them.
    """
    if record.get("span_kind") != "task":
        return False
    name = record.get("name")
    if not isinstance(name, str) or not name.startswith(ROUTE_SPAN_PREFIX):
        return False
    mode = _decode_metadata(record).get("mode")
    return not (isinstance(mode, str) and mode in NON_ATTEMPT_MODES)


def _ordered_skill_ids(meta: dict[str, Any]) -> list[str]:
    """``[skill_id, *top_skills]``, deduped, sentinel/empty dropped, capped."""
    candidates: list[str] = []
    primary = meta.get("skill_id")
    if isinstance(primary, str) and primary:
        candidates.append(primary)
    top = meta.get("top_skills")
    if isinstance(top, list):
        candidates.extend(item for item in top if isinstance(item, str) and item)
    ordered: list[str] = []
    for skill_id in candidates:
        if skill_id == FALLBACK_SENTINEL or skill_id in ordered:
            continue
        ordered.append(skill_id)
    return ordered[:MAX_SKILL_IDS]


def _selected_segment(meta: dict[str, Any], skill_ids: list[str]) -> dict[str, Any]:
    has_match_present = "has_match" in meta
    has_match = meta.get("has_match")
    primary = meta.get("skill_id")
    if isinstance(has_match, bool):
        if not has_match:
            state, reason = "no", None
        elif skill_ids:
            state, reason = "yes", None
        else:
            # gate41's documented hole: has_match=true with no real skill id
            # must never be reported as a hit.
            state, reason = None, R_HIT_WITHOUT_SKILL
    elif not has_match_present or has_match is None:
        state, reason = None, R_MISSING_HAS_MATCH
    else:
        state, reason = None, R_NON_BOOLEAN_HAS_MATCH
    demoted = meta.get("demoted_skill_id")
    mode = meta.get("mode")
    return {
        "state": state,
        "reason": reason,
        "primary": primary if isinstance(primary, str) else None,
        "skill_ids": list(skill_ids),
        "demoted_skill_id": demoted if isinstance(demoted, str) and demoted else None,
        "mode": mode if isinstance(mode, str) else None,
    }


def _read_segment(
    selected_state: str | None, population: str, tools: Sequence[str]
) -> dict[str, Any]:
    """The ``read`` segment: always unknown, plus two clearly-labelled proxies.

    ``injection_attempted`` is ``None`` when the routing verdict itself is
    unknown (nothing can be said about injection either).
    """
    if population == "cli":
        injection: bool | None = False
    elif selected_state == "yes":
        injection = True
    elif selected_state == "no":
        injection = False
    else:
        injection = None
    read_like = sum(1 for tool in tools if tool.casefold() in READ_LIKE_TOOLS)
    return {
        "state": None,
        "reason": R_NO_HARNESS_RECEIPT,
        "evidence": {
            "injection_attempted": injection,
            "read_like_tool_calls": read_like,
            "tools": sorted(set(tools)),
        },
    }


def build_row(
    record: dict[str, Any],
    tools: Sequence[str],
    *,
    recorded_at: str,
) -> dict[str, Any]:
    """Build one ledger row from a raw route span record.

    ``tools`` is the (possibly repeated) list of tool names of the
    ``tool_call`` spans parented to this route span — raw occurrences, so
    ``read_like_tool_calls`` counts calls while ``tools`` stays unique.
    """
    meta = _decode_metadata(record)
    skill_ids = _ordered_skill_ids(meta)
    selected = _selected_segment(meta, skill_ids)
    population = "cli" if _is_cli_span(meta) else "hook"
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "span_id": str(record.get("id") or ""),
        "trace_id": str(record.get("trace_id") or ""),
        "task_id": record.get("task_id") if isinstance(record.get("task_id"), str) else None,
        "session_id": (
            record.get("session_id") if isinstance(record.get("session_id"), str) else None
        ),
        "agent_id": record.get("agent_id") if isinstance(record.get("agent_id"), str) else None,
        "project_id": str(record.get("project_id") or "default"),
        "route_started_at": span_timestamp(record),
        "route_population": population,
        "mode": selected["mode"],
        "selected": selected,
        "read": _read_segment(selected["state"], population, tools),
        "applicable": {"state": None, "reason": R_NOT_OBSERVABLE},
        "executed": {"state": None, "reason": R_NO_STEP_RECEIPT},
        "accepted": {"state": None, "reason": R_NO_VERIFICATION_RECEIPT},
        "recorded_at": recorded_at,
    }


# ---------------------------------------------------------------------------
# Derivation pass (spans -> rows -> ledger)
# ---------------------------------------------------------------------------


def _tool_name(record: dict[str, Any]) -> str | None:
    """Tool name from a bridged ``tool_call`` span (metadata first, name second)."""
    meta = _decode_metadata(record)
    tool = meta.get("tool")
    if isinstance(tool, str) and tool:
        return tool
    name = record.get("name")
    if isinstance(name, str) and name.startswith("tool:"):
        stripped = name[len("tool:") :]
        return stripped or None
    return None


def _scan_spans(spans_path: Path) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """One pass over the spans file: route records + tool names by parent id.

    Corrupt lines are skipped (project JSONL convention); the ledger only
    needs the two record shapes, so anything else is ignored.
    """
    routes: list[dict[str, Any]] = []
    tools_by_parent: dict[str, list[str]] = {}
    if not spans_path.exists():
        return routes, tools_by_parent
    try:
        with spans_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                kind = record.get("span_kind")
                if kind == "task":
                    if is_routing_attempt(record):
                        routes.append(record)
                elif kind == "tool_call":
                    parent = record.get("parent_span_id")
                    tool = _tool_name(record)
                    if isinstance(parent, str) and parent and tool:
                        tools_by_parent.setdefault(parent, []).append(tool)
    except OSError:
        logger.debug("failed to read spans for consumption ledger", exc_info=True)
    routes.sort(
        key=lambda record: (
            span_timestamp(record) or "",
            str(record.get("id") or ""),
        )
    )
    return routes, tools_by_parent


def _read_raw_rows(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Existing ledger rows in file order, plus the corrupt-line count."""
    rows: list[dict[str, Any]] = []
    corrupt = 0
    if not path.exists():
        return rows, corrupt
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                corrupt += 1
                continue
            if not isinstance(record, dict):
                corrupt += 1
                continue
            rows.append(record)
    except OSError:
        logger.debug("failed to read consumption ledger", exc_info=True)
    return rows, corrupt


def _maybe_rotate(ledger_path: Path, rotated_path: Path, max_bytes: int) -> bool:
    """Move the live ledger aside when it exceeds ``max_bytes``."""
    try:
        if not ledger_path.exists() or ledger_path.stat().st_size <= max_bytes:
            return False
        ledger_path.replace(rotated_path)  # overwrites the previous generation
    except OSError:
        logger.debug("consumption ledger rotation skipped", exc_info=True)
        return False
    return True


def _row_key(row: dict[str, Any]) -> str:
    span_id = row.get("span_id")
    return span_id if isinstance(span_id, str) else ""


def record_consumption(
    project_root: str | Path,
    *,
    spans_path: Path | None = None,
    now: datetime | None = None,
    max_bytes: int = MAX_LEDGER_BYTES,
) -> int:
    """Derive and upsert ledger rows from the spans file; return rows written.

    Idempotent: a re-run whose derivation is unchanged writes nothing.
    Returns 0 (never raises) when the spans file is missing, holds no routing
    attempts, or cannot be read — the ledger is telemetry, not a control path.
    """
    root = Path(project_root)
    ledger_path, rotated_path = ledger_paths(root)
    resolved_spans = spans_path if spans_path is not None else spans_path_for(root)
    routes, tools_by_parent = _scan_spans(resolved_spans)
    if not routes:
        return 0
    try:
        _maybe_rotate(ledger_path, rotated_path, max_bytes)
        existing, _corrupt = _read_raw_rows(ledger_path)
        by_id: dict[str, int] = {}
        for index, row in enumerate(existing):
            key = _row_key(row)
            if key and key not in by_id:
                by_id[key] = index
        recorded_at_default = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
        written = 0
        for record in routes:
            span_id = str(record.get("id") or "")
            if not span_id:
                continue
            index = by_id.get(span_id)
            prior = existing[index] if index is not None else None
            recorded_at = recorded_at_default
            if isinstance(prior, dict):
                prior_recorded = prior.get("recorded_at")
                if isinstance(prior_recorded, str) and prior_recorded:
                    recorded_at = prior_recorded
            row = build_row(record, tools_by_parent.get(span_id, []), recorded_at=recorded_at)
            if index is None:
                existing.append(row)
                by_id[span_id] = len(existing) - 1
                written += 1
            elif existing[index] != row:
                existing[index] = row
                written += 1
        if written == 0:
            return 0
        content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in existing)
        write_text(ledger_path, content)
    except OSError:
        logger.debug("failed to update consumption ledger", exc_info=True)
        return 0
    return written


# ---------------------------------------------------------------------------
# Read side (ledger -> rows)
# ---------------------------------------------------------------------------


@dataclass
class LedgerScan:
    """Ledger contents (live ∪ rotated, live wins) plus read fault detail."""

    ledger_path: str
    rotated_path: str
    exists: bool
    mtime: float | None
    rows: list[dict[str, Any]] = field(default_factory=list)
    n_rotated_rows: int = 0
    n_corrupt: int = 0
    n_skipped: int = 0
    error_kind: str | None = None
    error_message: str | None = None


def _read_ledger_file(path: Path) -> tuple[list[dict[str, Any]], int, int, str | None]:
    """(rows, corrupt, skipped, error_message) for one ledger file."""
    rows: list[dict[str, Any]] = []
    corrupt = 0
    skipped = 0
    if not path.exists():
        return rows, corrupt, skipped, None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return rows, corrupt, skipped, str(exc)
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            corrupt += 1
            continue
        if not isinstance(record, dict) or not _row_key(record):
            skipped += 1
            continue
        rows.append(record)
    return rows, corrupt, skipped, None


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str]:
    ts = row.get("route_started_at") or row.get("recorded_at") or ""
    return (ts if isinstance(ts, str) else "", _row_key(row))


def read_ledger(ledger_path: Path, rotated_path: Path | None = None) -> LedgerScan:
    """Read the live ledger plus its rotation; live rows win per ``span_id``.

    Rotated rows are frozen history: they are unioned in for reading but never
    rewritten. Ordering is deterministic (route timestamp, then span id).
    """
    rotated = rotated_path or (ledger_path.parent / ROTATED_FILENAME)
    mtime: float | None = None
    try:
        mtime = ledger_path.stat().st_mtime if ledger_path.exists() else None
    except OSError:  # pragma: no cover - defensive
        mtime = None

    rotated_rows, rotated_corrupt, rotated_skipped, rotated_error = _read_ledger_file(rotated)
    live_rows, live_corrupt, live_skipped, live_error = _read_ledger_file(ledger_path)

    by_id: dict[str, dict[str, Any]] = {}
    for row in rotated_rows:
        by_id[_row_key(row)] = row
    n_rotated = len(by_id)
    for row in live_rows:  # live wins
        by_id[_row_key(row)] = row
    rows = sorted(by_id.values(), key=_row_sort_key)

    error = live_error or rotated_error
    return LedgerScan(
        ledger_path=str(ledger_path),
        rotated_path=str(rotated),
        exists=ledger_path.exists() or rotated.exists(),
        mtime=mtime,
        rows=rows,
        n_rotated_rows=n_rotated,
        n_corrupt=live_corrupt + rotated_corrupt,
        n_skipped=live_skipped + rotated_skipped,
        error_kind=UNREADABLE_LEDGER if error else None,
        error_message=error,
    )


# ---------------------------------------------------------------------------
# Query report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsumptionResult:
    """Machine report plus the process exit code it maps to."""

    report: dict[str, Any]
    exit_code: int
    fault: bool


def _matches_filters(
    row: dict[str, Any],
    *,
    span_id: str | None,
    session_id: str | None,
    task_id: str | None,
    since_dt: datetime | None,
    until_dt: datetime | None,
) -> tuple[bool, bool]:
    """(kept, dropped_by_missing_timestamp) for one row."""
    if span_id is not None and _row_key(row) != span_id:
        return False, False
    if session_id is not None and row.get("session_id") != session_id:
        return False, False
    if task_id is not None and row.get("task_id") != task_id:
        return False, False
    if since_dt is None and until_dt is None:
        return True, False
    ts = _parse_dt(row.get("route_started_at")) or _parse_dt(row.get("recorded_at"))
    if ts is None:
        return False, True
    if since_dt is not None and ts < since_dt:
        return False, False
    if until_dt is not None and ts >= until_dt:
        return False, False
    return True, False


def _segment_state(segment: Any) -> str | None:
    if not isinstance(segment, dict):
        return None
    state = segment.get("state")
    return state if isinstance(state, str) else None


def _segments(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Raw per-segment counts over the matched rows (no rates, ever)."""
    selected_yes = 0
    selected_no = 0
    selected_unknown = 0
    selected_reasons: dict[str, int] = {}
    read_unknown = 0
    read_reasons: dict[str, int] = {}
    injection_attempted = 0
    injection_unknown = 0
    read_like_tool_calls = 0
    rows_with_read_like_tool_calls = 0
    tail_unknown: dict[str, int] = {"applicable": 0, "executed": 0, "accepted": 0}
    tail_reasons: dict[str, dict[str, int]] = {
        "applicable": {},
        "executed": {},
        "accepted": {},
    }
    for row in rows:
        sel_state = _segment_state(row.get("selected"))
        if sel_state == "yes":
            selected_yes += 1
        elif sel_state == "no":
            selected_no += 1
        else:
            selected_unknown += 1
            reason = _reason_of(row.get("selected"))
            selected_reasons[reason] = selected_reasons.get(reason, 0) + 1

        read_seg = row.get("read") if isinstance(row.get("read"), dict) else {}
        if _segment_state(read_seg) is None:
            read_unknown += 1
            reason = _reason_of(read_seg)
            read_reasons[reason] = read_reasons.get(reason, 0) + 1
        evidence = read_seg.get("evidence") if isinstance(read_seg.get("evidence"), dict) else {}
        injection = evidence.get("injection_attempted")
        if injection is True:
            injection_attempted += 1
        elif injection is None:
            injection_unknown += 1
        calls = evidence.get("read_like_tool_calls")
        if isinstance(calls, int) and not isinstance(calls, bool) and calls > 0:
            read_like_tool_calls += calls
            rows_with_read_like_tool_calls += 1

        for name in tail_unknown:
            if _segment_state(row.get(name)) is None:
                tail_unknown[name] += 1
                reason = _reason_of(row.get(name))
                bucket = tail_reasons[name]
                bucket[reason] = bucket.get(reason, 0) + 1
    return {
        "selected": {
            "yes": selected_yes,
            "no": selected_no,
            "unknown": selected_unknown,
            "reasons": selected_reasons,
        },
        "read": {
            "unknown": read_unknown,
            "reasons": read_reasons,
            "injection_attempted": injection_attempted,
            "injection_unknown": injection_unknown,
            "read_like_tool_calls": read_like_tool_calls,
            "rows_with_read_like_tool_calls": rows_with_read_like_tool_calls,
        },
        "applicable": {
            "unknown": tail_unknown["applicable"],
            "reasons": tail_reasons["applicable"],
        },
        "executed": {"unknown": tail_unknown["executed"], "reasons": tail_reasons["executed"]},
        "accepted": {"unknown": tail_unknown["accepted"], "reasons": tail_reasons["accepted"]},
    }


def _reason_of(segment: Any) -> str:
    if not isinstance(segment, dict):
        return "missing_segment"
    reason = segment.get("reason")
    return reason if isinstance(reason, str) and reason else "unstated"


def consumption_report(
    ledger_path: Path,
    *,
    rotated_path: Path | None = None,
    span_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 20,
    now: datetime | None = None,
) -> ConsumptionResult:
    """Query the consumption ledger and return the v1 report plus exit code.

    Fail-soft by design: a missing ledger is NOT an error — the report says
    ``exists: false`` with empty rows/counts and exits 0. Raises ``ValueError``
    for usage errors (bad window, negative limit); callers map that to exit 2.
    An unreadable ledger is a fault (exit 3).

    Exit codes are labels for the query, not verdicts: this ledger has no
    healthy/warn state and must never gate anything.
    """
    if limit < 0:
        raise ValueError(f"--limit must be >= 0 (got {limit})")
    since_dt, until_dt = parse_window(since, until)
    generated_at = (now or datetime.now(UTC)).astimezone(UTC)

    scan = read_ledger(ledger_path, rotated_path)
    matched: list[dict[str, Any]] = []
    n_no_ts = 0
    for row in scan.rows:
        kept, missing_ts = _matches_filters(
            row,
            span_id=span_id,
            session_id=session_id,
            task_id=task_id,
            since_dt=since_dt,
            until_dt=until_dt,
        )
        if kept:
            matched.append(row)
        elif missing_ts:
            n_no_ts += 1

    fault = scan.error_kind is not None
    exit_code = 3 if fault else 0
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "ledger": {
            "path": scan.ledger_path,
            "rotated_path": scan.rotated_path,
            "exists": scan.exists,
            "mtime": scan.mtime,
        },
        "filters": {
            "span_id": span_id,
            "session_id": session_id,
            "task_id": task_id,
            "since": since_dt.isoformat() if since_dt is not None else None,
            "until": until_dt.isoformat() if until_dt is not None else None,
            "limit": limit,
        },
        "counts": {
            "n_rows": len(scan.rows),
            "n_rotated_rows": scan.n_rotated_rows,
            "n_matched": len(matched),
            "n_printed": min(len(matched), limit),
            "n_corrupt": scan.n_corrupt,
            "n_skipped": scan.n_skipped,
            "n_no_ts": n_no_ts,
        },
        "segments": _segments(matched),
        "rows": matched[:limit],
        "note": RAW_COUNTS_NOTE,
    }
    if fault:
        report["error"] = {
            "kind": scan.error_kind,
            "path": scan.ledger_path,
            "message": scan.error_message or "ledger could not be read",
        }
    return ConsumptionResult(report=report, exit_code=exit_code, fault=fault)


def render_human(report: dict[str, Any]) -> str:
    """Deterministic multi-line human block (no ANSI, no Rich markup)."""
    lines: list[str] = []
    lines.append(f"skill consumption ledger ({SCHEMA} v{SCHEMA_VERSION})")
    lines.append(f"generated_at: {report['generated_at']}")
    ledger = report["ledger"]
    lines.append(
        "ledger: path={path} rotated={rotated_path} exists={exists} mtime={mtime}".format(**ledger)
    )
    filters = report["filters"]
    lines.append(
        "filters: span_id={span_id} session_id={session_id} task_id={task_id} "
        "since={since} until={until} limit={limit}".format(**filters)
    )
    if "error" in report:
        err = report["error"]
        lines.append(f"error: {err['kind']} path={err['path']} message={err['message']}")
    counts = report["counts"]
    lines.append("counts: " + " ".join(f"{key}={value}" for key, value in counts.items()))
    segments = report["segments"]
    selected = segments["selected"]
    lines.append(
        f"selected: yes={selected['yes']} no={selected['no']} unknown={selected['unknown']} "
        f"reasons={json.dumps(selected['reasons'], ensure_ascii=False, sort_keys=True)}"
    )
    read = segments["read"]
    lines.append(
        f"read: unknown={read['unknown']} reasons="
        f"{json.dumps(read['reasons'], ensure_ascii=False, sort_keys=True)} "
        f"injection_attempted={read['injection_attempted']} "
        f"injection_unknown={read['injection_unknown']} "
        f"read_like_tool_calls={read['read_like_tool_calls']} "
        f"rows_with_read_like_tool_calls={read['rows_with_read_like_tool_calls']}"
    )
    for name in ("applicable", "executed", "accepted"):
        bucket = segments[name]
        lines.append(
            f"{name}: unknown={bucket['unknown']} "
            f"reasons={json.dumps(bucket['reasons'], ensure_ascii=False, sort_keys=True)}"
        )
    lines.append(f"rows ({len(report['rows'])} of {counts['n_matched']}):")
    for row in report["rows"]:
        sel = row.get("selected") or {}
        read_seg = row.get("read") or {}
        evidence = read_seg.get("evidence") or {}
        lines.append(
            f"  span={row.get('span_id')} ts={row.get('route_started_at')} "
            f"pop={row.get('route_population')} selected={sel.get('state')}"
            f"({sel.get('reason') or ','.join(sel.get('skill_ids') or []) or '-'}) "
            f"read={read_seg.get('state')}({read_seg.get('reason')}) "
            f"injection={evidence.get('injection_attempted')} "
            f"read_like={evidence.get('read_like_tool_calls')}"
        )
    lines.append(f"note: {report['note']}")
    return "\n".join(lines)
