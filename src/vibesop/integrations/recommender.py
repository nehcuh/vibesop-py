"""Integration recommendation system."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from vibesop.integrations import IntegrationManager, IntegrationStatus


class RecommendationPriority(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Recommendation:
    integration_id: str
    name: str
    description: str
    priority: RecommendationPriority
    reason: str
    confidence: float
    skills: list[str]


_USE_CASE_MAP: dict[str, list[tuple[str, RecommendationPriority, str]]] = {
    "software-development": [
        (
            "superpowers",
            RecommendationPriority.HIGH,
            "Essential for software development workflows",
        ),
    ],
    "code-review": [("superpowers", RecommendationPriority.HIGH, "Provides code review skills")],
    "brainstorming": [
        ("superpowers", RecommendationPriority.MEDIUM, "Great for ideation and brainstorming")
    ],
    "testing": [
        ("superpowers", RecommendationPriority.HIGH, "Includes test-driven development skills")
    ],
    "architecture": [
        ("superpowers", RecommendationPriority.HIGH, "Provides architecture design skills")
    ],
    "productivity": [
        ("superpowers", RecommendationPriority.MEDIUM, "General productivity enhancements")
    ],
}

_DEFAULT_REASONS: dict[str, str] = {
    "superpowers": "General productivity skills for development",
}


class IntegrationRecommender:
    def __init__(self) -> None:
        self._manager = IntegrationManager()

    def recommend(
        self,
        user_context: dict[str, Any],
        max_recommendations: int = 5,
    ) -> list[Recommendation]:
        available = {info.name: info for info in self._manager.list_integrations()}
        use_case = user_context.get("use_case", "")
        matched: list[tuple[str, RecommendationPriority, str]] = _USE_CASE_MAP.get(use_case, [])

        if not matched:
            matched = [
                (k, RecommendationPriority.MEDIUM, _DEFAULT_REASONS.get(k, "Recommended"))
                for k in available
            ]

        recs: list[Recommendation] = []
        for iid, prio, reason in matched:
            if iid not in available:
                continue
            info = available[iid]
            installed_bonus = 0.1 if info.status == IntegrationStatus.INSTALLED else 0.2
            confidence = (
                min(0.8 + installed_bonus, 1.0)
                if prio == RecommendationPriority.HIGH
                else min(0.5 + installed_bonus, 1.0)
            )
            recs.append(
                Recommendation(
                    integration_id=iid,
                    name=info.name,
                    description=info.description,
                    priority=prio,
                    reason=reason,
                    confidence=confidence,
                    skills=info.skills,
                )
            )

        return recs[:max_recommendations]

    def get_compatibility_report(
        self,
        integration_ids: list[str],
        platform: str,
    ) -> dict[str, Any]:
        return {
            "compatible": [i for i in integration_ids if i in ("superpowers", "omx", "mattpocock")],
            "incompatible": [
                {"integration_id": i, "reason": "Unknown integration"}
                for i in integration_ids
                if i not in ("superpowers", "omx", "mattpocock")
            ],
            "warnings": [],
            "platform": platform,
        }

    def generate_setup_plan(
        self,
        recommendations: list[Recommendation],
        platform: str,
        _output_dir: Path,
    ) -> dict[str, Any]:
        steps = [
            {
                "action": "install",
                "integration": r.integration_id,
                "command": f"vibe install {r.integration_id}",
                "description": f"Install {r.name}",
                "estimated_time": 5,
            }
            for r in recommendations
        ]
        return {
            "platform": platform,
            "integrations": [
                {
                    "id": r.integration_id,
                    "name": r.name,
                    "priority": r.priority.value,
                    "estimated_time": 5,
                }
                for r in recommendations
            ],
            "steps": steps,
            "estimated_time": len(steps) * 5,
            "errors": [],
        }
