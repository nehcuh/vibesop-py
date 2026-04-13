"""Unified similarity calculation for VibeSOP matching system.

This module consolidates similarity calculation logic from:
- triggers/utils.py (cosine_similarity for dict vectors)
- semantic/similarity.py (numpy-based vector similarity)
- core/routing/semantic.py (TF-IDF cosine similarity)

The goal is to have ONE canonical similarity calculator that serves all matchers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from vibesop.core.matching.base import SimilarityMetric

# Optional numpy dependency for vector operations
if TYPE_CHECKING:
    import numpy as np
else:
    try:
        import numpy as np
    except ImportError:
        np = None  # type: ignore[import-not-found, assignment]


class SimilarityConfig(BaseModel):
    """Configuration for similarity calculation."""

    metric: SimilarityMetric = SimilarityMetric.COSINE
    normalize: bool = True
    epsilon: float = 1e-10  # For numerical stability


@dataclass
class SimilarityResult:
    """Result of similarity calculation.

    Attributes:
        score: Similarity score (typically 0.0 to 1.0)
        metric: Which metric was used
        normalized: Whether vectors were normalized
    """

    score: float
    metric: SimilarityMetric
    normalized: bool


class ISimilarityCalculator(Protocol):
    """Protocol for similarity calculators."""

    def calculate(
        self,
        query: str | list[str],
        candidates: list[str] | list[list[str]],
    ) -> list[float]:
        """Calculate similarity scores.

        Args:
            query: Query text, tokens, or vector
            candidates: Candidate texts, token lists, or vectors

        Returns:
            List of similarity scores
        """
        ...

    def calculate_single(
        self,
        vec1: np.ndarray,
        vec2: np.ndarray,
    ) -> float:
        """Calculate similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Similarity score
        """
        ...

    def get_config(self) -> SimilarityConfig:
        """Get calculator configuration."""
        ...


class SimilarityCalculator:
    """Unified similarity calculator supporting multiple metrics.

    This calculator handles:
    - Dictionary-based TF-IDF vectors (from triggers/utils.py)
    - Numpy embedding vectors (from semantic/similarity.py)
    - Multiple metrics: cosine, dot product, euclidean, manhattan

    Example:
        >>> calc = SimilarityCalculator(metric=SimilarityMetric.COSINE)
        >>> scores = calc.calculate("query text", ["doc1", "doc2", "doc3"])
        >>> print(scores[0])  # Similarity to doc1
    """

    def __init__(
        self,
        metric: SimilarityMetric | str = SimilarityMetric.COSINE,
        normalize: bool = True,
        epsilon: float = 1e-10,
    ):
        _metric = metric if isinstance(metric, SimilarityMetric) else SimilarityMetric(metric)
        self._config = SimilarityConfig(
            metric=_metric,
            normalize=normalize,
            epsilon=epsilon,
        )

    def calculate(
        self,
        query: str | list[str] | np.ndarray,
        candidates: list[str] | list[list[str]] | np.ndarray,
    ) -> list[float]:
        """Calculate similarity scores.

        This method automatically detects input types and dispatches
        to the appropriate calculation method.

        Args:
            query: Query representation
            candidates: Candidate representations

        Returns:
            List of similarity scores, same order as candidates
        """
        # Detect input types and dispatch
        if isinstance(query, dict):
            # Dictionary-based TF-IDF vectors (triggers/utils.py style)
            dict_candidates = [c for c in candidates if isinstance(c, dict)]
            return self._calculate_dict_query(query, dict_candidates)

        # Check if numpy is available for vector operations
        if np is not None and isinstance(query, np.ndarray):
            # Numpy array (semantic/similarity.py style)
            return self._calculate_numpy_query(query, candidates)

        # String or list input - tokenize and convert to dict
        from vibesop.core.matching.tokenizers import tokenize

        query_tokens = tokenize(query) if isinstance(query, str) else query
        query_vec = self._tokens_to_dict(query_tokens)

        candidate_vecs = []
        for candidate in candidates:
            if isinstance(candidate, str):
                candidate_tokens = tokenize(candidate)
            elif isinstance(candidate, list):
                candidate_tokens = candidate
            else:
                raise TypeError(f"Unsupported candidate type: {type(candidate)}")

            candidate_vecs.append(self._tokens_to_dict(candidate_tokens))

        # Calculate using dict method
        query_scores = []
        for cand_vec in candidate_vecs:
            score = self.cosine_similarity_dict(query_vec, cand_vec)
            query_scores.append(score)

        return query_scores

    def calculate_single(
        self,
        vec1: np.ndarray,
        vec2: np.ndarray,
    ) -> float:
        """Calculate similarity between two numpy vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Similarity score
        """
        metric = self._config.metric

        if metric == SimilarityMetric.COSINE:
            return self._cosine_similarity_numpy(vec1, vec2)
        elif metric == SimilarityMetric.DOT_PRODUCT:
            return float(np.dot(vec1, vec2))
        elif metric == SimilarityMetric.EUCLIDEAN:
            return float(-np.linalg.norm(vec1 - vec2))  # Negative for "higher is better"
        elif metric == SimilarityMetric.MANHATTAN:
            return float(-np.sum(np.abs(vec1 - vec2)))
        elif metric == SimilarityMetric.JACCARD:
            intersection = np.sum(np.minimum(vec1, vec2))
            union = np.sum(np.maximum(vec1, vec2))
            return float(intersection / (union + self._config.epsilon))
        else:
            raise ValueError(f"Unsupported metric: {metric}")

    def get_config(self) -> SimilarityConfig:
        """Get calculator configuration."""
        return self._config

    def _calculate_dict_query(
        self,
        query: dict[str, float],
        candidates: list[dict[str, float]],
    ) -> list[float]:
        """Calculate similarity for dict-based TF-IDF vectors."""
        scores = []
        for candidate in candidates:
            score = self.cosine_similarity_dict(query, candidate)
            scores.append(score)
        return scores

    def _calculate_numpy_query(
        self,
        query: np.ndarray,
        candidates: np.ndarray,
    ) -> list[float]:
        """Calculate similarity for numpy array vectors."""
        if candidates.ndim == 1:
            candidates = candidates.reshape(1, -1)

        query = query.reshape(1, -1)

        if self._config.metric == SimilarityMetric.COSINE:
            # Batch cosine similarity
            norms = np.linalg.norm(candidates, axis=1)
            query_norm = np.linalg.norm(query)
            scores = np.dot(candidates, query.T).flatten() / (
                norms * query_norm + self._config.epsilon
            )
            return scores.tolist()
        else:
            # For other metrics, calculate individually
            scores = []
            for cand_vec in candidates:
                score = self.calculate_single(query.flatten(), cand_vec)
                scores.append(score)
            return scores

    @staticmethod
    def cosine_similarity_dict(vec1: dict[str, float], vec2: dict[str, float]) -> float:
        """Calculate cosine similarity for dict-based vectors.

        This is the original implementation from triggers/utils.py,
        preserved for backward compatibility.
        """
        if not vec1 or not vec2:
            return 0.0

        # Get all unique terms
        all_terms = set(vec1.keys()) | set(vec2.keys())

        # Calculate dot product
        dot_product = sum(vec1.get(term, 0) * vec2.get(term, 0) for term in all_terms)

        # Calculate magnitudes
        mag1 = math.sqrt(sum(v**2 for v in vec1.values()))
        mag2 = math.sqrt(sum(v**2 for v in vec2.values()))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    @staticmethod
    def _cosine_similarity_numpy(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity for numpy vectors.

        This is the original implementation from semantic/similarity.py,
        preserved for backward compatibility.
        """
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    @staticmethod
    def _tokens_to_dict(tokens: list[str]) -> dict[str, float]:
        """Convert token list to TF dictionary."""
        if not tokens:
            return {}

        total = len(tokens)
        counts = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1

        return {token: count / total for token, count in counts.items()}


def cosine_similarity(
    vec1: dict[str, float] | np.ndarray,
    vec2: dict[str, float] | np.ndarray,
) -> float:
    """Convenience function for cosine similarity calculation.

    Automatically detects vector type and uses appropriate calculation.

    Args:
        vec1: First vector (dict or numpy array)
        vec2: Second vector (dict or numpy array)

    Returns:
        Cosine similarity between 0.0 and 1.0

    Examples:
        >>> cosine_similarity({"a": 1.0, "b": 0.5}, {"a": 0.5, "b": 1.0})
        0.8
    """
    calc = SimilarityCalculator(metric=SimilarityMetric.COSINE)

    if isinstance(vec1, dict) and isinstance(vec2, dict):
        return calc.cosine_similarity_dict(vec1, vec2)
    else:
        # Convert to numpy if needed
        if not isinstance(vec1, np.ndarray):
            vec1 = np.array(list(vec1.values()))
        if not isinstance(vec2, np.ndarray):
            vec2 = np.array(list(vec2.values()))
        return calc.calculate_single(vec1, vec2)


# Convenience exports
__all__ = [
    "ISimilarityCalculator",
    "SimilarityCalculator",
    "SimilarityConfig",
    "SimilarityResult",
    "cosine_similarity",
]
