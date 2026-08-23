"""Skill route-outcome read model (gate39) — raw counts only, no verdicts.

Feeds the ``vibe skill outcomes`` table: the gate38 hit-outcome data
(``route_outcomes.jsonl``) made visible for the first time. Outcome rows
carry no ``skill_id`` — the join key is ``outcome.span_id`` → span ``id``,
with the skill id taken from the span's metadata. Span metadata may be a
JSON-encoded string, so the join reuses ``skill_health``'s route-hit
extraction (str→json.loads tolerance + span gates) instead of a literal
``span["metadata"]["skill_id"]`` — the raw variant
(``_route_hit_skill_id_raw``) so the ``fallback-llm`` sentinel can be
told apart from a genuinely empty id (gate40 项4).

Hard discipline (same bar as skill_health.py — do not relax):
- RAW COUNTS ONLY. No rates, no ratios, no percentages, no grades, no
  derived disposition actions. n<30 supports no conclusion (the table
  footnotes say so).
- SINGLE full scan of the outcomes file + SINGLE full scan of the spans
  file (span_id → skill_id map), plain reads, NO flock; file-missing →
  empty, never mkdir.
- Only ``side == "hit"`` rows are processed (a missing ``side`` defaults
  to the miss side; ``population`` defaults to hook and is not filtered —
  the writer only records hook rows today).
- Spans mirror ``spans_file_for`` dev/prod selection; the outcomes file is
  ALWAYS ``route_outcomes.jsonl`` (the writer has no dev variant — a known
  asymmetry, recorded in gate39 §4.7; same precedent as
  execution_feedback.jsonl).
- ``last_at`` is the outcome row's ``span_ts`` (never ``recorded_at`` —
  backfilled rows all share the backfill day's recorded_at, which would
  make the Last column a lie). A row without a parseable ``span_ts`` does
  not update ``last_at``.
- ``unjoined`` counts hit rows that cannot be attributed: source span
  missing OR span ``skill_id`` empty/missing (the fire column's non-empty
  predicate — cmspark measured 37/2437 dirty hits) OR an unknown reason
  (defensive: only three reasons exist today; if the writer adds a fourth,
  this keeps the invariant instead of silently dropping rows).
- ``fallback`` counts hit rows whose span carried the ``fallback-llm``
  sentinel (gate40 项4 — the sentinel is not a skill; its outcomes are
  discovery-queue signals, so it must NOT collapse into ``unjoined``:
  cmspark measured 1088/2440 hit-outcome rows). Producers stopped writing
  the sentinel on miss rows in gate40; these are pre-gate40 rows.
  Reconciliation invariant: Σ(per-skill reask + moved_on + expired) +
  unjoined + fallback == total hit rows.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vibesop.core.skills.skill_health import (
    FALLBACK_SENTINEL,
    _route_hit_skill_id_raw,
    spans_file_for,
)

logger = logging.getLogger(__name__)

OUTCOMES_FILENAME = "route_outcomes.jsonl"

#: Hit-outcome reason → table column. Only these three reasons exist
#: (tool_call_bridge._classify_hit); anything else is unattributable.
_REASON_TO_COLUMN = {
    "hit_reask_same_task_id": "reask",
    "hit_session_moved_on": "moved_on",
    "hit_session_expired": "expired",
}


def outcomes_file_for(project_root: Path) -> Path | None:
    """Resolve this project's outcomes file (always ``route_outcomes.jsonl``
    — no dev variant exists on the write side). Returns None when absent —
    never creates directories (file-missing → empty convention)."""
    path = project_root / ".vibe" / "observability" / OUTCOMES_FILENAME
    return path if path.exists() else None


def _span_skill_map(project_root: Path) -> dict[str, str]:
    """Single scan of the spans file → ``{span_id: raw skill_id}`` for
    route-hit spans. The raw id is kept (including ``""`` and the
    ``fallback-llm`` sentinel) so the bucketing layer can route sentinel
    rows to the top-level ``fallback`` count instead of ``unjoined``.
    Spans whose metadata is malformed or whose skill_id is missing are
    absent from the map — their outcome rows land in ``unjoined``.
    """
    path = spans_file_for(project_root)
    if path is None:
        return {}

    mapping: dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    span = json.loads(line)
                except json.JSONDecodeError:
                    continue  # bad line → skip (storage convention)
                span_id = span.get("id")
                if not isinstance(span_id, str) or not span_id:
                    continue
                skill_id = _route_hit_skill_id_raw(span)
                if skill_id is None:
                    continue
                mapping[span_id] = skill_id
    except OSError:
        return {}
    return mapping


def _parse_outcome_ts(raw: Any) -> datetime | None:
    """Parse an outcome row's ``span_ts`` as an aware UTC datetime. None
    when missing/unparseable — such a row must not update ``last_at``."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def count_skill_outcomes(project_root: Path) -> dict[str, Any]:
    """Raw per-skill hit-outcome counts + top-level ``unjoined``/``fallback``.

    Returns ``{"skills": {skill_id: {"reask", "moved_on", "expired",
    "last_at"}}, "unjoined": int, "fallback": int}`` with skills sorted by
    skill_id (lexicographic — never by count, which would be a leaderboard).
    ``last_at`` is the raw ``span_ts`` string of the latest outcome row
    for the skill (None when no row carried a parseable one).

    Missing files, bad lines, and bad metadata all degrade to "no data"
    — this read path never raises and never creates directories.
    """
    skills: dict[str, dict[str, Any]] = {}
    last_dt: dict[str, datetime] = {}
    unjoined = 0
    fallback = 0

    outcomes_path = outcomes_file_for(project_root)
    if outcomes_path is not None:
        span_skills = _span_skill_map(project_root)
        try:
            with outcomes_path.open("r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # bad line → skip (storage convention)
                    if row.get("side") != "hit":
                        continue  # miss side (missing side defaults to miss)

                    span_id = row.get("span_id")
                    skill_id = span_skills.get(span_id) if isinstance(span_id, str) else None
                    if skill_id == FALLBACK_SENTINEL:
                        # Fallback routing is a miss, not a skill — its
                        # outcomes belong to the discovery queue, counted
                        # separately so they don't collapse into unjoined.
                        fallback += 1
                        continue
                    column = _REASON_TO_COLUMN.get(row.get("reason"))
                    if not skill_id or column is None:
                        # Span missing, empty skill_id, or unknown reason —
                        # unattributable. Bucketing here (not silently
                        # dropping) keeps the reconciliation invariant.
                        unjoined += 1
                        continue

                    entry = skills.setdefault(
                        skill_id, {"reask": 0, "moved_on": 0, "expired": 0, "last_at": None}
                    )
                    entry[column] += 1
                    raw_ts = row.get("span_ts")
                    ts = _parse_outcome_ts(raw_ts)
                    if ts is not None and (skill_id not in last_dt or ts > last_dt[skill_id]):
                        last_dt[skill_id] = ts
                        entry["last_at"] = raw_ts
        except OSError:
            return {"skills": {}, "unjoined": 0, "fallback": 0}

    return {
        "skills": {sid: skills[sid] for sid in sorted(skills)},
        "unjoined": unjoined,
        "fallback": fallback,
    }
