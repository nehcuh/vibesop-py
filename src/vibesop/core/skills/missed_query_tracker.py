"""Missed-query clustering for the P2 market-search feedback loop.

Two suggestion sources:

1. **Live path** (works without the analytics opt-in): when ``route()`` ends
   in no-match/fallback, the *current* query's normalized form is looked up in
   the always-on :class:`~vibesop.core.skills.miss_counter.MissCounter`. Once
   its count reaches the threshold, a cluster is built using the current
   in-process query text as the representative — this path never reads query
   text from (or writes it to) any store.
2. **Analytics path** (requires the F-06 analytics opt-in): reads
   ``.vibe/analytics.jsonl`` records with ``primary_skill=null`` (text already
   redacted at write time) and groups them by token-set Jaccard similarity.

CJK note: Jaccard similarity over the shared tokenizer (which emits
overlapping 2-character tokens for CJK) clusters Chinese text poorly; that is
accepted for this stage. Sentence embeddings would be the better similarity
signal but are an opt-in heavy dependency and deliberately out of scope (see
``docs/proposals/skill-market-search-and-feedback-loop.md`` §P2 / 非目标).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vibesop.core.matching.tokenizers import tokenize
from vibesop.core.skills.miss_counter import MissCounter

logger = logging.getLogger(__name__)

#: Default miss threshold — a cluster needs at least this many misses.
DEFAULT_MIN_COUNT = 3

#: Token-set Jaccard similarity threshold for grouping two missed queries.
DEFAULT_SIMILARITY_THRESHOLD = 0.6

#: Safety cap on how many missed analytics records are clustered at once.
_MAX_ANALYTICS_RECORDS = 2000


@dataclass
class MissedCluster:
    """A group of similar queries that repeatedly missed routing.

    Attributes:
        cluster_key: Normalized representative string; the stable identity
            used by the suggestion collector for dedup and dismissal.
        representative_query: Human-readable representative text. For
            ``source="live"`` this is the current in-process query; for
            ``source="analytics"`` the most recently recorded group member.
        count: Number of misses in this cluster.
        first: ISO timestamp of the first observed miss ("" when unknown).
        last: ISO timestamp of the most recent miss ("" when unknown).
        source: ``"live"`` (hash counter only, no stored text) or
            ``"analytics"`` (opt-in, redacted query text).
    """

    cluster_key: str
    representative_query: str
    count: int
    first: str = ""
    last: str = ""
    source: str = "live"


def normalize_query(query: str) -> str:
    """Normalize a query exactly like ``MissCounter`` (collapse whitespace, lowercase)."""
    return " ".join(query.split()).lower()


class MissedQueryTracker:
    """Builds missed-query clusters from the live counter or analytics opt-in."""

    def __init__(self, project_root: str | Path) -> None:
        self._analytics_path = Path(project_root) / ".vibe" / "analytics.jsonl"

    # ------------------------------------------------------------------
    # Live path (no opt-in required)
    # ------------------------------------------------------------------

    def suggest_for_live_query(
        self,
        query: str,
        counter: MissCounter,
        min_count: int = DEFAULT_MIN_COUNT,
    ) -> MissedCluster | None:
        """Return a cluster when *query* has missed ≥ ``min_count`` times, else None.

        The counter holds only salted hashes; the representative text comes
        from the current process (the query being routed right now), so this
        path never depends on any text storage.
        """
        normalized = normalize_query(query)
        if not normalized:
            return None
        entry = counter.count_for(query)
        if entry is None or entry.count < min_count:
            return None
        return MissedCluster(
            cluster_key=normalized,
            representative_query=" ".join(query.split()),
            count=entry.count,
            first=entry.first,
            last=entry.last,
            source="live",
        )

    # ------------------------------------------------------------------
    # Analytics path (F-06 opt-in)
    # ------------------------------------------------------------------

    def clusters_from_analytics(self, min_count: int = DEFAULT_MIN_COUNT) -> list[MissedCluster]:
        """Group missed queries from ``analytics.jsonl`` by Jaccard similarity.

        Records with ``primary_skill=null`` (routing misses, text redacted at
        write time) are grouped greedily in file order: a record joins the
        first group whose accumulated token set has Jaccard similarity
        ≥ 0.6, otherwise it opens a new group. Groups with ≥ ``min_count``
        members become clusters; since the file is append-only chronological,
        the representative is the last member of each group and ``first`` /
        ``last`` come from the timestamps of the first/last members. Tolerates
        a missing file and corrupt lines. Most frequent cluster first.
        """
        groups: list[list[tuple[str, str]]] = []  # members: (query, timestamp)
        group_tokens: list[set[str]] = []
        for query, timestamp in self._load_missed_queries():
            tokens = set(tokenize(normalize_query(query)))
            for idx, tokens_so_far in enumerate(group_tokens):
                if _jaccard(tokens, tokens_so_far) >= DEFAULT_SIMILARITY_THRESHOLD:
                    groups[idx].append((query, timestamp))
                    group_tokens[idx] = tokens_so_far | tokens
                    break
            else:
                groups.append([(query, timestamp)])
                group_tokens.append(tokens)

        clusters: list[MissedCluster] = []
        for group in groups:
            if len(group) < min_count:
                continue
            representative_query, last_ts = group[-1]
            clusters.append(
                MissedCluster(
                    cluster_key=normalize_query(representative_query),
                    representative_query=representative_query,
                    count=len(group),
                    first=group[0][1],
                    last=last_ts,
                    source="analytics",
                )
            )
        clusters.sort(key=lambda c: c.count, reverse=True)
        return clusters

    def _load_missed_queries(self) -> list[tuple[str, str]]:
        """Load (query, timestamp) pairs for missed routes from analytics.jsonl.

        Keeps the most recent ``_MAX_ANALYTICS_RECORDS`` misses; every failure
        mode (missing file, unreadable file, corrupt line, wrong shape) is
        treated as "no data".
        """
        try:
            lines = self._analytics_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        records: list[tuple[str, str]] = []
        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                data: Any = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or data.get("primary_skill") is not None:
                continue
            query = data.get("query")
            if not isinstance(query, str) or not query.strip():
                continue
            timestamp = data.get("timestamp")
            records.append((query, timestamp if isinstance(timestamp, str) else ""))
        return records[-_MAX_ANALYTICS_RECORDS:]


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two token sets; two empty sets count as identical."""
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


__all__ = [
    "DEFAULT_MIN_COUNT",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "MissedCluster",
    "MissedQueryTracker",
    "normalize_query",
]
