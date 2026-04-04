"""Semantic matching strategies for pattern detection.

This module implements different strategies for semantic pattern matching,
including pure cosine similarity and hybrid approaches.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TYPE_CHECKING

import numpy as np

from vibesop.semantic.models import SemanticMatch, SemanticMethod

if TYPE_CHECKING:
    from vibesop.semantic.cache import VectorCache
    from vibesop.semantic.encoder import SemanticEncoder
    from vibesop.semantic.similarity import SimilarityCalculator

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


class MatchingStrategy:
    """Base class for semantic matching strategies."""

    def match(
        self,
        query: str,
        patterns: list,
    ) -> list[SemanticMatch]:
        """Execute matching strategy.

        Args:
            query: User query text.
            patterns: List of patterns to match against.

        Returns:
            List of SemanticMatch results, sorted by confidence.
        """
        raise NotImplementedError


class CosineSimilarityStrategy(MatchingStrategy):
    """Pure cosine similarity matching strategy.

    This strategy uses only semantic similarity (cosine similarity) for
    matching, without considering traditional keyword or regex matching.

    Example:
        >>> strategy = CosineSimilarityStrategy(encoder, cache, threshold=0.7)
        >>> matches = strategy.match("scan for vulnerabilities", patterns)
        >>> matches[0].pattern_id
        'security/scan'
    """

    def __init__(
        self,
        encoder: SemanticEncoder,
        cache: VectorCache,
        threshold: float = 0.7,
    ):
        """Initialize cosine similarity strategy.

        Args:
            encoder: Semantic encoder for computing query vector.
            cache: Vector cache for pattern vectors.
            threshold: Minimum similarity threshold.
        """
        self.encoder = encoder
        self.cache = cache
        self.threshold = threshold

    def match(
        self,
        query: str,
        patterns: list,
    ) -> list[SemanticMatch]:
        """Match query against patterns using cosine similarity.

        Args:
            query: User query text.
            patterns: List of SemanticPattern instances.

        Returns:
            List of SemanticMatch results, sorted by confidence.
        """
        import time

        # Encode query
        start = time.time()
        query_vector = self.encoder.encode_query(query, normalize=True)
        encoding_time = time.time() - start

        # Collect pattern vectors
        pattern_ids = []
        pattern_vectors = []

        for pattern in patterns:
            vector = self.cache.get_or_compute(pattern.pattern_id, pattern.examples)
            pattern_ids.append(pattern.pattern_id)
            pattern_vectors.append(vector)

        # Calculate similarities
        pattern_vectors_array = np.array(pattern_vectors)

        # Cosine similarity (vectors are already normalized)
        similarities = np.dot(pattern_vectors_array, query_vector)

        # Create matches
        matches = []
        for pattern_id, similarity in zip(pattern_ids, similarities):
            # Filter by threshold
            if similarity >= self.threshold:
                match = SemanticMatch(
                    pattern_id=pattern_id,
                    confidence=similarity,
                    semantic_score=similarity,
                    semantic_method=SemanticMethod.COSINE,
                    vector_similarity=similarity,
                    model_used=self.encoder.model_name,
                    encoding_time=encoding_time,
                )
                matches.append(match)

        # Sort by confidence (descending)
        matches.sort(key=lambda m: m.confidence, reverse=True)

        return matches


class HybridMatchingStrategy(MatchingStrategy):
    """Hybrid matching strategy combining traditional and semantic methods.

    This strategy combines keyword matching, regex matching, and semantic
    matching to provide accurate and robust pattern detection.

    The strategy works in two stages:
    1. Fast filter: Use keyword/regex to quickly filter candidates
    2. Semantic refine: Use semantic similarity to rank and refine candidates

    Score fusion:
    - If traditional score > 0.8: keep traditional score (high confidence)
    - If semantic score > 0.8: use semantic score (strong signal)
    - Otherwise: weighted average of traditional and semantic

    Example:
        >>> strategy = HybridMatchingStrategy(
        ...     encoder, cache,
        ...     keyword_weight=0.3,
        ...     semantic_weight=0.5,
        ... )
        >>> matches = strategy.match("scan for vulnerabilities", patterns)
    """

    def __init__(
        self,
        encoder: SemanticEncoder,
        cache: VectorCache,
        keyword_weight: float = 0.3,
        regex_weight: float = 0.2,
        semantic_weight: float = 0.5,
        threshold: float = 0.7,
    ):
        """Initialize hybrid matching strategy.

        Args:
            encoder: Semantic encoder for computing query vector.
            cache: Vector cache for pattern vectors.
            keyword_weight: Weight for keyword matching (0-1).
            regex_weight: Weight for regex matching (0-1).
            semantic_weight: Weight for semantic matching (0-1).
            threshold: Minimum confidence threshold.

        Raises:
            ValueError: If weights don't sum to 1.0.
        """
        total = keyword_weight + regex_weight + semantic_weight
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total:.2f}")

        self.encoder = encoder
        self.cache = cache
        self.keyword_weight = keyword_weight
        self.regex_weight = regex_weight
        self.semantic_weight = semantic_weight
        self.threshold = threshold

    def match(
        self,
        query: str,
        patterns: list,
    ) -> list[SemanticMatch]:
        """Match query against patterns using hybrid strategy.

        Args:
            query: User query text.
            patterns: List of SemanticPattern instances.

        Returns:
            List of SemanticMatch results, sorted by confidence.
        """
        import time

        # Stage 1: Compute semantic similarities for all patterns
        start = time.time()
        query_vector = self.encoder.encode_query(query, normalize=True)
        encoding_time = time.time() - start

        # Collect pattern vectors and compute semantic scores
        pattern_data = []

        for pattern in patterns:
            vector = self.cache.get_or_compute(pattern.pattern_id, pattern.examples)

            # Cosine similarity
            similarity = float(np.dot(query_vector, vector))

            pattern_data.append({
                "pattern_id": pattern.pattern_id,
                "semantic_score": similarity,
                "examples": pattern.examples,
            })

        # Stage 2: Compute traditional scores (keyword + regex)
        for data in pattern_data:
            keyword_score = self._calculate_keyword_score(query, data["examples"])
            regex_score = self._calculate_regex_score(query, data["examples"])

            # Combine traditional scores
            traditional_score = (
                keyword_score * self.keyword_weight +
                regex_score * self.regex_weight
            ) / (self.keyword_weight + self.regex_weight)

            data["keyword_score"] = keyword_score
            data["regex_score"] = regex_score
            data["traditional_score"] = traditional_score

        # Stage 3: Fuse traditional and semantic scores
        matches = []

        for data in pattern_data:
            traditional_score = data["traditional_score"]
            semantic_score = data["semantic_score"]

            # Fusion strategy
            if traditional_score > 0.8:
                # High traditional confidence, keep it
                final_score = traditional_score
            elif semantic_score > 0.8:
                # High semantic confidence, use it
                final_score = semantic_score
            else:
                # Weighted average
                final_score = (
                    traditional_score * (self.keyword_weight + self.regex_weight) +
                    semantic_score * self.semantic_weight
                )

            # Filter by threshold
            if final_score >= self.threshold:
                match = SemanticMatch(
                    pattern_id=data["pattern_id"],
                    confidence=final_score,
                    semantic_score=semantic_score,
                    semantic_method=SemanticMethod.HYBRID,
                    vector_similarity=semantic_score,
                    model_used=self.encoder.model_name,
                    encoding_time=encoding_time,
                )
                matches.append(match)

        # Sort by confidence (descending)
        matches.sort(key=lambda m: m.confidence, reverse=True)

        return matches

    def _calculate_keyword_score(
        self,
        query: str,
        examples: list[str],
    ) -> float:
        """Calculate keyword matching score.

        Args:
            query: User query.
            examples: Example texts for the pattern.

        Returns:
            Keyword score in range [0, 1].
        """
        if not examples:
            return 0.0

        query_lower = query.lower()
        matched = 0

        for example in examples:
            example_lower = example.lower()
            # Check if any word from example appears in query
            words = example_lower.split()
            for word in words:
                if word in query_lower:
                    matched += 1
                    break

        if matched == 0:
            return 0.0

        # Lenient scoring
        score = 0.5 + (matched - 1) * 0.5 / len(examples)
        return min(score, 1.0)

    def _calculate_regex_score(
        self,
        query: str,
        examples: list[str],
    ) -> float:
        """Calculate regex pattern matching score.

        Args:
            query: User query.
            examples: Example texts for the pattern.

        Returns:
            Regex score in range [0, 1].
        """
        import re

        if not examples:
            return 0.0

        matched = 0

        for example in examples:
            # Create simple regex pattern from example
            # (this is a simplified approach)
            pattern = re.escape(example)
            pattern = pattern.replace(r'\ ', r'\s+')  # Allow flexible spacing

            if re.search(pattern, query, re.IGNORECASE):
                matched += 1

        if matched == 0:
            return 0.0

        # Lenient scoring
        score = 0.5 + (matched - 1) * 0.5 / len(examples)
        return min(score, 1.0)
