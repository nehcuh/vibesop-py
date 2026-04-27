"""Per-skill recommendation engine based on query patterns and candidate similarity.

Unlike IntegrationRecommender (pack-level), this engine recommends individual skills
based on intent keyword overlap, trigger matching, and priority weighting.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, ClassVar

from vibesop.core.orchestration.patterns import INTENT_DOMAIN_KEYWORDS


@dataclass
class Recommendation:
    """A single skill recommendation with a relevance score."""

    skill_id: str
    namespace: str
    score: float
    matched_keywords: list[str] = field(default_factory=list)
    intent: str = ""
    reason: str = ""


class SkillRecommender:
    """Recommend individual skills based on query-candidate similarity.

    Scoring dimensions:
    - Intent keyword overlap (40%): how many intent-domain keywords match
    - Trigger keyword match (30%): direct trigger word hits
    - Priority bonus (20%): P0 > P1 > P2
    - Namespace diversity boost (10%): avoid recommending all from same namespace
    """

    _PRIORITY_WEIGHTS: ClassVar[dict[str, float]] = {"P0": 1.0, "P1": 0.7, "P2": 0.4}

    def __init__(self) -> None:
        self._keyword_index: dict[str, set[str]] = self._build_keyword_index()

    @staticmethod
    def _build_keyword_index() -> dict[str, set[str]]:
        index: dict[str, set[str]] = {}
        for domain, keywords in INTENT_DOMAIN_KEYWORDS.items():
            for kw in keywords:
                index.setdefault(kw.lower(), set()).add(domain)
        return index

    def recommend(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 3,
        exclude_namespaces: list[str] | None = None,
    ) -> list[Recommendation]:
        if not candidates:
            return []

        exclude = set(exclude_namespaces or [])
        query_lower = query.lower()

        matched_domains: Counter[str] = Counter()
        for kw, domains in self._keyword_index.items():
            if kw in query_lower:
                for domain in domains:
                    matched_domains[domain] += 1

        scored: list[Recommendation] = []

        for candidate in candidates:
            if candidate.get("namespace", "") in exclude:
                continue

            skill_id = str(candidate.get("id", ""))
            namespace = str(candidate.get("namespace", "builtin"))
            intent = str(candidate.get("intent", ""))
            triggers = candidate.get("triggers", [])
            priority = str(candidate.get("priority", "P2"))
            intent_lower = intent.lower()

            score = 0.0
            matched_keywords: list[str] = []

            intent_overlap = 0
            for kw, _domains in self._keyword_index.items():
                if kw in intent_lower:
                    intent_overlap += 1
                    matched_keywords.append(kw)
            score += min(intent_overlap / max(len(self._keyword_index) * 0.1, 1), 1.0) * 0.4

            trigger_hits = sum(1 for t in triggers if t in query_lower)
            score += min(trigger_hits / max(len(triggers) * 0.3, 1), 1.0) * 0.3

            score += self._PRIORITY_WEIGHTS.get(priority, 0.4) * 0.2

            ns_count = sum(1 for r in scored if r.namespace == namespace)
            score += max(0, (1.0 - ns_count * 0.3)) * 0.1

            for kw in matched_keywords:
                if kw in matched_domains:
                    score += 0.05

            score = min(score, 1.0)

            reason_parts = []
            if intent_overlap:
                reason_parts.append(f"{intent_overlap} intent keyword matches")
            if trigger_hits:
                reason_parts.append(f"{trigger_hits} trigger hits")
            reason = "; ".join(reason_parts) if reason_parts else "priority-based match"

            scored.append(
                Recommendation(
                    skill_id=skill_id,
                    namespace=namespace,
                    score=round(score, 4),
                    matched_keywords=matched_keywords,
                    intent=intent,
                    reason=reason,
                )
            )

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def discover(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        used_skill_ids: set[str] | None = None,
        top_k: int = 3,
    ) -> list[Recommendation]:
        """Discover unused skills relevant to the current query domain.

        Unlike recommend(), this prioritizes skills the user has NOT yet used,
        acting as a proactive discovery engine. Skills already in used_skill_ids
        are still scored but receive a penalty.

        Args:
            query: Natural language query or activity description
            candidates: All available skill candidates
            used_skill_ids: Set of skill IDs already used (penalized)
            top_k: Number of discoveries to return

        Returns:
            Sorted list of Recommendation, highest discovery score first
        """
        if not candidates:
            return []

        used = used_skill_ids or set()
        query_lower = query.lower()

        matched_domains: Counter[str] = Counter()
        for kw, domains in self._keyword_index.items():
            if kw in query_lower:
                for domain in domains:
                    matched_domains[domain] += 1

        scored: list[Recommendation] = []

        for candidate in candidates:
            skill_id = str(candidate.get("id", ""))
            namespace = str(candidate.get("namespace", "builtin"))
            intent = str(candidate.get("intent", ""))
            triggers = candidate.get("triggers", [])
            priority = str(candidate.get("priority", "P2"))
            intent_lower = intent.lower()

            score = 0.0
            matched_keywords: list[str] = []

            intent_overlap = 0
            for kw, _domains in self._keyword_index.items():
                if kw in intent_lower:
                    intent_overlap += 1
                    matched_keywords.append(kw)
            score += min(intent_overlap / max(len(self._keyword_index) * 0.1, 1), 1.0) * 0.3

            trigger_hits = sum(1 for t in triggers if t in query_lower)
            score += min(trigger_hits / max(len(triggers) * 0.3, 1), 1.0) * 0.3

            discovery_bonus = 1.0 if skill_id not in used else 0.2
            score += discovery_bonus * 0.2

            score += self._PRIORITY_WEIGHTS.get(priority, 0.4) * 0.2

            for kw in matched_keywords:
                if kw in matched_domains:
                    score += 0.05

            score = min(score, 1.0)

            reason_parts = []
            if skill_id not in used and intent_overlap > 0:
                reason_parts.append("new skill for your workflow")
            elif skill_id not in used:
                reason_parts.append("undiscovered skill")
            if intent_overlap:
                reason_parts.append(f"{intent_overlap} keyword matches")
            reason = "; ".join(reason_parts) if reason_parts else "discovery suggestion"

            scored.append(
                Recommendation(
                    skill_id=skill_id,
                    namespace=namespace,
                    score=round(score, 4),
                    matched_keywords=matched_keywords,
                    intent=intent,
                    reason=reason,
                )
            )

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]
