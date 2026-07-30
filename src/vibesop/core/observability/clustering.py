"""Task-memory cluster algorithm (W1 Task B).

Groups recent spans into clusters by combining two signals:

1. **Hard group**: spans sharing the same ``task_id`` always belong to
   the same cluster (because task_id is derived from the normalised
   query — see ``task_id.derive_task_id``).
2. **Soft merge**: distinct task_ids whose representative query
   embeddings have ``cosine ≥ threshold`` are transitively merged
   (Union-Find connected components).

Output: a list of ``Cluster`` objects. Each cluster has a deterministic
``cluster_id`` (sha1 of sorted member task_ids) so the same input set
produces stable IDs across runs.

The ``is_gold`` flag is always ``False`` here — Task C
(``InstinctLearner.record_outcome`` integration) flips it based on
success signals.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from vibesop.core.observability._span_fields import span_timestamp
from vibesop.core.observability.embedding import EmbeddingCache, get_embedding_cache

logger = logging.getLogger(__name__)

__all__ = ["Cluster", "cluster_queries"]

_DEFAULT_THRESHOLD = 0.80


@dataclass
class Cluster:
    """A cluster of task_ids with their combined span count.

    Attributes
    ----------
    cluster_id:
        Deterministic ID — sha1 of sorted task_ids, first 16 hex chars.
    task_ids:
        Sorted list of task_ids in the cluster. Sorted so equality is
        order-independent.
    span_count:
        Total spans across all member task_ids.
    queries:
        Distinct representative queries (one per task_id, in sorted order).
    centroid:
        Mean of member embeddings (None if embeddings unavailable).
    is_gold:
        Set by ``assess_gold_status`` when cluster has success signal
        AND ``span_count >= min_cluster_size``. Defaults to False.
    is_candidate:
        Set by ``assess_gold_status`` when cluster has success signal
        but ``span_count < min_cluster_size``. Provisional — too few
        spans to call it gold yet.
    gold_task_ids:
        Member task_ids whose instinct has ``success_count >= threshold``.
        Populated by ``assess_gold_status``.
    gold_rate:
        Fraction of member task_ids with success signal
        (``len(gold_task_ids) / len(task_ids)``). Used by W4 skill
        promote trigger (``gold_rate >= 0.6``).

    Note on ``span_count`` semantics (W5.0.C): when ``cluster_queries`` is
    called with ``max_spans_per_task=N``, ``span_count`` reflects the
    post-cap count (most-recent-N per task_id), not the raw count. The
    representative ``queries[0]`` is also drawn from the post-cap set,
    keeping both fields consistent with the same sampling window.
    """

    cluster_id: str
    task_ids: list[str]
    span_count: int
    queries: list[str] = field(default_factory=list)
    centroid: np.ndarray | None = None
    is_gold: bool = False
    is_candidate: bool = False
    gold_task_ids: list[str] = field(default_factory=list)
    gold_rate: float = 0.0

    def __repr__(self) -> str:
        tid_str = ",".join(self.task_ids[:3])
        if len(self.task_ids) > 3:
            tid_str += f",...(+{len(self.task_ids) - 3})"
        return (
            f"Cluster(id={self.cluster_id}, "
            f"task_ids=[{tid_str}], spans={self.span_count}, "
            f"gold={self.is_gold})"
        )


class _UnionFind:
    """Standard Union-Find with path compression + union by rank."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity with zero-vector guard (returns 0.0)."""
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def cluster_queries(
    spans: list[dict],
    cache: EmbeddingCache | None = None,
    threshold: float = _DEFAULT_THRESHOLD,
    max_spans_per_task: int | None = None,
) -> list[Cluster]:
    """Cluster spans by task_id (hard) + cosine similarity (soft).

    Parameters
    ----------
    spans:
        Span dicts from ``SpanWriter.query_recent`` or equivalent. Each
        span must have a ``task_id`` field (None task_ids are skipped)
        and ``input_data.query`` for embedding lookup.
    cache:
        Embedding cache. Defaults to module singleton.
    threshold:
        Cosine similarity threshold for soft merge. Default 0.80 per
        v3 design §8.1 (Benchmark decision: MiniLM p90 near-miss at 0.894
        — 0.80 absorbs screenshot-adjacent queries into gold clusters).
    max_spans_per_task:
        Optional cap on spans counted per task_id. When a task has more
        than this many spans, only the most-recent-N (by ``started_at``
        descending) contribute to ``Cluster.span_count``. Default None =
        no cap (all spans counted). Does NOT bound the O(n²) cosine pass
        (that's across distinct task_ids, not spans) — bounds the span
        counter so a chatty hot task doesn't dominate ``span_count``.
        W5.0.C instrumentation; not yet exposed via CLI.

    Returns
    -------
    list[Cluster]
        Sorted by span_count descending (most active first).
    """
    if not spans:
        return []
    cache = cache or get_embedding_cache()

    # 1) Group spans by task_id (hard group). Representative query is picked
    #    AFTER the sampling cap (W5.0 review H2): post-cap the list is sorted
    #    by started_at desc, so [0] is the most recent span's query.
    per_task_queries: dict[str, str] = {}
    per_task_spans: dict[str, list[dict]] = defaultdict(list)
    for span in spans:
        tid = span.get("task_id")
        if not tid:
            continue
        per_task_spans[tid].append(span)

    if not per_task_spans:
        return []

    # 1b) W5.0.C: apply per-task sampling cap. Most-recent-N by started_at desc.
    #     Doesn't bound O(n²) cosine (that's across distinct task_ids); bounds
    #     span_count so one chatty task can't dwarf smaller clusters.
    if max_spans_per_task is not None:
        for tid in list(per_task_spans.keys()):
            group = per_task_spans[tid]
            if len(group) > max_spans_per_task:
                group_sorted = sorted(
                    group,
                    key=lambda s: span_timestamp(s) or "",
                    reverse=True,
                )
                per_task_spans[tid] = group_sorted[:max_spans_per_task]

    # 1c) Pick representative query per task. Post-cap, per_task_spans[tid][0]
    #     is the most recent span in the (possibly sampled) set. This keeps
    #     span_count + representative query consistent with the same time window.
    for tid, group in per_task_spans.items():
        for span in group:
            query = _extract_query(span)
            if query:
                per_task_queries[tid] = query
                break

    if not per_task_queries:
        return []

    per_task_count = {tid: len(spans) for tid, spans in per_task_spans.items()}

    # 2) Compute embedding for each representative query (cache-backed).
    task_ids_sorted = sorted(per_task_queries.keys())
    queries_sorted = [per_task_queries[t] for t in task_ids_sorted]
    embeddings = cache.embed_batch(queries_sorted)

    # 3) Build adjacency via pairwise cosine ≥ threshold.
    n = len(task_ids_sorted)
    uf = _UnionFind(n)
    for i in range(n):
        vi = embeddings[i]
        if vi is None:
            continue
        for j in range(i + 1, n):
            vj = embeddings[j]
            if vj is None:
                continue
            if _cosine(vi, vj) >= threshold:
                uf.union(i, j)

    # 4) Group task_ids by Union-Find root.
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)

    # 5) Build Cluster objects.
    clusters: list[Cluster] = []
    for members in groups.values():
        member_tids = sorted(task_ids_sorted[i] for i in members)
        member_embeddings: list[np.ndarray] = []
        for i in members:
            e = embeddings[i]
            if e is not None:
                member_embeddings.append(e)
        centroid = np.mean(np.stack(member_embeddings), axis=0) if member_embeddings else None
        cluster_id = hashlib.sha1("\x1f".join(member_tids).encode("utf-8")).hexdigest()[:16]
        total_spans = sum(per_task_count[t] for t in member_tids)
        clusters.append(
            Cluster(
                cluster_id=cluster_id,
                task_ids=member_tids,
                span_count=total_spans,
                queries=[per_task_queries[t] for t in member_tids],
                centroid=centroid,
                is_gold=False,
            )
        )

    clusters.sort(key=lambda c: c.span_count, reverse=True)
    return clusters


def _extract_query(span: dict) -> str | None:
    """Pull the user query out of a span's input_data.

    Handles three shapes observed in spans.jsonl:
    - ``input_data`` is a dict with ``query`` key (route spans)
    - ``input_data`` is a JSON-encoded string of same shape
    - ``input_data`` is the raw query string itself
    """
    raw = span.get("input_data")
    if raw is None:
        return None
    if isinstance(raw, dict):
        q = raw.get("query")
        return str(q) if q is not None else None
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return raw  # treat the string itself as the query
        if isinstance(parsed, dict):
            q = parsed.get("query")
            return str(q) if q is not None else None
        return raw
    return None
