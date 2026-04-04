"""Vector similarity calculation for semantic matching.

This module provides efficient similarity calculation between vectors,
supporting multiple distance/similarity metrics.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING, Literal

import numpy as np

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


class SimilarityMetric(str, Enum):
    """Similarity/distance metrics."""

    COSINE = "cosine"  # Cosine similarity [-1, 1] -> normalized to [0, 1]
    DOT = "dot"  # Dot product [0, ∞] -> normalized to [0, 1]
    EUCLIDEAN = "euclidean"  # Euclidean distance [0, ∞] -> inverted to [0, 1]
    MANHATTAN = "manhattan"  # Manhattan distance [0, ∞] -> inverted to [0, 1]


class SimilarityCalculator:
    """Vector similarity calculator with multiple metrics.

    This class provides efficient calculation of similarity/distance between
    vectors, with support for multiple metrics and normalization.

    Features:
        - Multiple metrics: Cosine, dot product, Euclidean, Manhattan
        - Vectorized operations: Efficient NumPy-based computation
        - Normalization: All metrics normalized to [0, 1] range
        - Batch processing: Calculate multiple similarities at once

    Example:
        >>> calc = SimilarityCalculator(metric="cosine")
        >>> query = np.random.rand(384)
        >>> patterns = np.random.rand(10, 384)
        >>> similarities = calc.calculate(query, patterns)
        >>> similarities.shape
        (10,)
        >>> np.all((similarities >= 0) & (similarities <= 1))
        True
    """

    def __init__(
        self,
        metric: Literal["cosine", "dot", "euclidean", "manhattan"] = "cosine",
        normalize: bool = True,
    ) -> None:
        """Initialize the similarity calculator.

        Args:
            metric: The similarity/distance metric to use.
                - "cosine": Cosine similarity (default, recommended for semantic search)
                - "dot": Dot product (faster but requires normalized vectors)
                - "euclidean": Euclidean distance (inverted)
                - "manhattan": Manhattan distance (inverted)
            normalize: Whether to normalize output to [0, 1] range.
                For distance metrics, values are inverted: similarity = 1 / (1 + distance).

        Raises:
            ValueError: If metric is not recognized.
        """
        try:
            self.metric = SimilarityMetric(metric)
        except ValueError:
            valid_metrics = [m.value for m in SimilarityMetric]
            raise ValueError(
                f"Unknown metric: {metric}. Valid options: {valid_metrics}"
            )

        self.normalize = normalize

        # Select calculation function based on metric
        self._calc_func = self._get_calculation_function()

    def _get_calculation_function(self):
        """Get the appropriate calculation function for the metric."""
        if self.metric == SimilarityMetric.COSINE:
            return self._cosine_similarity
        elif self.metric == SimilarityMetric.DOT:
            return self._dot_product
        elif self.metric == SimilarityMetric.EUCLIDEAN:
            return self._euclidean_similarity
        elif self.metric == SimilarityMetric.MANHATTAN:
            return self._manhattan_similarity
        else:
            raise ValueError(f"Unsupported metric: {self.metric}")

    def calculate(
        self,
        query_vector: np.ndarray,
        pattern_vectors: np.ndarray,
    ) -> np.ndarray:
        """Calculate similarity between query and multiple pattern vectors.

        This method computes the similarity/distance between a single query vector
        and multiple pattern vectors efficiently using vectorized NumPy operations.

        Args:
            query_vector: Query vector with shape (dim,).
            pattern_vectors: Pattern vectors with shape (n_patterns, dim).

        Returns:
            Similarity scores as numpy array with shape (n_patterns,).
            All values are in the range [0, 1] if normalize=True.

        Raises:
            ValueError: If vector dimensions don't match.

        Example:
            >>> calc = SimilarityCalculator()
            >>> query = np.random.rand(384)
            >>> patterns = np.random.rand(5, 384)
            >>> similarities = calc.calculate(query, patterns)
            >>> similarities.shape
            (5,)
            >>> np.all((similarities >= 0) & (similarities <= 1))
            True
        """
        if query_vector.ndim != 1:
            raise ValueError(f"query_vector must be 1D, got shape {query_vector.shape}")

        if pattern_vectors.ndim != 2:
            raise ValueError(f"pattern_vectors must be 2D, got shape {pattern_vectors.shape}")

        if query_vector.shape[0] != pattern_vectors.shape[1]:
            raise ValueError(
                f"Dimension mismatch: query_vector has dim {query_vector.shape[0]}, "
                f"pattern_vectors has dim {pattern_vectors.shape[1]}"
            )

        # Calculate using the selected metric
        similarities = self._calc_func(query_vector, pattern_vectors)

        return similarities

    def calculate_single(
        self,
        query_vector: np.ndarray,
        pattern_vector: np.ndarray,
    ) -> float:
        """Calculate similarity between two single vectors.

        This is a convenience method for calculating similarity between two
        individual vectors.

        Args:
            query_vector: Query vector with shape (dim,).
            pattern_vector: Pattern vector with shape (dim,).

        Returns:
            Similarity score in range [0, 1] if normalize=True.

        Example:
            >>> calc = SimilarityCalculator()
            >>> v1 = np.random.rand(384)
            >>> v2 = np.random.rand(384)
            >>> similarity = calc.calculate_single(v1, v2)
            >>> 0 <= similarity <= 1
            True
        """
        if query_vector.shape != pattern_vector.shape:
            raise ValueError(
                f"Vector shape mismatch: {query_vector.shape} vs {pattern_vector.shape}"
            )

        # Reshape pattern_vectors to 2D for calculate()
        pattern_vectors_2d = pattern_vector.reshape(1, -1)
        similarities = self.calculate(query_vector, pattern_vectors_2d)

        return float(similarities[0])

    def batch_calculate(
        self,
        query_vectors: np.ndarray,
        pattern_vectors: np.ndarray,
    ) -> np.ndarray:
        """Batch calculate similarities between multiple queries and patterns.

        This method computes a similarity matrix where each element (i, j)
        represents the similarity between query_vectors[i] and pattern_vectors[j].

        Args:
            query_vectors: Query vectors with shape (n_queries, dim).
            pattern_vectors: Pattern vectors with shape (n_patterns, dim).

        Returns:
            Similarity matrix with shape (n_queries, n_patterns).
            All values are in the range [0, 1] if normalize=True.

        Example:
            >>> calc = SimilarityCalculator()
            >>> queries = np.random.rand(3, 384)
            >>> patterns = np.random.rand(5, 384)
            >>> sim_matrix = calc.batch_calculate(queries, patterns)
            >>> sim_matrix.shape
            (3, 5)
        """
        if query_vectors.ndim != 2:
            raise ValueError(f"query_vectors must be 2D, got shape {query_vectors.shape}")

        if pattern_vectors.ndim != 2:
            raise ValueError(f"pattern_vectors must be 2D, got shape {pattern_vectors.shape}")

        if query_vectors.shape[1] != pattern_vectors.shape[1]:
            raise ValueError(
                f"Dimension mismatch: query_vectors has dim {query_vectors.shape[1]}, "
                f"pattern_vectors has dim {pattern_vectors.shape[1]}"
            )

        n_queries = query_vectors.shape[0]
        n_patterns = pattern_vectors.shape[0]

        # Initialize similarity matrix
        similarity_matrix = np.zeros((n_queries, n_patterns))

        # Calculate similarities for each query
        for i, query_vector in enumerate(query_vectors):
            similarity_matrix[i] = self.calculate(query_vector, pattern_vectors)

        return similarity_matrix

    def _cosine_similarity(
        self,
        query_vector: np.ndarray,
        pattern_vectors: np.ndarray,
    ) -> np.ndarray:
        """Calculate cosine similarity.

        Cosine similarity measures the cosine of the angle between vectors,
        ranging from -1 (opposite) to 1 (identical). We normalize this to [0, 1]
        by applying (sim + 1) / 2.

        Args:
            query_vector: Query vector (dim,).
            pattern_vectors: Pattern vectors (n, dim).

        Returns:
            Similarity scores in range [0, 1].
        """
        # Calculate dot product
        dot_products = np.dot(pattern_vectors, query_vector)

        # Calculate magnitudes
        query_norm = np.linalg.norm(query_vector)
        pattern_norms = np.linalg.norm(pattern_vectors, axis=1)

        # Avoid division by zero
        if query_norm == 0:
            return np.zeros(len(pattern_vectors))

        # Cosine similarity
        cosine_sim = dot_products / (query_norm * pattern_norms + 1e-8)

        # Normalize from [-1, 1] to [0, 1]
        if self.normalize:
            cosine_sim = (cosine_sim + 1) / 2

        return cosine_sim

    def _dot_product(
        self,
        query_vector: np.ndarray,
        pattern_vectors: np.ndarray,
    ) -> np.ndarray:
        """Calculate dot product similarity.

        Dot product is faster than cosine similarity but requires vectors
        to be normalized. We normalize to [0, 1] by applying sigmoid.

        Args:
            query_vector: Query vector (dim,).
            pattern_vectors: Pattern vectors (n, dim).

        Returns:
            Similarity scores in range [0, 1].
        """
        # Calculate dot products
        dot_products = np.dot(pattern_vectors, query_vector)

        if self.normalize:
            # Apply sigmoid to normalize to [0, 1]
            # This assumes vectors are roughly L2 normalized
            similarities = 1 / (1 + np.exp(-dot_products))
        else:
            similarities = dot_products

        return similarities

    def _euclidean_similarity(
        self,
        query_vector: np.ndarray,
        pattern_vectors: np.ndarray,
    ) -> np.ndarray:
        """Calculate Euclidean distance-based similarity.

        We convert distance to similarity using: similarity = 1 / (1 + distance).

        Args:
            query_vector: Query vector (dim,).
            pattern_vectors: Pattern vectors (n, dim).

        Returns:
            Similarity scores in range [0, 1].
        """
        # Calculate Euclidean distances
        distances = np.linalg.norm(pattern_vectors - query_vector, axis=1)

        if self.normalize:
            # Convert distance to similarity: 1 / (1 + distance)
            similarities = 1 / (1 + distances)
        else:
            similarities = distances

        return similarities

    def _manhattan_similarity(
        self,
        query_vector: np.ndarray,
        pattern_vectors: np.ndarray,
    ) -> np.ndarray:
        """Calculate Manhattan distance-based similarity.

        We convert distance to similarity using: similarity = 1 / (1 + distance).

        Args:
            query_vector: Query vector (dim,).
            pattern_vectors: Pattern vectors (n, dim).

        Returns:
            Similarity scores in range [0, 1].
        """
        # Calculate Manhattan distances
        distances = np.sum(np.abs(pattern_vectors - query_vector), axis=1)

        if self.normalize:
            # Convert distance to similarity: 1 / (1 + distance)
            similarities = 1 / (1 + distances)
        else:
            similarities = distances

        return similarities

    def get_metric(self) -> str:
        """Get the current metric being used.

        Returns:
            Metric name as a string.
        """
        return self.metric.value

    def set_metric(self, metric: str) -> None:
        """Change the similarity metric.

        Args:
            metric: New metric to use.

        Raises:
            ValueError: If metric is not recognized.
        """
        try:
            self.metric = SimilarityMetric(metric)
            self._calc_func = self._get_calculation_function()
        except ValueError:
            valid_metrics = [m.value for m in SimilarityMetric]
            raise ValueError(
                f"Unknown metric: {metric}. Valid options: {valid_metrics}"
            )
