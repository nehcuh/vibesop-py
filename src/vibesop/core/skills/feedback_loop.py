"""Feedback loop — closes the gap between evaluation and action.

Connects SkillEvaluator quality scores to lifecycle management:
- F-grade skills with sufficient data → auto-deprecate
- A-grade skills → routing priority boost
- Generates retention suggestions for user review
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

from vibesop.core.skills.config_manager import SkillConfigManager
from vibesop.core.skills.evaluator import RoutingEvaluator, SkillEvaluation

logger = logging.getLogger(__name__)


@dataclass
class RetentionSuggestion:
    """Actionable suggestion based on skill evaluation."""

    skill_id: str
    action: str  # "deprecate", "warn", "boost", "none"
    reason: str
    grade: str
    days_since_last_use: int | None
    total_routes: int
    quality_score: float


class FeedbackLoop:
    """Autonomous feedback loop for skill quality management.

    Analyzes skill evaluations and takes automated actions:
    - Deprecates F-grade skills with sufficient data
    - Boosts A-grade skills in routing priority
    - Generates retention suggestions for user review

    Example:
        >>> loop = FeedbackLoop(project_root=Path("."))
        >>> suggestions = loop.analyze_all()
        >>> for s in suggestions:
        ...     print(f"{s.skill_id}: {s.action} — {s.reason}")
    """

    F_QUALITY_THRESHOLD = 0.30
    F_MIN_ROUTES = 3
    A_QUALITY_THRESHOLD = 0.90

    def __init__(
        self,
        project_root: str | Path = ".",
        evaluator: RoutingEvaluator | None = None,
    ) -> None:
        self._project_root = Path(project_root)
        self._evaluator = evaluator or RoutingEvaluator(project_root=project_root)

    def analyze_all(self, auto_deprecate: bool = True) -> list[RetentionSuggestion]:
        """Analyze all skills and return actionable suggestions.

        Args:
            auto_deprecate: If True, automatically deprecates F-grade skills.
                          If False, only returns suggestions for user review.

        Returns:
            List of RetentionSuggestion objects.
        """
        suggestions: list[RetentionSuggestion] = []
        evaluations = self._evaluator.evaluate_all_skills()

        for skill_id, evaluation in evaluations.items():
            suggestion = self._analyze_skill(skill_id, evaluation)
            if suggestion is None:
                continue
            suggestions.append(suggestion)

            if auto_deprecate and suggestion.action == "deprecate":
                self._apply_deprecation(skill_id, suggestion.reason)
            elif auto_deprecate and suggestion.action == "archive":
                self._apply_archive(skill_id, suggestion.reason)
            elif auto_deprecate and suggestion.action == "boost":
                self._apply_boost(skill_id)

        return sorted(suggestions, key=lambda s: s.quality_score)

    def _analyze_skill(
        self, skill_id: str, evaluation: SkillEvaluation
    ) -> RetentionSuggestion | None:
        """Analyze a single skill evaluation and produce a suggestion."""
        grade = evaluation.grade
        quality = evaluation.quality_score

        # Compute days since last use
        days_since = None
        if evaluation.last_used:
            try:
                from datetime import datetime

                last = datetime.fromisoformat(evaluation.last_used)
                now = datetime.now(UTC).replace(tzinfo=None)
                days_since = (now - last).days
            except (ValueError, TypeError):
                days_since = None

        # F-grade: strong suggestion to deprecate
        if grade == "F" and evaluation.total_routes >= self.F_MIN_ROUTES:
            delay_msg = ""
            if days_since is not None and days_since >= 30:
                delay_msg = f" (unused for {days_since}d)"
            return RetentionSuggestion(
                skill_id=skill_id,
                action="deprecate",
                reason=f"Quality score {quality:.0%}, grade {grade}{delay_msg}",
                grade=grade,
                days_since_last_use=days_since,
                total_routes=evaluation.total_routes,
                quality_score=quality,
            )

        # D-grade: warn but don't deprecate
        if grade == "D" and evaluation.total_routes >= self.F_MIN_ROUTES:
            return RetentionSuggestion(
                skill_id=skill_id,
                action="warn",
                reason=f"Quality score {quality:.0%}, grade {grade} — consider reviewing",
                grade=grade,
                days_since_last_use=days_since,
                total_routes=evaluation.total_routes,
                quality_score=quality,
            )

        # 90+ days unused with grade C/D/F → archive
        if days_since is not None and days_since >= 90 and grade in ("C", "D", "F"):
            return RetentionSuggestion(
                skill_id=skill_id,
                action="archive",
                reason=f"Unused for {days_since}d, grade {grade} — auto-archive candidate",
                grade=grade,
                days_since_last_use=days_since,
                total_routes=evaluation.total_routes,
                quality_score=quality,
            )

        # A-grade: boost
        if grade == "A" and evaluation.total_routes >= self.F_MIN_ROUTES:
            return RetentionSuggestion(
                skill_id=skill_id,
                action="boost",
                reason=f"Quality score {quality:.0%}, grade {grade} — high performer",
                grade=grade,
                days_since_last_use=days_since,
                total_routes=evaluation.total_routes,
                quality_score=quality,
            )

        return None

    def _apply_deprecation(self, skill_id: str, reason: str) -> None:
        """Deprecate a skill."""
        try:
            SkillConfigManager.set_lifecycle(skill_id, "deprecated")
            logger.info("Auto-deprecated skill %s: %s", skill_id, reason)
        except (ValueError, OSError, KeyError, AttributeError):
            logger.warning("Failed to deprecate skill %s", skill_id)

    def _apply_archive(self, skill_id: str, reason: str) -> None:
        """Archive a stale skill."""
        try:
            SkillConfigManager.set_lifecycle(skill_id, "archived")
            logger.info("Auto-archived skill %s: %s", skill_id, reason)
        except (ValueError, OSError, KeyError, AttributeError):
            logger.warning("Failed to archive skill %s", skill_id)

    def _apply_boost(self, skill_id: str) -> None:
        """Boost a high-quality skill — ensure it stays active if deprecated."""
        try:
            config = SkillConfigManager.get_skill_config(skill_id)
            if config and config.lifecycle == "deprecated":
                SkillConfigManager.set_lifecycle(skill_id, "active")
                logger.info("Auto-boosted skill %s back to active", skill_id)
        except (ValueError, OSError, KeyError, AttributeError):
            logger.warning("Failed to boost skill %s", skill_id)

    def generate_report(self) -> dict[str, Any]:
        """Generate a summary report with evaluation results and actions."""
        suggestions = self.analyze_all()
        deprecate_count = sum(1 for s in suggestions if s.action == "deprecate")
        warn_count = sum(1 for s in suggestions if s.action == "warn")
        archive_count = sum(1 for s in suggestions if s.action == "archive")
        boost_count = sum(1 for s in suggestions if s.action == "boost")

        return {
            "total_skills_analyzed": len(suggestions),
            "actions": {
                "deprecate": deprecate_count,
                "warn": warn_count,
                "archive": archive_count,
                "boost": boost_count,
            },
            "suggestions": [
                {
                    "skill_id": s.skill_id,
                    "action": s.action,
                    "reason": s.reason,
                    "grade": s.grade,
                    "days_since_last_use": s.days_since_last_use,
                    "total_routes": s.total_routes,
                    "quality_score": s.quality_score,
                }
                for s in suggestions
            ],
        }

    def end_of_session_check(self) -> dict[str, Any]:
        """Check for suggestions at session end.

        Combines retention analysis (stale skills) with skill
        suggestion detection (new patterns). Called by the
        session-end hook or `vibe skill end-check`.

        Returns:
            Dict with retention and suggestion data for display/logging.
        """
        retention_suggestions = self.analyze_all()
        retention_actions = [s for s in retention_suggestions if s.action != "none"]

        suggestion_stats: dict[str, Any] = {"pending": 0, "should_prompt": False}
        try:
            from vibesop.core.skills.suggestion_collector import SkillSuggestionCollector

            collector = SkillSuggestionCollector()
            suggestion_stats = {
                "pending": len(collector.get_pending()),
                "should_prompt": collector.should_prompt(),
            }
        except (ImportError, OSError):
            pass

        return {
            "retention_actions": [
                {"skill_id": s.skill_id, "action": s.action, "reason": s.reason}
                for s in retention_actions
            ],
            "skill_suggestions_pending": suggestion_stats["pending"],
            "should_prompt_suggestions": suggestion_stats["should_prompt"],
            "total_skills_analyzed": len(retention_suggestions),
        }
