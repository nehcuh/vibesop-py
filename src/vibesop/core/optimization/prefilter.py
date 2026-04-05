"""Candidate pre-filtering for skill routing."""

from __future__ import annotations
from typing import Any

COMPLEXITY_INDICATORS = [
    "复杂",
    "很多",
    "多个",
    "很多文件",
    "麻烦",
    "large",
    "complex",
    "multiple",
    "several",
    "many",
    "architecture",
    "架构",
    "设计",
    "design",
    "plan",
    "规划",
]

NAMESPACE_KEYWORDS = {
    "gstack": ["gstack", "g stack", "gee stack"],
    "superpowers": ["superpowers", "super powers", "超能力"],
    "omx": ["omx", "oh-my-codex", "codex"],
}


class CandidatePrefilter:
    """Pre-filter skill candidates before matching."""

    def __init__(self, cluster_index=None):
        self._cluster_index = cluster_index

    def filter(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates:
            return []
        tier_filtered = self._filter_by_priority(query, candidates)
        ns_filtered = self._filter_by_namespace(query, tier_filtered)
        if self._cluster_index:
            return self._filter_by_cluster(query, ns_filtered)
        return ns_filtered

    def _get_triggered_namespaces(self, query: str) -> set[str]:
        query_lower = query.lower()
        triggered = set()
        for namespace, keywords in NAMESPACE_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                triggered.add(namespace)
        return triggered

    def _filter_by_priority(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        result = []
        is_complex = any(kw in query for kw in COMPLEXITY_INDICATORS)
        triggered_ns = self._get_triggered_namespaces(query)
        for candidate in candidates:
            priority = candidate.get("priority", "P2")
            ns = candidate.get("namespace")
            if priority == "P0":
                result.append(candidate)
            elif priority == "P1":
                if is_complex or ns in triggered_ns:
                    result.append(candidate)
            elif priority == "P2":
                if ns in triggered_ns:
                    result.append(candidate)
        return result

    def _filter_by_namespace(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        query_lower = query.lower()
        triggered_namespaces = set()
        for namespace, keywords in NAMESPACE_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                triggered_namespaces.add(namespace)
        if triggered_namespaces:
            return [
                c
                for c in candidates
                if c.get("namespace") in triggered_namespaces or c.get("priority") == "P0"
            ]
        return candidates

    def _filter_by_cluster(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not self._cluster_index:
            return candidates
        relevant_clusters = self._cluster_index.get_relevant_clusters(query)
        if not relevant_clusters:
            return candidates
        cluster_skills = set()
        for cluster_id in relevant_clusters:
            cluster_skills.update(self._cluster_index.get_cluster_members(cluster_id))
        p0_ids = {c["id"] for c in candidates if c.get("priority") == "P0"}
        allowed_ids = cluster_skills | p0_ids
        return [c for c in candidates if c["id"] in allowed_ids]
