"""Skill evaluation and quality metrics (Phase 3).

Provides aggregated quality metrics for skills based on 5 dimensions:
- Routing accuracy (25%): FeedbackCollector (was_correct)
- User satisfaction (25%): ExecutionFeedbackCollector (was_helpful)
- Execution success (25%): ExecutionFeedbackCollector (execution_success)
- Usage frequency (15%): Normalized usage count
- Health score (10%): HealthMonitor file checks
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vibesop.core.feedback import ExecutionFeedbackCollector, FeedbackCollector
from vibesop.core.preference import PreferenceLearner


@dataclass
class SkillEvaluation:
    """Quality evaluation for a single skill.

    Attributes:
        skill_id: Skill identifier
        total_routes: Number of times the skill was routed to
        routing_accuracy: Fraction of correct routings (0.0-1.0)
        user_satisfaction: User helpfulness rating (0.0-1.0)
        execution_success: Execution completion rate (0.0-1.0)
        usage_frequency: Normalized usage frequency (0.0-1.0)
        health_score: HealthMonitor file check score (0.0-1.0)
        avg_confidence: Average routing confidence
        user_score: PreferenceLearner score (0.0-1.0)
        last_used: ISO timestamp of last usage, or None
    """

    skill_id: str
    total_routes: int = 0
    routing_accuracy: float = 0.0
    user_satisfaction: float = 0.0
    execution_success: float = 0.0
    usage_frequency: float = 0.0
    health_score: float = 0.0
    avg_confidence: float = 0.0
    user_score: float = 0.0
    last_used: str | None = None

    @property
    def quality_score(self) -> float:
        """Combined quality score (0.0-1.0).

        Weights (per plan):
        - routing_accuracy: 25%
        - user_satisfaction: 25%
        - execution_success: 25%
        - usage_frequency: 15%
        - health_score: 10%
        """
        if self.total_routes == 0:
            # No routing data: fall back to confidence + user_score blend
            return 0.5 + (self.avg_confidence * 0.05) + (self.user_score * 0.05)
        return (
            self.routing_accuracy * 0.25
            + self.user_satisfaction * 0.25
            + self.execution_success * 0.25
            + self.usage_frequency * 0.15
            + self.health_score * 0.10
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
            "routing_accuracy": self.routing_accuracy,
            "user_satisfaction": self.user_satisfaction,
            "execution_success": self.execution_success,
            "usage_frequency": self.usage_frequency,
            "health_score": self.health_score,
            "avg_confidence": self.avg_confidence,
            "user_score": self.user_score,
            "last_used": self.last_used,
            "quality_score": self.quality_score,
            "grade": self.grade,
        }


class RoutingEvaluator:
    """Evaluate skill quality from feedback, execution, and health data.

    Example:
        >>> evaluator = RoutingEvaluator(project_root=Path("."))
        >>> eval = evaluator.evaluate_skill("gstack/review")
        >>> print(f"Quality: {eval.quality_score:.0%} ({eval.grade})")
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        feedback_collector: FeedbackCollector | None = None,
        execution_collector: ExecutionFeedbackCollector | None = None,
        preference_learner: PreferenceLearner | None = None,
    ) -> None:
        """Initialize evaluator.

        Args:
            project_root: Project root directory
            feedback_collector: Optional pre-configured routing feedback collector
            execution_collector: Optional pre-configured execution feedback collector
            preference_learner: Optional pre-configured preference learner
        """
        self._project_root = Path(project_root)

        if feedback_collector is None:
            feedback_path = self._project_root / ".vibe" / "feedback.json"
            self._feedback = FeedbackCollector(storage_path=feedback_path)
        else:
            self._feedback = feedback_collector

        if execution_collector is None:
            exec_path = self._project_root / ".vibe" / "execution_feedback.json"
            self._execution = ExecutionFeedbackCollector(storage_path=exec_path)
        else:
            self._execution = execution_collector

        if preference_learner is None:
            pref_path = self._project_root / ".vibe" / "preferences.json"
            self._preferences = PreferenceLearner(storage_path=pref_path)
        else:
            self._preferences = preference_learner

    def evaluate_skill(self, skill_id: str) -> SkillEvaluation | None:
        """Evaluate a single skill across all 5 dimensions."""
        # 1. Routing accuracy from FeedbackCollector
        feedback_records = [
            r for r in self._feedback.get_records() if r.routed_skill == skill_id
        ]
        total_routes = len(feedback_records)
        routing_accuracy = (
            sum(1 for r in feedback_records if r.was_correct) / total_routes
            if total_routes > 0 else 0.0
        )
        avg_confidence = (
            sum(r.confidence for r in feedback_records) / total_routes
            if total_routes > 0 else 0.0
        )
        last_used = max(
            (r.timestamp for r in feedback_records), default=None
        )

        # Merge with SkillConfig.usage_stats.last_used (written by record_usage)
        # so the FeedbackLoop stale-skill detection can use usage data
        try:
            from vibesop.core.skills.config_manager import SkillConfigManager
            config = SkillConfigManager.get_skill_config(skill_id)
            if config and config.usage_stats:
                usage_last = config.usage_stats.get("last_used")
                if usage_last and (last_used is None or usage_last > last_used):
                    last_used = usage_last
        except Exception:
            pass

        # 2. User satisfaction + execution success from ExecutionFeedbackCollector
        exec_summary = self._execution.get_skill_summary(skill_id)
        user_satisfaction = exec_summary.get("helpful_rate") or 0.0
        execution_success = exec_summary.get("success_rate") or 0.0

        # 3. Usage frequency: normalize against most-used skill
        all_counts = {
            sid: len([r for r in self._feedback.get_records() if r.routed_skill == sid])
            for sid in {r.routed_skill for r in self._feedback.get_records()}
        }
        max_count = max(all_counts.values(), default=0)
        usage_frequency = (
            total_routes / max_count if max_count > 0 else 0.0
        )

        # 4. Health score from HealthMonitor (if available)
        health_score = self._get_health_score(skill_id)

        # 5. User preference score
        user_score = self._preferences.get_preference_score(skill_id)

        # Blend community rating into satisfaction score if available
        if user_satisfaction == 0.0:
            try:
                from vibesop.core.skills.ratings import SkillRatingStore
                store = SkillRatingStore()
                avg_rating = store.get_avg_score(skill_id)
                if avg_rating is not None:
                    user_satisfaction = avg_rating / 5.0
            except (ImportError, OSError):
                pass

        return SkillEvaluation(
            skill_id=skill_id,
            total_routes=total_routes,
            routing_accuracy=routing_accuracy,
            user_satisfaction=user_satisfaction,
            execution_success=execution_success,
            usage_frequency=usage_frequency,
            health_score=health_score,
            avg_confidence=avg_confidence,
            user_score=user_score,
            last_used=last_used,
        )

    def _get_health_score(self, skill_id: str) -> float:
        """Get health score from HealthMonitor if available."""
        try:
            from vibesop.integrations.health_monitor import SkillHealthMonitor

            monitor = SkillHealthMonitor()
            # HealthMonitor works at pack level, not skill level
            # We check if the skill's pack is healthy
            parts = skill_id.split("/")
            pack_name = parts[0] if len(parts) > 1 else "builtin"
            status = monitor.check_local_health(pack_name)
            health_map = {"healthy": 1.0, "warning": 0.6, "critical": 0.2, "unknown": 0.5}
            return health_map.get(status.health, 0.5)
        except (OSError, ValueError, KeyError):
            return 0.5  # Neutral if health monitor unavailable

    def evaluate_all_skills(self) -> dict[str, SkillEvaluation]:
        """Evaluate all skills with feedback data."""
        skill_ids: set[str] = set()
        for record in self._feedback.get_records():
            skill_ids.add(record.routed_skill)
        skill_ids.update(self._preferences._storage.skill_scores.keys())
        # Also include skills with execution feedback
        for record in self._execution.get_records():
            skill_ids.add(record.skill_id)

        result: dict[str, SkillEvaluation] = {}
        for skill_id in skill_ids:
            evaluation = self.evaluate_skill(skill_id)
            if evaluation is not None:
                result[skill_id] = evaluation
        return result

    def get_low_quality_skills(
        self,
        threshold: float = 0.3,
        min_routes: int = 3,
    ) -> list[SkillEvaluation]:
        """Get skills with low quality scores."""
        all_evals = self.evaluate_all_skills().values()
        low_quality = [
            e for e in all_evals
            if e.total_routes >= min_routes and e.quality_score < threshold
        ]
        return sorted(low_quality, key=lambda e: e.quality_score)

    def generate_report(self) -> dict[str, Any]:
        """Generate overall evaluation report."""
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
