"""Skill retention policy — advisory lifecycle management.

Analyzes SkillEvaluation data and generates actionable retention
recommendations based on time decay and usage patterns.

Policy rules (advisory only, no automatic removal):
- Grade F for 30+ days with < 3 uses → suggest removal
- Grade D for 60+ days with no improvement → warn
- Grade A for 7+ consecutive days of active use → highlight as "recommended"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from vibesop.core.skills.evaluator import RoutingEvaluator, SkillEvaluation


@dataclass
class RetentionSuggestion:
    """A single retention recommendation for a skill.

    Attributes:
        skill_id: Target skill
        action: "remove" | "warn" | "highlight" | "none"
        reason: Human-readable explanation
        grade: Current letter grade
        days_since_last_use: Number of days
        total_uses: Total usage count
    """

    skill_id: str
    action: str  # remove, warn, highlight, none
    reason: str
    grade: str
    days_since_last_use: int | None
    total_uses: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "action": self.action,
            "reason": self.reason,
            "grade": self.grade,
            "days_since_last_use": self.days_since_last_use,
            "total_uses": self.total_uses,
        }


class RetentionPolicy:
    """Advisory retention policy for skills.

    Example:
        >>> policy = RetentionPolicy()
        >>> suggestions = policy.analyze_skill("my-skill")
        >>> for s in suggestions:
        ...     print(f"{s.skill_id}: {s.action} — {s.reason}")
    """

    def __init__(self, evaluator: RoutingEvaluator | None = None) -> None:
        self._evaluator = evaluator or RoutingEvaluator()

    def analyze_skill(self, skill_id: str) -> RetentionSuggestion:
        """Analyze a single skill and return retention recommendation."""
        evaluation = self._evaluator.evaluate_skill(skill_id)
        if evaluation is None:
            return RetentionSuggestion(
                skill_id=skill_id,
                action="none",
                reason="No evaluation data available",
                grade="?",
                days_since_last_use=None,
                total_uses=0,
            )

        days_since = self._days_since(evaluation.last_used)
        grade = evaluation.grade
        uses = evaluation.total_routes

        # Rule: Grade F for 30+ days with < 3 uses → suggest removal
        if grade == "F" and days_since is not None and days_since >= 30 and uses < 3:
            return RetentionSuggestion(
                skill_id=skill_id,
                action="remove",
                reason=f"Grade F, only {uses} use(s), last used {days_since} days ago",
                grade=grade,
                days_since_last_use=days_since,
                total_uses=uses,
            )

        # Rule: Grade D for 60+ days with no improvement → warn
        if grade == "D" and days_since is not None and days_since >= 60:
            return RetentionSuggestion(
                skill_id=skill_id,
                action="warn",
                reason=f"Grade D, no improvement for {days_since} days",
                grade=grade,
                days_since_last_use=days_since,
                total_uses=uses,
            )

        # Rule: Grade A for 7+ days of active use → highlight
        if grade == "A" and days_since is not None and days_since < 7:
            return RetentionSuggestion(
                skill_id=skill_id,
                action="highlight",
                reason=f"Grade A, actively used ({uses} routes)",
                grade=grade,
                days_since_last_use=days_since,
                total_uses=uses,
            )

        return RetentionSuggestion(
            skill_id=skill_id,
            action="none",
            reason=f"Grade {grade}, {uses} route(s)",
            grade=grade,
            days_since_last_use=days_since,
            total_uses=uses,
        )

    def analyze_all(self) -> list[RetentionSuggestion]:
        """Analyze all skills and return actionable suggestions."""
        all_evals = self._evaluator.evaluate_all_skills()
        suggestions = []
        for skill_id in all_evals:
            suggestion = self.analyze_skill(skill_id)
            if suggestion.action != "none":
                suggestions.append(suggestion)
        # Sort by severity: remove > warn > highlight
        severity = {"remove": 0, "warn": 1, "highlight": 2}
        suggestions.sort(key=lambda s: severity.get(s.action, 99))
        return suggestions

    def _days_since(self, timestamp: str | None) -> int | None:
        """Calculate days since a timestamp."""
        if timestamp is None:
            return None
        try:
            last = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            delta = datetime.now(last.tzinfo) - last
            return max(0, delta.days)
        except Exception:
            return None
