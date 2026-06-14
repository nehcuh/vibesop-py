"""Base interfaces and models for unified matching system.

This module defines the Protocol (interface) that all matchers must implement,
along with the unified MatchResult model.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from vibesop.core.types import (
    ConfidenceScore,
    MatcherCapabilitiesDict,
    RoutingMetadataDict,
    SkillCandidateDict,
)


class SimilarityMetric(StrEnum):
    """Types of similarity metrics."""

    COSINE = "cosine"
    DOT_PRODUCT = "dot_product"
    EUCLIDEAN = "euclidean"
    MANHATTAN = "manhattan"
    JACCARD = "jaccard"
    LEVENSHTEIN = "levenshtein"


class MatcherType(StrEnum):
    """Types of matchers."""

    KEYWORD = "keyword"
    REGEX = "regex"
    TFIDF = "tfidf"
    EMBEDDING = "embedding"
    LEVENSHTEIN = "levenshtein"
    AI_TRIAGE = "ai_triage"
    CUSTOM = "custom"


@dataclass
class RoutingContext:
    """Context information for routing decisions.

    Attributes:
        file_type: Type of file being edited (e.g., "py", "md")
        error_count: Number of errors in the session
        recent_files: List of recently accessed files
        project_type: Detected project type (e.g., "python", "rust")
        user_skill_level: User's proficiency level (novice/intermediate/expert)
        conversation_id: Active conversation ID for memory lookup
        recent_queries: Recent user queries from conversation history
        interception_mode: First-class field carrying the InterceptionMode
            value (e.g. ``"multi_agent_squad"``, ``"single_agent"``).
            Replaces the legacy ``metadata["_interception_mode"]``
            backchannel; readers should prefer this field and fall back
            to metadata only for backward compatibility with code paths
            that have not yet been migrated.
        intent_analysis: First-class field carrying the IntentAnalysis
            payload (already serialized to dict via ``.to_dict()``).
            Replaces the legacy ``metadata["intent_analysis"]``
            backchannel; same field-first / metadata-fallback policy.
        role_context: Per-role routing hints (role id, prompt, allowed
            skills). Used by SINGLE_AGENT routing.
        metadata: Free-form bag for matcher-specific extensions. New
            code should add first-class fields above rather than piling
            into metadata — the backchannel pattern is fragile because
            string keys can drift between writers and readers without
            any type-checker signal.
    """

    file_type: str | None = None
    error_count: int = 0
    recent_files: list[str] = field(default_factory=list)
    project_type: str | None = None
    user_skill_level: str = "intermediate"
    conversation_id: str | None = None
    recent_queries: list[str] = field(default_factory=list)
    current_skill: str | None = None
    habit_boosts: dict[str, float] = field(default_factory=dict)
    strategy_hint: str | None = None
    skip_ai_triage: bool = False
    # Phase 6: interception mode and role context for agent routing
    interception_mode: str | None = None
    role_context: dict[str, Any] | None = None
    # Phase 7.0.3 (v7.0.3): promote intent_analysis from metadata backchannel
    # to a first-class field. See S26 handoff for migration context.
    intent_analysis: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "file_type": self.file_type,
            "error_count": self.error_count,
            "recent_files": self.recent_files,
            "project_type": self.project_type,
            "user_skill_level": self.user_skill_level,
            "conversation_id": self.conversation_id,
            "recent_queries": self.recent_queries,
            "current_skill": self.current_skill,
            "interception_mode": self.interception_mode,
            "role_context": self.role_context,
            "intent_analysis": self.intent_analysis,
            "metadata": self.metadata,
        }

    @property
    def has_memory(self) -> bool:
        """Whether memory context is available."""
        return bool(self.conversation_id or self.recent_queries)


class MatchResult(BaseModel):
    """Unified result from any matcher.

    This is the single source of truth for match results across
    the entire routing system.

    Attributes:
        skill_id: The matched skill identifier
        confidence: Confidence score (0.0 to 1.0)
        score_breakdown: Individual scores from each strategy
        matcher_type: Which matcher produced this result
        matched_keywords: Keywords that matched (for keyword matcher)
        matched_patterns: Regex patterns that matched (for regex matcher)
        semantic_score: Semantic similarity score (for semantic matchers)
        metadata: Additional matcher-specific data
    """

    skill_id: str = Field(..., description="Matched skill identifier")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence score",
    )
    score_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="Individual strategy scores",
    )
    matcher_type: MatcherType = Field(
        ...,
        description="Type of matcher that produced this result",
    )
    matched_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords that matched",
    )
    matched_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns that matched",
    )
    semantic_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Semantic similarity score",
    )
    metadata: RoutingMetadataDict = Field(
        default_factory=dict,
        description="Additional matcher-specific data",
    )

    def meets_threshold(self, threshold: float) -> bool:
        """Check if this result meets the minimum confidence threshold."""
        return self.confidence >= threshold

    def with_boost(
        self,
        boost: float,
        source: str = "unknown",
    ) -> "MatchResult":
        """Return a new result with boosted confidence."""
        boosted = min(1.0, self.confidence + boost)
        return MatchResult(
            skill_id=self.skill_id,
            confidence=boosted,
            score_breakdown={
                **self.score_breakdown,
                "boost": boost,
            },
            matcher_type=self.matcher_type,
            matched_keywords=self.matched_keywords.copy(),
            matched_patterns=self.matched_patterns.copy(),
            semantic_score=self.semantic_score,
            metadata={
                **self.metadata,
                "boosted": True,
                "original_confidence": self.confidence,
                "boost_source": source,
            },
        )


class IMatcher(Protocol):
    """Protocol defining the interface for all matchers.

    All matchers (keyword, TF-IDF, embedding, etc.) must implement
    this interface to ensure compatibility with the UnifiedRouter.
    """

    def score(
        self,
        query: str,
        candidate: SkillCandidateDict,
        context: RoutingContext | None = None,
    ) -> ConfidenceScore:
        """Score a single candidate against the query.

        Args:
            query: User's natural language query
            candidate: Skill candidate dictionary with 'id', 'name', 'description', 'intent'
            context: Additional routing context

        Returns:
            Confidence score between 0.0 and 1.0
        """
        ...

    def match(
        self,
        query: str,
        candidates: list[SkillCandidateDict],
        context: RoutingContext | None = None,
        top_k: int = 10,
    ) -> list[MatchResult]:
        """Match query against all candidates, sorted by confidence.

        Args:
            query: User's natural language query
            candidates: List of skill candidates
            context: Additional routing context
            top_k: Maximum number of results to return

        Returns:
            List of MatchResult, sorted by confidence (descending)
        """
        ...

    def warm_up(self, candidates: list[SkillCandidateDict]) -> None:
        """Warm up matcher by initializing lazy-loaded components.

        This prevents cold-start latency on the first route() call by
        pre-loading heavy components like embedding models.

        Args:
            candidates: List of skill candidates to use for warm-up
        """
        ...

    def preprocess(self, query: str) -> str:
        """Preprocess query text before matching.

        Args:
            query: Raw user query

        Returns:
            Preprocessed query string
        """
        ...

    def get_capabilities(self) -> MatcherCapabilitiesDict:
        """Return information about this matcher's capabilities.

        Returns:
            Dictionary with 'type', 'speed', 'accuracy', 'requires_semantic'
        """
        ...
