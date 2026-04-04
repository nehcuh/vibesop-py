"""Tests for SemanticRefiner."""

from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pytest

from vibesop.triggers.models import PatternMatch
from vibesop.triggers.semantic_refiner import SemanticRefiner


@pytest.fixture
def mock_encoder() -> Mock:
    encoder = Mock()
    encoder.model_name = "test-model"
    encoder.encode_query.return_value = np.array([1.0, 0.0, 0.0])
    return encoder


@pytest.fixture
def mock_cache() -> Mock:
    cache = Mock()
    cache.get_or_compute.return_value = np.array([1.0, 0.0, 0.0])
    return cache


@pytest.fixture
def mock_calculator() -> Mock:
    calc = Mock()
    calc.calculate.return_value = np.array([0.9, 0.5, 0.3])
    return calc


@pytest.fixture
def mock_patterns() -> list[Mock]:
    p1 = Mock()
    p1.pattern_id = "security/scan"
    p1.examples = ["scan for vulnerabilities"]
    p1.semantic_examples = []
    p1.keywords = ["scan", "security"]
    p1.regex_patterns = []

    p2 = Mock()
    p2.pattern_id = "dev/test"
    p2.examples = ["run tests"]
    p2.semantic_examples = []
    p2.keywords = ["test", "run"]
    p2.regex_patterns = []

    return [p1, p2]


class TestFuseScores:
    """Test static _fuse_scores method."""

    def test_high_traditional_kept(self) -> None:
        result = SemanticRefiner._fuse_scores(0.9, 0.3)
        assert result == 0.9

    def test_high_semantic_used(self) -> None:
        result = SemanticRefiner._fuse_scores(0.3, 0.9)
        assert result == 0.9

    def test_medium_weighted_average(self) -> None:
        result = SemanticRefiner._fuse_scores(0.5, 0.6)
        expected = 0.5 * 0.4 + 0.6 * 0.6
        assert pytest.approx(result) == expected

    def test_boundary_traditional(self) -> None:
        # 0.8 is NOT > 0.8 (strict), falls through to weighted average
        result = SemanticRefiner._fuse_scores(0.8, 0.5)
        expected = 0.8 * 0.4 + 0.5 * 0.6
        assert pytest.approx(result) == expected

    def test_boundary_semantic(self) -> None:
        # 0.8 is NOT > 0.8 (strict), falls through to weighted average
        result = SemanticRefiner._fuse_scores(0.5, 0.8)
        expected = 0.5 * 0.4 + 0.8 * 0.6
        assert pytest.approx(result) == expected


class TestRefine:
    """Test refine() method."""

    def test_empty_candidates(
        self, mock_encoder, mock_cache, mock_calculator, mock_patterns
    ) -> None:
        refiner = SemanticRefiner(mock_encoder, mock_cache, mock_calculator, mock_patterns)
        result = refiner.refine("test query", [])
        assert result == []

    def test_updates_candidates_in_place(
        self, mock_encoder, mock_cache, mock_calculator, mock_patterns
    ) -> None:
        refiner = SemanticRefiner(mock_encoder, mock_cache, mock_calculator, mock_patterns)
        candidates = [
            PatternMatch(pattern_id="security/scan", confidence=0.5),
            PatternMatch(pattern_id="dev/test", confidence=0.4),
        ]

        refiner.refine("test query", candidates)

        assert candidates[0].semantic_score == pytest.approx(0.9)
        assert candidates[0].model_used == "test-model"
        assert candidates[0].encoding_time is not None
        assert candidates[0].semantic_method == "cosine"

    def test_returns_same_list(
        self, mock_encoder, mock_cache, mock_calculator, mock_patterns
    ) -> None:
        refiner = SemanticRefiner(mock_encoder, mock_cache, mock_calculator, mock_patterns)
        candidates = [PatternMatch(pattern_id="security/scan", confidence=0.5)]
        result = refiner.refine("test query", candidates)
        assert result is candidates


class TestRefineBest:
    """Test refine_best() method."""

    def test_returns_best_above_threshold(
        self, mock_encoder, mock_cache, mock_calculator, mock_patterns
    ) -> None:
        refiner = SemanticRefiner(mock_encoder, mock_cache, mock_calculator, mock_patterns)
        candidates = [PatternMatch(pattern_id="security/scan", confidence=0.5)]

        result = refiner.refine_best("test query", candidates, threshold=0.7)

        assert result is not None
        assert result.pattern_id == "security/scan"

    def test_returns_none_below_threshold(
        self, mock_encoder, mock_cache, mock_calculator, mock_patterns
    ) -> None:
        mock_calculator.calculate.return_value = np.array([0.1])
        refiner = SemanticRefiner(mock_encoder, mock_cache, mock_calculator, mock_patterns)
        candidates = [PatternMatch(pattern_id="security/scan", confidence=0.2)]

        result = refiner.refine_best("test query", candidates, threshold=0.7)

        assert result is None

    def test_empty_candidates(
        self, mock_encoder, mock_cache, mock_calculator, mock_patterns
    ) -> None:
        refiner = SemanticRefiner(mock_encoder, mock_cache, mock_calculator, mock_patterns)
        result = refiner.refine_best("test query", [], threshold=0.7)
        assert result is None
