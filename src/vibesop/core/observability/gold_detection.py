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

import logging

from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.observability.clustering import Cluster

logger = logging.getLogger(__name__)

__all__ = ["assess_gold_status"]

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
        for tid, query in zip(cluster.task_ids, cluster.queries):
            instinct = learner.get_instinct_for_query(query)
            if instinct is not None and instinct.success_count >= min_success_count:
                gold_task_ids.append(tid)

        has_success = len(gold_task_ids) > 0
        gold_rate = len(gold_task_ids) / member_count

        cluster.is_gold = has_success and cluster.span_count >= min_cluster_size
        cluster.is_candidate = (
            has_success and cluster.span_count < min_cluster_size
        )
        cluster.gold_task_ids = gold_task_ids
        cluster.gold_rate = gold_rate

    return clusters
