"""Skill suggestion collector — bridge from instinct detection to skill creation.

Connects InstinctLearner's SequencePattern detection to actionable skill
suggestions that users can accept to auto-generate and register skills.

Lifecycle:
    1. InstinctLearner.record_sequence() detects repeatable patterns
    2. This collector stores them as SkillSuggestion candidates
    3. When pending candidates reach threshold, user is prompted
    4. User accepts → SKILL.md generated + auto-configured + registered
    5. User dismisses → candidate removed from pending
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SkillSuggestion:
    """A candidate skill detected from usage patterns."""

    id: str
    pattern_steps: list[str]
    success_rate: float
    occurrences: int
    suggested_name: str
    suggested_description: str = ""
    confidence: float = 0.5
    context_tags: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | dismissed | created
    created_at: datetime = field(default_factory=datetime.now)
    skill_id: str | None = None  # Set after creation

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pattern_steps": self.pattern_steps,
            "success_rate": self.success_rate,
            "occurrences": self.occurrences,
            "suggested_name": self.suggested_name,
            "suggested_description": self.suggested_description,
            "confidence": self.confidence,
            "context_tags": self.context_tags,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "skill_id": self.skill_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillSuggestion:
        return cls(
            id=data["id"],
            pattern_steps=data.get("pattern_steps", []),
            success_rate=data.get("success_rate", 0.0),
            occurrences=data.get("occurrences", 0),
            suggested_name=data["suggested_name"],
            suggested_description=data.get("suggested_description", ""),
            confidence=data.get("confidence", 0.5),
            context_tags=data.get("context_tags", []),
            status=data.get("status", "pending"),
            created_at=datetime.fromisoformat(data["created_at"]),
            skill_id=data.get("skill_id"),
        )

    @classmethod
    def from_sequence_pattern(
        cls,
        pattern: Any,  # SequencePattern from instinct/learner.py
        suggested_name: str | None = None,
    ) -> SkillSuggestion:
        name = suggested_name or cls._infer_name(pattern.steps)
        description = cls._infer_description(pattern.steps, pattern.context_tags)

        return cls(
            id=f"sug_{pattern.sequence_hash}",
            pattern_steps=pattern.steps,
            success_rate=pattern.success_rate,
            occurrences=pattern.total_count,
            suggested_name=name,
            suggested_description=description,
            confidence=pattern.success_rate * 0.7 + min(pattern.total_count / 10, 1.0) * 0.3,
            context_tags=pattern.context_tags,
        )

    @staticmethod
    def _infer_name(steps: list[str]) -> str:
        if not steps:
            return "auto-workflow"
        keywords = []
        for step in steps:
            parts = step.replace(":", " ").split()
            for p in parts:
                clean = p.strip().lower()
                if clean in ("bash", "edit", "write", "read", "glob", "grep", "task"):
                    continue
                if len(clean) >= 3:
                    keywords.append(clean)
        if not keywords:
            keywords = [s.split(":")[-1].strip().lower() for s in steps]
        name = "-".join(keywords[:3])
        return name[:40] if len(name) <= 40 else name[:37] + "...-wrk"

    @staticmethod
    def _infer_description(steps: list[str], tags: list[str]) -> str:
        step_summary = " → ".join(steps[:5])
        tag_str = f" ({', '.join(tags)})" if tags else ""
        return f"Auto-detected workflow: {step_summary}{tag_str}"


class SkillSuggestionCollector:
    """Collect and manage skill suggestions from learned patterns.

    Example:
        >>> collector = SkillSuggestionCollector()
        >>> collector.add_from_pattern(sequence_pattern)
        >>> if collector.should_prompt():
        ...     for s in collector.get_pending():
        ...         print(f"Suggested: {s.suggested_name}")
    """

    DEFAULT_THRESHOLD = 3

    def __init__(self, storage_dir: Path | None = None) -> None:
        self._storage_dir = storage_dir or Path(".vibe/instincts")
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._suggestions: dict[str, SkillSuggestion] = {}
        self._load()

    @property
    def storage_file(self) -> Path:
        return self._storage_dir / "skill_candidates.jsonl"

    def add_from_pattern(
        self,
        pattern: Any,  # SequencePattern
        suggested_name: str | None = None,
    ) -> SkillSuggestion | None:
        suggestion = SkillSuggestion.from_sequence_pattern(pattern, suggested_name)

        if suggestion.id in self._suggestions:
            existing = self._suggestions[suggestion.id]
            if existing.status == "dismissed":
                return None
            existing.occurrences = suggestion.occurrences
            existing.success_rate = suggestion.success_rate
            existing.confidence = suggestion.confidence
        else:
            self._suggestions[suggestion.id] = suggestion

        self._save()
        return self._suggestions[suggestion.id]

    def get_pending(self) -> list[SkillSuggestion]:
        return sorted(
            [s for s in self._suggestions.values() if s.status == "pending"],
            key=lambda s: s.confidence,
            reverse=True,
        )

    def should_prompt(self, threshold: int | None = None) -> bool:
        threshold = threshold or self.DEFAULT_THRESHOLD
        return len(self.get_pending()) >= threshold

    def dismiss(self, suggestion_id: str) -> None:
        if suggestion_id in self._suggestions:
            self._suggestions[suggestion_id].status = "dismissed"
            self._save()

    def dismiss_all(self) -> int:
        count = 0
        for s in self._suggestions.values():
            if s.status == "pending":
                s.status = "dismissed"
                count += 1
        self._save()
        return count

    def mark_created(self, suggestion_id: str, skill_id: str) -> None:
        if suggestion_id in self._suggestions:
            self._suggestions[suggestion_id].status = "created"
            self._suggestions[suggestion_id].skill_id = skill_id
            self._save()

    def get(self, suggestion_id: str) -> SkillSuggestion | None:
        return self._suggestions.get(suggestion_id)

    def get_stats(self) -> dict[str, Any]:
        pending = self.get_pending()
        created = [s for s in self._suggestions.values() if s.status == "created"]
        dismissed = [s for s in self._suggestions.values() if s.status == "dismissed"]
        return {
            "total": len(self._suggestions),
            "pending": len(pending),
            "created": len(created),
            "dismissed": len(dismissed),
            "will_prompt": self.should_prompt(),
        }

    def _load(self) -> None:
        if not self.storage_file.exists():
            return
        self._suggestions = {}
        with self.storage_file.open() as f:
            for raw_line in f:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    suggestion = SkillSuggestion.from_dict(data)
                    self._suggestions[suggestion.id] = suggestion
                except (json.JSONDecodeError, KeyError):
                    continue

    def _save(self) -> None:
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_file.open("w") as f:
            for suggestion in self._suggestions.values():
                f.write(json.dumps(suggestion.to_dict(), default=str) + "\n")
