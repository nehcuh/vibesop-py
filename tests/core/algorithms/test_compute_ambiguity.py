"""Tests for ambiguity computation."""

import pytest

from vibesop.core.algorithms.interview.compute_ambiguity import compute_ambiguity


class TestComputeAmbiguity:
    """Test compute_ambiguity function."""

    def test_fully_clear(self):
        """All dimensions at 1.0 should yield 0.0 ambiguity."""
        result = compute_ambiguity(
            intent=1.0, outcome=1.0, scope=1.0, constraints=1.0, success=1.0
        )
        assert result == pytest.approx(0.0)

    def test_fully_ambiguous(self):
        """All dimensions at 0.0 should yield 1.0 ambiguity."""
        result = compute_ambiguity(
            intent=0.0, outcome=0.0, scope=0.0, constraints=0.0, success=0.0
        )
        assert result == pytest.approx(1.0)

    def test_neutral(self):
        """All dimensions at 0.5 should yield 0.5 ambiguity."""
        result = compute_ambiguity(
            intent=0.5, outcome=0.5, scope=0.5, constraints=0.5, success=0.5
        )
        assert result == pytest.approx(0.5)

    def test_weighted_intent_dominant(self):
        """Intent has the highest weight (0.30)."""
        result = compute_ambiguity(
            intent=0.0, outcome=1.0, scope=1.0, constraints=1.0, success=1.0
        )
        # clarity = 0*0.30 + 1*0.25 + 1*0.20 + 1*0.15 + 1*0.10 = 0.70
        # ambiguity = 1 - 0.70 = 0.30
        assert result == pytest.approx(0.30)

    def test_weighted_success_least(self):
        """Success has the lowest weight (0.10)."""
        result = compute_ambiguity(
            intent=1.0, outcome=1.0, scope=1.0, constraints=1.0, success=0.0
        )
        # clarity = 1*0.30 + 1*0.25 + 1*0.20 + 1*0.15 + 0*0.10 = 0.90
        # ambiguity = 1 - 0.90 = 0.10
        assert result == pytest.approx(0.10)

    def test_clamped_to_0(self):
        """Should not go below 0.0."""
        result = compute_ambiguity(
            intent=2.0, outcome=2.0, scope=2.0, constraints=2.0, success=2.0
        )
        assert result == pytest.approx(0.0)

    def test_clamped_to_1(self):
        """Should not go above 1.0."""
        result = compute_ambiguity(
            intent=-1.0, outcome=-1.0, scope=-1.0, constraints=-1.0, success=-1.0
        )
        assert result == pytest.approx(1.0)
