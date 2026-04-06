"""Integration management for VibeSOP.

This module provides detection and management capabilities
for external skill pack integrations (Superpowers, gstack, etc.).
"""

from vibesop.integrations.detector import (
    IntegrationDetector,
    IntegrationInfo,
    IntegrationStatus,
)
from vibesop.integrations.health_monitor import (
    HealthStatus,
    SkillHealthMonitor,
)
from vibesop.integrations.manager import IntegrationManager
from vibesop.integrations.recommender import (
    IntegrationRecommender,
    Recommendation,
    RecommendationPriority,
)
from vibesop.integrations.verifier import (
    IntegrationReport,
    IntegrationVerifier,
    VerificationResult,
    VerificationStatus,
)

__all__ = [
    "HealthStatus",
    "IntegrationDetector",
    "IntegrationInfo",
    "IntegrationManager",
    "IntegrationRecommender",
    "IntegrationReport",
    "IntegrationStatus",
    "IntegrationVerifier",
    "Recommendation",
    "RecommendationPriority",
    "SkillHealthMonitor",
    "VerificationResult",
    "VerificationStatus",
]
