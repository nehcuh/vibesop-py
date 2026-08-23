"""L2-lite skill health read model (gate37) — raw facts only, no verdicts.

Feeds the health summary columns of ``vibe skill list``. Three read-only
facts (gate37 synthesis §6 修订 B + §6.1 修订 B 补丁/H):

- source (computed by ``candidate_manager._get_skill_source``, read from
  the candidate dict — pack collapses into external);
- 30-day fire count from THIS project's spans file (always-on source);
- explicit feedback raw counts from the project-level
  ``.vibe/execution_feedback.jsonl``.

Hard discipline (修订 B/C/H — do not relax):
- RAW COUNTS ONLY. No rates, no ratios, no derived disposition actions.
  n<30 supports no conclusion (column footnotes say so).
- Never calls ``evaluator`` / ``aggregator.success_rate`` — those are the
  repo's existing "fake L2" (修订 C).
- The fire scan is a SINGLE full pass over the spans file, plain reads,
  NO flock (the writer's LOCK_EX is the hook hot path,
  span_writer.py:47-50); file-missing → empty, never mkdir.
- Feedback counts use ``get_records()`` and count ``was_helpful``
  True/False directly — NOT ``get_skill_summary`` (which only returns a
  ratio, 修订 H).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from vibesop.core.observability._span_fields import span_timestamp
from vibesop.core.observability.dev_detect import is_dev_environment

logger = logging.getLogger(__name__)

FIRE_WINDOW_DAYS = 30


def spans_file_for(project_root: Path) -> Path | None:
    """Resolve this project's spans file, mirroring SpanWriter's dev/prod
    selection (span_writer.py:65). Returns None when absent — never
    creates directories (file-missing → empty convention)."""
    filename = "spans.dev.jsonl" if is_dev_environment() else "spans.jsonl"
    path = project_root / ".vibe" / "observability" / filename
    return path if path.exists() else None


#: PlanBuilder's no-match step sentinel (plan_builder.py:321-339/:626) —
#: written into span metadata by pre-gate40 producers (活洞群 B). A
#: fallback is a routing miss, not a skill: its reask/expired outcomes
#: are discovery-queue signals, so the sentinel is excluded from the
#: fire/skill columns and bucketed separately by the outcomes read model
#: (skill_outcomes top-level ``fallback`` count).
FALLBACK_SENTINEL = "fallback-llm"


def _route_hit_skill_id_raw(span: dict[str, Any]) -> str | None:
    """Raw extraction: a route HIT span's ``metadata.skill_id`` AS WRITTEN.

    Same span gates as ``_route_hit_skill_id`` (``span_kind == "task"`` ∧
    ``name.startswith("route:")`` ∧ ``metadata.has_match is True``), but
    returns the raw string — including ``""`` and the ``fallback-llm``
    sentinel — so bucketing layers (skill_outcomes) can distinguish the
    sentinel from a genuinely empty id. None only when the span is not a
    route hit or the id is missing/not a string.

    Metadata may be a dict or a JSON-encoded string (SpanWriter
    serialises it); malformed JSON → not a hit, never raises.
    """
    if span.get("span_kind") != "task":
        return None
    name = span.get("name")
    if not isinstance(name, str) or not name.startswith("route:"):
        return None

    meta = span.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (TypeError, ValueError):
            return None
    if not isinstance(meta, dict) or meta.get("has_match") is not True:
        return None

    skill_id = meta.get("skill_id")
    return skill_id if isinstance(skill_id, str) else None


def _route_hit_skill_id(span: dict[str, Any]) -> str | None:
    """Fire predicate (修订 B): a route HIT span's matched skill id.

    ``_route_hit_skill_id_raw`` minus the empty string AND the
    ``fallback-llm`` sentinel (gate40 项4 — cmspark measured the sentinel
    as the largest 30d fire bucket, 1061/2822; it is not a skill). CLI-path
    hits count too (修订 B 补丁: the feedback UI lives on the CLI path;
    excluding CLI would disconnect the fire and feedback populations).
    """
    skill_id = _route_hit_skill_id_raw(span)
    if skill_id is None or not skill_id or skill_id == FALLBACK_SENTINEL:
        return None
    return skill_id


def _parse_span_time(span: dict[str, Any]) -> datetime | None:
    """Parse a span's timestamp (started_at preferred, legacy timestamp
    fallback) as an aware UTC datetime. None when missing/unparseable —
    a span we cannot place in time is dropped from a windowed count."""
    raw = span_timestamp(span)
    if not isinstance(raw, str) or not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def count_skill_fires(
    project_root: Path,
    *,
    days: int = FIRE_WINDOW_DAYS,
    now: datetime | None = None,
) -> dict[str, int]:
    """Count route-hit fires per skill over the last ``days`` days.

    Single full-table scan, plain unlocked reads. Missing file, bad
    lines, and unparseable timestamps all degrade to "no data".
    """
    path = spans_file_for(project_root)
    if path is None:
        return {}

    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    counts: dict[str, int] = {}
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
                skill_id = _route_hit_skill_id(span)
                if skill_id is None:
                    continue
                ts = _parse_span_time(span)
                if ts is None or ts < cutoff:
                    continue
                counts[skill_id] = counts.get(skill_id, 0) + 1
    except OSError:
        return {}
    return counts


def count_skill_feedback(project_root: Path) -> dict[str, tuple[int, int]]:
    """Raw explicit-feedback counts per skill: ``{skill_id: (yes, no)}``.

    Reads the PROJECT-level ``.vibe/execution_feedback.jsonl`` via
    ``ExecutionFeedbackCollector.get_records()`` (修订 H). Two known
    biases the column footnotes must disclose:
    - ``vibe skills feedback`` writes to the GLOBAL store — an existing
      gap, not counted here (留档, not fixed in gate37);
    - "partial" is recorded as ``was_helpful=False`` (cli/feedback.py)
      — the "no" count mixes in partially-satisfied responses.
    """
    from vibesop.core.feedback import ExecutionFeedbackCollector

    # Same path shape as cli/feedback.py:85 — the collector's constructor
    # swaps the suffix to .jsonl.
    storage = project_root / ".vibe" / "execution_feedback.json"
    try:
        records = ExecutionFeedbackCollector(storage_path=storage).get_records()
    except OSError:
        return {}

    counts: dict[str, tuple[int, int]] = {}
    for record in records:
        yes, no = counts.get(record.skill_id, (0, 0))
        if record.was_helpful is True:
            counts[record.skill_id] = (yes + 1, no)
        elif record.was_helpful is False:
            counts[record.skill_id] = (yes, no + 1)
        # was_helpful=None carries no vote — skipped.
    return counts
