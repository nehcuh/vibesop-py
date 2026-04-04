"""Integration recommendation system.

This module provides intelligent recommendations for
skill pack integrations based on user needs and context.
"""

from pathlib import Path
from typing import Any
from dataclasses import dataclass
from enum import Enum

from vibesop.integrations import IntegrationManager, IntegrationInfo, IntegrationStatus


class RecommendationPriority(Enum):
    """Priority level for recommendations.

    Attributes:
        HIGH: Highly recommended
        MEDIUM: Nice to have
        LOW: Optional
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Recommendation:
    """Integration recommendation.

    Attributes:
        integration_id: Integration identifier
        name: Integration name
        description: Integration description
        priority: Recommendation priority
        reason: Reason for recommendation
        confidence: Confidence score (0-1)
        skills: List of skills provided
    """

    integration_id: str
    name: str
    description: str
    priority: RecommendationPriority
    reason: str
    confidence: float
    skills: list[str]


class IntegrationRecommender:
    """Recommends integrations based on user context.

    Analyzes user needs and recommends appropriate
    skill pack integrations.

    Example:
        >>> recommender = IntegrationRecommender()
        >>> recommendations = recommender.recommend(
        ...     user_context={"use_case": "software-development"}
        ... )
    """

    # Recommendation rules
    RECOMMENDATION_RULES: dict[str, dict[str, Any]] = {
        "software-development": {
            "integrations": ["gstack", "superpowers"],
            "priority": RecommendationPriority.HIGH,
            "reason": "Essential for software development workflows",
        },
        "code-review": {
            "integrations": ["gstack"],
            "priority": RecommendationPriority.HIGH,
            "reason": "Provides specialized code review skills",
        },
        "brainstorming": {
            "integrations": ["superpowers"],
            "priority": RecommendationPriority.MEDIUM,
            "reason": "Great for ideation and brainstorming",
        },
        "testing": {
            "integrations": ["gstack"],
            "priority": RecommendationPriority.HIGH,
            "reason": "Includes automated QA skills",
        },
        "architecture": {
            "integrations": ["gstack"],
            "priority": RecommendationPriority.HIGH,
            "reason": "Provides architecture review skills",
        },
        "productivity": {
            "integrations": ["superpowers"],
            "priority": RecommendationPriority.MEDIUM,
            "reason": "General productivity enhancements",
        },
    }

    # Skill compatibility matrix
    SKILL_COMPATIBILITY = {
        "gstack": {
            "compatible_with": ["claude-code", "opencode"],
            "conflicts_with": [],
        },
        "superpowers": {
            "compatible_with": ["claude-code", "opencode"],
            "conflicts_with": [],
        },
    }

    def __init__(self) -> None:
        """Initialize the integration recommender."""
        self._manager = IntegrationManager()

    def recommend(
        self,
        user_context: dict[str, Any],
        max_recommendations: int = 5,
    ) -> list[Recommendation]:
        """Generate integration recommendations.

        Args:
            user_context: User context and preferences
            max_recommendations: Maximum number of recommendations

        Returns:
            List of Recommendation objects
        """
        recommendations: list[Recommendation] = []
        scores: dict[str, float] = {}

        # Get available integrations
        available = self._get_available_integrations()

        # Score each integration
        for integration_id, info in available.items():
            score = self._score_integration(
                integration_id,
                info,
                user_context,
            )
            scores[integration_id] = score

        # Sort by score
        sorted_integrations = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        # Create recommendations
        for integration_id, score in sorted_integrations[:max_recommendations]:
            info = available[integration_id]

            # Determine priority
            if score >= 0.8:
                priority = RecommendationPriority.HIGH
            elif score >= 0.5:
                priority = RecommendationPriority.MEDIUM
            else:
                priority = RecommendationPriority.LOW

            recommendation = Recommendation(
                integration_id=integration_id,
                name=info.name,
                description=info.description,
                priority=priority,
                reason=self._get_recommendation_reason(integration_id, user_context),
                confidence=score,
                skills=info.skills,
            )
            recommendations.append(recommendation)

        return recommendations

    def get_compatibility_report(
        self,
        integration_ids: list[str],
        platform: str,
    ) -> dict[str, Any]:
        """Get compatibility report for integrations.

        Args:
            integration_ids: List of integration IDs
            platform: Target platform

        Returns:
            Compatibility report dictionary
        """
        compatible: list[str] = []
        incompatible: list[dict[str, str]] = []
        warnings: list[dict[str, list[str]]] = []

        report: dict[str, Any] = {
            "compatible": compatible,
            "incompatible": incompatible,
            "warnings": warnings,
            "platform": platform,
        }

        for integration_id in integration_ids:
            if integration_id not in self.SKILL_COMPATIBILITY:
                incompatible.append(
                    {
                        "integration_id": integration_id,
                        "reason": "Unknown integration",
                    }
                )
                continue

            compat_info = self.SKILL_COMPATIBILITY[integration_id]
            platform = platform.lower()

            if platform in compat_info.get("compatible_with", []):
                compatible.append(integration_id)
            else:
                incompatible.append(
                    {
                        "integration_id": integration_id,
                        "reason": f"Not compatible with {platform}",
                    }
                )

            # Check for conflicts
            if platform in compat_info.get("conflicts_with", []):
                warnings.append(
                    {
                        "integration_id": integration_id,
                        "conflicts_with": compat_info["conflicts_with"],
                    }
                )

        return report

    def generate_setup_plan(
        self,
        recommendations: list[Recommendation],
        platform: str,
        output_dir: Path,
    ) -> dict[str, Any]:
        """Generate setup plan for integrations.

        Args:
            recommendations: List of recommendations
            platform: Target platform
            output_dir: Output directory

        Returns:
            Setup plan dictionary
        """
        integrations: list[dict[str, Any]] = []
        steps: list[dict[str, Any]] = []
        errors: list[str] = []

        plan: dict[str, Any] = {
            "platform": platform,
            "integrations": integrations,
            "steps": steps,
            "estimated_time": 0,
            "errors": errors,
        }

        try:
            high_priority = [
                r for r in recommendations if r.priority == RecommendationPriority.HIGH
            ]
            medium_priority = [
                r for r in recommendations if r.priority == RecommendationPriority.MEDIUM
            ]

            for rec in high_priority:
                install_time = self._estimate_install_time(rec.integration_id)

                integrations.append(
                    {
                        "id": rec.integration_id,
                        "name": rec.name,
                        "priority": "high",
                        "estimated_time": install_time,
                    }
                )

                steps.append(
                    {
                        "action": "install",
                        "integration": rec.integration_id,
                        "command": f"vibe install {rec.integration_id}",
                        "description": f"Install {rec.name}",
                        "estimated_time": install_time,
                    }
                )

            for rec in medium_priority:
                install_time = self._estimate_install_time(rec.integration_id)
                integrations.append(
                    {
                        "id": rec.integration_id,
                        "name": rec.name,
                        "priority": "medium",
                        "estimated_time": install_time,
                    }
                )

                steps.append(
                    {
                        "action": "install",
                        "integration": rec.integration_id,
                        "command": f"vibe install {rec.integration_id}",
                        "description": f"Install {rec.name} (optional)",
                        "estimated_time": install_time,
                    }
                )

            plan["estimated_time"] = sum(step.get("estimated_time", 0) for step in steps)

        except Exception as e:
            errors.append(f"Setup plan generation failed: {e}")

        return plan

    def _get_available_integrations(self) -> dict[str, IntegrationInfo]:
        """Get available integrations.

        Returns:
            Dictionary of integration info
        """
        integrations = self._manager.list_integrations()
        return {info.name: info for info in integrations}

    def _score_integration(
        self,
        integration_id: str,
        info: IntegrationInfo,
        user_context: dict[str, Any],
    ) -> float:
        """Score an integration based on user context.

        Args:
            integration_id: Integration ID
            info: Integration info
            user_context: User context

        Returns:
            Score between 0 and 1
        """
        score = 0.0

        # Base score for being installed
        if info.status == IntegrationStatus.INSTALLED:
            score += 0.1
        else:
            score += 0.3  # Preference for new installations

        # Use case matching
        use_case = user_context.get("use_case", "")
        if use_case in self.RECOMMENDATION_RULES:
            rule = self.RECOMMENDATION_RULES[use_case]
            if integration_id in rule["integrations"]:
                if rule["priority"] == RecommendationPriority.HIGH:
                    score += 0.5
                elif rule["priority"] == RecommendationPriority.MEDIUM:
                    score += 0.3

        # Platform preference
        preferred_platform = user_context.get("platform", "")
        if preferred_platform:
            compat_info = self.SKILL_COMPATIBILITY.get(integration_id, {})
            if preferred_platform.lower() in compat_info.get("compatible_with", []):
                score += 0.2

        # User preferences
        preferences = user_context.get("preferences", {})
        if preferences.get("include_testing", False):
            if integration_id == "gstack":  # Has testing skills
                score += 0.3

        if preferences.get("include_brainstorming", False):
            if integration_id == "superpowers":  # Has brainstorming
                score += 0.3

        return min(score, 1.0)

    def _get_recommendation_reason(self, integration_id: str, user_context: dict[str, Any]) -> str:
        """Get reason for recommendation.

        Args:
            integration_id: Integration ID
            user_context: User context

        Returns:
            Reason string
        """
        use_case = user_context.get("use_case", "")

        if use_case in self.RECOMMENDATION_RULES:
            rule = self.RECOMMENDATION_RULES[use_case]
            if integration_id in rule["integrations"]:
                return rule["reason"]

        # Default reasons
        if integration_id == "gstack":
            return "Virtual engineering team skills for code review and QA"
        elif integration_id == "superpowers":
            return "General productivity skills for development"
        else:
            return "Recommended for enhanced functionality"

    def _estimate_install_time(self, integration_id: str) -> int:
        """Estimate installation time in minutes.

        Args:
            integration_id: Integration ID

        Returns:
            Estimated time in minutes
        """
        # Base times (in minutes)
        base_times = {
            "gstack": 5,
            "superpowers": 5,
        }

        return base_times.get(integration_id, 5)
