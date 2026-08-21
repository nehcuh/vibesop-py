"""Gold standard detection for task-memory clusters (W1 Task C).

Marks clusters as ``gold`` (proven successful pattern worth replaying) or
``candidate`` (success signal but too few spans to be sure) based on
``InstinctLearner.record_outcome`` data.

Rules (per v3 design §3 W1 Task C):

- **Primary signal**: any member task_id has an instinct with
  ``success_count >= 1`` (configurable via ``min_success_count``).
- **Size gate**: cluster needs ``span_count >= min_cluster_size``
  (default 5) for full ``is_gold``; below that it becomes
  ``is_candidate`` instead. Avoids promoting one-shot successes.
- **gold_rate**: fraction of member task_ids whose instinct has success.
  Used downstream by W4 skill promote (trigger: ``gold_rate >= 0.6``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.observability.clustering import Cluster

logger = logging.getLogger(__name__)

__all__ = ["assess_gold_status", "is_route_miss_span"]

_DEFAULT_MIN_CLUSTER_SIZE = 5
_DEFAULT_MIN_SUCCESS_COUNT = 1


def assess_gold_status(
    clusters: list[Cluster],
    learner: InstinctLearner,
    min_cluster_size: int = _DEFAULT_MIN_CLUSTER_SIZE,
    min_success_count: int = _DEFAULT_MIN_SUCCESS_COUNT,
) -> list[Cluster]:
    """Enrich clusters with gold/candidate flags in-place.

    Mutates each Cluster's ``is_gold`` and ``is_candidate`` flags and
    attaches ``gold_task_ids`` and ``gold_rate`` metadata via attribute
    assignment (Cluster is a dataclass without these fields to keep the
    base type lean; they're added as dynamic attributes here so the W2/W4
    consumers can read them).

    Parameters
    ----------
    clusters:
        Output of ``cluster_queries``.
    learner:
        InstinctLearner with recorded outcomes.
    min_cluster_size:
        Minimum span_count for full gold status. Below this, success
        signal yields ``candidate`` instead.
    min_success_count:
        Minimum ``success_count`` on a member instinct to count toward
        gold signal.

    Returns
    -------
    list[Cluster]
        Same list (mutated), for chaining.
    """
    for cluster in clusters:
        gold_task_ids: list[str] = []
        member_count = len(cluster.task_ids)
        if member_count == 0:
            cluster.is_gold = False
            cluster.is_candidate = False
            cluster.gold_task_ids = []
            cluster.gold_rate = 0.0
            continue

        # ``cluster_queries`` always emits one query per task_id, so the
        # lengths match in production. Manually-constructed clusters (or
        # future producers) may not honour that — truncate to the shorter
        # instead of ``strict=True``, which would raise ValueError and take
        # down a whole cron-scheduled candidate scan on one malformed
        # cluster (review finding F1). Repo convention: skip bad rows,
        # never take down the batch.
        if len(cluster.task_ids) != len(cluster.queries):
            logger.warning(
                "cluster %s: task_ids/queries length mismatch (%d vs %d) — "
                "truncating to the shorter for gold assessment",
                cluster.cluster_id,
                len(cluster.task_ids),
                len(cluster.queries),
            )
        for tid, query in zip(cluster.task_ids, cluster.queries, strict=False):
            instinct = learner.get_instinct_for_query(query)
            if instinct is not None and instinct.success_count >= min_success_count:
                gold_task_ids.append(tid)

        has_success = len(gold_task_ids) > 0
        gold_rate = len(gold_task_ids) / member_count

        cluster.is_gold = has_success and cluster.span_count >= min_cluster_size
        cluster.is_candidate = has_success and cluster.span_count < min_cluster_size
        cluster.gold_task_ids = gold_task_ids
        cluster.gold_rate = gold_rate

    return clusters


def is_route_miss_span(span: dict[str, Any]) -> bool:
    """M12 miss classification (design v3, gate15b final rule).

    A span is a route **miss** iff ALL of:

    - it is a route span: ``span_kind == "task"`` and ``name`` starts
      with ``"route:"``;
    - ``metadata.has_match`` is explicitly ``False`` (producers set
      ``has_match=False`` for no-match, which already excludes the
      ``fallback_llm`` sentinel — a fallback is not a match);
    - ``metadata.mode`` is NOT ``"not_intercepted"`` (the interceptor
      deliberately abstained — e.g. "继续"-style continuation prompts —
      so no routing attempt happened).

    Spans with ``has_match`` missing (CLI error paths, pre-W5.0 legacy
    spans) are **unknown**, never misses (conservative direction).

    Producer alignment (gate20): both route-span producers now write the
    router's REAL match verdict — the CLI path always did
    (``cli/main.py``), and the hook path (``agent_runtime.handle_query``)
    writes ``router_matched`` here since gate20 (previously a mode-derived
    value that hid hook-path misses from this predicate).

    Metadata may be a dict or a JSON-encoded string (SpanWriter
    serialises it); malformed JSON is treated as unknown, never raises.

    Cross-reference (gate17 claude nit 6): ``tool_call_bridge._is_miss``
    classifies misses too, but is DELIBERATELY stricter — it additionally
    excludes CLI-path spans (``is_cli``) and ``mode="slash_command"``.
    The divergence is intentional, not drift: the bridge predicate feeds
    **outcome-signal derivation** (a CLI invocation mints a one-shot
    session, so "session continued" evidence can never exist for it and
    its misses would decay into hollow weak positives), while THIS
    predicate feeds **discovery candidates** (a CLI miss is a legitimate
    discovery signal — the user asked, routing had no answer). If you
    change one, re-read the other before deciding they should match.
    """
    if span.get("span_kind") != "task":
        return False
    name = span.get("name")
    if not isinstance(name, str) or not name.startswith("route:"):
        return False

    meta = span.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (TypeError, ValueError):
            return False
    if not isinstance(meta, dict):
        return False

    has_match = meta.get("has_match")
    if has_match is not False:  # True → hit; missing/other → unknown
        return False
    return meta.get("mode") != "not_intercepted"
