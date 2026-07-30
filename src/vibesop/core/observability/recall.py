"""Recall retrieval logic for task-memory loop (W2 Task A + W3 extension).

Given a query and a list of historical spans, returns the top-k most
similar past task_ids by cosine similarity on representative query
embeddings (cached via ``EmbeddingCache``).

Output: ``RecallResult`` per match containing the task_id, similarity
score, representative query, span_count, step sequence (span names in
temporal order), last_seen timestamp, and (W3) trace_id + skill_id +
gold status when an ``InstinctLearner`` is supplied.

Default absolute threshold of 0.70 filters weak matches — per v3 design
§3 W2: "默认未达阈值视为无召回（防错召回污染信任）".
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from vibesop.core.observability._span_fields import span_timestamp
from vibesop.core.observability.clustering import _cosine
from vibesop.core.observability.embedding import EmbeddingCache, get_embedding_cache

if TYPE_CHECKING:
    from vibesop.core.instinct.learner import InstinctLearner

logger = logging.getLogger(__name__)

__all__ = ["RecallResult", "recall_similar"]

_DEFAULT_TOP_K = 3
_DEFAULT_THRESHOLD = 0.70
_DEFAULT_DAYS_WINDOW = 30
# W3 per-task gold gate. Unit = distinct trace_ids (= distinct runs), not raw
# span lines. A single chatty route can emit ≥5 child spans (llm:, tool:,
# workflow_node) in one execution; counting spans as evidence of "proven"
# inflates false gold (grok P0-3). Fallback to span_count when trace_id
# absent from legacy spans.
_DEFAULT_MIN_GOLD_RUN_COUNT = 3


@dataclass
class RecallResult:
    """A single recall match.

    Attributes
    ----------
    task_id:
        The matched task_id (sha1 of normalised past query).
    similarity:
        Cosine similarity between query embedding and task_id's
        representative query embedding. Range [-1, 1].
    representative_query:
        The first observed raw query for this task_id.
    span_count:
        Number of spans contributing to this task_id within the window.
    step_sequence:
        Span names in temporal order (oldest first). Empty if no
        timestamp available — falls back to file order.
    last_seen:
        ISO timestamp of the most recent span for this task_id.
    is_gold:
        True if this task_id has a successful instinct AND ≥ ``min_gold_run_count``
        distinct trace_ids (W3 per-task gold). Distinct traces are the unit of
        "proven" — a single chatty execution emitting ≥5 child spans must not
        qualify (grok P0-3). When trace_ids are absent from legacy spans, falls
        back to span_count >= ``min_gold_run_count``. Populated only when
        ``recall_similar`` is called with a ``learner``; otherwise stays False
        (preserves W2 D5 retrieval-primitive purity).
    trace_id:
        Most recent trace_id observed for this task_id. None if spans
        don't carry trace_id. Used by W3 replay span emission to link
        new trace ↔ old trace.
    skill_id:
        Most common skill_id routed for this task_id (mode over spans).
        None if no skill_id in spans. Used by W3 prompt to show
        "last time routed to skill X".
    gold_success_count:
        ``success_count`` from the matched Instinct, or 0 if no instinct
        or no learner provided. Surfaces "how many times this task
        succeeded historically" in the replay prompt.
    distinct_trace_count:
        Number of distinct trace_ids observed for this task_id. The gold
        size unit (see ``is_gold``). Falls back to ``span_count`` semantic
        when no traces carry trace_id.
    """

    task_id: str
    similarity: float
    representative_query: str
    span_count: int
    step_sequence: list[str] = field(default_factory=list)
    last_seen: str | None = None
    is_gold: bool = False
    trace_id: str | None = None
    skill_id: str | None = None
    gold_success_count: int = 0
    distinct_trace_count: int = 0


def recall_similar(
    query: str,
    spans: list[dict],
    cache: EmbeddingCache | None = None,
    learner: InstinctLearner | None = None,
    top_k: int = _DEFAULT_TOP_K,
    threshold: float = _DEFAULT_THRESHOLD,
    days: int = _DEFAULT_DAYS_WINDOW,
    min_gold_run_count: int = _DEFAULT_MIN_GOLD_RUN_COUNT,
) -> list[RecallResult]:
    """Return top-k similar past task_ids by cosine on query embedding.

    Parameters
    ----------
    query:
        The current query to find matches for.
    spans:
        Span dicts from ``SpanWriter.query_recent``. Must have
        ``task_id`` and ``input_data.query`` for the recall path.
    cache:
        Embedding cache. Defaults to module singleton.
    learner:
        Optional InstinctLearner. When provided, each result's
        ``is_gold`` / ``gold_success_count`` are populated via
        ``learner.get_instinct_for_query(representative_query)``.
        When None, both stay at default (False / 0).
    top_k:
        Maximum number of matches to return.
    threshold:
        Minimum cosine similarity to include in results.
    days:
        Look-back window. Spans older than this are excluded.
    min_gold_run_count:
        Minimum distinct trace_id count for ``is_gold=True``. Distinct
        traces are the "proven" unit; falls back to span_count when
        spans lack trace_id (legacy compatibility).

    Returns
    -------
    list[RecallResult]
        Sorted by similarity descending. Empty if no matches above
        threshold, or if embeddings unavailable (library missing).
    """
    if not spans or not query.strip():
        return []
    cache = cache or get_embedding_cache()

    # Filter spans by days window.
    cutoff = datetime.now(UTC) - timedelta(days=days)
    recent_spans = _filter_recent(spans, cutoff)
    if not recent_spans:
        return []

    # Group spans by task_id; collect representative query + step sequence.
    per_task = _group_by_task_id(recent_spans)
    if not per_task:
        return []

    # Compute query embedding once.
    query_vec = cache.embed(query)
    if query_vec is None:
        logger.debug("recall: embedding library unavailable; returning no matches")
        return []

    # Compute task_id embeddings (cache-backed).
    task_ids = sorted(per_task.keys())
    rep_queries = [per_task[t]["query"] for t in task_ids]
    task_vecs = cache.embed_batch(rep_queries)

    # Score by cosine.
    scored: list[tuple[float, str]] = []
    for tid, vec in zip(task_ids, task_vecs, strict=True):
        if vec is None:
            continue
        sim = _cosine(query_vec, vec)
        if sim >= threshold:
            scored.append((sim, tid))

    scored.sort(reverse=True)
    top = scored[:top_k]

    results: list[RecallResult] = []
    for sim, tid in top:
        task_info = per_task[tid]
        is_gold = False
        gold_success_count = 0
        if learner is not None:
            instinct = learner.get_instinct_for_query(task_info["query"])
            if instinct is not None and instinct.success_count >= 1:
                gold_success_count = instinct.success_count
                # Gold size unit = distinct trace_ids (= distinct runs).
                # Fall back to span_count when legacy spans lack trace_id
                # (grok P0-3: span lines inflate false gold).
                distinct_count = task_info["distinct_trace_count"]
                size_signal = distinct_count if distinct_count > 0 else task_info["count"]
                is_gold = size_signal >= min_gold_run_count
        results.append(
            RecallResult(
                task_id=tid,
                similarity=sim,
                representative_query=task_info["query"],
                span_count=task_info["count"],
                step_sequence=task_info["steps"],
                last_seen=task_info["last_seen"],
                trace_id=task_info["trace_id"],
                skill_id=task_info["skill_id"],
                is_gold=is_gold,
                gold_success_count=gold_success_count,
                distinct_trace_count=task_info["distinct_trace_count"],
            )
        )
    return results


def _filter_recent(spans: list[dict], cutoff: datetime) -> list[dict]:
    """Keep spans whose timestamp is at or after ``cutoff``.

    Spans without a parseable timestamp are kept (don't drop data on a
    formatting quirk). Spans with malformed timestamps are also kept
    rather than crashing the recall.
    """
    recent: list[dict] = []
    for span in spans:
        ts_raw = span_timestamp(span)
        if not ts_raw:
            recent.append(span)
            continue
        try:
            ts = _parse_timestamp(ts_raw)
            if ts is None or ts >= cutoff:
                recent.append(span)
        except (ValueError, TypeError):
            recent.append(span)
    return recent


def _parse_timestamp(ts: str) -> datetime | None:
    """Parse an ISO timestamp. Returns None if not parseable."""
    if not ts:
        return None
    try:
        # Python 3.11+ handles most ISO formats including TZ offsets.
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        return None


def _group_by_task_id(spans: list[dict]) -> dict[str, dict]:
    """Group spans by task_id, collecting per-task metadata for RecallResult.

    Returns a dict shaped::

        {
            task_id: {
                "query": <first non-empty raw query>,
                "count": <total spans>,
                "steps": <list of span names in temporal order>,
                "last_seen": <ISO timestamp of most recent span>,
                "trace_id": <most recent trace_id>,     # W3
                "skill_id": <most common skill_id>,     # W3
                "distinct_trace_count": <len(set(trace_ids))>,  # W3 Fix-1
            }
        }
    """
    per_task: dict[str, dict] = {}
    spans_by_task: dict[str, list[dict]] = defaultdict(list)

    for span in spans:
        tid = span.get("task_id")
        if not tid:
            continue
        spans_by_task[tid].append(span)

    for tid, group in spans_by_task.items():
        # Representative query = first non-empty query in original order.
        rep_query = ""
        for s in group:
            q = _extract_query(s)
            if q:
                rep_query = q
                break

        # Skip task_ids with no extractable query — embedding an empty string
        # produces noise vectors that pollute recall results.
        if not rep_query:
            continue

        # Sort by timestamp for stable step sequence; fall back to file order.
        def _ts_key(s: dict) -> datetime:
            ts = _parse_timestamp(span_timestamp(s) or "")
            return ts or datetime.min.replace(tzinfo=UTC)

        sorted_group = sorted(group, key=_ts_key)
        steps = [s.get("name", "") for s in sorted_group if s.get("name")]

        # Last seen = max timestamp.
        timestamps = [
            parsed
            for s in group
            if (parsed := _parse_timestamp(span_timestamp(s) or "")) is not None
        ]
        last_seen_dt = max(timestamps) if timestamps else None
        last_seen = last_seen_dt.isoformat() if last_seen_dt else None

        # W3: trace_id = trace_id of the most recent span that has one.
        trace_id: str | None = None
        if last_seen_dt is not None:
            for s in sorted_group:
                if _parse_timestamp(span_timestamp(s) or "") == last_seen_dt:
                    tid_field = s.get("trace_id")
                    if isinstance(tid_field, str) and tid_field:
                        trace_id = tid_field
                        break
        if trace_id is None:
            # Fallback: first span with a trace_id, any position.
            for s in group:
                tid_field = s.get("trace_id")
                if isinstance(tid_field, str) and tid_field:
                    trace_id = tid_field
                    break

        # W3: skill_id = most common skill_id across spans (mode).
        skill_counter: Counter[str] = Counter()
        for s in group:
            sk_id = _extract_skill_id(s)
            if sk_id:
                skill_counter[sk_id] += 1
        skill_id = skill_counter.most_common(1)[0][0] if skill_counter else None

        # W3 Fix-1: distinct trace_id count = number of separate runs.
        # The gold size unit. Empty when legacy spans don't carry trace_id;
        # caller falls back to span_count.
        distinct_trace_ids: set[str] = set()
        for s in group:
            tid_field = s.get("trace_id")
            if isinstance(tid_field, str) and tid_field:
                distinct_trace_ids.add(tid_field)
        distinct_trace_count = len(distinct_trace_ids)

        per_task[tid] = {
            "query": rep_query,
            "count": len(group),
            "steps": steps,
            "last_seen": last_seen,
            "trace_id": trace_id,
            "skill_id": skill_id,
            "distinct_trace_count": distinct_trace_count,
        }

    return per_task


def _extract_skill_id(span: dict) -> str | None:
    """Extract skill_id from a span.

    Spans store skill_id in one of three places depending on age:
    - Top-level ``skill_id`` field (newer schema)
    - ``metadata.skill_id`` (current main.py:786 pattern)
    - ``output_data.skill_id`` (route decision result)

    Returns None if no skill_id is found.
    """
    top = span.get("skill_id")
    if isinstance(top, str) and top:
        return top
    metadata = span.get("metadata")
    if isinstance(metadata, dict):
        sk = metadata.get("skill_id")
        if isinstance(sk, str) and sk:
            return sk
    output = span.get("output_data")
    if isinstance(output, dict):
        sk = output.get("skill_id")
        if isinstance(sk, str) and sk:
            return sk
    return None


def _extract_query(span: dict) -> str | None:
    """Same shape as clustering._extract_query — kept local to avoid cross-module coupling."""
    raw = span.get("input_data")
    if raw is None:
        return None
    if isinstance(raw, dict):
        q = raw.get("query")
        return str(q) if q is not None else None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return raw
        if isinstance(parsed, dict):
            q = parsed.get("query")
            return str(q) if q is not None else None
        return raw
    return None
