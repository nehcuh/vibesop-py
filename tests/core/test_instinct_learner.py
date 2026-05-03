"""Tests for instinct learning system."""

from datetime import datetime

import pytest

from vibesop.core.instinct.learner import Instinct, SequencePattern


class TestInstinct:
    """Test Instinct dataclass."""

    def test_creation(self):
        instinct = Instinct(id="i1", pattern="p", action="a")
        assert instinct.id == "i1"
        assert instinct.pattern == "p"
        assert instinct.action == "a"
        assert instinct.confidence == pytest.approx(0.5)
        assert instinct.success_count == 0
        assert instinct.failure_count == 0
        assert instinct.tags == []

    def test_total_applications(self):
        instinct = Instinct(id="i1", pattern="p", action="a", success_count=3, failure_count=2)
        assert instinct.total_applications == 5

    def test_success_rate_with_data(self):
        instinct = Instinct(id="i1", pattern="p", action="a", success_count=3, failure_count=1)
        assert instinct.success_rate == pytest.approx(0.75)

    def test_success_rate_empty(self):
        instinct = Instinct(id="i1", pattern="p", action="a")
        assert instinct.success_rate == pytest.approx(0.5)

    def test_is_reliable_true(self):
        instinct = Instinct(id="i1", pattern="p", action="a", success_count=3, failure_count=0)
        # update() will recalculate confidence
        instinct.update(success=True)
        assert instinct.is_reliable is True

    def test_is_reliable_false_low_applications(self):
        instinct = Instinct(id="i1", pattern="p", action="a", success_count=1, failure_count=0)
        assert instinct.is_reliable is False

    def test_is_reliable_false_low_success_rate(self):
        instinct = Instinct(id="i1", pattern="p", action="a", success_count=1, failure_count=2)
        instinct.update(success=False)
        assert instinct.is_reliable is False

    def test_update_success(self):
        instinct = Instinct(id="i1", pattern="p", action="a")
        instinct.update(success=True)
        assert instinct.success_count == 1
        assert instinct.failure_count == 0
        assert instinct.last_used is not None
        assert instinct.confidence > 0.5

    def test_update_failure(self):
        instinct = Instinct(id="i1", pattern="p", action="a")
        instinct.update(success=False)
        assert instinct.success_count == 0
        assert instinct.failure_count == 1
        assert instinct.confidence < 0.5

    def test_update_multiple(self):
        instinct = Instinct(id="i1", pattern="p", action="a")
        for _ in range(5):
            instinct.update(success=True)
        assert instinct.success_count == 5
        assert instinct.confidence > 0.7

    def test_to_dict(self):
        dt = datetime(2026, 1, 1, 12, 0, 0)
        instinct = Instinct(
            id="i1",
            pattern="p",
            action="a",
            context="c",
            confidence=0.8,
            success_count=5,
            failure_count=1,
            last_used=dt,
            created_at=dt,
            source="test",
            tags=["t1"],
        )
        d = instinct.to_dict()
        assert d["id"] == "i1"
        assert d["confidence"] == pytest.approx(0.8)
        assert d["last_used"] == "2026-01-01T12:00:00"
        assert d["created_at"] == "2026-01-01T12:00:00"
        assert d["tags"] == ["t1"]

    def test_from_dict(self):
        d = {
            "id": "i1",
            "pattern": "p",
            "action": "a",
            "context": "c",
            "confidence": 0.8,
            "success_count": 5,
            "failure_count": 1,
            "last_used": "2026-01-01T12:00:00",
            "created_at": "2026-01-01T12:00:00",
            "source": "test",
            "tags": ["t1"],
        }
        instinct = Instinct.from_dict(d)
        assert instinct.id == "i1"
        assert instinct.confidence == pytest.approx(0.8)
        assert instinct.last_used == datetime(2026, 1, 1, 12, 0, 0)
        assert instinct.tags == ["t1"]

    def test_from_dict_defaults(self):
        d = {
            "id": "i1",
            "pattern": "p",
            "action": "a",
            "created_at": "2026-01-01T12:00:00",
        }
        instinct = Instinct.from_dict(d)
        assert instinct.confidence == pytest.approx(0.5)
        assert instinct.success_count == 0
        assert instinct.tags == []


class TestSequencePattern:
    """Test SequencePattern dataclass."""

    def test_creation(self):
        pattern = SequencePattern(steps=["a", "b", "c"])
        assert pattern.steps == ["a", "b", "c"]
        assert pattern.success_count == 0
        assert pattern.total_count == 0

    def test_total_count(self):
        pattern = SequencePattern(steps=["a"], success_count=3, total_count=5)
        assert pattern.total_count == 5

    def test_success_rate(self):
        pattern = SequencePattern(steps=["a"], success_count=3, total_count=4)
        assert pattern.success_rate == pytest.approx(0.75)

    def test_success_rate_empty(self):
        pattern = SequencePattern(steps=["a"])
        assert pattern.success_rate == pytest.approx(0.0)
