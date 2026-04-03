"""Integration management for VibeSOP.

This module provides detection and management capabilities
for external skill pack integrations (Superpowers, gstack, etc.).
"""

from vibesop.integrations.detector import (
    IntegrationDetector,
    IntegrationStatus,
    IntegrationInfo,
)
from vibesop.integrations.manager import IntegrationManager
from vibesop.integrations.recommender import (
    IntegrationRecommender,
    Recommendation,
    RecommendationPriority,
)
from vibesop.integrations.verifier import (
    IntegrationVerifier,
    VerificationResult,
    VerificationStatus,
    IntegrationReport,
)

__all__ = [
    "IntegrationDetector",
    "IntegrationManager",
    "IntegrationStatus",
    "IntegrationInfo",
    "IntegrationRecommender",
    "Recommendation",
    "RecommendationPriority",
    "IntegrationVerifier",
    "VerificationResult",
    "VerificationStatus",
    "IntegrationReport",
]
