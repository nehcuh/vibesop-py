"""Multi-intent detection for orchestration.

Uses a two-phase approach:
1. Heuristic filter (zero LLM cost) — fast path for obvious single-intent queries
2. LLM confirmation — only when heuristic signals multi-intent candidate
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vibesop.core.orchestration.patterns import (
    INTENT_DOMAINS,
    MULTI_INTENT_REGEX,
)

if TYPE_CHECKING:
    from vibesop.core.models import RoutingResult

logger = logging.getLogger(__name__)

_KEYWORD_PATTERN = MULTI_INTENT_REGEX
_INTENT_DOMAINS = INTENT_DOMAINS


class MultiIntentDetector:
    """Detects whether a query contains multiple distinct intents.

    Two-phase detection:
    1. Heuristic: fast, zero-LLM-cost filtering
    2. LLM confirmation: lightweight yes/no confirmation (only if heuristic passes)
    """

    def __init__(
        self,
        min_query_length: int = 20,
        low_confidence_threshold: float = 0.8,
        alternative_threshold: float = 0.6,
        confidence_gap_threshold: float = 0.15,
    ):
        self.min_query_length = min_query_length
        self.low_confidence_threshold = low_confidence_threshold
        self.alternative_threshold = alternative_threshold
        self.confidence_gap_threshold = confidence_gap_threshold

    def should_decompose(
        self,
        query: str,
        single_result: RoutingResult,
    ) -> bool:
        """Determine if a query should be decomposed into multiple sub-tasks.

        Returns True only if BOTH heuristic and (optional) LLM confirm multi-intent.
        """
        # Phase 1: Heuristic filter
        heuristic_pass = self._heuristic_check(query, single_result)
        if not heuristic_pass:
            logger.debug("Heuristic rejected multi-intent for query: %s", query[:50])
            return False

        # Phase 2: LLM confirmation (optional, can be skipped for speed)
        # For v1, heuristic is sufficient. LLM confirmation can be added later
        # to reduce false positives without adding latency to every query.
        logger.debug("Heuristic passed multi-intent for query: %s", query[:50])
        return True

    def _heuristic_check(self, query: str, single_result: RoutingResult) -> bool:
        """Fast heuristic check for multi-intent candidates.

        Returns True if ANY of the following conditions match:
        - Query contains multi-intent conjunctions AND is long enough AND spans >= 2 intent domains
        - Single-skill confidence is low AND top alternatives are strong
        - Top two alternatives have close confidence scores
        """
        # Condition 1: Conjunction-based (requires >= 2 intent domains to reduce false positives)
        if len(query) >= self.min_query_length and self._has_conjunctions(query):
            intent_domains = self._count_intent_domains(query)
            if intent_domains >= 2:
                return True

        # Condition 1b: Multiple intent domains detected (even without conjunctions)
        intent_domains = self._count_intent_domains(query)
        if intent_domains >= 2 and len(query) >= self.min_query_length:
            return True

        if single_result.primary is None:
            # No match at all — might be a complex multi-part request
            return len(query) >= self.min_query_length * 2

        primary_conf = single_result.primary.confidence

        # Condition 2: Low confidence with strong alternatives
        if primary_conf < self.low_confidence_threshold:
            strong_alts = [
                alt for alt in single_result.alternatives
                if alt.confidence >= self.alternative_threshold
            ]
            if len(strong_alts) >= 2:
                return True

        # Condition 3: Close confidence gap between top candidates
        if len(single_result.alternatives) >= 1:
            top_alt = single_result.alternatives[0]
            gap = primary_conf - top_alt.confidence
            if gap < self.confidence_gap_threshold and top_alt.confidence >= self.alternative_threshold:
                return True

        return False

    def _has_conjunctions(self, query: str) -> bool:
        """Check if query contains multi-intent conjunctions."""
        return bool(_KEYWORD_PATTERN.search(query))

    def _count_intent_domains(self, query: str) -> int:
        """Count how many distinct intent domains appear in the query."""
        query_lower = query.lower()
        domains_found = 0
        for _domain, keywords in _INTENT_DOMAINS:
            if any(kw in query_lower for kw in keywords):
                domains_found += 1
        return domains_found
