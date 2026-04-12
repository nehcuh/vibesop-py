"""Type definitions for VibeSOP core modules.

This module provides TypedDict and type alias definitions to improve type safety
and eliminate dict[str, Any] throughout the codebase.
"""

from typing import TypedDict


class SkillCandidate(TypedDict, total=False):
    """Structure for skill candidate dictionaries.

    Used throughout the routing pipeline as the canonical representation
    of a skill that can be routed to.
    """

    id: str
    name: str
    description: str
    intent: str
    namespace: str
    keywords: list[str]
    triggers: list[str]
    tags: list[str]
    version: str
    author: str
    skill_type: str
    source: str


class MatcherCapabilities(TypedDict, total=False):
    """Structure for matcher capability information."""

    type: str
    speed: str
    accuracy: str
    requires_semantic: bool


class RoutingMetadata(TypedDict, total=False):
    """Common metadata fields for routing results."""

    namespace: str
    matcher: str
    scenario: str | None
    override: bool
    boosted: bool
    original_confidence: float | None
    preference_applied: bool
    ai_triage: bool
    model: str


# Score type aliases
type ConfidenceScore = float
type SimilarityScore = float
type BoostAmount = float

# Convenience aliases for dict types used in matching
type SkillCandidateDict = dict[str, object]
type MatcherCapabilitiesDict = dict[str, object]
type RoutingMetadataDict = dict[str, object]

__all__ = [
    "BoostAmount",
    "ConfidenceScore",
    "MatcherCapabilities",
    "MatcherCapabilitiesDict",
    "RoutingMetadata",
    "RoutingMetadataDict",
    "SimilarityScore",
    "SkillCandidate",
    "SkillCandidateDict",
]
