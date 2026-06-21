"""Per-skill recommendation engine based on query patterns and candidate similarity."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, ClassVar

from vibesop.core.orchestration.patterns import INTENT_DOMAIN_KEYWORDS


@dataclass
class Recommendation:
    skill_id: str
    namespace: str
    score: float
    matched_keywords: list[str] = field(default_factory=list)
    intent: str = ""
    reason: str = ""


class SkillRecommender:
    _PRIORITY_WEIGHTS: ClassVar[dict[str, float]] = {"P0": 1.0, "P1": 0.7, "P2": 0.4}

    def __init__(self) -> None:
        self._keyword_index: dict[str, set[str]] = {}
        for domain, keywords in INTENT_DOMAIN_KEYWORDS.items():
            for kw in keywords:
                self._keyword_index.setdefault(kw.lower(), set()).add(domain)

    def _match_domains(self, text: str) -> Counter[str]:
        lower = text.lower()
        return Counter(
            domain
            for kw, domains in self._keyword_index.items()
            if kw in lower
            for domain in domains
        )

    def _intent_overlap(self, intent_lower: str) -> list[str]:
        return [kw for kw in self._keyword_index if kw in intent_lower]

    def _trigger_hits(self, triggers: list[Any], query_lower: str) -> int:
        return sum(1 for t in triggers if t in query_lower)

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
        matched_domains = self._match_domains(query)
        ns_counts: dict[str, int] = {}
        scored: list[Recommendation] = []

        for c in candidates:
            namespace = str(c.get("namespace", "builtin"))
            if namespace in exclude:
                continue
            skill_id = str(c.get("id", ""))
            intent_lower = str(c.get("intent", "")).lower()
            triggers = c.get("triggers", [])
            priority = str(c.get("priority", "P2"))

            intent_kw = self._intent_overlap(intent_lower)
            th = self._trigger_hits(triggers, query_lower)
            score = min(len(intent_kw) / max(len(self._keyword_index) * 0.1, 1), 1.0) * 0.4
            score += min(th / max(len(triggers) * 0.3, 1), 1.0) * 0.3
            score += self._PRIORITY_WEIGHTS.get(priority, 0.4) * 0.2
            score += max(0, (1.0 - ns_counts.get(namespace, 0) * 0.3)) * 0.1
            for kw in intent_kw:
                if kw in matched_domains:
                    score += 0.05

            ns_counts[namespace] = ns_counts.get(namespace, 0) + 1
            reason_parts = []
            if intent_kw:
                reason_parts.append(f"{len(intent_kw)} intent keyword matches")
            if th:
                reason_parts.append(f"{th} trigger hits")

            scored.append(
                Recommendation(
                    skill_id=skill_id,
                    namespace=namespace,
                    score=round(min(score, 1.0), 4),
                    matched_keywords=intent_kw,
                    intent=str(c.get("intent", "")),
                    reason="; ".join(reason_parts) if reason_parts else "priority-based match",
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
        if not candidates:
            return []
        used = used_skill_ids or set()
        query_lower = query.lower()
        matched_domains = self._match_domains(query)
        scored: list[Recommendation] = []

        for c in candidates:
            skill_id = str(c.get("id", ""))
            namespace = str(c.get("namespace", "builtin"))
            intent_lower = str(c.get("intent", "")).lower()
            triggers = c.get("triggers", [])
            priority = str(c.get("priority", "P2"))

            intent_kw = self._intent_overlap(intent_lower)
            th = self._trigger_hits(triggers, query_lower)
            score = min(len(intent_kw) / max(len(self._keyword_index) * 0.1, 1), 1.0) * 0.3
            score += min(th / max(len(triggers) * 0.3, 1), 1.0) * 0.3
            score += (1.0 if skill_id not in used else 0.2) * 0.2
            score += self._PRIORITY_WEIGHTS.get(priority, 0.4) * 0.2
            for kw in intent_kw:
                if kw in matched_domains:
                    score += 0.05

            reason_parts = []
            if skill_id not in used and intent_kw:
                reason_parts.append("new skill for your workflow")
            elif skill_id not in used:
                reason_parts.append("undiscovered skill")
            if intent_kw:
                reason_parts.append(f"{len(intent_kw)} keyword matches")

            scored.append(
                Recommendation(
                    skill_id=skill_id,
                    namespace=namespace,
                    score=round(min(score, 1.0), 4),
                    matched_keywords=intent_kw,
                    intent=str(c.get("intent", "")),
                    reason="; ".join(reason_parts) if reason_parts else "discovery suggestion",
                )
            )

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]
