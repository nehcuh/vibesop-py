"""Data models for the keyword trigger system.

This module defines the core data structures used for pattern matching
and intent detection.
"""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator


class PatternCategory(str, Enum):
    """Categories of trigger patterns.

    Patterns are organized into logical categories to help with
    organization, filtering, and priority management.
    """

    SECURITY = "security"
    """Security-related patterns (scanning, analysis, threats)"""

    CONFIG = "config"
    """Configuration management patterns (deploy, validate, render)"""

    DEV = "dev"
    """Development patterns (build, test, debug, refactor)"""

    DOCS = "docs"
    """Documentation patterns (generate, update, format)"""

    PROJECT = "project"
    """Project management patterns (setup, migrate, audit)"""

    def __str__(self) -> str:
        return self.value


class TriggerPattern(BaseModel):
    """A trigger pattern for automatic intent detection.

    Trigger patterns define how the system recognizes user intent from
    natural language input. Each pattern combines multiple strategies
    (keywords, regex, semantic similarity) for robust detection.

    Attributes:
        pattern_id: Unique identifier (e.g., "security/scan")
        name: Human-readable name
        description: What this pattern matches
        category: Pattern category for organization
        keywords: Key trigger words for keyword matching (40% weight)
        regex_patterns: Regex patterns for pattern matching (30% weight)
        skill_id: Skill to activate when pattern matches
        workflow_id: Optional workflow to run instead of skill
        priority: Higher priority patterns are checked first (1-100)
        confidence_threshold: Minimum confidence score to match (0.0-1.0)
        examples: Example queries that should match this pattern
        metadata: Additional pattern metadata

    Example:
        >>> pattern = TriggerPattern(
        ...     pattern_id="security/scan",
        ...     name="Security Scan",
        ...     description="Detects security scanning requests",
        ...     category=PatternCategory.SECURITY,
        ...     keywords=["扫描", "scan", "检查", "安全", "漏洞"],
        ...     regex_patterns=[r"扫描.*安全", r"安全.*检查"],
        ...     skill_id="/security/scan",
        ...     workflow_id="security-review",
        ...     priority=100,
        ...     confidence_threshold=0.6,
        ...     examples=["扫描安全漏洞", "检查安全问题", "scan for vulnerabilities"]
        ... )
    """

    pattern_id: str = Field(..., min_length=1, description="Unique pattern identifier")
    name: str = Field(..., min_length=1, description="Human-readable pattern name")
    description: str = Field(..., description="What this pattern matches")
    category: PatternCategory = Field(..., description="Pattern category")
    keywords: list[str] = Field(default_factory=list, description="Keywords for keyword matching")
    regex_patterns: list[str] = Field(
        default_factory=list, description="Regex patterns for pattern matching"
    )
    skill_id: str = Field(..., description="Skill to activate when matched")
    workflow_id: str | None = Field(
        default=None, description="Optional workflow to run instead of skill"
    )
    priority: int = Field(
        default=50, ge=1, le=100, description="Pattern priority (higher = checked first)"
    )
    confidence_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Minimum confidence to match"
    )
    examples: list[str] = Field(default_factory=list, description="Example queries that match")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional pattern metadata"
    )

    # Semantic matching fields (v2.1.0)
    enable_semantic: bool = Field(
        default=False, description="Enable semantic matching for this pattern"
    )
    semantic_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Semantic similarity threshold for this pattern"
    )
    semantic_examples: list[str] = Field(
        default_factory=list, description="Additional semantic examples for enhanced understanding"
    )
    embedding_vector: list[float] | None = Field(
        default=None, description="Pre-computed embedding vector (JSON serialized)"
    )

    @field_validator("pattern_id")
    @classmethod
    def validate_pattern_id(cls, v: str) -> str:
        """Validate pattern_id format."""
        if "/" not in v:
            raise ValueError(f"pattern_id must contain '/' (category/name): {v}")
        parts = v.split("/")
        if len(parts) != 2:
            raise ValueError(f"pattern_id must be 'category/name' format: {v}")
        return v

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: list[str]) -> list[str]:
        """Validate keywords are non-empty and unique."""
        if not v:
            return v

        # Check for empty strings
        if any(not kw.strip() for kw in v):
            raise ValueError("Keywords cannot be empty strings")

        # Normalize and deduplicate
        seen: set[str] = set()
        normalized: list[str] = []
        for kw in v:
            kw_lower = kw.lower().strip()
            if kw_lower and kw_lower not in seen:
                seen.add(kw_lower)
                normalized.append(kw_lower)

        return normalized

    def matches_threshold(self, confidence: float) -> bool:
        """Check if confidence score meets threshold.

        Args:
            confidence: Confidence score from matching

        Returns:
            True if confidence >= threshold
        """
        return confidence >= self.confidence_threshold


class PatternMatch(BaseModel):
    """Result of pattern matching operation.

    Contains information about which pattern matched and the
    confidence score of the match.

    Attributes:
        pattern_id: ID of matched pattern
        confidence: Confidence score (0.0 - 1.0)
        metadata: Additional match information
        matched_keywords: Keywords that matched
        matched_regex: Regex patterns that matched
        semantic_score: Semantic similarity score

    Example:
        >>> match = PatternMatch(
        ...     pattern_id="security/scan",
        ...     confidence=0.95,
        ...     metadata={"category": "security"},
        ...     matched_keywords=["扫描", "安全"],
        ...     matched_regex=[r"扫描.*安全"],
        ...     semantic_score=0.85
        ... )
    """

    pattern_id: str = Field(..., description="ID of matched pattern")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0 - 1.0)")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional match information"
    )
    matched_keywords: list[str] = Field(default_factory=list, description="Keywords that matched")
    matched_regex: list[str] = Field(
        default_factory=list, description="Regex patterns that matched"
    )
    semantic_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Semantic similarity score"
    )
    # Additional semantic fields (v2.1.0)
    semantic_method: str | None = Field(
        default=None, description="Method used for semantic matching (e.g., 'cosine', 'hybrid')"
    )
    model_used: str | None = Field(default=None, description="Name of the embedding model used")
    encoding_time: float | None = Field(
        default=None, ge=0.0, description="Time taken to encode query (in seconds)"
    )

    def meets_threshold(self, threshold: float) -> bool:
        """Check if match meets minimum confidence threshold.

        Args:
            threshold: Minimum confidence threshold

        Returns:
            True if confidence >= threshold
        """
        return self.confidence >= threshold
