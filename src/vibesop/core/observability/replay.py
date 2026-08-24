"""Replay decision logic for task-memory loop (W3 Task C + D).

Given a query and historical spans, decides whether to prompt the user
to replay a proven (gold) prior execution. Used by ``vibe route`` to
auto-prompt on gold recall matches.

Decision flow::

    learner=None      → should_prompt=False, reason="no_learner"
    recall empty      → should_prompt=False, reason="no_recall"
    any top-k is_gold → should_prompt=True,  reason="gold_match"
    otherwise         → should_prompt=False, reason="not_gold"

Scans top-3 (not just rank-1) for the first gold match — handles the
case where rank-1 is a non-gold near-miss but rank-2/3 is gold
(grok P1-1).

Rationale: per W3 design (v3 §3 line 110-114) + merged review P0-3
(``_review-task-memory-loop-merged.md:51``), replay must be one-key
confirm of a PROVEN solution. Without gold status, there's no trust
signal to offer the user.

``emit_replay_span()`` writes a provenance marker into the current
trace, linking new execution ↔ prior trace_id. Uses ``workflow_node``
kind (not ``task``) to avoid creating a sibling top-level trace.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from vibesop.core.observability.embedding import EmbeddingCache
from vibesop.core.observability.recall import RecallResult, recall_similar

if TYPE_CHECKING:
    from vibesop.core.instinct.learner import InstinctLearner
    from vibesop.core.observability.tracer import ObservabilityTracer

logger = logging.getLogger(__name__)

__all__ = ["ReplayDecision", "emit_replay_span", "should_replay"]

_DEFAULT_THRESHOLD = 0.70
_DEFAULT_DAYS_WINDOW = 30


@dataclass
class ReplayDecision:
    """Outcome of evaluating whether to prompt for replay.

    Attributes
    ----------
    should_prompt:
        True only when learner is provided, recall returns ≥1 match,
        and at least one of the top-3 matches has ``is_gold=True``.
    top_match:
        The first gold match in the top-3 (when should_prompt=True), or
        the highest-similarity non-gold match (when should_prompt=False
        + reason="not_gold"), or None if recall empty. Caller uses this
        to display trace_id / step_sequence / skill_id in the Y/n prompt.
    reason:
        Machine-readable reason for the decision. One of:
        - ``"gold_match"``: prompt (a top-3 match is gold)
        - ``"no_learner"``: caller didn't supply learner; gold undecidable
        - ``"no_recall"``: no spans matched the query above threshold
        - ``"not_gold"``: top-3 matches exist but none are gold
    """

    should_prompt: bool
    top_match: RecallResult | None
    reason: str


def should_replay(
    query: str,
    spans: list[dict],
    cache: EmbeddingCache | None = None,
    learner: InstinctLearner | None = None,
    threshold: float = _DEFAULT_THRESHOLD,
    days: int = _DEFAULT_DAYS_WINDOW,
) -> ReplayDecision:
    """Decide whether to prompt the user to replay a prior gold execution.

    Parameters
    ----------
    query:
        Current query being routed.
    spans:
        Historical spans from SpanWriter.query_recent.
    cache:
        EmbeddingCache (defaults to singleton).
    learner:
        InstinctLearner used to populate is_gold on recall results.
        If None, replay is impossible (gold status undecidable) and
        ``should_prompt=False`` with reason ``"no_learner"``.
    threshold:
        Cosine similarity threshold for recall.
    days:
        Look-back window.

    Returns
    -------
    ReplayDecision
        See class docstring for fields.
    """
    if learner is None:
        return ReplayDecision(should_prompt=False, top_match=None, reason="no_learner")

    if not spans:
        return ReplayDecision(should_prompt=False, top_match=None, reason="no_recall")

    results = recall_similar(
        query=query,
        spans=spans,
        cache=cache,
        learner=learner,
        top_k=3,  # Scan top-3 for first gold (grok P1-1)
        threshold=threshold,
        days=days,
    )
    if not results:
        return ReplayDecision(should_prompt=False, top_match=None, reason="no_recall")

    # Iterate to find first gold; rank-1 may be a non-gold near-miss.
    top_match = results[0]
    for result in results:
        if result.is_gold:
            return ReplayDecision(should_prompt=True, top_match=result, reason="gold_match")

    return ReplayDecision(should_prompt=False, top_match=top_match, reason="not_gold")


def emit_replay_span(
    tracer: ObservabilityTracer,
    top_match: RecallResult,
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> str | None:
    """Emit a ``workflow_node`` span linking current execution to prior trace.

    Called after user confirms Y on the replay prompt. The span records:
    - ``name``: ``replay:<old_task_id>``
    - ``kind``: ``workflow_node`` (annotation, not top-level task)
    - ``metadata.replay_of``: prior trace_id (provenance link)
    - ``metadata.old_task_id``: prior task_id
    - ``metadata.old_query``: prior representative query
    - ``metadata.skill_id``: skill that was routed last time
    - ``metadata.similarity``: cosine similarity of the match

    Returns the new span's trace_id (so caller can pass it downstream if
    needed), or None if tracer is disabled / no active trace.

    Parameters
    ----------
    tracer:
        Active Tracer (typically from ``get_tracer()``).
    top_match:
        The gold RecallResult the user confirmed to replay.
    extra_metadata:
        Optional additional metadata to merge into the span.
    """
    metadata: dict[str, Any] = {
        "replay_of": top_match.trace_id,
        "old_task_id": top_match.task_id,
        "old_query": top_match.representative_query,
        "skill_id": top_match.skill_id,
        "similarity": top_match.similarity,
        "gold_success_count": top_match.gold_success_count,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    span_name = f"replay:{top_match.task_id}"
    try:
        with tracer.span(span_name, kind="workflow_node", metadata=metadata) as span:
            return span.trace_id
    except Exception as exc:
        logger.warning("emit_replay_span failed: %s", exc)
        return None
