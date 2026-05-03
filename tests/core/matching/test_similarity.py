"""Tests for similarity calculation module."""

import math

import numpy as np
import pytest

from vibesop.core.matching.base import SimilarityMetric
from vibesop.core.matching.similarity import (
    SimilarityCalculator,
    SimilarityConfig,
    SimilarityResult,
    cosine_similarity,
)


class TestSimilarityConfig:
    def test_default_values(self):
        config = SimilarityConfig()
        assert config.metric == SimilarityMetric.COSINE
        assert config.normalize is True
        assert config.epsilon == 1e-10


class TestSimilarityResult:
    def test_basic_creation(self):
        result = SimilarityResult(score=0.8, metric=SimilarityMetric.COSINE, normalized=True)
        assert result.score == pytest.approx(0.8)
        assert result.metric == SimilarityMetric.COSINE
        assert result.normalized is True


class TestSimilarityCalculatorDict:
    def test_cosine_similarity_dict_identical(self):
        vec = {"a": 1.0, "b": 1.0}
        score = SimilarityCalculator.cosine_similarity_dict(vec, vec)
        assert score == pytest.approx(1.0)

    def test_cosine_similarity_dict_orthogonal(self):
        vec1 = {"a": 1.0}
        vec2 = {"b": 1.0}
        score = SimilarityCalculator.cosine_similarity_dict(vec1, vec2)
        assert score == pytest.approx(0.0)

    def test_cosine_similarity_dict_empty(self):
        assert SimilarityCalculator.cosine_similarity_dict({}, {"a": 1.0}) == 0.0
        assert SimilarityCalculator.cosine_similarity_dict({"a": 1.0}, {}) == 0.0
        assert SimilarityCalculator.cosine_similarity_dict({}, {}) == 0.0

    def test_cosine_similarity_dict_zero_magnitude(self):
        assert SimilarityCalculator.cosine_similarity_dict({"a": 0.0}, {"a": 1.0}) == 0.0

    def test_calculate_with_dict_vectors(self):
        calc = SimilarityCalculator()
        query = {"hello": 0.5, "world": 0.5}
        candidates = [
            {"hello": 0.5, "world": 0.5},
            {"hello": 1.0},
        ]
        scores = calc.calculate(query, candidates)
        assert len(scores) == 2
        assert scores[0] == pytest.approx(1.0)
        assert scores[1] == pytest.approx(1.0 / math.sqrt(2))


class TestSimilarityCalculatorString:
    def test_calculate_with_strings(self):
        calc = SimilarityCalculator()
        scores = calc.calculate("hello world", ["hello world", "hello"])
        assert len(scores) == 2
        assert scores[0] == pytest.approx(1.0)
        assert scores[1] > 0.0
        assert scores[1] < 1.0

    def test_calculate_with_token_lists(self):
        calc = SimilarityCalculator()
        query = ["hello", "world"]
        candidates = [["hello", "world"], ["hello"]]
        scores = calc.calculate(query, candidates)
        assert len(scores) == 2
        assert scores[0] == pytest.approx(1.0)


class TestSimilarityCalculatorNumpy:
    def test_calculate_single_cosine(self):
        calc = SimilarityCalculator(metric=SimilarityMetric.COSINE)
        vec1 = np.array([1.0, 0.0])
        vec2 = np.array([1.0, 0.0])
        assert calc.calculate_single(vec1, vec2) == pytest.approx(1.0)

    def test_calculate_single_cosine_orthogonal(self):
        calc = SimilarityCalculator(metric=SimilarityMetric.COSINE)
        vec1 = np.array([1.0, 0.0])
        vec2 = np.array([0.0, 1.0])
        assert calc.calculate_single(vec1, vec2) == pytest.approx(0.0)

    def test_calculate_single_dot_product(self):
        calc = SimilarityCalculator(metric=SimilarityMetric.DOT_PRODUCT)
        vec1 = np.array([1.0, 2.0])
        vec2 = np.array([3.0, 4.0])
        assert calc.calculate_single(vec1, vec2) == pytest.approx(11.0)

    def test_calculate_single_euclidean(self):
        calc = SimilarityCalculator(metric=SimilarityMetric.EUCLIDEAN)
        vec1 = np.array([0.0, 0.0])
        vec2 = np.array([3.0, 4.0])
        assert calc.calculate_single(vec1, vec2) == pytest.approx(-5.0)

    def test_calculate_single_manhattan(self):
        calc = SimilarityCalculator(metric=SimilarityMetric.MANHATTAN)
        vec1 = np.array([0.0, 0.0])
        vec2 = np.array([3.0, 4.0])
        assert calc.calculate_single(vec1, vec2) == pytest.approx(-7.0)

    def test_calculate_single_jaccard(self):
        calc = SimilarityCalculator(metric=SimilarityMetric.JACCARD)
        vec1 = np.array([1.0, 0.0])
        vec2 = np.array([1.0, 1.0])
        assert calc.calculate_single(vec1, vec2) == pytest.approx(1.0 / 2.0)

    def test_calculate_numpy_batch(self):
        calc = SimilarityCalculator(metric=SimilarityMetric.COSINE)
        query = np.array([1.0, 0.0])
        candidates = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        scores = calc.calculate(query, candidates)
        assert len(scores) == 3
        assert scores[0] == pytest.approx(1.0)
        assert scores[1] == pytest.approx(0.0)
        assert scores[2] == pytest.approx(1.0 / math.sqrt(2))

    def test_calculate_numpy_single_candidate(self):
        calc = SimilarityCalculator(metric=SimilarityMetric.COSINE)
        query = np.array([1.0, 0.0])
        candidate = np.array([1.0, 0.0])
        scores = calc.calculate(query, candidate)
        assert scores[0] == pytest.approx(1.0)

    def test_cosine_similarity_numpy_zero_norm(self):
        calc = SimilarityCalculator()
        vec1 = np.array([0.0, 0.0])
        vec2 = np.array([1.0, 0.0])
        assert calc._cosine_similarity_numpy(vec1, vec2) == 0.0


class TestTokensToDict:
    def test_basic_tokens(self):
        result = SimilarityCalculator._tokens_to_dict(["a", "b", "a"])
        assert result == {"a": 2.0 / 3.0, "b": 1.0 / 3.0}

    def test_empty_tokens(self):
        assert SimilarityCalculator._tokens_to_dict([]) == {}


class TestCosineSimilarityFunction:
    def test_with_dicts(self):
        vec1 = {"a": 1.0, "b": 0.5}
        vec2 = {"a": 0.5, "b": 1.0}
        score = cosine_similarity(vec1, vec2)
        assert 0.0 < score < 1.0

    def test_with_numpy_arrays(self):
        vec1 = np.array([1.0, 0.0])
        vec2 = np.array([0.0, 1.0])
        score = cosine_similarity(vec1, vec2)
        assert score == pytest.approx(0.0)

    def test_mixed_types(self):
        vec1 = {"a": 1.0, "b": 0.0}
        vec2 = np.array([1.0, 0.0])
        score = cosine_similarity(vec1, vec2)
        assert score == pytest.approx(1.0)


class TestGetConfig:
    def test_returns_config(self):
        calc = SimilarityCalculator(metric=SimilarityMetric.EUCLIDEAN, normalize=False)
        config = calc.get_config()
        assert config.metric == SimilarityMetric.EUCLIDEAN
        assert config.normalize is False
