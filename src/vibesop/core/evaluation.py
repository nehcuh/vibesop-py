"""Skill evaluation and quality metrics.

Provides aggregated quality metrics for skills based on:
- Routing feedback (success rate)
- User preferences (selection scores)
- Usage frequency
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vibesop.core.feedback import FeedbackCollector
from vibesop.core.preference import PreferenceLearner


@dataclass
class SkillEvaluation:
    """Quality evaluation for a single skill.

    Attributes:
        skill_id: Skill identifier
        total_routes: Number of times the skill was routed to
        success_rate: Fraction of correct routings (0.0-1.0)
        avg_confidence: Average routing confidence
        user_score: User preference score (0.0-1.0)
        last_used: ISO timestamp of last usage, or None
    """

    skill_id: str
    total_routes: int = 0
    success_rate: float = 0.0
    avg_confidence: float = 0.0
    user_score: float = 0.0
    last_used: str | None = None

    @property
    def quality_score(self) -> float:
        """Combined quality score (0.0-1.0).

        Weights:
        - success_rate: 40%
        - user_score: 40%
        - avg_confidence: 20%
        """
        if self.total_routes == 0:
            # No data: neutral score with slight boost for confidence
            return 0.5 + (self.avg_confidence * 0.1)
        return (
            self.success_rate * 0.4
            + self.user_score * 0.4
            + self.avg_confidence * 0.2
        )

    @property
    def grade(self) -> str:
        """Letter grade based on quality score (0-100 scale).

        A: 90-100 (Excellent)
        B: 75-89  (Good)
        C: 60-74  (Acceptable)
        D: 40-59  (Needs improvement)
        F: 0-39   (Consider removal)
        """
        score = self.quality_score * 100
        if score >= 90:
            return "A"
        if score >= 75:
            return "B"
        if score >= 60:
            return "C"
        if score >= 40:
            return "D"
        return "F"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "skill_id": self.skill_id,
            "total_routes": self.total_routes,
            "success_rate": self.success_rate,
            "avg_confidence": self.avg_confidence,
            "user_score": self.user_score,
            "last_used": self.last_used,
            "quality_score": self.quality_score,
            "grade": self.grade,
        }


class RoutingEvaluator:
    """Evaluate skill quality from feedback and preference data.

    Example:
        >>> evaluator = RoutingEvaluator(project_root=Path("."))
        >>> eval = evaluator.evaluate_skill("gstack/review")
        >>> print(f"Quality: {eval.quality_score:.0%}")
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        feedback_collector: FeedbackCollector | None = None,
        preference_learner: PreferenceLearner | None = None,
    ) -> None:
        """Initialize evaluator.

        Args:
            project_root: Project root directory
            feedback_collector: Optional pre-configured feedback collector
            preference_learner: Optional pre-configured preference learner
        """
        self._project_root = Path(project_root)

        if feedback_collector is None:
            feedback_path = self._project_root / ".vibe" / "feedback.json"
            self._feedback = FeedbackCollector(storage_path=feedback_path)
        else:
            self._feedback = feedback_collector

        if preference_learner is None:
            pref_path = self._project_root / ".vibe" / "preferences.json"
            self._preferences = PreferenceLearner(storage_path=pref_path)
        else:
            self._preferences = preference_learner

    def evaluate_skill(self, skill_id: str) -> SkillEvaluation | None:
        """Evaluate a single skill.

        Args:
            skill_id: Skill identifier

        Returns:
            SkillEvaluation or None if no data exists
        """
        feedback_records = [
            r for r in self._feedback.get_records() if r.routed_skill == skill_id
        ]

        total_routes = len(feedback_records)
        if total_routes == 0:
            # Return evaluation with preference score only
            user_score = self._preferences.get_preference_score(skill_id)
            return SkillEvaluation(
                skill_id=skill_id,
                total_routes=0,
                success_rate=0.0,
                avg_confidence=0.0,
                user_score=user_score,
                last_used=None,
            )

        correct = sum(1 for r in feedback_records if r.was_correct)
        success_rate = correct / total_routes
        avg_confidence = sum(r.confidence for r in feedback_records) / total_routes

        # Get last usage timestamp
        last_used = max(
            (r.timestamp for r in feedback_records),
            default=None,
        )

        user_score = self._preferences.get_preference_score(skill_id)

        return SkillEvaluation(
            skill_id=skill_id,
            total_routes=total_routes,
            success_rate=success_rate,
            avg_confidence=avg_confidence,
            user_score=user_score,
            last_used=last_used,
        )

    def evaluate_all_skills(self) -> dict[str, SkillEvaluation]:
        """Evaluate all skills with feedback data.

        Returns:
            Dictionary mapping skill_id to SkillEvaluation
        """
        # Collect all skill IDs from feedback and preferences
        skill_ids: set[str] = set()
        for record in self._feedback.get_records():
            skill_ids.add(record.routed_skill)
        skill_ids.update(self._preferences._storage.skill_scores.keys())

        return {
            skill_id: self.evaluate_skill(skill_id)
            for skill_id in skill_ids
            if self.evaluate_skill(skill_id) is not None
        }

    def get_low_quality_skills(
        self,
        threshold: float = 0.3,
        min_routes: int = 3,
    ) -> list[SkillEvaluation]:
        """Get skills with low quality scores.

        Args:
            threshold: Quality score threshold (below this is low quality)
            min_routes: Minimum number of routes to consider

        Returns:
            List of low-quality skill evaluations, sorted by quality score
        """
        all_evals = self.evaluate_all_skills().values()
        low_quality = [
            e for e in all_evals
            if e.total_routes >= min_routes and e.quality_score < threshold
        ]
        return sorted(low_quality, key=lambda e: e.quality_score)

    def generate_report(self) -> dict[str, Any]:
        """Generate overall evaluation report.

        Returns:
            Dictionary with summary statistics
        """
        all_evals = list(self.evaluate_all_skills().values())
        if not all_evals:
            return {
                "total_skills_evaluated": 0,
                "avg_quality_score": 0.0,
                "low_quality_skills": [],
            }

        avg_quality = sum(e.quality_score for e in all_evals) / len(all_evals)
        low_quality = self.get_low_quality_skills()

        return {
            "total_skills_evaluated": len(all_evals),
            "avg_quality_score": avg_quality,
            "low_quality_skills": [e.to_dict() for e in low_quality],
        }
