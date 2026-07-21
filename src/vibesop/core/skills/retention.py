"""Skill retention policy — advisory lifecycle management.

Analyzes SkillEvaluation data and generates actionable retention
recommendations based on time decay and usage patterns.

Policy rules (advisory only, no automatic removal):
- Grade F for 30+ days with < 3 uses → suggest removal
- Grade D for 60+ days with no improvement → warn
- Grade A for 7+ consecutive days of active use → highlight as "recommended"
- 90+ days unused with grade C/D/F → auto-archive
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from vibesop.core.skills.evaluator import RoutingEvaluator

logger = logging.getLogger(__name__)


@dataclass
class DeprecatedRetentionSuggestion:
    """A single retention recommendation for a skill.

    DEPRECATED: Use feedback_loop.RetentionSuggestion instead.
    This class is kept for backwards compatibility.
    """

    skill_id: str
    action: str  # deprecate, warn, boost, none, archive
    reason: str
    grade: str
    days_since_last_use: int | None = None
    total_routes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "action": self.action,
            "reason": self.reason,
            "grade": self.grade,
            "days_since_last_use": self.days_since_last_use,
            "total_routes": self.total_routes,
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

    def analyze_skill(self, skill_id: str) -> DeprecatedRetentionSuggestion:
        """Analyze a single skill and return retention recommendation."""
        evaluation = self._evaluator.evaluate_skill(skill_id)
        if evaluation is None:
            return DeprecatedRetentionSuggestion(
                skill_id=skill_id,
                action="none",
                reason="No evaluation data available",
                grade="?",
                days_since_last_use=None,
                total_routes=0,
            )

        days_since = self._days_since(evaluation.last_used)
        grade = evaluation.grade
        uses = evaluation.total_routes

        # Rule: Grade F for 30+ days with < 3 uses → suggest removal
        if grade == "F" and days_since is not None and days_since >= 30 and uses < 3:
            return DeprecatedRetentionSuggestion(
                skill_id=skill_id,
                action="remove",
                reason=f"Grade F, only {uses} use(s), last used {days_since} days ago",
                grade=grade,
                days_since_last_use=days_since,
                total_routes=uses,
            )

        # Rule: Grade D for 60+ days with no improvement → warn
        if grade == "D" and days_since is not None and days_since >= 60:
            return DeprecatedRetentionSuggestion(
                skill_id=skill_id,
                action="warn",
                reason=f"Grade D, no improvement for {days_since} days",
                grade=grade,
                days_since_last_use=days_since,
                total_routes=uses,
            )

        # Rule: 90+ days unused with grade C/D/F → auto-archive
        if days_since is not None and days_since >= 90 and grade in ("C", "D", "F"):
            return DeprecatedRetentionSuggestion(
                skill_id=skill_id,
                action="archive",
                reason=f"Unused for {days_since} days, grade {grade} — auto-archive candidate",
                grade=grade,
                days_since_last_use=days_since,
                total_routes=uses,
            )

        # Rule: Grade A for 7+ days of active use → highlight
        if grade == "A" and days_since is not None and days_since < 7:
            return DeprecatedRetentionSuggestion(
                skill_id=skill_id,
                action="highlight",
                reason=f"Grade A, actively used ({uses} routes)",
                grade=grade,
                days_since_last_use=days_since,
                total_routes=uses,
            )

        return DeprecatedRetentionSuggestion(
            skill_id=skill_id,
            action="none",
            reason=f"Grade {grade}, {uses} route(s)",
            grade=grade,
            days_since_last_use=days_since,
            total_routes=uses,
        )

    def analyze_all(self) -> list[DeprecatedRetentionSuggestion]:
        """Analyze all skills and return actionable suggestions."""
        all_evals = self._evaluator.evaluate_all_skills()
        suggestions = []
        for skill_id in all_evals:
            suggestion = self.analyze_skill(skill_id)
            if suggestion.action != "none":
                suggestions.append(suggestion)
        # Sort by severity: archive > remove > warn > highlight
        severity = {"archive": 0, "remove": 1, "warn": 2, "highlight": 3}
        suggestions.sort(key=lambda s: severity.get(s.action, 99))
        return suggestions

    def apply_auto_actions(
        self, suggestions: list[DeprecatedRetentionSuggestion] | None = None
    ) -> int:
        """Apply automatic lifecycle transitions for retention recommendations.

        Auto-applies: archive → DEPRECATED, remove → DEPRECATED (advisory).
        Warn and highlight are informational only.

        Args:
            suggestions: Optional pre-computed suggestions. If None, analyze_all() is called.

        Returns:
            Number of automatic actions applied.
        """
        if suggestions is None:
            suggestions = self.analyze_all()

        applied = 0
        for s in suggestions:
            if s.action in ("archive", "remove"):
                try:
                    from vibesop.core.skills.config_manager import SkillConfigManager

                    SkillConfigManager.set_lifecycle(s.skill_id, "deprecated")
                    applied += 1
                except Exception as e:
                    logger.warning("Failed to deprecate skill %s: %s", s.skill_id, e)
        return applied

    def _days_since(self, timestamp: str | None) -> int | None:
        """Calculate days since a timestamp."""
        if timestamp is None:
            return None
        try:
            last = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            delta = datetime.now(last.tzinfo) - last
            return max(0, delta.days)
        except (ValueError, TypeError):
            return None
