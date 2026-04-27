"""Lightweight badge/achievement system for VibeSOP skill ecosystem gamification.

Badges are stored in ~/.vibe/badges.json.
This is intentionally lightweight - no DB, no complex state machine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class BadgeType(StrEnum):
    """Types of badges a user can earn."""

    FIRST_FEEDBACK = "first_feedback"
    SKILL_CHAMPION = "skill_champion"
    QUALITY_MASTER = "quality_master"
    ECOSYSTEM_GUARDIAN = "ecosystem_guardian"


@dataclass
class Badge:
    """A single earned badge."""

    type: BadgeType
    awarded_at: str
    skill_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "type": self.type.value,
            "awarded_at": self.awarded_at,
            "skill_id": self.skill_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Badge:
        """Deserialize from dict."""
        return cls(
            type=BadgeType(data["type"]),
            awarded_at=data["awarded_at"],
            skill_id=data.get("skill_id"),
        )


_BADGE_METADATA: dict[BadgeType, dict[str, str]] = {
    BadgeType.FIRST_FEEDBACK: {
        "icon": "🎖️",
        "title": "First Feedback",
        "description": "You've started improving the ecosystem!",
    },
    BadgeType.SKILL_CHAMPION: {
        "icon": "🏆",
        "title": "Skill Champion",
        "description": "Your skill has been used 10 times!",
    },
    BadgeType.QUALITY_MASTER: {
        "icon": "✨",
        "title": "Quality Master",
        "description": "All your skills are performing well!",
    },
    BadgeType.ECOSYSTEM_GUARDIAN: {
        "icon": "🛡️",
        "title": "Ecosystem Guardian",
        "description": "You've given 5 feedbacks to improve skills!",
    },
}


def get_badge_display(badge_type: BadgeType) -> dict[str, str]:
    """Get display metadata for a badge type."""
    return _BADGE_METADATA.get(
        badge_type,
        {
            "icon": "🏅",
            "title": badge_type.value,
            "description": "",
        },
    )


class BadgeTracker:
    """Track and award badges stored in user config.

    Storage location: ~/.vibe/badges.json
    """

    def __init__(self, data_path: str | Path | None = None) -> None:
        self._data_path = Path(
            data_path or Path.home() / ".vibe" / "badges.json",
        )
        self._badges: list[Badge] = []
        self._load()

    def _load(self) -> None:
        """Load badges from data file."""
        if not self._data_path.exists():
            return
        try:
            with self._data_path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        badge_list = data.get("badges", [])
        self._badges = [Badge.from_dict(b) for b in badge_list if isinstance(b, dict)]

    def _save(self) -> None:
        """Save badges to data file."""
        self._data_path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {"badges": [b.to_dict() for b in self._badges]}

        # Atomic write to prevent corruption
        import tempfile

        try:
            fd, tmp_path = tempfile.mkstemp(dir=self._data_path.parent, prefix=".tmp_badges_")
            with open(fd, "w", encoding="utf-8", closefd=False) as f:
                json.dump(data, f, indent=2)
            Path(tmp_path).replace(self._data_path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_badges(self) -> list[Badge]:
        """Return all earned badges (newest first)."""
        return list(self._badges)

    def has_badge(self, badge_type: BadgeType) -> bool:
        """Check if user has earned a specific badge."""
        return any(b.type == badge_type for b in self._badges)

    def award(self, badge_type: BadgeType, skill_id: str | None = None) -> Badge | None:
        """Award a badge if not already earned. Returns the badge or None."""
        if self.has_badge(badge_type):
            return None
        badge = Badge(
            type=badge_type,
            awarded_at=datetime.now(UTC).isoformat(),
            skill_id=skill_id,
        )
        self._badges.append(badge)
        self._save()
        return badge

    # ------------------------------------------------------------------
    # Event-driven checks
    # ------------------------------------------------------------------

    def check_feedback_event(self) -> list[Badge]:
        """Check if a feedback event triggers new badges.

        Returns list of newly awarded badges.
        """
        newly_awarded: list[Badge] = []

        # FIRST_FEEDBACK: first time giving any feedback
        badge = self.award(BadgeType.FIRST_FEEDBACK)
        if badge:
            newly_awarded.append(badge)

        # ECOSYSTEM_GUARDIAN: 5+ feedbacks given
        feedback_count = self._count_feedbacks()
        if feedback_count >= 5:
            badge = self.award(BadgeType.ECOSYSTEM_GUARDIAN)
            if badge:
                newly_awarded.append(badge)

        return newly_awarded

    def check_route_event(self, skill_id: str, route_history: list[dict[str, Any]]) -> list[Badge]:
        """Check if a routing event triggers new badges.

        Args:
            skill_id: The skill that was just routed to.
            route_history: List of previous route decisions.

        Returns list of newly awarded badges.
        """
        newly_awarded: list[Badge] = []

        # SKILL_CHAMPION: skill used 10 times total
        count = sum(1 for r in route_history if r.get("skill_id") == skill_id)
        if count >= 10:
            badge = self.award(BadgeType.SKILL_CHAMPION, skill_id=skill_id)
            if badge:
                newly_awarded.append(badge)

        return newly_awarded

    def check_quality_master(self, all_evals: dict[str, Any]) -> list[Badge]:
        """Check if all skills meet quality threshold.

        Args:
            all_evals: Mapping of skill_id -> evaluation object with .grade.

        Returns list of newly awarded badges.
        """
        newly_awarded: list[Badge] = []

        if not all_evals:
            return newly_awarded

        # QUALITY_MASTER: all evaluated skills are Grade B or better
        grades = [getattr(ev, "grade", None) for ev in all_evals.values()]
        if grades and all(g in ("A", "B") for g in grades if g):
            badge = self.award(BadgeType.QUALITY_MASTER)
            if badge:
                newly_awarded.append(badge)

        return newly_awarded

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _count_feedbacks(self) -> int:
        """Count total feedback records on disk."""
        feedback_path = Path.home() / ".vibe" / "execution_feedback.json"
        if not feedback_path.exists():
            return 0
        import json

        try:
            with feedback_path.open(encoding="utf-8") as f:
                data = json.load(f)
            return len(data) if isinstance(data, list) else 0
        except (OSError, json.JSONDecodeError):
            return 0
