"""Tests for deep-interview ambiguity scoring."""

import pytest

from vibesop.core.algorithms.interview.ambiguity import (
    WEIGHTS,
    DimensionScore,
    compute_ambiguity,
)


def test_perfect_clarity():
    perfect = DimensionScore(score=1.0)
    result = compute_ambiguity(perfect, perfect, perfect, perfect, perfect)
    assert result.ambiguity == 0.0
    assert result.clarity == 1.0


def test_total_ambiguity():
    empty = DimensionScore(score=0.0)
    result = compute_ambiguity(empty, empty, empty, empty, empty)
    assert result.ambiguity == 1.0
    assert result.clarity == 0.0


def test_weighted_scoring():
    intent = DimensionScore(score=1.0)
    empty = DimensionScore(score=0.0)
    result = compute_ambiguity(intent, empty, empty, empty, empty)
    assert result.ambiguity == pytest.approx(0.70, abs=0.001)
    result = compute_ambiguity(empty, intent, empty, empty, empty)
    assert result.ambiguity == pytest.approx(0.75, abs=0.001)


def test_weakest_dimension():
    result = compute_ambiguity(
        DimensionScore(score=0.8),
        DimensionScore(score=0.3),
        DimensionScore(score=0.6),
        DimensionScore(score=0.5),
        DimensionScore(score=0.7),
    )
    assert result.weakest_dimension() == "outcome"


def test_to_dict():
    result = compute_ambiguity(
        DimensionScore(score=0.8, evidence=["clear goal"], missing=["timeline"]),
        DimensionScore(score=0.5),
        DimensionScore(score=0.6),
        DimensionScore(score=0.4),
        DimensionScore(score=0.7),
    )
    d = result.to_dict()
    assert "ambiguity" in d
    assert "clarity" in d
    assert d["weakest"] == "constraints"
    assert d["intent"]["evidence"] == ["clear goal"]
    assert d["intent"]["missing"] == ["timeline"]


def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
