"""Feedback loop — closes the gap between evaluation and action.

Connects SkillEvaluator quality scores to lifecycle management:
- F-grade skills with sufficient data → deprecate suggestion
- A-grade skills → routing priority boost suggestion
- Generates retention suggestions for user review

Lifecycle writes are strictly opt-in: ``analyze_all()`` is read-only by
default (``auto_deprecate=False``). The explicit auto-disposition
entry points are ``vibe skill stale --auto``, ``vibe optimize --apply``,
and ``vibe skill cleanup --auto``.
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
    """Opt-in feedback loop for skill quality management.

    Analyzes skill evaluations and produces retention suggestions.
    Lifecycle writes only happen when ``analyze_all`` is called with
    ``auto_deprecate=True``:
    - Deprecates F-grade skills with sufficient data
    - Archives 90+ day unused C/D/F-grade skills
    - Restores deprecated A-grade skills back to active (boost)
    - Generates retention suggestions for user review

    Example:
        >>> loop = FeedbackLoop(project_root=Path("."))
        >>> suggestions = loop.analyze_all()
        >>> for s in suggestions:
        ...     print(f"{s.skill_id}: {s.action} — {s.reason}")
    """

    F_QUALITY_THRESHOLD = 0.30
    F_MIN_ROUTES = 3
    F_STALE_DAYS = 30  # Must be unused 30+ days before F-grade triggers deprecation
    D_STALE_DAYS = 60  # Must be unused 60+ days before D-grade triggers warning
    ARCHIVE_DAYS = 90  # Unused 90+ days with C/D/F grade → auto-archive
    A_QUALITY_THRESHOLD = 0.90

    def __init__(
        self,
        project_root: str | Path = ".",
        evaluator: RoutingEvaluator | None = None,
    ) -> None:
        self._project_root = Path(project_root)
        self._evaluator = evaluator or RoutingEvaluator(project_root=project_root)
        # Skill IDs whose lifecycle was actually written during the most
        # recent analyze_all(auto_deprecate=True) call.
        self._last_applied: list[str] = []

    @property
    def last_applied_skill_ids(self) -> list[str]:
        """Skill IDs whose lifecycle was written by the last auto apply run."""
        return list(self._last_applied)

    def analyze_all(self, auto_deprecate: bool = False) -> list[RetentionSuggestion]:
        """Analyze all skills and return actionable suggestions.

        Args:
            auto_deprecate: If True, applies lifecycle writes for
                          deprecate/archive/boost suggestions.
                          If False (default), only returns suggestions for
                          user review — no lifecycle state is written.

        Returns:
            List of RetentionSuggestion objects.
        """
        self._last_applied = []
        suggestions: list[RetentionSuggestion] = []
        evaluations = self._evaluator.evaluate_all_skills()

        for skill_id, evaluation in evaluations.items():
            suggestion = self._analyze_skill(skill_id, evaluation)
            if suggestion is None:
                continue
            suggestions.append(suggestion)

            applied = False
            if auto_deprecate:
                if suggestion.action == "deprecate":
                    applied = self._apply_deprecation(skill_id, suggestion.reason)
                elif suggestion.action == "archive":
                    applied = self._apply_archive(skill_id, suggestion.reason)
                elif suggestion.action == "boost":
                    applied = self._apply_boost(skill_id)
            if applied:
                self._last_applied.append(skill_id)

        return sorted(suggestions, key=lambda s: s.quality_score)

    def _analyze_skill(
        self, skill_id: str, evaluation: SkillEvaluation
    ) -> RetentionSuggestion | None:
        """Analyze a single skill evaluation and produce a suggestion.

        Rules (aligned with GOALS.md):
        - Grade F, 30+ days unused, < 3 uses → deprecate
        - Grade D, 60+ days unused → warn
        - Grade C/D/F, 90+ days unused → archive
        - Grade A, sufficient data → boost
        """
        grade = evaluation.grade
        quality = evaluation.quality_score

        days_since = None
        if evaluation.last_used:
            try:
                from datetime import datetime

                last = datetime.fromisoformat(evaluation.last_used)
                now = datetime.now(UTC).replace(tzinfo=None)
                days_since = (now - last).days
            except (ValueError, TypeError):
                days_since = None

        # Rule: Grade F, 30+ days unused, < 3 uses → deprecate
        if (
            grade == "F"
            and days_since is not None
            and days_since >= self.F_STALE_DAYS
            and evaluation.total_routes < self.F_MIN_ROUTES
        ):
            return RetentionSuggestion(
                skill_id=skill_id,
                action="deprecate",
                reason=(
                    f"Grade F, only {evaluation.total_routes} use(s), "
                    f"unused for {days_since}d — quality {quality:.0%}"
                ),
                grade=grade,
                days_since_last_use=days_since,
                total_routes=evaluation.total_routes,
                quality_score=quality,
            )

        # Rule: Grade D, 60+ days unused → warn
        if grade == "D" and days_since is not None and days_since >= self.D_STALE_DAYS:
            return RetentionSuggestion(
                skill_id=skill_id,
                action="warn",
                reason=(
                    f"Grade D, unused for {days_since}d — "
                    f"consider reviewing (quality {quality:.0%})"
                ),
                grade=grade,
                days_since_last_use=days_since,
                total_routes=evaluation.total_routes,
                quality_score=quality,
            )

        # Rule: 90+ days unused with grade C/D/F → archive
        if days_since is not None and days_since >= self.ARCHIVE_DAYS and grade in ("C", "D", "F"):
            return RetentionSuggestion(
                skill_id=skill_id,
                action="archive",
                reason=f"Unused for {days_since}d, grade {grade} — auto-archive candidate",
                grade=grade,
                days_since_last_use=days_since,
                total_routes=evaluation.total_routes,
                quality_score=quality,
            )

        # Rule: Grade A, sufficient data → boost
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

    def _apply_deprecation(self, skill_id: str, reason: str) -> bool:
        """Deprecate a skill. Returns True iff the lifecycle was written."""
        try:
            SkillConfigManager.set_lifecycle(skill_id, "deprecated")
            logger.info("Auto-deprecated skill %s: %s", skill_id, reason)
            return True
        except (ValueError, OSError, KeyError, AttributeError):
            logger.warning("Failed to deprecate skill %s", skill_id)
            return False

    def _apply_archive(self, skill_id: str, reason: str) -> bool:
        """Archive a stale skill. Returns True iff the lifecycle was written."""
        try:
            SkillConfigManager.set_lifecycle(skill_id, "archived")
            logger.info("Auto-archived skill %s: %s", skill_id, reason)
            return True
        except (ValueError, OSError, KeyError, AttributeError):
            logger.warning("Failed to archive skill %s", skill_id)
            return False

    def _apply_boost(self, skill_id: str) -> bool:
        """Boost a high-quality skill — restore it to active if deprecated.

        Returns True iff the lifecycle was written. An already-active
        (or otherwise non-deprecated) skill is a no-op and returns False.
        """
        try:
            config = SkillConfigManager.get_skill_config(skill_id)
            if config and config.lifecycle == "deprecated":
                SkillConfigManager.set_lifecycle(skill_id, "active")
                logger.info("Auto-boosted skill %s back to active", skill_id)
                return True
            return False
        except (ValueError, OSError, KeyError, AttributeError):
            logger.warning("Failed to boost skill %s", skill_id)
            return False

    def generate_report(self) -> dict[str, Any]:
        """Generate a summary report with evaluation results and actions.

        Read-only: never writes lifecycle state.
        """
        suggestions = self.analyze_all(auto_deprecate=False)
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

        Read-only: never writes lifecycle state.

        Returns:
            Dict with retention and suggestion data for display/logging.
        """
        retention_suggestions = self.analyze_all(auto_deprecate=False)
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
