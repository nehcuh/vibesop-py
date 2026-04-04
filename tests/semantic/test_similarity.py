"""Unit tests for similarity calculator."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy", reason="numpy not installed")

from vibesop.semantic.similarity import (
    SimilarityCalculator,
    SimilarityMetric,
)


class TestSimilarityCalculatorInit:
    """Tests for SimilarityCalculator initialization."""

    def test_initialization_default(self):
        """Test calculator initialization with default parameters."""
        calc = SimilarityCalculator()

        assert calc.metric == SimilarityMetric.COSINE
        assert calc.normalize is True

    def test_initialization_cosine_metric(self):
        """Test calculator initialization with cosine metric."""
        calc = SimilarityCalculator(metric="cosine")

        assert calc.metric == SimilarityMetric.COSINE

    def test_initialization_dot_metric(self):
        """Test calculator initialization with dot product metric."""
        calc = SimilarityCalculator(metric="dot")

        assert calc.metric == SimilarityMetric.DOT

    def test_initialization_euclidean_metric(self):
        """Test calculator initialization with euclidean metric."""
        calc = SimilarityCalculator(metric="euclidean")

        assert calc.metric == SimilarityMetric.EUCLIDEAN

    def test_initialization_manhattan_metric(self):
        """Test calculator initialization with manhattan metric."""
        calc = SimilarityCalculator(metric="manhattan")

        assert calc.metric == SimilarityMetric.MANHATTAN

    def test_initialization_normalize_true(self):
        """Test calculator initialization with normalization enabled."""
        calc = SimilarityCalculator(normalize=True)

        assert calc.normalize is True

    def test_initialization_normalize_false(self):
        """Test calculator initialization with normalization disabled."""
        calc = SimilarityCalculator(normalize=False)

        assert calc.normalize is False

    def test_initialization_invalid_metric_raises_error(self):
        """Test that invalid metric raises ValueError."""
        with pytest.raises(ValueError, match="Unknown metric"):
            SimilarityCalculator(metric="invalid_metric")


class TestCosineSimilarity:
    """Tests for cosine similarity calculation."""

    def test_cosine_identical_vectors(self):
        """Test cosine similarity of identical vectors."""
        calc = SimilarityCalculator(metric="cosine")

        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([1.0, 0.0, 0.0])

        similarity = calc.calculate_single(v1, v2)

        # Identical vectors should have similarity 1.0
        assert abs(similarity - 1.0) < 1e-5

    def test_cosine_orthogonal_vectors(self):
        """Test cosine similarity of orthogonal vectors."""
        calc = SimilarityCalculator(metric="cosine")

        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0])

        similarity = calc.calculate_single(v1, v2)

        # Orthogonal vectors should have similarity around 0.5
        # (because we normalize [-1, 1] to [0, 1])
        assert abs(similarity - 0.5) < 1e-5

    def test_cosine_opposite_vectors(self):
        """Test cosine similarity of opposite vectors."""
        calc = SimilarityCalculator(metric="cosine")

        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([-1.0, 0.0, 0.0])

        similarity = calc.calculate_single(v1, v2)

        # Opposite vectors should have similarity 0.0
        assert abs(similarity - 0.0) < 1e-5

    def test_cosine_multiple_patterns(self):
        """Test cosine similarity with multiple pattern vectors."""
        calc = SimilarityCalculator(metric="cosine")

        query = np.array([1.0, 0.0, 0.0])
        patterns = np.array(
            [
                [1.0, 0.0, 0.0],  # Identical
                [0.0, 1.0, 0.0],  # Orthogonal
                [-1.0, 0.0, 0.0],  # Opposite
            ]
        )

        similarities = calc.calculate(query, patterns)

        assert similarities.shape == (3,)
        assert abs(similarities[0] - 1.0) < 1e-5  # Identical
        assert abs(similarities[1] - 0.5) < 1e-5  # Orthogonal
        assert abs(similarities[2] - 0.0) < 1e-5  # Opposite

    def test_cosine_normalized_output(self):
        """Test that cosine similarity output is normalized to [0, 1]."""
        calc = SimilarityCalculator(metric="cosine", normalize=True)

        # Generate random vectors
        query = np.random.rand(384)
        patterns = np.random.rand(10, 384)

        similarities = calc.calculate(query, patterns)

        # All similarities should be in [0, 1]
        assert np.all(similarities >= 0.0)
        assert np.all(similarities <= 1.0)


class TestDotProductSimilarity:
    """Tests for dot product similarity calculation."""

    def test_dot_product_normalized_vectors(self):
        """Test dot product with normalized vectors."""
        calc = SimilarityCalculator(metric="dot", normalize=True)

        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([1.0, 0.0, 0.0])

        similarity = calc.calculate_single(v1, v2)

        # Same direction should give high similarity
        assert similarity > 0.9

    def test_dot_product_opposite_directions(self):
        """Test dot product with opposite directions."""
        calc = SimilarityCalculator(metric="dot", normalize=True)

        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([-1.0, 0.0, 0.0])

        similarity = calc.calculate_single(v1, v2)

        # Opposite directions should give low similarity
        assert similarity < 0.5


class TestEuclideanSimilarity:
    """Tests for Euclidean distance-based similarity."""

    def test_euclidean_identical_vectors(self):
        """Test Euclidean similarity of identical vectors."""
        calc = SimilarityCalculator(metric="euclidean")

        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([1.0, 0.0, 0.0])

        similarity = calc.calculate_single(v1, v2)

        # Identical vectors should have similarity 1.0
        assert abs(similarity - 1.0) < 1e-5

    def test_euclidean_far_vectors(self):
        """Test Euclidean similarity of far vectors."""
        calc = SimilarityCalculator(metric="euclidean")

        v1 = np.array([0.0, 0.0, 0.0])
        v2 = np.array([10.0, 10.0, 10.0])

        similarity = calc.calculate_single(v1, v2)

        # Far vectors should have low similarity
        assert similarity < 0.3

    def test_euclidean_distance_to_similarity_conversion(self):
        """Test that distance is properly converted to similarity."""
        calc = SimilarityCalculator(metric="euclidean", normalize=True)

        # Similar vectors (small distance)
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([1.01, 0.0, 0.0])

        similarity = calc.calculate_single(v1, v2)

        # Should be high similarity (low distance)
        assert similarity > 0.9


class TestManhattanSimilarity:
    """Tests for Manhattan distance-based similarity."""

    def test_manhattan_identical_vectors(self):
        """Test Manhattan similarity of identical vectors."""
        calc = SimilarityCalculator(metric="manhattan")

        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([1.0, 0.0, 0.0])

        similarity = calc.calculate_single(v1, v2)

        # Identical vectors should have similarity 1.0
        assert abs(similarity - 1.0) < 1e-5

    def test_manhattan_far_vectors(self):
        """Test Manhattan similarity of far vectors."""
        calc = SimilarityCalculator(metric="manhattan")

        v1 = np.array([0.0, 0.0, 0.0])
        v2 = np.array([10.0, 10.0, 10.0])

        similarity = calc.calculate_single(v1, v2)

        # Far vectors should have low similarity
        assert similarity < 0.3


class TestSimilarityCalculatorCalculate:
    """Tests for SimilarityCalculator.calculate() method."""

    def test_calculate_1d_query_vector(self):
        """Test calculate with 1D query vector."""
        calc = SimilarityCalculator()

        query = np.random.rand(384)
        patterns = np.random.rand(5, 384)

        similarities = calc.calculate(query, patterns)

        assert similarities.shape == (5,)

    def test_calculate_2d_pattern_vectors(self):
        """Test calculate with 2D pattern vectors."""
        calc = SimilarityCalculator()

        query = np.random.rand(384)
        patterns = np.random.rand(10, 384)

        similarities = calc.calculate(query, patterns)

        assert similarities.shape == (10,)

    def test_calculate_dimension_mismatch_raises_error(self):
        """Test that dimension mismatch raises ValueError."""
        calc = SimilarityCalculator()

        query = np.random.rand(384)
        patterns = np.random.rand(5, 256)  # Wrong dimension

        with pytest.raises(ValueError, match="Dimension mismatch"):
            calc.calculate(query, patterns)

    def test_calculate_query_not_1d_raises_error(self):
        """Test that non-1D query vector raises ValueError."""
        calc = SimilarityCalculator()

        query = np.random.rand(2, 384)  # 2D instead of 1D
        patterns = np.random.rand(5, 384)

        with pytest.raises(ValueError, match="query_vector must be 1D"):
            calc.calculate(query, patterns)

    def test_calculate_patterns_not_2d_raises_error(self):
        """Test that non-2D pattern vectors raises ValueError."""
        calc = SimilarityCalculator()

        query = np.random.rand(384)
        patterns = np.random.rand(384)  # 1D instead of 2D

        with pytest.raises(ValueError, match="pattern_vectors must be 2D"):
            calc.calculate(query, patterns)


class TestSimilarityCalculatorCalculateSingle:
    """Tests for SimilarityCalculator.calculate_single() method."""

    def test_calculate_single_same_dimensions(self):
        """Test calculate_single with vectors of same dimension."""
        calc = SimilarityCalculator()

        v1 = np.random.rand(384)
        v2 = np.random.rand(384)

        similarity = calc.calculate_single(v1, v2)

        assert isinstance(similarity, float)
        assert 0.0 <= similarity <= 1.0

    def test_calculate_single_different_dimensions_raises_error(self):
        """Test calculate_single with different dimension vectors."""
        calc = SimilarityCalculator()

        v1 = np.random.rand(384)
        v2 = np.random.rand(256)  # Different dimension

        with pytest.raises(ValueError, match="Vector shape mismatch"):
            calc.calculate_single(v1, v2)


class TestSimilarityCalculatorBatchCalculate:
    """Tests for SimilarityCalculator.batch_calculate() method."""

    def test_batch_calculate_returns_matrix(self):
        """Test that batch_calculate returns similarity matrix."""
        calc = SimilarityCalculator()

        queries = np.random.rand(3, 384)
        patterns = np.random.rand(5, 384)

        sim_matrix = calc.batch_calculate(queries, patterns)

        assert sim_matrix.shape == (3, 5)

    def test_batch_calculate_all_values_in_range(self):
        """Test that all similarity values are in [0, 1]."""
        calc = SimilarityCalculator()

        queries = np.random.rand(10, 384)
        patterns = np.random.rand(20, 384)

        sim_matrix = calc.batch_calculate(queries, patterns)

        assert np.all(sim_matrix >= 0.0)
        assert np.all(sim_matrix <= 1.0)

    def test_batch_calculate_dimension_mismatch_raises_error(self):
        """Test that dimension mismatch raises ValueError."""
        calc = SimilarityCalculator()

        queries = np.random.rand(3, 256)  # Wrong dimension
        patterns = np.random.rand(5, 384)

        with pytest.raises(ValueError, match="Dimension mismatch"):
            calc.batch_calculate(queries, patterns)

    def test_batch_calculate_queries_not_2d_raises_error(self):
        """Test that non-2D queries raises ValueError."""
        calc = SimilarityCalculator()

        queries = np.random.rand(384)  # 1D instead of 2D
        patterns = np.random.rand(5, 384)

        with pytest.raises(ValueError, match="query_vectors must be 2D"):
            calc.batch_calculate(queries, patterns)

    def test_batch_calculate_patterns_not_2d_raises_error(self):
        """Test that non-2D patterns raises ValueError."""
        calc = SimilarityCalculator()

        queries = np.random.rand(3, 384)
        patterns = np.random.rand(384)  # 1D instead of 2D

        with pytest.raises(ValueError, match="pattern_vectors must be 2D"):
            calc.batch_calculate(queries, patterns)


class TestSimilarityCalculatorGetMetric:
    """Tests for SimilarityCalculator.get_metric() method."""

    def test_get_metric_returns_string(self):
        """Test that get_metric returns metric name string."""
        calc = SimilarityCalculator(metric="cosine")

        metric = calc.get_metric()

        assert isinstance(metric, str)
        assert metric == "cosine"

    def test_get_metric_returns_different_metrics(self):
        """Test get_metric with different metrics."""
        calc1 = SimilarityCalculator(metric="cosine")
        calc2 = SimilarityCalculator(metric="dot")
        calc3 = SimilarityCalculator(metric="euclidean")

        assert calc1.get_metric() == "cosine"
        assert calc2.get_metric() == "dot"
        assert calc3.get_metric() == "euclidean"


class TestSimilarityCalculatorSetMetric:
    """Tests for SimilarityCalculator.set_metric() method."""

    def test_set_metric_changes_metric(self):
        """Test that set_metric changes the metric."""
        calc = SimilarityCalculator(metric="cosine")

        assert calc.get_metric() == "cosine"

        calc.set_metric("dot")

        assert calc.get_metric() == "dot"

    def test_set_metric_invalid_raises_error(self):
        """Test that setting invalid metric raises ValueError."""
        calc = SimilarityCalculator()

        with pytest.raises(ValueError, match="Unknown metric"):
            calc.set_metric("invalid_metric")


class TestSimilarityCalculatorPerformance:
    """Performance tests for similarity calculator."""

    @pytest.mark.slow
    def test_similarity_calculation_performance(self):
        """Test similarity calculation performance benchmark."""
        calc = SimilarityCalculator()

        query = np.random.rand(384)
        patterns = np.random.rand(30, 384)  # 30 patterns (typical)

        import time

        iterations = 10000
        start = time.time()

        for _ in range(iterations):
            calc.calculate(query, patterns)

        elapsed = time.time() - start
        avg_time = elapsed / iterations

        # Should be very fast (< 0.1ms per calculation)
        assert avg_time < 0.0001, f"Similarity calculation too slow: {avg_time * 1000:.3f}ms"

    @pytest.mark.slow
    def test_batch_calculate_performance(self):
        """Test batch calculation performance."""
        calc = SimilarityCalculator()

        queries = np.random.rand(100, 384)
        patterns = np.random.rand(30, 384)

        import time

        start = time.time()

        sim_matrix = calc.batch_calculate(queries, patterns)

        elapsed = time.time() - start
        avg_time = elapsed / len(queries)

        # Batch processing should be fast
        assert avg_time < 0.01, f"Batch calculation too slow: {avg_time * 1000:.2f}ms per query"


class TestSimilarityNormalization:
    """Tests for output normalization."""

    def test_normalization_enabled_range(self):
        """Test that normalization keeps values in [0, 1]."""
        calc = SimilarityCalculator(normalize=True)

        query = np.random.rand(384)
        patterns = np.random.rand(50, 384)

        similarities = calc.calculate(query, patterns)

        assert np.all(similarities >= 0.0)
        assert np.all(similarities <= 1.0)

    def test_normalization_disabled_range(self):
        """Test that without normalization, range may vary."""
        calc = SimilarityCalculator(normalize=False)

        query = np.random.rand(384)
        patterns = np.random.rand(50, 384)

        similarities = calc.calculate(query, patterns)

        # For cosine with normalize=False, range is [-1, 1]
        if calc.metric == SimilarityMetric.COSINE:
            assert np.all(similarities >= -1.0)
            assert np.all(similarities <= 1.0)

    def test_dot_product_normalization_effect(self):
        """Test that normalization affects dot product output."""
        query = np.array([1.0, 0.0, 0.0])
        patterns = np.array(
            [
                [1.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [-1.0, 0.0, 0.0],
            ]
        )

        calc_normalized = SimilarityCalculator(metric="dot", normalize=True)
        calc_not_normalized = SimilarityCalculator(metric="dot", normalize=False)

        sim_normalized = calc_normalized.calculate(query, patterns)
        sim_not_normalized = calc_not_normalized.calculate(query, patterns)

        # Normalized should be in [0, 1]
        assert np.all(sim_normalized >= 0.0)
        assert np.all(sim_normalized <= 1.0)

        # Not normalized could have values > 1
        assert np.any(sim_not_normalized >= 0.0)
