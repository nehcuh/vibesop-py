"""Feedback collection system for routing improvement."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibesop.core.models import RoutingResult


@dataclass
class FeedbackRecord:
    """A single routing feedback record."""

    query: str
    routed_skill: str
    was_correct: bool
    actual_skill: str | None = None
    confidence: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
    """Aggregated feedback report."""

    total_records: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    accuracy_rate: float = 0.0
    by_skill: dict[str, dict[str, int]] = field(default_factory=dict)
    by_confidence: dict[str, dict[str, int]] = field(default_factory=dict)
    common_errors: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
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
    """Collect and manage routing feedback."""

    def __init__(self, storage_path: str | Path = "~/.vibe/feedback.json"):
        storage = Path(storage_path).expanduser()
        self._storage_path = storage.with_suffix(".jsonl")  # Use JSONL for append performance
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
        if was_correct is None:
            was_correct = True

        primary = result.primary
        if primary is None:
            return

        self.collect_feedback(
            query=query,
            routed_skill=primary.skill_id,
            was_correct=was_correct,
            actual_skill=actual_skill,
            confidence=primary.confidence,
            context={
                "layer": primary.layer.value if primary.layer else "unknown",
                "source": primary.source,
                "alternatives": [alt.skill_id for alt in result.alternatives],
            },
        )

    def generate_report(self) -> FeedbackReport:
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

    def get_top_mismatches(self, top_n: int = 10) -> list[dict[str, Any]]:
        mismatches: dict[tuple[str, str], dict[str, Any]] = {}
        for record in self._records:
            if record.was_correct or not record.actual_skill:
                continue
            key = (record.routed_skill, record.actual_skill)
            if key not in mismatches:
                mismatches[key] = {
                    "routed_skill": record.routed_skill,
                    "actual_skill": record.actual_skill,
                    "count": 0,
                    "example_queries": [],
                    "total_confidence": 0.0,
                }
            entry = mismatches[key]
            entry["count"] += 1
            entry["total_confidence"] += record.confidence
            if len(entry["example_queries"]) < 3:
                entry["example_queries"].append(record.query)

        result = sorted(
            mismatches.values(),
            key=lambda m: m["count"],
            reverse=True,
        )[:top_n]

        for m in result:
            m["avg_confidence"] = m["total_confidence"] / m["count"]
            del m["total_confidence"]

        return result

    def get_high_confidence_errors(self, min_confidence: float = 0.8) -> list[dict[str, Any]]:
        mismatches = self.get_top_mismatches(top_n=100)
        return [m for m in mismatches if m["avg_confidence"] >= min_confidence]

    def get_records(self, limit: int | None = None) -> list[FeedbackRecord]:
        if limit:
            return self._records[-limit:]
        return self._records

    def clear_records(self) -> None:
        self._records = []
        # _save_records() no-ops on an empty list, so unlink the file to
        # actually remove persisted records (F-08 — otherwise purge is a no-op).
        if self._storage_path.exists():
            self._storage_path.unlink()

    def export_records(self, output_path: str | Path) -> None:
        output_path = Path(output_path).expanduser()

        data = [record.to_dict() for record in self._records]
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def import_records(self, input_path: str | Path) -> int:
        input_path = Path(input_path).expanduser()

        with input_path.open(encoding="utf-8") as f:
            data = json.load(f)

        for record_data in data:
            record = FeedbackRecord.from_dict(record_data)
            self._records.append(record)

        self._save_records()
        return len(data)

    def _load_records(self) -> None:
        if self._storage_path.exists():
            try:
                self._records = []
                with self._storage_path.open(encoding="utf-8") as f:
                    for raw_line in f:
                        stripped = raw_line.strip()
                        if not stripped:
                            continue
                        try:
                            data = json.loads(stripped)
                            self._records.append(FeedbackRecord.from_dict(data))
                        except (json.JSONDecodeError, KeyError):
                            pass
            except (json.JSONDecodeError, OSError, KeyError, UnicodeDecodeError):
                self._records = []

    def _save_records(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._records:
            return
        record = self._records[-1]
        with self._storage_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


# Convenience function for quick feedback collection
_collector_instance: FeedbackCollector | None = None


def _get_collector() -> FeedbackCollector:
    global _collector_instance  # noqa: PLW0603
    if _collector_instance is None:
        _collector_instance = FeedbackCollector()
    return _collector_instance


def collect_feedback(
    query: str,
    routed_skill: str,
    was_correct: bool,
    actual_skill: str | None = None,
    confidence: float = 0.0,
) -> None:
    _get_collector().collect_feedback(
        query=query,
        routed_skill=routed_skill,
        was_correct=was_correct,
        actual_skill=actual_skill,
        confidence=confidence,
    )


def get_feedback_report() -> FeedbackReport:
    return _get_collector().generate_report()


@dataclass
class SkillExecutionFeedback:
    """Post-execution feedback for a skill."""

    skill_id: str
    query: str
    was_helpful: bool | None = None
    execution_success: bool | None = None
    execution_time_ms: float | None = None
    notes: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
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
    """Collect post-execution feedback for skills."""

    def __init__(self, storage_path: str | Path = "~/.vibe/execution_feedback.json"):
        storage = Path(storage_path).expanduser()
        self._storage_path = storage.with_suffix(".jsonl")
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
        records = self._records
        if skill_id:
            records = [r for r in records if r.skill_id == skill_id]
        if limit:
            records = records[-limit:]
        return records

    def get_skill_summary(self, skill_id: str) -> dict[str, Any]:
        records = [r for r in self._records if r.skill_id == skill_id]
        if not records:
            return {"total": 0, "helpful_rate": None, "success_rate": None}

        helpful = [r for r in records if r.was_helpful is not None]
        success = [r for r in records if r.execution_success is not None]

        return {
            "total": len(records),
            "helpful_rate": sum(1 for r in helpful if r.was_helpful) / len(helpful)
            if helpful
            else None,
            "success_rate": sum(1 for r in success if r.execution_success) / len(success)
            if success
            else None,
            "avg_execution_time_ms": sum(
                r.execution_time_ms for r in records if r.execution_time_ms is not None
            )
            / len([r for r in records if r.execution_time_ms is not None])
            if any(r.execution_time_ms is not None for r in records)
            else None,
        }

    def clear_records(self) -> None:
        self._records = []
        # _save_records() no-ops on an empty list, so unlink the file to
        # actually remove persisted records (F-08 — otherwise purge is a no-op).
        if self._storage_path.exists():
            self._storage_path.unlink()

    def _load_records(self) -> None:
        if self._storage_path.exists():
            try:
                self._records = []
                with self._storage_path.open(encoding="utf-8") as f:
                    for raw_line in f:
                        stripped = raw_line.strip()
                        if not stripped:
                            continue
                        try:
                            data = json.loads(stripped)
                            self._records.append(SkillExecutionFeedback.from_dict(data))
                        except (json.JSONDecodeError, KeyError):
                            pass
            except (json.JSONDecodeError, OSError, KeyError, UnicodeDecodeError):
                self._records = []

    def _save_records(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._records:
            return
        record = self._records[-1]
        with self._storage_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
