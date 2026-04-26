"""Tests for feedback collection system.

Covers: FeedbackCollector, ExecutionFeedbackCollector, FeedbackRecord, SkillExecutionFeedback.
"""

from pathlib import Path

import pytest

from vibesop.core.feedback import (
    ExecutionFeedbackCollector,
    FeedbackCollector,
    FeedbackRecord,
    SkillExecutionFeedback,
    collect_feedback,
    get_feedback_report,
)
from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute


class TestFeedbackRecord:
    """Test FeedbackRecord dataclass."""

    def test_to_dict(self) -> None:
        record = FeedbackRecord(
            query="test",
            routed_skill="builtin/test",
            was_correct=True,
            confidence=0.9,
        )
        d = record.to_dict()
        assert d["query"] == "test"
        assert d["routed_skill"] == "builtin/test"
        assert d["was_correct"] is True
        assert d["confidence"] == 0.9

    def test_from_dict(self) -> None:
        data = {
            "query": "test",
            "routed_skill": "builtin/test",
            "was_correct": False,
            "actual_skill": "builtin/other",
            "confidence": 0.5,
            "timestamp": "2024-01-01T00:00:00",
            "context": {"layer": "keyword"},
        }
        record = FeedbackRecord.from_dict(data)
        assert record.query == "test"
        assert record.was_correct is False
        assert record.actual_skill == "builtin/other"


class TestFeedbackCollector:
    """Test FeedbackCollector."""

    def test_collect_and_report(self, tmp_path: Path) -> None:
        storage = tmp_path / "feedback.json"
        collector = FeedbackCollector(storage_path=str(storage))

        collector.collect_feedback(
            query="q1", routed_skill="s1", was_correct=True, confidence=0.9
        )
        collector.collect_feedback(
            query="q2", routed_skill="s2", was_correct=False, actual_skill="s1", confidence=0.4
        )

        report = collector.generate_report()
        assert report.total_records == 2
        assert report.correct_count == 1
        assert report.incorrect_count == 1
        assert report.accuracy_rate == 0.5
        assert "s1" in report.by_skill
        assert "s2" in report.by_skill

    def test_report_empty(self, tmp_path: Path) -> None:
        storage = tmp_path / "feedback.json"
        collector = FeedbackCollector(storage_path=str(storage))
        report = collector.generate_report()
        assert report.total_records == 0
        assert report.accuracy_rate == 0.0

    def test_persistence(self, tmp_path: Path) -> None:
        storage = tmp_path / "feedback.json"
        c1 = FeedbackCollector(storage_path=str(storage))
        c1.collect_feedback(query="q", routed_skill="s", was_correct=True)

        c2 = FeedbackCollector(storage_path=str(storage))
        assert len(c2.get_records()) == 1

    def test_clear(self, tmp_path: Path) -> None:
        storage = tmp_path / "feedback.json"
        collector = FeedbackCollector(storage_path=str(storage))
        collector.collect_feedback(query="q", routed_skill="s", was_correct=True)
        collector.clear_records()
        assert len(collector.get_records()) == 0

    def test_export_import(self, tmp_path: Path) -> None:
        storage = tmp_path / "feedback.json"
        collector = FeedbackCollector(storage_path=str(storage))
        collector.collect_feedback(query="q", routed_skill="s", was_correct=True)

        export_path = tmp_path / "export.json"
        collector.export_records(str(export_path))
        assert export_path.exists()

        collector.clear_records()
        imported = collector.import_records(str(export_path))
        assert imported == 1
        assert len(collector.get_records()) == 1

    def test_collect_from_routing_result(self, tmp_path: Path) -> None:
        storage = tmp_path / "feedback.json"
        collector = FeedbackCollector(storage_path=str(storage))

        result = RoutingResult(
            primary=SkillRoute(
                skill_id="builtin/test",
                confidence=0.9,
                layer=RoutingLayer.KEYWORD,
            ),
            alternatives=[],
            routing_path=[RoutingLayer.KEYWORD],
            layer_details=[],
            query="test",
        )
        collector.collect_from_routing_result(query="test", result=result)
        assert len(collector.get_records()) == 1
        assert collector.get_records()[0].routed_skill == "builtin/test"


class TestExecutionFeedbackCollector:
    """Test ExecutionFeedbackCollector."""

    def test_collect_and_summary(self, tmp_path: Path) -> None:
        storage = tmp_path / "exec_feedback.json"
        collector = ExecutionFeedbackCollector(storage_path=str(storage))

        collector.collect(
            skill_id="s1",
            query="q1",
            was_helpful=True,
            execution_success=True,
            execution_time_ms=1000.0,
        )
        collector.collect(
            skill_id="s1",
            query="q2",
            was_helpful=False,
            execution_success=True,
            execution_time_ms=2000.0,
        )

        summary = collector.get_skill_summary("s1")
        assert summary["total"] == 2
        assert summary["helpful_rate"] == 0.5
        assert summary["success_rate"] == 1.0
        assert summary["avg_execution_time_ms"] == 1500.0

    def test_get_records_filtered(self, tmp_path: Path) -> None:
        storage = tmp_path / "exec_feedback.json"
        collector = ExecutionFeedbackCollector(storage_path=str(storage))

        collector.collect(skill_id="s1", query="q1")
        collector.collect(skill_id="s2", query="q2")

        assert len(collector.get_records(skill_id="s1")) == 1
        assert len(collector.get_records()) == 2
        assert len(collector.get_records(limit=1)) == 1

    def test_persistence(self, tmp_path: Path) -> None:
        storage = tmp_path / "exec_feedback.json"
        c1 = ExecutionFeedbackCollector(storage_path=str(storage))
        c1.collect(skill_id="s1", query="q1", was_helpful=True)

        c2 = ExecutionFeedbackCollector(storage_path=str(storage))
        assert len(c2.get_records()) == 1

    def test_clear(self, tmp_path: Path) -> None:
        storage = tmp_path / "exec_feedback.json"
        collector = ExecutionFeedbackCollector(storage_path=str(storage))
        collector.collect(skill_id="s1", query="q1")
        collector.clear_records()
        assert len(collector.get_records()) == 0


class TestSkillExecutionFeedback:
    """Test SkillExecutionFeedback dataclass."""

    def test_to_dict(self) -> None:
        record = SkillExecutionFeedback(
            skill_id="s1",
            query="q1",
            was_helpful=True,
            execution_success=True,
            execution_time_ms=1000.0,
        )
        d = record.to_dict()
        assert d["skill_id"] == "s1"
        assert d["was_helpful"] is True
        assert d["execution_time_ms"] == 1000.0

    def test_from_dict(self) -> None:
        data = {
            "skill_id": "s1",
            "query": "q1",
            "was_helpful": False,
            "execution_success": None,
            "execution_time_ms": None,
            "notes": "slow",
            "timestamp": "2024-01-01T00:00:00",
        }
        record = SkillExecutionFeedback.from_dict(data)
        assert record.skill_id == "s1"
        assert record.was_helpful is False
        assert record.notes == "slow"


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_collect_feedback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        collect_feedback(query="q", routed_skill="s", was_correct=True)
        report = get_feedback_report()
        assert report.total_records >= 1
