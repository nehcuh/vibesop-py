"""Semantic refinement logic extracted from KeywordDetector.

This module handles Stage 2 semantic refinement using sentence embeddings,
shared between _semantic_refine and _semantic_refine_all.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Optional

from vibesop.triggers.models import PatternMatch

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from vibesop.triggers.models import TriggerPattern


class SemanticRefiner:
    """Applies semantic refinement to candidate pattern matches.

    Score Fusion Strategy:
    - Traditional score > 0.8: Keep as-is (high confidence)
    - Semantic score > 0.8: Use semantic score (high semantic confidence)
    - Otherwise: Weighted average (40% traditional + 60% semantic)
    """

    def __init__(
        self,
        encoder: Any,
        cache: Any,
        calculator: Any,
        patterns: list[TriggerPattern],
    ) -> None:
        """Initialize semantic refiner.

        Args:
            encoder: SemanticEncoder instance
            cache: VectorCache instance
            calculator: SimilarityCalculator instance
            patterns: List of TriggerPattern objects
        """
        self.encoder = encoder
        self.cache = cache
        self.calculator = calculator
        self._patterns_by_id: dict[str, TriggerPattern] = {p.pattern_id: p for p in patterns}

    def refine(
        self,
        query: str,
        candidates: list[PatternMatch],
    ) -> list[PatternMatch]:
        """Apply semantic refinement to candidates.

        Updates candidates in-place with semantic scores.

        Args:
            query: User query
            candidates: Candidate matches from fast filter

        Returns:
            Same candidates list with updated semantic scores
        """
        if not candidates:
            return candidates

        # Encode query
        start_time = time.time()
        query_vector: Any = self.encoder.encode_query(query)
        encoding_time = time.time() - start_time

        # Get pattern vectors
        pattern_vectors: list[tuple[PatternMatch, Any]] = []
        for match in candidates:
            pattern = self._patterns_by_id.get(match.pattern_id)
            if not pattern:
                continue

            # Use semantic examples if available
            examples = pattern.examples + pattern.semantic_examples
            if not examples:
                # Fallback to keywords and regex patterns
                examples = pattern.keywords + pattern.regex_patterns

            if examples:
                vector = self.cache.get_or_compute(pattern.pattern_id, examples)
                pattern_vectors.append((match, vector))

        if not pattern_vectors:
            return candidates

        # Calculate similarities
        matches_with_vectors: list[PatternMatch] = [m for m, _ in pattern_vectors]
        vectors: Any = np.array([v for _, v in pattern_vectors])
        similarities: Any = self.calculator.calculate(query_vector, vectors)

        # Fuse scores and update matches
        for match, similarity in zip(matches_with_vectors, similarities):
            final_score: float = self._fuse_scores(match.confidence, float(similarity))
            match.confidence = min(final_score, 1.0)
            match.semantic_score = float(similarity)
            match.semantic_method = "cosine"
            match.model_used = self.encoder.model_name
            match.encoding_time = encoding_time

        return candidates

    def refine_best(
        self,
        query: str,
        candidates: list[PatternMatch],
        threshold: float,
    ) -> Optional[PatternMatch]:
        """Apply semantic refinement and return the best match.

        Updates candidates in-place and returns the best one if it meets
        the threshold.

        Args:
            query: User query
            candidates: Candidate matches from fast filter
            threshold: Minimum confidence threshold

        Returns:
            Best PatternMatch if it meets threshold, None otherwise
        """
        if not candidates:
            return None

        self.refine(query, candidates)

        best_match: Optional[PatternMatch] = max(candidates, key=lambda m: m.confidence)

        if best_match.confidence >= threshold:
            return best_match

        return None

    @staticmethod
    def _fuse_scores(traditional: float, semantic: float) -> float:
        """Fuse traditional and semantic scores.

        Args:
            traditional: Traditional matching score
            semantic: Semantic similarity score

        Returns:
            Fused score
        """
        if traditional > 0.8:
            return traditional
        if semantic > 0.8:
            return semantic
        return traditional * 0.4 + semantic * 0.6
