"""Candidate pre-filtering for skill routing.

This module provides dynamic namespace discovery from skill metadata,
eliminating hardcoded namespace limitations to support third-party skill packs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibesop.core.optimization.clustering import SkillClusterIndex

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

# Default namespace keywords (fallback if dynamic discovery fails)
# These provide sensible defaults for well-known skill packs
_DEFAULT_NAMESPACE_KEYWORDS: dict[str, list[str]] = {
    "gstack": ["gstack", "g stack", "gee stack"],
    "superpowers": ["superpowers", "super powers", "超能力"],
    "omx": ["omx", "oh-my-codex", "codex"],
}


class CandidatePrefilter:
    """Pre-filter skill candidates before matching.

    This prefilter now supports dynamic namespace discovery:
    - Extracts namespaces from candidate skill metadata
    - Builds keyword mappings from skill tags and names
    - Falls back to defaults for unknown namespaces

    Example:
        >>> # Auto-discover namespaces from candidates
        >>> prefilter = CandidatePrefilter.from_candidates(candidates)
        >>> filtered = prefilter.filter("debug this error", candidates)
    """

    def __init__(
        self,
        cluster_index: SkillClusterIndex | None = None,
        namespace_keywords: dict[str, list[str]] | None = None,
    ):
        """Initialize the candidate prefilter.

        Args:
            cluster_index: Optional cluster index for cluster-based filtering
            namespace_keywords: Optional custom namespace keywords mapping.
                If None, defaults to _DEFAULT_NAMESPACE_KEYWORDS.
        """
        self._cluster_index = cluster_index
        self._namespace_keywords = namespace_keywords or _DEFAULT_NAMESPACE_KEYWORDS.copy()

    @classmethod
    def from_candidates(
        cls,
        candidates: list[dict[str, Any]],
        cluster_index: SkillClusterIndex | None = None,
    ) -> CandidatePrefilter:
        """Create a prefilter by discovering namespaces from candidates.

        This method analyzes the candidate skills to build a dynamic
        namespace-to-keywords mapping, eliminating the need for hardcoded
        namespace definitions.

        Args:
            candidates: List of skill candidates to analyze
            cluster_index: Optional cluster index for cluster-based filtering

        Returns:
            Configured CandidatePrefilter with dynamic namespace mappings
        """
        # Start with defaults
        namespace_keywords = _DEFAULT_NAMESPACE_KEYWORDS.copy()

        # Discover namespaces from candidates
        discovered_keywords = cls._discover_namespace_keywords(candidates)

        # Merge discovered keywords (discovered takes precedence)
        for ns, keywords in discovered_keywords.items():
            if ns in namespace_keywords:
                # Merge with existing (keep unique)
                merged = set(namespace_keywords[ns]) | set(keywords)
                namespace_keywords[ns] = list(merged)
            else:
                namespace_keywords[ns] = keywords

        return cls(cluster_index=cluster_index, namespace_keywords=namespace_keywords)

    def filter(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter candidates based on query complexity and namespace triggers.

        Args:
            query: The search query
            candidates: List of skill candidates to filter

        Returns:
            Filtered list of candidates
        """
        if not candidates:
            return []
        tier_filtered = self._filter_by_priority(query, candidates)
        ns_filtered = self._filter_by_namespace(query, tier_filtered)
        if self._cluster_index:
            return self._filter_by_cluster(query, ns_filtered)
        return ns_filtered

    def _get_triggered_namespaces(self, query: str) -> set[str]:
        """Get namespaces triggered by the query using dynamic keyword mapping.

        Args:
            query: The search query

        Returns:
            Set of triggered namespace names
        """
        query_lower = query.lower()
        triggered = set()
        for namespace, keywords in self._namespace_keywords.items():
            if any(kw in query_lower for kw in keywords):
                triggered.add(namespace)
        return triggered

    def _filter_by_priority(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter candidates by priority level.

        P0 skills are always included.
        P1 skills are included if query indicates complexity or namespace match.
        P2 skills are included only if namespace matches.

        Args:
            query: The search query
            candidates: List of skill candidates

        Returns:
            Filtered list of candidates
        """
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
            elif priority == "P2" and ns in triggered_ns:
                result.append(candidate)
        return result

    def _filter_by_namespace(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter candidates by namespace matching.

        Args:
            query: The search query
            candidates: List of skill candidates

        Returns:
            Filtered list of candidates
        """
        triggered_namespaces = self._get_triggered_namespaces(query)
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
        """Filter candidates by cluster membership.

        Args:
            query: The search query
            candidates: List of skill candidates

        Returns:
            Filtered list of candidates
        """
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
        triggered_ns = self._get_triggered_namespaces(query)
        # Allow cluster members, P0 skills, and skills whose namespace was
        # dynamically triggered (e.g. newly installed third-party packs not yet
        # present in the cluster index).
        return [
            c
            for c in candidates
            if c["id"] in allowed_ids or c.get("namespace") in triggered_ns
        ]

    @staticmethod
    def _discover_namespace_keywords(
        candidates: list[dict[str, Any]]
    ) -> dict[str, list[str]]:
        """Discover namespace-to-keywords mappings from skill metadata.

        This enables third-party skill packs to be discovered without
        hardcoded namespace definitions. Keywords are extracted from:
        - The namespace name itself
        - Skill tags (if present)
        - Skill name variations

        Args:
            candidates: List of skill candidates to analyze

        Returns:
            Dictionary mapping namespace names to lists of keywords
        """
        namespace_keywords: dict[str, set[str]] = {}

        for candidate in candidates:
            ns = candidate.get("namespace", "")
            if not ns or ns == "builtin":
                continue

            if ns not in namespace_keywords:
                namespace_keywords[ns] = set()

            # Add namespace name variations
            ns_lower = ns.lower()
            namespace_keywords[ns].add(ns_lower)

            # Add hyphen and space variations
            if "-" in ns:
                parts = ns.split("-")
                namespace_keywords[ns].add(" ".join(parts))
            if "_" in ns:
                parts = ns.split("_")
                namespace_keywords[ns].add(" ".join(parts))

            # Extract from tags/keywords
            tags = candidate.get("keywords", []) or candidate.get("tags", [])
            if tags:
                for tag in tags:
                    if isinstance(tag, str):
                        namespace_keywords[ns].add(tag.lower())

            # Extract from name (first word)
            name = candidate.get("name", "")
            if name:
                first_word = name.split()[0].lower()
                if len(first_word) > 2:  # Skip very short words
                    namespace_keywords[ns].add(first_word)

        # Convert sets to sorted lists
        return {ns: sorted(keywords) for ns, keywords in namespace_keywords.items()}

    def update_namespace_keywords(
        self,
        namespace_keywords: dict[str, list[str]],
    ) -> None:
        """Update the namespace keywords mapping.

        This allows for runtime updates when new skill packs are discovered.

        Args:
            namespace_keywords: New namespace keywords mapping
        """
        self._namespace_keywords.update(namespace_keywords)

    def get_supported_namespaces(self) -> set[str]:
        """Get the set of namespaces this prefilter recognizes.

        Returns:
            Set of namespace names
        """
        return set(self._namespace_keywords.keys())

    def get_keywords_for_namespace(self, namespace: str) -> list[str]:
        """Get the keywords associated with a namespace.

        Args:
            namespace: The namespace name

        Returns:
            List of keywords for the namespace, or empty list if unknown
        """
        return self._namespace_keywords.get(namespace, []).copy()
