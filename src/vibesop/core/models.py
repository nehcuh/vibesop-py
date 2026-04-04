"""Core Pydantic models for VibeSOP.

All data structures use Pydantic v2 for runtime validation and type safety.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SkillRoute(BaseModel):
    """Result of skill routing operation.

    Attributes:
        skill_id: Unique skill identifier (e.g., '/review')
        confidence: Routing confidence (0.0 to 1.0)
        layer: Routing layer that matched (0-4)
        source: Skill pack source (e.g., 'builtin', 'gstack')
        metadata: Additional routing metadata
    """

    skill_id: str = Field(..., min_length=1, description="Skill identifier")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Routing confidence score",
    )
    layer: Literal[0, 1, 2, 3, 4] = Field(
        ...,
        description="Routing layer (0=AI, 1=Explicit, 2=Scenario, 3=Semantic, 4=Fuzzy)",
    )
    source: str = Field(..., description="Skill pack source")
    metadata: dict[str, str | int | float] = Field(
        default_factory=dict,
        description="Additional routing metadata",
    )

    @field_validator("skill_id")
    @classmethod
    def validate_skill_id(cls, v: str) -> str:
        """Validate skill ID format.

        Accepts formats:
        - /review (shorthand)
        - gstack/review (namespaced)
        - superpowers/refactor (namespaced)

        For consistency, ensures shorthand forms have a leading slash.
        """
        if not v:
            raise ValueError("skill_id cannot be empty")

        # Allow namespaced IDs (gstack/review, superpowers/refactor)
        if "/" in v and not v.startswith("/"):
            # Namespaced ID, validate format
            parts = v.split("/")
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError("skill_id must be in format 'namespace/skill' or '/skill'")
            return v

        # Shorthand ID (review), ensure leading slash
        if not v.startswith("/"):
            return f"/{v}"

        return v


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
        primary: Best matching skill
        alternatives: List of alternative matches
        routing_path: Which layers were consulted
    """

    primary: SkillRoute
    alternatives: list[SkillRoute] = Field(  # type: ignore[reportUnknownVariableType]
        default_factory=list,
        description="Alternative skill matches",
    )
    routing_path: list[Literal[0, 1, 2, 3, 4]] = Field(  # type: ignore[reportUnknownVariableType]
        default_factory=list,
        description="Layers consulted during routing",
    )


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
