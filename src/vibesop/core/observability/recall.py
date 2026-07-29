"""Recall retrieval logic for task-memory loop (W2 Task A).

Given a query and a list of historical spans, returns the top-k most
similar past task_ids by cosine similarity on representative query
embeddings (cached via ``EmbeddingCache``).

Output: ``RecallResult`` per match containing the task_id, similarity
score, representative query, span_count, step sequence (span names in
temporal order), and last_seen timestamp.

Default absolute threshold of 0.70 filters weak matches — per v3 design
§3 W2: "默认未达阈值视为无召回（防错召回污染信任）".
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from vibesop.core.observability.clustering import _cosine
from vibesop.core.observability.embedding import EmbeddingCache, get_embedding_cache

logger = logging.getLogger(__name__)

__all__ = ["RecallResult", "recall_similar"]

_DEFAULT_TOP_K = 3
_DEFAULT_THRESHOLD = 0.70
_DEFAULT_DAYS_WINDOW = 30


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
        True if this task_id belongs to a gold cluster (W1 Task C).
        False otherwise. Populated downstream by callers that run
        ``assess_gold_status``; recall itself doesn't query InstinctLearner.
    """

    task_id: str
    similarity: float
    representative_query: str
    span_count: int
    step_sequence: list[str] = field(default_factory=list)
    last_seen: str | None = None
    is_gold: bool = False


def recall_similar(
    query: str,
    spans: list[dict],
    cache: EmbeddingCache | None = None,
    top_k: int = _DEFAULT_TOP_K,
    threshold: float = _DEFAULT_THRESHOLD,
    days: int = _DEFAULT_DAYS_WINDOW,
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
    top_k:
        Maximum number of matches to return.
    threshold:
        Minimum cosine similarity to include in results.
    days:
        Look-back window. Spans older than this are excluded.

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

    return [
        RecallResult(
            task_id=tid,
            similarity=sim,
            representative_query=per_task[tid]["query"],
            span_count=per_task[tid]["count"],
            step_sequence=per_task[tid]["steps"],
            last_seen=per_task[tid]["last_seen"],
        )
        for sim, tid in top
    ]


def _filter_recent(spans: list[dict], cutoff: datetime) -> list[dict]:
    """Keep spans whose timestamp is at or after ``cutoff``.

    Spans without a parseable timestamp are kept (don't drop data on a
    formatting quirk). Spans with malformed timestamps are also kept
    rather than crashing the recall.
    """
    recent: list[dict] = []
    for span in spans:
        ts_raw = span.get("timestamp")
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
            ts = _parse_timestamp(s.get("timestamp", ""))
            return ts or datetime.min.replace(tzinfo=UTC)

        sorted_group = sorted(group, key=_ts_key)
        steps = [s.get("name", "") for s in sorted_group if s.get("name")]

        # Last seen = max timestamp.
        timestamps = [
            _parse_timestamp(s.get("timestamp", ""))
            for s in group
            if _parse_timestamp(s.get("timestamp", ""))
        ]
        last_seen = max(timestamps).isoformat() if timestamps else None

        per_task[tid] = {
            "query": rep_query,
            "count": len(group),
            "steps": steps,
            "last_seen": last_seen,
        }

    return per_task


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
