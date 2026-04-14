"""Conflict resolution framework for skill routing.

When multiple skills match a query, we need a strategy to choose the best one.
This module provides a configurable framework for resolving such conflicts.

Usage:
    from vibesop.core.routing.conflict import ConflictResolver, PriorityStrategy

    resolver = ConflictResolver()
    resolver.add_strategy(PriorityStrategy())
    result = resolver.resolve(matches, query)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from vibesop.core.matching import MatchResult

logger = logging.getLogger(__name__)


class ConflictReason(Enum):
    """Reason why conflict occurred."""

    MULTIPLE_HIGH_CONFIDENCE = "multiple_high_confidence"
    SAME_NAMESPACE = "same_namespace"
    SAME_CLUSTER = "same_cluster"
    SIMILAR_INTENT = "similar_intent"


@dataclass
class ConflictResolution:
    """Result of conflict resolution."""

    primary: str | None
    """The winning skill ID."""

    alternatives: list[str]
    """Other skills that were considered."""

    reason: str
    """Explanation of the decision."""

    needs_review: bool = False
    """Whether this should be reviewed by the user."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional information about the resolution."""


class ResolutionStrategy(ABC):
    """Base class for conflict resolution strategies."""

    @abstractmethod
    def resolve(
        self,
        matches: list[MatchResult],
        _query: str,
        _context: dict[str, Any] | None = None,
    ) -> ConflictResolution | None:
        """Resolve conflicts among matched skills.

        Args:
            matches: List of matched skills
            query: Original user query
            context: Additional routing context

        Returns:
            ConflictResolution if this strategy can handle it, None otherwise
        """

    @abstractmethod
    def priority(self) -> int:
        """Priority of this strategy (higher = tried first).

        Returns:
            Priority value (0-100)
        """


class ConfidenceGapStrategy(ResolutionStrategy):
    """Resolve conflicts by looking for a clear confidence gap.

    If one skill has significantly higher confidence than others,
    it's automatically selected.
    """

    def __init__(self, gap_threshold: float = 0.15):
        """Initialize confidence gap strategy.

        Args:
            gap_threshold: Minimum gap between top two candidates
        """
        self.gap_threshold = gap_threshold

    def resolve(
        self,
        matches: list[MatchResult],
        query: str,
        context: dict[str, Any] | None = None,
    ) -> ConflictResolution | None:
        _ = query, context  # Protocol requirement
        if len(matches) < 2:
            return None

        sorted_matches = sorted(matches, key=lambda m: m.confidence, reverse=True)
        top = sorted_matches[0]
        second = sorted_matches[1]

        gap = top.confidence - second.confidence
        if gap >= self.gap_threshold:
            return ConflictResolution(
                primary=top.skill_id,
                alternatives=[m.skill_id for m in sorted_matches[1:]],
                reason=f"Clear confidence gap: {top.skill_id} ({top.confidence:.2f}) vs {second.skill_id} ({second.confidence:.2f})",
                needs_review=False,
                metadata={"gap": gap, "strategy": "confidence_gap"},
            )

        return None

    def priority(self) -> int:
        return 90


class NamespacePriorityStrategy(ResolutionStrategy):
    """Resolve conflicts by preferring certain namespaces.

    Project skills > external skills > built-in fallback.
    Any unknown namespace is treated as external (priority 80).
    """

    # Default namespace priorities
    DEFAULT_PRIORITIES: ClassVar[dict[str, int]] = {
        "project": 100,
        "builtin": 60,
    }

    def __init__(self, priorities: dict[str, int] | None = None):
        """Initialize namespace priority strategy.

        Args:
            priorities: Custom namespace priority mapping
        """
        self.priorities = {**self.DEFAULT_PRIORITIES, **(priorities or {})}

    def resolve(
        self,
        matches: list[MatchResult],
        _query: str,
        _context: dict[str, Any] | None = None,
    ) -> ConflictResolution | None:
        _ = _query, _context  # Protocol requirement
        if len(matches) < 2:
            return None

        # Group by namespace
        by_namespace: dict[str, list[MatchResult]] = {}
        for match in matches:
            namespace = str(match.metadata.get("namespace", "other"))
            if namespace not in by_namespace:
                by_namespace[namespace] = []
            by_namespace[namespace].append(match)

        # Find highest priority namespace (unknown namespaces default to external: 80)
        top_namespace = max(by_namespace.keys(), key=lambda ns: self.priorities.get(ns, 80))

        # If there's a clear priority winner, use it
        top_priority = self.priorities.get(top_namespace, 80)
        other_priorities = [self.priorities.get(ns, 80) for ns in by_namespace if ns != top_namespace]

        if top_priority > max(other_priorities, default=0) + 10:
            top_matches = by_namespace[top_namespace]
            best = max(top_matches, key=lambda m: m.confidence)
            return ConflictResolution(
                primary=best.skill_id,
                alternatives=[m.skill_id for m in matches if m.skill_id != best.skill_id],
                reason=f"Namespace priority: {top_namespace} ({top_priority}) > others",
                needs_review=False,
                metadata={"namespace": top_namespace, "priority": top_priority, "strategy": "namespace_priority"},
            )

        return None

    def priority(self) -> int:
        return 80


class RecencyStrategy(ResolutionStrategy):
    """Resolve conflicts by preferring recently used skills.

    This requires access to preference learning data.
    """

    def __init__(self, storage_path: str = ".vibe/preferences.json"):
        """Initialize recency strategy.

        Args:
            storage_path: Path to preferences file
        """
        self.storage_path = storage_path
        self._recent_skills: dict[str, float] | None = None

    def _load_recent_skills(self) -> dict[str, float]:
        """Load recently used skills with timestamps."""
        if self._recent_skills is not None:
            return self._recent_skills

        try:
            import json
            from pathlib import Path

            prefs_path = Path(self.storage_path)
            if not prefs_path.exists():
                self._recent_skills = {}
                return {}

            with prefs_path.open("r") as f:
                data = json.load(f)

            # Extract most recent selection for each skill
            recent: dict[str, float] = {}
            for skill_id, selections in data.get("selections", {}).items():
                if selections:
                    # Get most recent timestamp
                    recent[skill_id] = max(s.get("timestamp", 0) for s in selections)

            self._recent_skills = recent
            return recent
        except Exception as e:
            logger.debug(f"Failed to load recent skills from storage: {e}")
            self._recent_skills = {}
            return {}

    def resolve(
        self,
        matches: list[MatchResult],
        _query: str,
        _context: dict[str, Any] | None = None,
    ) -> ConflictResolution | None:
        if len(matches) < 2:
            return None

        recent = self._load_recent_skills()
        if not recent:
            return None

        # Filter to recently used skills
        recent_matches = [(m, recent.get(m.skill_id, 0)) for m in matches if m.skill_id in recent]

        if len(recent_matches) < 2:
            return None

        # Sort by recency (most recent first)
        recent_matches.sort(key=lambda x: x[1], reverse=True)
        top_match, top_time = recent_matches[0]

        # Only use if top was used recently (within 7 days)
        import time

        week_ago = time.time() - 7 * 24 * 3600
        if top_time > week_ago:
            return ConflictResolution(
                primary=top_match.skill_id,
                alternatives=[m.skill_id for m in matches if m.skill_id != top_match.skill_id],
                reason=f"Recently used: {top_match.skill_id} (used {int((time.time() - top_time) / 3600)}h ago)",
                needs_review=False,
                metadata={"last_used": top_time, "strategy": "recency"},
            )

        return None

    def priority(self) -> int:
        return 70


class ExplicitOverrideStrategy(ResolutionStrategy):
    """Check for explicit user override in query.

    Patterns like "/review" or "use tdd" indicate explicit choice.
    """

    OVERRIDE_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"^/(\w+(?:/\w+)*)$", "slash"),  # /review, /gstack/review
        (r"^(?:use|using|调用)\s+(\w+(?:/\w+)*)", "use"),  # use tdd
        (r"^(?:run|execute)\s+(\w+(?:/\w+)*)", "run"),  # run review
    ]

    def resolve(
        self,
        matches: list[MatchResult],
        query: str,
        _context: dict[str, Any] | None = None,
    ) -> ConflictResolution | None:
        import re

        query_lower = query.lower().strip()

        for pattern, pattern_type in self.OVERRIDE_PATTERNS:
            match = re.match(pattern, query_lower)
            if match:
                requested_skill = match.group(1)
                # Find if requested skill is in matches
                for m in matches:
                    if m.skill_id == requested_skill or m.skill_id.endswith(requested_skill):
                        return ConflictResolution(
                            primary=m.skill_id,
                            alternatives=[m2.skill_id for m2 in matches if m2.skill_id != m.skill_id],
                            reason=f"Explicit override: {pattern_type} pattern matched",
                            needs_review=False,
                            metadata={"override_type": pattern_type, "strategy": "explicit_override"},
                        )

        return None

    def priority(self) -> int:
        return 100  # Highest priority - user explicitly asked


class FallbackStrategy(ResolutionStrategy):
    """Fallback strategy: use highest confidence.

    This is always tried last if no other strategy applies.
    """

    def resolve(
        self,
        matches: list[MatchResult],
        _query: str,
        _context: dict[str, Any] | None = None,
    ) -> ConflictResolution | None:
        if not matches:
            return ConflictResolution(
                primary=None,
                alternatives=[],
                reason="No matches found",
                needs_review=False,
                metadata={"strategy": "fallback"},
            )

        sorted_matches = sorted(matches, key=lambda m: m.confidence, reverse=True)
        top = sorted_matches[0]

        # Check if it's a close call
        needs_review = len(sorted_matches) >= 2 and abs(top.confidence - sorted_matches[1].confidence) < 0.1

        return ConflictResolution(
            primary=top.skill_id,
            alternatives=[m.skill_id for m in sorted_matches[1:]],
            reason=f"Highest confidence: {top.confidence:.2f}",
            needs_review=needs_review,
            metadata={"strategy": "fallback"},
        )

    def priority(self) -> int:
        return 0  # Lowest priority - always works


class ConflictResolver:
    """Main conflict resolver using multiple strategies.

    Strategies are tried in priority order. First strategy to return
    a resolution wins.
    """

    def __init__(self):
        """Initialize conflict resolver with default strategies."""
        self._strategies: list[ResolutionStrategy] = []
        self._setup_default_strategies()

    def _setup_default_strategies(self) -> None:
        """Set up default resolution strategies in priority order."""
        self.add_strategy(ExplicitOverrideStrategy())
        self.add_strategy(ConfidenceGapStrategy())
        self.add_strategy(NamespacePriorityStrategy())
        self.add_strategy(RecencyStrategy())
        self.add_strategy(FallbackStrategy())

    def add_strategy(self, strategy: ResolutionStrategy) -> None:
        """Add a resolution strategy.

        Strategies are tried in priority order (highest priority first).

        Args:
            strategy: Strategy to add
        """
        self._strategies.append(strategy)
        self._strategies.sort(key=lambda s: s.priority(), reverse=True)

    def resolve(
        self,
        matches: list[MatchResult],
        query: str,
        context: dict[str, Any] | None = None,
    ) -> ConflictResolution:
        """Resolve conflicts among matched skills.

        Args:
            matches: List of matched skills
            query: Original user query
            context: Additional routing context

        Returns:
            Conflict resolution result
        """
        if not matches:
            return ConflictResolution(
                primary=None,
                alternatives=[],
                reason="No matches to resolve",
                needs_review=False,
            )

        # Try each strategy in priority order
        for strategy in self._strategies:
            result = strategy.resolve(matches, query, context)
            if result is not None:
                return result

        # Should never reach here due to FallbackStrategy
        return ConflictResolution(
            primary=matches[0].skill_id,
            alternatives=[m.skill_id for m in matches[1:]],
            reason="Default (no strategy matched)",
            needs_review=True,
        )


__all__ = [
    "ConfidenceGapStrategy",
    "ConflictReason",
    "ConflictResolution",
    "ConflictResolver",
    "ExplicitOverrideStrategy",
    "FallbackStrategy",
    "NamespacePriorityStrategy",
    "RecencyStrategy",
    "ResolutionStrategy",
]
