"""Feedback collection system for routing improvement.

This module provides tools for collecting, storing, and analyzing
user feedback on routing decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from vibesop.core.models import RoutingResult


@dataclass
class FeedbackRecord:
    """A single routing feedback record.

    Attributes:
        query: User's query text
        routed_skill: The skill that was routed to
        was_correct: Whether the routing was correct
        actual_skill: The correct skill if routing was wrong
        confidence: Confidence score of the routing
        timestamp: When the feedback was collected
        context: Additional context (layer, model, etc.)
    """

    query: str
    routed_skill: str
    was_correct: bool
    actual_skill: str | None = None
    confidence: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query": self.query,
            "routed_skill": self.routed_skill,
            "was_correct": self.was_correct,
            "actual_skill": self.actual_skill,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeedbackRecord:
        """Create from dictionary."""
        return cls(
            query=data.get("query", ""),
            routed_skill=data.get("routed_skill", ""),
            was_correct=data.get("was_correct", True),
            actual_skill=data.get("actual_skill"),
            confidence=data.get("confidence", 0.0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            context=data.get("context", {}),
        )


@dataclass
class FeedbackReport:
    """Aggregated feedback report.

    Attributes:
        total_records: Total number of feedback records
        correct_count: Number of correct routings
        incorrect_count: Number of incorrect routings
        accuracy_rate: Overall accuracy rate
        by_skill: Accuracy breakdown by skill
        by_confidence: Accuracy breakdown by confidence level
        common_errors: Most common routing errors
    """

    total_records: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    accuracy_rate: float = 0.0
    by_skill: dict[str, dict[str, int]] = field(default_factory=dict)
    by_confidence: dict[str, dict[str, int]] = field(default_factory=dict)
    common_errors: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_records": self.total_records,
            "correct_count": self.correct_count,
            "incorrect_count": self.incorrect_count,
            "accuracy_rate": self.accuracy_rate,
            "by_skill": self.by_skill,
            "by_confidence": self.by_confidence,
            "common_errors": self.common_errors,
        }


class FeedbackCollector:
    """Collect and manage routing feedback.

    Example:
        >>> collector = FeedbackCollector()
        >>> collector.collect_feedback(
        ...     query="帮我 review 代码",
        ...     routed_skill="superpowers/review",
        ...     was_correct=True,
        ... )
        >>> report = collector.generate_report()
        >>> print(f"Accuracy: {report.accuracy_rate:.1%}")
    """

    def __init__(self, storage_path: str | Path = "~/.vibe/feedback.json"):
        """Initialize feedback collector.

        Args:
            storage_path: Path to feedback storage file
        """
        self._storage_path = Path(storage_path).expanduser()
        self._records: list[FeedbackRecord] = []
        self._load_records()

    def collect_feedback(
        self,
        query: str,
        routed_skill: str,
        was_correct: bool,
        actual_skill: str | None = None,
        confidence: float = 0.0,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Collect a routing feedback record.

        Args:
            query: User's query text
            routed_skill: The skill that was routed to
            was_correct: Whether the routing was correct
            actual_skill: The correct skill if routing was wrong
            confidence: Confidence score of the routing
            context: Additional context
        """
        record = FeedbackRecord(
            query=query,
            routed_skill=routed_skill,
            was_correct=was_correct,
            actual_skill=actual_skill,
            confidence=confidence,
            context=context or {},
        )

        self._records.append(record)
        self._save_records()

    def collect_from_routing_result(
        self,
        query: str,
        result: RoutingResult,
        was_correct: bool | None = None,
        actual_skill: str | None = None,
    ) -> None:
        """Collect feedback from a routing result.

        Args:
            query: User's query
            result: Routing result
            was_correct: Whether routing was correct (None = assume correct)
            actual_skill: Correct skill if wrong
        """
        # If not specified, assume routing was correct
        if was_correct is None:
            was_correct = True

        self.collect_feedback(
            query=query,
            routed_skill=result.primary.skill_id,
            was_correct=was_correct,
            actual_skill=actual_skill,
            confidence=result.primary.confidence,
            context={
                "layer": result.primary.layer.value if result.primary.layer else "unknown",
                "source": result.primary.source,
                "alternatives": [alt.skill_id for alt in result.alternatives],
            },
        )

    def generate_report(self) -> FeedbackReport:
        """Generate aggregated feedback report.

        Returns:
            Feedback report with statistics and insights
        """
        if not self._records:
            return FeedbackReport()

        correct = sum(1 for r in self._records if r.was_correct)
        incorrect = len(self._records) - correct
        accuracy = correct / len(self._records) if self._records else 0.0

        # Break down by skill
        by_skill: dict[str, dict[str, int]] = {}
        for record in self._records:
            skill = record.routed_skill
            if skill not in by_skill:
                by_skill[skill] = {"correct": 0, "incorrect": 0}

            if record.was_correct:
                by_skill[skill]["correct"] += 1
            else:
                by_skill[skill]["incorrect"] += 1

        # Break down by confidence
        by_confidence: dict[str, dict[str, int]] = {
            "high (0.7-1.0)": {"correct": 0, "incorrect": 0},
            "medium (0.4-0.7)": {"correct": 0, "incorrect": 0},
            "low (0.0-0.4)": {"correct": 0, "incorrect": 0},
        }

        for record in self._records:
            if record.confidence >= 0.7:
                bucket = "high (0.7-1.0)"
            elif record.confidence >= 0.4:
                bucket = "medium (0.4-0.7)"
            else:
                bucket = "low (0.0-0.4)"

            if record.was_correct:
                by_confidence[bucket]["correct"] += 1
            else:
                by_confidence[bucket]["incorrect"] += 1

        # Most common errors
        error_counts: dict[str, int] = {}
        for record in self._records:
            if not record.was_correct and record.actual_skill:
                error_key = f"{record.routed_skill} → {record.actual_skill}"
                error_counts[error_key] = error_counts.get(error_key, 0) + 1

        common_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return FeedbackReport(
            total_records=len(self._records),
            correct_count=correct,
            incorrect_count=incorrect,
            accuracy_rate=accuracy,
            by_skill=by_skill,
            by_confidence=by_confidence,
            common_errors=common_errors,
        )

    def get_records(self, limit: int | None = None) -> list[FeedbackRecord]:
        """Get feedback records.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of feedback records
        """
        if limit:
            return self._records[-limit:]
        return self._records

    def clear_records(self) -> None:
        """Clear all feedback records."""
        self._records = []
        self._save_records()

    def export_records(self, output_path: str | Path) -> None:
        """Export records to JSON file.

        Args:
            output_path: Path to output file
        """
        output_path = Path(output_path).expanduser()

        data = [record.to_dict() for record in self._records]
        with output_path.open("w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def import_records(self, input_path: str | Path) -> int:
        """Import records from JSON file.

        Args:
            input_path: Path to input file

        Returns:
            Number of records imported
        """
        input_path = Path(input_path).expanduser()

        with input_path.open() as f:
            data = json.load(f)

        for record_data in data:
            record = FeedbackRecord.from_dict(record_data)
            self._records.append(record)

        self._save_records()
        return len(data)

    def _load_records(self) -> None:
        """Load records from storage."""
        if self._storage_path.exists():
            try:
                with self._storage_path.open() as f:
                    data = json.load(f)
                    self._records = [FeedbackRecord.from_dict(r) for r in data]
            except Exception:
                # If file is corrupted, start fresh
                self._records = []

    def _save_records(self) -> None:
        """Save records to storage."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = [record.to_dict() for record in self._records]
        with self._storage_path.open("w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


# Convenience function for quick feedback collection
_collector_instance: FeedbackCollector | None = None


def collect_feedback(
    query: str,
    routed_skill: str,
    was_correct: bool,
    actual_skill: str | None = None,
    confidence: float = 0.0,
) -> None:
    """Quick function to collect feedback.

    Example:
        >>> collect_feedback(
        ...     query="帮我 review 代码",
        ...     routed_skill="superpowers/review",
        ...     was_correct=True,
        ... )
    """
    global _collector_instance

    if _collector_instance is None:
        _collector_instance = FeedbackCollector()

    _collector_instance.collect_feedback(
        query=query,
        routed_skill=routed_skill,
        was_correct=was_correct,
        actual_skill=actual_skill,
        confidence=confidence,
    )


def get_feedback_report() -> FeedbackReport:
    """Get the current feedback report.

    Example:
        >>> report = get_feedback_report()
        >>> print(f"Accuracy: {report.accuracy_rate:.1%}")
    """
    global _collector_instance

    if _collector_instance is None:
        _collector_instance = FeedbackCollector()

    return _collector_instance.generate_report()


@dataclass
class SkillExecutionFeedback:
    """Post-execution feedback for a skill.

    Captures user satisfaction and execution quality beyond routing correctness.

    Attributes:
        skill_id: The skill that was executed
        query: User's original query
        was_helpful: User rating (thumbs up/down)
        execution_success: Whether execution completed without errors
        execution_time_ms: Execution duration in milliseconds
        notes: Optional user notes
        timestamp: When the feedback was collected
    """

    skill_id: str
    query: str
    was_helpful: bool | None = None
    execution_success: bool | None = None
    execution_time_ms: float | None = None
    notes: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "skill_id": self.skill_id,
            "query": self.query,
            "was_helpful": self.was_helpful,
            "execution_success": self.execution_success,
            "execution_time_ms": self.execution_time_ms,
            "notes": self.notes,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillExecutionFeedback:
        """Create from dictionary."""
        return cls(
            skill_id=data.get("skill_id", ""),
            query=data.get("query", ""),
            was_helpful=data.get("was_helpful"),
            execution_success=data.get("execution_success"),
            execution_time_ms=data.get("execution_time_ms"),
            notes=data.get("notes"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


class ExecutionFeedbackCollector:
    """Collect post-execution feedback for skills.

    Stores execution feedback separately from routing feedback
    to enable composite quality scoring.

    Example:
        >>> collector = ExecutionFeedbackCollector()
        >>> collector.collect(
        ...     skill_id="gstack/review",
        ...     query="review my code",
        ...     was_helpful=True,
        ...     execution_success=True,
        ...     execution_time_ms=1250.0,
        ... )
    """

    def __init__(self, storage_path: str | Path = "~/.vibe/execution_feedback.json"):
        self._storage_path = Path(storage_path).expanduser()
        self._records: list[SkillExecutionFeedback] = []
        self._load_records()

    def collect(
        self,
        skill_id: str,
        query: str,
        was_helpful: bool | None = None,
        execution_success: bool | None = None,
        execution_time_ms: float | None = None,
        notes: str | None = None,
    ) -> None:
        """Collect a post-execution feedback record."""
        record = SkillExecutionFeedback(
            skill_id=skill_id,
            query=query,
            was_helpful=was_helpful,
            execution_success=execution_success,
            execution_time_ms=execution_time_ms,
            notes=notes,
        )
        self._records.append(record)
        self._save_records()

    def get_records(
        self,
        skill_id: str | None = None,
        limit: int | None = None,
    ) -> list[SkillExecutionFeedback]:
        """Get execution feedback records."""
        records = self._records
        if skill_id:
            records = [r for r in records if r.skill_id == skill_id]
        if limit:
            records = records[-limit:]
        return records

    def get_skill_summary(self, skill_id: str) -> dict[str, Any]:
        """Get aggregated execution feedback for a skill."""
        records = [r for r in self._records if r.skill_id == skill_id]
        if not records:
            return {"total": 0, "helpful_rate": None, "success_rate": None}

        helpful = [r for r in records if r.was_helpful is not None]
        success = [r for r in records if r.execution_success is not None]

        return {
            "total": len(records),
            "helpful_rate": sum(1 for r in helpful if r.was_helpful) / len(helpful) if helpful else None,
            "success_rate": sum(1 for r in success if r.execution_success) / len(success) if success else None,
            "avg_execution_time_ms": sum(r.execution_time_ms for r in records if r.execution_time_ms is not None) / len([r for r in records if r.execution_time_ms is not None]) if any(r.execution_time_ms is not None for r in records) else None,
        }

    def clear_records(self) -> None:
        """Clear all execution feedback records."""
        self._records = []
        self._save_records()

    def _load_records(self) -> None:
        if self._storage_path.exists():
            try:
                with self._storage_path.open() as f:
                    data = json.load(f)
                    self._records = [SkillExecutionFeedback.from_dict(r) for r in data]
            except Exception:
                self._records = []

    def _save_records(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = [record.to_dict() for record in self._records]
        with self._storage_path.open("w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
