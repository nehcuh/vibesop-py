"""Core Pydantic models for VibeSOP.

All data structures use Pydantic v2 for runtime validation and type safety.
This module is the single source of truth for routing models.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RoutingLayer(StrEnum):
    """Routing layers in priority order."""

    AI_TRIAGE = "ai_triage"
    EXPLICIT = "explicit"
    SCENARIO = "scenario"
    KEYWORD = "keyword"
    TFIDF = "tfidf"
    EMBEDDING = "embedding"
    LEVENSHTEIN = "levenshtein"
    NO_MATCH = "no_match"

    @property
    def layer_number(self) -> int:
        """Return numeric layer index for backward compatibility."""
        mapping = {
            RoutingLayer.AI_TRIAGE: 0,
            RoutingLayer.EXPLICIT: 1,
            RoutingLayer.SCENARIO: 2,
            RoutingLayer.KEYWORD: 3,
            RoutingLayer.TFIDF: 4,
            RoutingLayer.EMBEDDING: 5,
            RoutingLayer.LEVENSHTEIN: 6,
            RoutingLayer.NO_MATCH: 7,
        }
        return mapping[self]


class SkillRoute(BaseModel):
    """Result of skill routing operation.

    Attributes:
        skill_id: Unique skill identifier (e.g., 'gstack/review')
        confidence: Routing confidence (0.0 to 1.0)
        layer: Which routing layer made this decision
        source: Skill pack source (e.g., 'builtin', 'gstack', 'external')
        metadata: Additional routing metadata
    """

    model_config = {"arbitrary_types_allowed": True}

    skill_id: str = Field(..., min_length=1, description="Skill identifier")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Routing confidence score",
    )
    layer: RoutingLayer = Field(
        ...,
        description="Routing layer that produced this match",
    )
    source: str = Field(default="builtin", description="Skill pack source")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional routing metadata",
    )

    @field_validator("skill_id")
    @classmethod
    def validate_skill_id(cls, v: str) -> str:
        """Validate skill ID format."""
        if not v:
            raise ValueError("skill_id cannot be empty")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "skill_id": self.skill_id,
            "confidence": self.confidence,
            "layer": self.layer.value,
            "source": self.source,
            "metadata": self.metadata,
        }


class RoutingRequest(BaseModel):
    """Request for skill routing.

    Attributes:
        query: User's natural language query
        context: Additional context (file type, error count, etc.)
    """

    query: str = Field(..., min_length=1, description="User query")
    context: dict[str, str | int] = Field(
        default_factory=dict,
        description="Routing context",
    )


class RoutingResult(BaseModel):
    """Result of skill routing operation.

    Attributes:
        primary: Best matching skill (None if no match)
        alternatives: List of alternative matches
        routing_path: Which layers were consulted
        query: The original query
        duration_ms: How long routing took
    """

    model_config = {"arbitrary_types_allowed": True}

    primary: SkillRoute | None = Field(
        default=None,
        description="Primary skill match",
    )
    alternatives: list[SkillRoute] = Field(
        default_factory=list,
        description="Alternative skill matches",
    )
    routing_path: list[RoutingLayer] = Field(
        default_factory=list,
        description="Layers consulted during routing",
    )
    query: str = Field(default="", description="Original query")
    duration_ms: float = Field(default=0.0, description="Routing duration in ms")

    @property
    def has_match(self) -> bool:
        """Whether a match was found."""
        return self.primary is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "primary": self.primary.to_dict() if self.primary else None,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "routing_path": [layer.value for layer in self.routing_path],
            "query": self.query,
            "duration_ms": self.duration_ms,
            "has_match": self.has_match,
        }


class SkillDefinition(BaseModel):
    """Definition of a skill.

    Attributes:
        id: Unique skill identifier
        name: Human-readable name
        description: Skill description
        trigger_when: When this skill should be triggered
        metadata: Additional metadata
    """

    id: str = Field(..., min_length=1, description="Skill ID")
    name: str = Field(..., min_length=1, description="Skill name")
    description: str = Field(..., description="Skill description")
    trigger_when: str = Field(..., description="Trigger condition")
    metadata: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
        description="Additional metadata",
    )


class SkillRegistry(BaseModel):
    """Registry of all available skills.

    Attributes:
        skills: Map of skill_id to SkillDefinition
        version: Registry version
    """

    skills: dict[str, SkillDefinition] = Field(
        default_factory=dict,
        description="Available skills",
    )
    version: str = Field(default="1.0.0", description="Registry version")


class AppSettings(BaseSettings):
    """Application settings.

    Loaded from environment variables with type validation.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VIBE_",
        extra="ignore",
    )

    debug: bool = Field(default=False, description="Debug mode")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Log level",
    )
    llm_provider: Literal["anthropic", "openai"] = Field(
        default="anthropic",
        description="LLM provider",
    )
    anthropic_api_key: str | None = Field(
        default=None,
        description="Anthropic API key",
    )
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key",
    )


# Type aliases for better readability
SkillId = str
ConfidenceScore = float
