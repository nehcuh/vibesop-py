"""Canonical SKILL.md specification models.

SkillSpec is the single authoritative definition of a skill's metadata,
replacing four competing definitions that previously existed across the codebase.

All 29 fields that the SKILL.md format supports are captured here, including
12 that were previously read from frontmatter but discarded by the parser.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SkillType(StrEnum):
    """Skill types matching the canonical spec.

    Note: STANDARD is added in v3.0 to fix a long-standing bug where 6 of 13
    core skills used type: standard but the enum lacked this value, causing
    silent fallback to PROMPT.
    """

    PROMPT = "prompt"
    WORKFLOW = "workflow"
    COMMAND = "command"
    HYBRID = "hybrid"
    STANDARD = "standard"


class SkillLifecycle(StrEnum):
    """Lifecycle states for a skill."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class LLMConfigSpec(BaseModel):
    """LLM configuration for a skill (from spec v2, now canonical)."""

    provider: str | None = Field(default=None, description="LLM provider name")
    model: str | None = Field(default=None, description="Model identifier")
    temperature: float | None = Field(default=None, description="Sampling temperature")
    api_key: str | None = Field(default=None, description="API key (env var name)")
    api_base: str | None = Field(default=None, description="API base URL")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional provider-specific parameters",
    )
    fallback: str | None = Field(default=None, description="Fallback provider")


class SourceConfigSpec(BaseModel):
    """Source configuration for a skill (from spec v2, now canonical)."""

    type: str = Field(default="github", description="Source type: github, url, local")
    repository: str | None = Field(default=None, description="Git repository URL")
    checksum: str | None = Field(default=None, description="Content checksum")
    ref: str | None = Field(default=None, description="Git ref (branch, tag, commit)")


class SkillSpec(BaseModel):
    """Canonical skill specification -- the single source of truth for SKILL.md metadata.

    This model captures all 29 fields that the SKILL.md format supports.
    Fields previously discarded by the parser (commands, user_invocable,
    allowed_tools, mode, routing_patterns, priority, category, dependencies,
    env_vars, llm_config, source_config) are now properly stored.
    """

    model_config = {"arbitrary_types_allowed": True, "populate_by_name": True}

    # ---- Required fields ----
    id: str = Field(..., min_length=1, description="Unique skill identifier, e.g. 'gstack/review'")
    name: str = Field(..., min_length=1, description="Human-readable name")
    description: str = Field(..., description="Short description of what the skill does")
    version: str = Field(default="1.0.0", description="SemVer version string")

    # ---- Optional identity fields ----
    author: str = Field(default="", description="Skill author")
    namespace: str = Field(
        default="builtin", description="Skill namespace: builtin, gstack, superpowers, project"
    )

    # ---- Type & intent ----
    skill_type: SkillType = Field(
        default=SkillType.PROMPT,
        alias="type",
        description="Skill type. Frontmatter key is 'type', stored as 'skill_type'.",
    )
    intent: str | None = Field(
        default=None,
        description="What the skill does, used for routing. Auto-derived from description if absent.",
    )

    # ---- Routing fields ----
    trigger_when: str = Field(default="", description="When to trigger this skill")
    triggers: list[str] = Field(default_factory=list, description="Trigger phrases for routing")
    routing_patterns: list[str] = Field(
        default_factory=list,
        description="Regex/natural-language patterns for scenario-based routing",
    )
    priority: int = Field(
        default=50, ge=1, le=100, description="Routing priority (higher = preferred)"
    )

    # ---- Categorization ----
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    keywords: list[str] = Field(
        default_factory=list, description="Search keywords (distinct from tags)"
    )
    category: str = Field(
        default="development", description="Skill category: development, testing, ops, docs, etc."
    )

    # ---- Capabilities ----
    capabilities: list[str] = Field(
        default_factory=list,
        description="Capability tags: analysis, review, design, debug, refactor, plan, test, etc.",
    )
    algorithms: list[str] = Field(default_factory=list, description="Algorithmic strategies used")

    # ---- Command interface ----
    commands: list[str] = Field(
        default_factory=list,
        description="CLI sub-commands this skill provides (e.g. ['route', 'list'])",
    )
    user_invocable: bool = Field(
        default=False,
        description="Whether this skill can be invoked by the user via slash command",
    )
    allowed_tools: list[str] = Field(
        default_factory=list,
        description="Tool names the skill is allowed to use (e.g. ['Read', 'Write', 'Bash'])",
    )

    # ---- Operational mode ----
    mode: str = Field(default="", description="Operational mode, e.g. 'observe-only'")

    # ---- Lifecycle & scope ----
    lifecycle: SkillLifecycle = Field(default=SkillLifecycle.ACTIVE, description="Lifecycle state")
    scope: str = Field(default="global", description="Scope: global or project")
    enabled: bool = Field(default=True, description="Whether this skill is enabled for routing")
    deprecation_reason: str | None = Field(default=None, description="Reason for deprecation")

    # ---- Environment & dependencies ----
    dependencies: list[str] = Field(
        default_factory=list,
        description="Required pip packages",
    )
    env_vars: list[str] = Field(
        default_factory=list,
        description="Required environment variables",
    )

    # ---- LLM configuration ----
    llm_config: LLMConfigSpec | None = Field(
        default=None,
        description="LLM provider and model configuration",
    )
    source_config: SourceConfigSpec | None = Field(
        default=None,
        description="Source repository and verification info",
    )

    # ---- Display & metadata ----
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Default confidence score")
    auto_configured: bool = Field(default=False, description="Whether config was auto-detected")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extension point for non-standard metadata",
    )
