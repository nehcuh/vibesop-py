"""Usage analytics and feedback collection for orchestration.

Records execution data, user feedback, and skill quality metrics
to enable continuous improvement of the routing system.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExecutionRecord:
    """Record of a single orchestration execution."""

    query: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    mode: str = "single"  # single or orchestrated
    primary_skill: str | None = None
    plan_steps: list[str] = field(default_factory=list)
    step_count: int = 0
    duration_ms: float = 0.0
    user_modified: bool = False  # Did user edit the plan?
    user_satisfied: bool | None = None  # User feedback
    routing_layers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "primary_skill": self.primary_skill,
            "plan_steps": self.plan_steps,
            "step_count": self.step_count,
            "duration_ms": self.duration_ms,
            "user_modified": self.user_modified,
            "user_satisfied": self.user_satisfied,
            "routing_layers": self.routing_layers,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionRecord:
        return cls(
            query=data["query"],
            timestamp=data.get("timestamp", datetime.now(UTC).isoformat()),
            mode=data.get("mode", "single"),
            primary_skill=data.get("primary_skill"),
            plan_steps=data.get("plan_steps", []),
            step_count=data.get("step_count", 0),
            duration_ms=data.get("duration_ms", 0.0),
            user_modified=data.get("user_modified", False),
            user_satisfied=data.get("user_satisfied"),
            routing_layers=data.get("routing_layers", []),
            metadata=data.get("metadata", {}),
        )


class AnalyticsStore:
    """Persistent store for execution analytics.

    Stores records as JSONL in .vibe/analytics.jsonl
    """

    def __init__(self, storage_dir: str | Path = ".vibe") -> None:
        self.storage_path = Path(storage_dir) / "analytics.jsonl"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, record: ExecutionRecord) -> None:
        """Append an execution record."""
        try:
            with self.storage_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Failed to record analytics: %s", e)

    def list_records(
        self,
        limit: int = 100,
        skill_id: str | None = None,
    ) -> list[ExecutionRecord]:
        """List recent execution records."""
        if not self.storage_path.exists():
            return []

        records: list[ExecutionRecord] = []
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in reversed(lines):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    if skill_id and data.get("primary_skill") != skill_id:
                        continue
                    records.append(ExecutionRecord.from_dict(data))
                    if len(records) >= limit:
                        break
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError as e:
            logger.warning("Failed to read analytics: %s", e)

        return list(reversed(records))

    def get_skill_stats(self, skill_id: str) -> dict[str, Any]:
        """Get usage statistics for a specific skill."""
        records = self.list_records(limit=1000, skill_id=skill_id)

        if not records:
            return {"total_uses": 0, "satisfaction_rate": None}

        total = len(records)
        satisfied = sum(1 for r in records if r.user_satisfied is True)
        dissatisfied = sum(1 for r in records if r.user_satisfied is False)
        modified = sum(1 for r in records if r.user_modified)

        return {
            "total_uses": total,
            "satisfaction_rate": satisfied / total if total > 0 else None,
            "dissatisfaction_rate": dissatisfied / total if total > 0 else None,
            "modification_rate": modified / total if total > 0 else None,
            "avg_duration_ms": sum(r.duration_ms for r in records) / total if total > 0 else 0,
        }

    def get_low_quality_skills(self, threshold: float = 0.5) -> list[tuple[str, float]]:
        """Identify skills with low satisfaction rates.

        Returns list of (skill_id, satisfaction_rate) tuples.
        """
        all_records = self.list_records(limit=1000)
        skill_ids = {r.primary_skill for r in all_records if r.primary_skill}

        low_quality: list[tuple[str, float]] = []
        for skill_id in skill_ids:
            stats = self.get_skill_stats(skill_id)
            satisfaction = stats.get("satisfaction_rate")
            total = stats.get("total_uses", 0)
            if total >= 3 and satisfaction is not None and satisfaction < threshold:
                low_quality.append((skill_id, satisfaction))

        return sorted(low_quality, key=lambda x: x[1])

    def get_popular_skills(self, limit: int = 20) -> list[tuple[str, int, float]]:
        """Get most-used skills with usage counts and avg satisfaction.

        Args:
            limit: Maximum number of skills to return

        Returns:
            List of (skill_id, use_count, satisfaction_rate) sorted by use_count desc
        """
        all_records = self.list_records(limit=2000)
        skill_counts: dict[str, int] = {}
        skill_satisfaction: dict[str, list[bool]] = {}

        for record in all_records:
            if record.primary_skill:
                skill_counts[record.primary_skill] = skill_counts.get(record.primary_skill, 0) + 1
                if record.user_satisfied is not None:
                    if record.primary_skill not in skill_satisfaction:
                        skill_satisfaction[record.primary_skill] = []
                    skill_satisfaction[record.primary_skill].append(record.user_satisfied)

        result: list[tuple[str, int, float]] = []
        for skill_id, count in skill_counts.items():
            sats = skill_satisfaction.get(skill_id, [])
            avg_sat = sum(sats) / len(sats) if sats else 0.5
            result.append((skill_id, count, avg_sat))

        result.sort(key=lambda x: (-x[1], -x[2]))
        return result[:limit]
