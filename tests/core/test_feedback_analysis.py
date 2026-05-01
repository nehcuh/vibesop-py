"""Tests for FeedbackCollector routing failure analysis."""

from __future__ import annotations

from pathlib import Path

from vibesop.core.feedback import FeedbackCollector, collect_feedback


class TestFeedbackCollector:
    """Test FeedbackCollector analysis methods."""

    def test_empty_collector(self) -> None:
        collector = FeedbackCollector(storage_path="/tmp/_test_empty_feedback.jsonl")
        report = collector.generate_report()
        assert report.total_records == 0
        assert report.accuracy_rate == 0.0

    def test_get_top_mismatches(self, tmp_path: Path) -> None:
        path = tmp_path / "feedback.jsonl"
        collector = FeedbackCollector(storage_path=str(path))

        collector.collect_feedback("debug error", "gstack/review", False, "gstack/investigate", 0.85)
        collector.collect_feedback("fix bug", "gstack/review", False, "gstack/investigate", 0.90)
        collector.collect_feedback("code review", "gstack/review", True, confidence=0.92)
        collector.collect_feedback("refactor", "gstack/review", False, "superpowers/refactor", 0.75)

        mismatches = collector.get_top_mismatches(top_n=5)
        assert len(mismatches) >= 1

        top = mismatches[0]
        assert top["routed_skill"] == "gstack/review"
        assert top["actual_skill"] == "gstack/investigate"
        assert top["count"] == 2
        assert len(top["example_queries"]) == 2
        assert abs(top["avg_confidence"] - 0.875) < 0.01

    def test_high_confidence_errors(self, tmp_path: Path) -> None:
        path = tmp_path / "feedback.jsonl"
        collector = FeedbackCollector(storage_path=str(path))

        collector.collect_feedback("debug", "wrong_skill", False, "right_skill", 0.90)
        collector.collect_feedback("fix", "wrong_skill", False, "right_skill", 0.85)
        collector.collect_feedback("test", "wrong_skill", False, "right_skill", 0.95)

        errors = collector.get_high_confidence_errors(min_confidence=0.8)
        assert len(errors) >= 1
        assert all(e["avg_confidence"] >= 0.8 for e in errors)

    def test_correct_records_excluded(self, tmp_path: Path) -> None:
        path = tmp_path / "feedback.jsonl"
        collector = FeedbackCollector(storage_path=str(path))

        collector.collect_feedback("debug error", "gstack/investigate", True, confidence=0.95)
        collector.collect_feedback("review code", "gstack/review", True, confidence=0.90)

        mismatches = collector.get_top_mismatches()
        assert len(mismatches) == 0

    def test_no_actual_skill_excluded(self, tmp_path: Path) -> None:
        path = tmp_path / "feedback.jsonl"
        collector = FeedbackCollector(storage_path=str(path))

        collector.collect_feedback("debug", "gstack/review", False, actual_skill=None, confidence=0.80)

        mismatches = collector.get_top_mismatches()
        assert len(mismatches) == 0

    def test_report_common_errors(self, tmp_path: Path) -> None:
        path = tmp_path / "feedback.jsonl"
        collector = FeedbackCollector(storage_path=str(path))

        collector.collect_feedback("debug", "gstack/review", False, "gstack/investigate", 0.80)
        collector.collect_feedback("review", "gstack/investigate", False, "gstack/review", 0.75)

        report = collector.generate_report()
        assert report.total_records == 2
        assert report.incorrect_count == 2
        assert report.accuracy_rate == 0.0
        assert len(report.common_errors) >= 1
