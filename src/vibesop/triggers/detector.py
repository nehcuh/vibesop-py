"""Keyword detection engine for pattern matching.

This module provides the core detection logic for matching user input
against trigger patterns using multiple strategies.
"""

import re
from typing import Optional
from vibesop.triggers.models import TriggerPattern, PatternMatch
from vibesop.triggers.utils import (
    tokenize,
    calculate_tfidf,
    cosine_similarity,
    calculate_keyword_match_score,
    calculate_regex_match_score,
    calculate_combined_score,
)


class KeywordDetector:
    """Detect user intent from natural language input.

    Uses multi-strategy matching:
    1. Rule-based patterns (regex, keywords)
    2. TF-IDF vector similarity
    3. Confidence scoring

    Attributes:
        patterns: List of trigger patterns to match against
        confidence_threshold: Default minimum confidence for matches
        idf_cache: Pre-computed IDF scores for all patterns

    Example:
        >>> detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        >>> match = detector.detect_best("扫描安全漏洞")
        >>> print(match.pattern_id)  # "security/scan"
        >>> print(match.confidence)  # 0.95
    """

    def __init__(
        self,
        patterns: list[TriggerPattern],
        confidence_threshold: float = 0.6
    ):
        """Initialize keyword detector.

        Args:
            patterns: List of trigger patterns
            confidence_threshold: Default minimum confidence threshold
        """
        self.patterns = sorted(
            patterns,
            key=lambda p: p.priority,
            reverse=True
        )
        self.confidence_threshold = confidence_threshold

        # Pre-compute IDF scores for all pattern examples
        self.idf_cache = self._build_idf_cache()

    def _build_idf_cache(self) -> dict[str, float]:
        """Build IDF cache from all pattern examples and keywords.

        Returns:
            Dictionary mapping term to IDF score
        """
        from vibesop.triggers.utils import calculate_idf

        # Collect all text from patterns
        documents = []

        for pattern in self.patterns:
            # Add keywords as a document
            if pattern.keywords:
                documents.append(pattern.keywords)

            # Add examples as documents
            for example in pattern.examples:
                documents.append(tokenize(example))

        return calculate_idf(documents)

    def detect_best(
        self,
        query: str,
        min_confidence: Optional[float] = None
    ) -> Optional[PatternMatch]:
        """Detect best matching pattern for query.

        Args:
            query: User input query
            min_confidence: Minimum confidence threshold (uses default if None)

        Returns:
            PatternMatch with best match, or None if no match meets threshold
        """
        if not query or not query.strip():
            return None

        threshold = min_confidence or self.confidence_threshold

        # Score all patterns
        matches = []
        for pattern in self.patterns:
            match = self._score_pattern(query, pattern)
            if match and match.confidence >= pattern.confidence_threshold:
                matches.append(match)

        if not matches:
            return None

        # Return highest confidence match
        best_match = max(matches, key=lambda m: m.confidence)

        # Check against overall threshold
        if best_match.confidence >= threshold:
            return best_match

        return None

    def detect_all(
        self,
        query: str,
        min_confidence: Optional[float] = None
    ) -> list[PatternMatch]:
        """Detect all matching patterns for query.

        Args:
            query: User input query
            min_confidence: Minimum confidence threshold

        Returns:
            List of PatternMatch objects, sorted by confidence (descending)
        """
        if not query or not query.strip():
            return []

        threshold = min_confidence or self.confidence_threshold

        # Score all patterns
        matches = []
        for pattern in self.patterns:
            match = self._score_pattern(query, pattern)
            if match and match.confidence >= threshold:
                matches.append(match)

        # Sort by confidence (descending)
        matches.sort(key=lambda m: m.confidence, reverse=True)

        return matches

    def _score_pattern(
        self,
        query: str,
        pattern: TriggerPattern
    ) -> Optional[PatternMatch]:
        """Score a single pattern against the query.

        Calculates combined confidence using:
        - Keyword matching (40%)
        - Regex matching (30%)
        - Semantic similarity (30%)

        Args:
            query: User input query
            pattern: Pattern to score

        Returns:
            PatternMatch with confidence score, or None if no match
        """
        # Calculate keyword score
        keyword_score = calculate_keyword_match_score(
            query,
            pattern.keywords
        )

        # Calculate regex score
        regex_score = calculate_regex_match_score(
            query,
            pattern.regex_patterns
        )

        # Calculate semantic score
        semantic_score = self._calculate_semantic_score(
            query,
            pattern
        )

        # Calculate combined score
        combined_score = calculate_combined_score(
            keyword_score,
            regex_score,
            semantic_score
        )

        # If combined score is very low, no match
        if combined_score < 0.1:
            return None

        # Collect matched keywords
        matched_keywords = [
            kw for kw in pattern.keywords
            if kw.lower() in query.lower()
        ]

        # Collect matched regex
        matched_regex = [
            pattern_str for pattern_str in pattern.regex_patterns
            if _regex_matches(pattern_str, query)
        ]

        return PatternMatch(
            pattern_id=pattern.pattern_id,
            confidence=combined_score,
            metadata={
                "category": pattern.category,
                "name": pattern.name,
                "keyword_score": keyword_score,
                "regex_score": regex_score,
            },
            matched_keywords=matched_keywords,
            matched_regex=matched_regex,
            semantic_score=semantic_score
        )

    def _calculate_semantic_score(
        self,
        query: str,
        pattern: TriggerPattern
    ) -> float:
        """Calculate semantic similarity score using TF-IDF.

        Compares query against pattern examples using TF-IDF + cosine similarity.

        Args:
            query: User input query
            pattern: Pattern to compare against

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not pattern.examples:
            return 0.0

        # Tokenize query
        query_tokens = tokenize(query)
        query_tfidf = calculate_tfidf(query_tokens, self.idf_cache)

        # Calculate similarity with each example
        similarities = []
        for example in pattern.examples:
            example_tokens = tokenize(example)
            example_tfidf = calculate_tfidf(example_tokens, self.idf_cache)

            sim = cosine_similarity(query_tfidf, example_tfidf)
            similarities.append(sim)

        # Return maximum similarity, clamped to [0, 1]
        max_sim = max(similarities) if similarities else 0.0
        return min(max(max_sim, 0.0), 1.0)


def _regex_matches(pattern: str, text: str) -> bool:
    """Check if regex pattern matches text.

    Args:
        pattern: Regex pattern string
        text: Text to match against

    Returns:
        True if pattern matches text
    """
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        # Invalid regex pattern
        return False
