"""Task-memory cluster algorithm (W1 Task B, W5.1 cross-project bridge).

Groups recent spans into clusters by combining two signals:

1. **Hard group** (W5.1): spans sharing the same ``(project_id, task_id)``
   composite key always belong to the same cluster. Pre-W5.1 used
   ``task_id`` alone, which collapsed the same query in two projects
   into one cluster and contaminated gold/promote decisions.
2. **Soft merge**: distinct task_keys whose representative query
   embeddings have ``cosine ≥ threshold`` are transitively merged
   (Union-Find connected components). Soft-merge still crosses project
   boundaries for discovery — the resulting cross-project cluster
   surfaces heterogeneity via ``Cluster.project_distribution`` and
   ``Cluster.is_cross_project`` (W5.1 Task 2.2).

Output: a list of ``Cluster`` objects. Each cluster has a deterministic
``cluster_id`` (sha1 of sorted ``(project_id, task_id)`` pairs) so the
same input set produces stable IDs across runs.

Legacy span age-out (W5.1 Task 2.3): when ``include_legacy=False``
(default), spans with ``project_id == "default"`` (pre-W5.0
instrumentation) are skipped. This ages out old spans without a backfill
migration; pass ``include_legacy=True`` for diagnostics.

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
    """A cluster of task_keys with their combined span count.

    Attributes
    ----------
    cluster_id:
        Deterministic ID — sha1 of sorted ``(project_id, task_id)`` pairs,
        first 16 hex chars. Changes when the project mix changes (W5.1).
    task_ids:
        Sorted list of task_ids in the cluster (one per composite key).
        W5.1 note: the same literal task_id can now appear multiple times
        when the cluster spans multiple projects — use ``task_keys`` for
        the unambiguous identifier. Sorted by composite key.
    task_keys:
        Sorted list of ``(project_id, task_id)`` composite keys. W5.1.
        This is the authoritative hard-key identifier; ``task_ids`` is a
        projection kept for backwards-compat with consumers that haven't
        migrated yet.
    span_count:
        Total spans across all member task_keys.
    queries:
        Distinct representative queries (one per task_key, in sorted order).
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

        W5.1 note: ``task_ids`` may contain duplicates when a cluster spans
        multiple projects (same query in 2 projects → 2 composite keys →
        2 entries in ``task_ids``). Since ``task_id = sha1(normalize(query))``
        is purely query-derived, the same literal ``task_id`` always maps
        to the same instinct lookup result. So the gold/total ratio is
        preserved across the duplicate expansion — both numerator and
        denominator grow proportionally.
    project_distribution:
        Bucket counts per ``project_id`` across member task_keys. W5.1.
        Example: ``{"vibesop": 12, "cmspark": 3}``. Used by
        ``is_cross_project`` and UI warnings on heterogeneous clusters.
        Single-project clusters have one key.

    Note on ``span_count`` semantics (W5.0.C): when ``cluster_queries`` is
    called with ``max_spans_per_task=N``, ``span_count`` reflects the
    post-cap count (most-recent-N per task_key), not the raw count. The
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
    task_keys: list[tuple[str, str]] = field(default_factory=list)
    project_distribution: dict[str, int] = field(default_factory=dict)

    @property
    def is_cross_project(self) -> bool:
        """True when the cluster spans >1 project (W5.1).

        UI consumers should warn before promoting a cross-project cluster
        — the instinct store is per-project, so promotion semantics are
        ambiguous. See ``skill_promote`` guard.
        """
        return len(self.project_distribution) > 1

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
    include_legacy: bool = False,
) -> list[Cluster]:
    """Cluster spans by ``(project_id, task_id)`` (hard) + cosine (soft).

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
        Optional cap on spans counted per task_key. When a task has more
        than this many spans, only the most-recent-N (by ``started_at``
        descending) contribute to ``Cluster.span_count``. Default None =
        no cap (all spans counted). Does NOT bound the O(n²) cosine pass
        (that's across distinct task_keys, not spans) — bounds the span
        counter so a chatty hot task doesn't dominate ``span_count``.
        W5.0.C instrumentation; not yet exposed via CLI.
    include_legacy:
        When False (default), spans with ``project_id == "default"``
        (pre-W5.0 instrumentation) are skipped. W5.1 Task 2.3: lazy
        age-out — old spans age out without a backfill migration.
        Pass True for diagnostics (e.g. ``vibe observability audit``).

    Returns
    -------
    list[Cluster]
        Sorted by span_count descending (most active first).

    Hard-key change (W5.1 Task 2.1): pre-W5.1 the hard-group was
    ``task_id`` alone, which collapsed the same query in two projects
    into one cluster. Now the key is ``(project_id, task_id)``; the same
    literal task_id can appear in multiple clusters (one per project).
    Soft-merge still crosses project boundaries via cosine — the
    resulting cross-project cluster surfaces heterogeneity via
    ``Cluster.project_distribution``.
    """
    if not spans:
        return []
    cache = cache or get_embedding_cache()

    # W5.1 Task 2.3: lazy age-out. Skip pre-W5.0 spans (project_id="default")
    # unless explicitly included. Use `or "default"` (not `.get(..., "default")`)
    # so empty-string project_id from buggy emitters is also treated as missing.
    if not include_legacy:
        spans = [s for s in spans if (s.get("project_id") or "default") != "default"]
        if not spans:
            return []

    # 1) Hard group by (project_id, task_id). Representative query is picked
    #    AFTER the sampling cap (W5.0 review H2): post-cap the list is sorted
    #    by started_at desc, so [0] is the most recent span's query.
    per_task_queries: dict[tuple[str, str], str] = {}
    per_task_spans: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for span in spans:
        tid = span.get("task_id")
        if not tid:
            continue
        pid = span.get("project_id") or "default"
        per_task_spans[(pid, tid)].append(span)

    if not per_task_spans:
        return []

    # 1b) W5.0.C: apply per-task sampling cap. Most-recent-N by started_at desc.
    #     Doesn't bound O(n²) cosine (that's across distinct task_keys); bounds
    #     span_count so one chatty task can't dwarf smaller clusters.
    if max_spans_per_task is not None:
        for key in list(per_task_spans.keys()):
            group = per_task_spans[key]
            if len(group) > max_spans_per_task:
                group_sorted = sorted(
                    group,
                    key=lambda s: span_timestamp(s) or "",
                    reverse=True,
                )
                per_task_spans[key] = group_sorted[:max_spans_per_task]

    # 1c) Pick representative query per task_key. Post-cap, per_task_spans[key][0]
    #     is the most recent span in the (possibly sampled) set. This keeps
    #     span_count + representative query consistent with the same time window.
    for key, group in per_task_spans.items():
        for span in group:
            query = _extract_query(span)
            if query:
                per_task_queries[key] = query
                break

    if not per_task_queries:
        return []

    per_task_count = {key: len(spans) for key, spans in per_task_spans.items()}

    # 2) Compute embedding for each representative query (cache-backed).
    task_keys_sorted = sorted(per_task_queries.keys())
    queries_sorted = [per_task_queries[k] for k in task_keys_sorted]
    embeddings = cache.embed_batch(queries_sorted)

    # 3) Build adjacency via pairwise cosine ≥ threshold.
    n = len(task_keys_sorted)
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

    # 4) Group task_keys by Union-Find root.
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)

    # 5) Build Cluster objects.
    clusters: list[Cluster] = []
    for members in groups.values():
        member_keys = sorted(task_keys_sorted[i] for i in members)
        member_embeddings: list[np.ndarray] = []
        for i in members:
            e = embeddings[i]
            if e is not None:
                member_embeddings.append(e)
        centroid = np.mean(np.stack(member_embeddings), axis=0) if member_embeddings else None
        # W5.1: cluster_id hash input is now composite-keyed to keep same
        # task_id in different projects from colliding.
        hash_input = "\x1f".join(f"{pid}|{tid}" for pid, tid in member_keys)
        cluster_id = hashlib.sha1(hash_input.encode("utf-8")).hexdigest()[:16]
        total_spans = sum(per_task_count[k] for k in member_keys)

        # W5.1 Task 2.2: bucket span counts per project_id for cross-project
        # heterogeneity detection.
        proj_dist: dict[str, int] = defaultdict(int)
        for pid, _tid in member_keys:
            proj_dist[pid] += per_task_count[(pid, _tid)]

        clusters.append(
            Cluster(
                cluster_id=cluster_id,
                task_ids=[tid for _pid, tid in member_keys],
                task_keys=member_keys,
                span_count=total_spans,
                queries=[per_task_queries[k] for k in member_keys],
                centroid=centroid,
                is_gold=False,
                project_distribution=dict(proj_dist),
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
