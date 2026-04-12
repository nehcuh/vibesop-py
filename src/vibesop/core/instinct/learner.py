"""Instinct learning system for pattern extraction.

This module implements learning from experience:
- Extract patterns from successful/unsuccessful attempts
- Build instincts (rules of thumb)
- Improve routing and decision-making over time
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Instinct:
    """A learned pattern or rule of thumb.

    Attributes:
        id: Unique identifier
        pattern: The pattern description (what to look for)
        action: Recommended action when pattern matches
        context: When this instinct applies
        confidence: How confident we are (0-1, based on evidence)
        success_count: Number of successful applications
        failure_count: Number of failed applications
        last_used: When this instinct was last applied
        created_at: When this instinct was created
        source: Where this instinct came from (experiment, manual, etc.)
        tags: Categories for this instinct
    """

    id: str
    pattern: str
    action: str
    context: str = ""
    confidence: float = 0.5
    success_count: int = 0
    failure_count: int = 0
    last_used: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)
    source: str = "extracted"
    tags: list[str] = field(default_factory=list)

    @property
    def total_applications(self) -> int:
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        if self.total_applications == 0:
            return 0.5
        return self.success_count / self.total_applications

    @property
    def is_reliable(self) -> bool:
        """Whether this instinct is reliable enough to use."""
        return self.total_applications >= 3 and self.success_rate >= 0.6 and self.confidence >= 0.5

    def update(self, success: bool) -> None:
        """Update instinct based on new evidence."""
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        # Update confidence based on success rate and sample size
        # Use Wilson score interval for better small-sample behavior
        n = self.total_applications
        if n > 0:
            p = self.success_rate
            z = 1.96  # 95% confidence
            denominator = 1 + z**2 / n
            center = (p + z**2 / (2 * n)) / denominator
            self.confidence = center

        self.last_used = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pattern": self.pattern,
            "action": self.action,
            "context": self.context,
            "confidence": self.confidence,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "created_at": self.created_at.isoformat(),
            "source": self.source,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Instinct:
        return cls(
            id=data["id"],
            pattern=data["pattern"],
            action=data["action"],
            context=data.get("context", ""),
            confidence=data.get("confidence", 0.5),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            last_used=datetime.fromisoformat(data["last_used"]) if data.get("last_used") else None,
            created_at=datetime.fromisoformat(data["created_at"]),
            source=data.get("source", "extracted"),
            tags=data.get("tags", []),
        )


class InstinctLearner:
    """Learn and manage instincts from experience.

    This is the core of the "Memory > Intelligence" principle.
    Instead of trying to be smart every time, we remember what worked.
    """

    def __init__(self, storage_path: Path | None = None):
        """Initialize the instinct learner.

        Args:
            storage_path: Path to store instincts (default: .vibe/instincts.jsonl)
        """
        self.storage_path = storage_path or Path(".vibe/instincts.jsonl")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self._instincts: dict[str, Instinct] = {}
        self._load()

    def _load(self) -> None:
        """Load instincts from storage."""
        if not self.storage_path.exists():
            return

        with self.storage_path.open() as f:
            for raw_line in f:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    instinct = Instinct.from_dict(data)
                    self._instincts[instinct.id] = instinct
                except (json.JSONDecodeError, KeyError):
                    continue

    def _save(self) -> None:
        """Save instincts to storage."""
        with self.storage_path.open("w") as f:
            for instinct in self._instincts.values():
                f.write(json.dumps(instinct.to_dict()) + "\n")

    def learn(
        self,
        pattern: str,
        action: str,
        context: str = "",
        tags: list[str] | None = None,
        source: str = "manual",
    ) -> Instinct:
        """Learn a new instinct.

        Args:
            pattern: What to look for (e.g., "user asks about debugging")
            action: What to do (e.g., "suggest systematic-debugging skill")
            context: When this applies (e.g., "error handling scenarios")
            tags: Categories (e.g., ["routing", "debugging"])
            source: Where this came from

        Returns:
            The learned instinct
        """
        # Generate ID from pattern
        instinct_id = self._generate_id(pattern)

        # Check if already exists
        if instinct_id in self._instincts:
            instinct = self._instincts[instinct_id]
            # Update if action changed
            if instinct.action != action:
                instinct.action = action
                instinct.confidence = 0.5  # Reset confidence
        else:
            instinct = Instinct(
                id=instinct_id,
                pattern=pattern,
                action=action,
                context=context,
                source=source,
                tags=tags or [],
            )
            self._instincts[instinct_id] = instinct

        self._save()
        return instinct

    def record_outcome(self, instinct_id: str, success: bool) -> None:
        """Record whether an instinct led to success.

        Args:
            instinct_id: ID of the instinct
            success: Whether following the instinct worked
        """
        if instinct_id not in self._instincts:
            return

        self._instincts[instinct_id].update(success)
        self._save()

    def find_matching(
        self,
        query: str,
        context: str = "",
        min_confidence: float = 0.5,
    ) -> list[Instinct]:
        """Find instincts that match a query.

        Args:
            query: The query to match against
            context: Additional context
            min_confidence: Minimum confidence threshold

        Returns:
            List of matching instincts, sorted by relevance
        """
        matches = []

        for instinct in self._instincts.values():
            # Skip unreliable instincts
            if not instinct.is_reliable or instinct.confidence < min_confidence:
                continue

            # Check if pattern matches query
            score = self._match_score(instinct.pattern, query)

            # Boost score for context match
            if context and instinct.context:
                context_score = self._match_score(instinct.context, context)
                score = max(score, context_score * 0.8)

            if score > 0.3:  # Threshold for match
                matches.append((instinct, score))

        # Sort by score (descending)
        matches.sort(key=lambda x: x[1], reverse=True)

        return [instinct for instinct, _ in matches]

    def get_reliable_instincts(self, tag: str | None = None) -> list[Instinct]:
        """Get all reliable instincts.

        Args:
            tag: Optional tag filter

        Returns:
            List of reliable instincts
        """
        instincts = [i for i in self._instincts.values() if i.is_reliable]

        if tag:
            instincts = [i for i in instincts if tag in i.tags]

        # Sort by confidence
        instincts.sort(key=lambda i: i.confidence, reverse=True)

        return instincts

    def extract_from_experiment(
        self,
        hypothesis: str,
        outcome: str,
        was_successful: bool,
    ) -> Instinct | None:
        """Extract an instinct from an experiment result.

        This is the key autoresearch feature - turning experiments into learnings.

        Args:
            hypothesis: The hypothesis that was tested
            outcome: What happened
            was_successful: Whether it worked

        Returns:
            Extracted instinct or None
        """
        # Simple extraction: hypothesis -> pattern, outcome -> action
        # In a more sophisticated version, this would use NLP

        pattern = hypothesis.lower()
        action = outcome if was_successful else f"Avoid: {outcome}"

        instinct = self.learn(
            pattern=pattern,
            action=action,
            context="extracted_from_experiment",
            tags=["autoresearch"],
            source="experiment",
        )

        # Record the outcome
        self.record_outcome(instinct.id, was_successful)

        return instinct

    def _generate_id(self, pattern: str) -> str:
        """Generate a stable ID from pattern."""
        import hashlib

        # Normalize and hash
        normalized = re.sub(r"\s+", " ", pattern.lower().strip())
        hash_obj = hashlib.md5(normalized.encode())
        return f"instinct_{hash_obj.hexdigest()[:12]}"

    def _match_score(self, pattern: str, text: str) -> float:
        """Calculate match score between pattern and text.

        Uses a hybrid of Jaccard similarity and containment with bigram overlap,
        plus proper CJK tokenization via the project's tokenizer.
        """
        from vibesop.core.matching.tokenizers import tokenize

        pattern_tokens = tokenize(pattern)
        text_tokens = tokenize(text)

        pattern_words = set(pattern_tokens)
        text_words = set(text_tokens)

        if not pattern_words:
            return 0.0

        # Jaccard similarity
        intersection = pattern_words & text_words
        union = pattern_words | text_words
        jaccard = len(intersection) / len(union) if union else 0.0

        # Containment: how much of the pattern is found in the text
        containment = len(intersection) / len(pattern_words) if pattern_words else 0.0

        # Bigram overlap for phrase-level matching
        def _bigrams(tokens: list[str]) -> set[str]:
            return {f"{tokens[i]} {tokens[i + 1]}" for i in range(len(tokens) - 1)}

        pattern_bigrams = _bigrams(pattern_tokens)
        text_bigrams = _bigrams(text_tokens)
        if pattern_bigrams:
            bigram_overlap = len(pattern_bigrams & text_bigrams) / len(pattern_bigrams)
        else:
            bigram_overlap = 0.0

        # Weighted combination: containment matters more than Jaccard for short queries
        return 0.4 * jaccard + 0.4 * containment + 0.2 * bigram_overlap

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about instincts."""
        total = len(self._instincts)
        reliable = sum(1 for i in self._instincts.values() if i.is_reliable)

        by_source: dict[str, int] = {}
        for instinct in self._instincts.values():
            source = instinct.source
            by_source[source] = by_source.get(source, 0) + 1

        return {
            "total_instincts": total,
            "reliable_instincts": reliable,
            "by_source": by_source,
            "avg_confidence": sum(i.confidence for i in self._instincts.values()) / total
            if total > 0
            else 0,
        }

    def export_for_routing(self) -> list[dict[str, Any]]:
        """Export instincts in format suitable for routing."""
        return [
            {
                "id": i.id,
                "pattern": i.pattern,
                "action": i.action,
                "confidence": i.confidence,
                "success_rate": i.success_rate,
            }
            for i in self.get_reliable_instincts()
        ]


# Convenience functions


def learn_instinct(
    pattern: str,
    action: str,
    storage_path: Path | None = None,
    **kwargs,
) -> Instinct:
    """Convenience function to learn a single instinct.

    Example:
        learn_instinct(
            pattern="user asks about debugging",
            action="suggest systematic-debugging skill",
            tags=["routing", "debugging"],
        )
    """
    learner = InstinctLearner(storage_path)
    return learner.learn(pattern, action, **kwargs)


def get_routing_suggestion(
    query: str,
    storage_path: Path | None = None,
) -> str | None:
    """Get routing suggestion based on learned instincts.

    Example:
        suggestion = get_routing_suggestion("help me debug this error")
        # Returns: "suggest systematic-debugging skill" if learned
    """
    learner = InstinctLearner(storage_path)
    matches = learner.find_matching(query)

    if matches:
        return matches[0].action

    return None
