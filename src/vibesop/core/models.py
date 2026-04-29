"""Core Pydantic models for VibeSOP.

All data structures use Pydantic v2 for runtime validation and type safety.
This module is the single source of truth for routing models.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RoutingLayer(StrEnum):
    """Routing layers in priority order (Layer 0 → Layer 9)."""

    EXPLICIT = "explicit"           # Layer 0
    SCENARIO = "scenario"           # Layer 1
    AI_TRIAGE = "ai_triage"         # Layer 2
    KEYWORD = "keyword"             # Layer 3
    TFIDF = "tfidf"                 # Layer 4
    EMBEDDING = "embedding"         # Layer 5
    LEVENSHTEIN = "levenshtein"     # Layer 6
    CUSTOM = "custom"               # Layer 7
    NO_MATCH = "no_match"           # Layer 8
    FALLBACK_LLM = "fallback_llm"   # Layer 9

    @property
    def layer_number(self) -> int:
        """Return numeric layer index for backward compatibility."""
        mapping = {
            RoutingLayer.EXPLICIT: 0,
            RoutingLayer.SCENARIO: 1,
            RoutingLayer.AI_TRIAGE: 2,
            RoutingLayer.KEYWORD: 3,
            RoutingLayer.TFIDF: 4,
            RoutingLayer.EMBEDDING: 5,
            RoutingLayer.LEVENSHTEIN: 6,
            RoutingLayer.CUSTOM: 7,
            RoutingLayer.NO_MATCH: 8,
            RoutingLayer.FALLBACK_LLM: 9,
        }
        return mapping[self]


class DegradationLevel(StrEnum):
    """Confidence-gated degradation levels for skill routing fallback.

    Replaces binary fallback (match/no-match) with layered degradation:
    - AUTO: high confidence, auto-select
    - SUGGEST: moderate confidence, show with alternatives
    - DEGRADE: low confidence, use skill but warn
    - FALLBACK: below threshold, raw LLM
    """

    AUTO = "auto"
    SUGGEST = "suggest"
    DEGRADE = "degrade"
    FALLBACK = "fallback"


class SkillLifecycle(StrEnum):
    """Lifecycle states for a skill.

    State machine:
        DRAFT → ACTIVE → DEPRECATED → ARCHIVED
              ↘ ACTIVE (re-activation from deprecated)
    """

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


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
    description: str = Field(
        default="",
        description="Skill description for display in CLI",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional routing metadata",
    )

    # Note: min_length=1 on the Field already enforces non-empty skill_id
    # No additional field_validator needed

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


class RejectedCandidate(BaseModel):
    """A candidate that was considered but rejected by a routing layer.

    Attributes:
        skill_id: The rejected skill identifier
        confidence: Confidence score (below threshold)
        layer: Which layer rejected this candidate
        reason: Why it was rejected (e.g., "below threshold (0.6)")
    """

    model_config = {"arbitrary_types_allowed": True}

    skill_id: str = Field(..., description="Rejected skill identifier")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score below threshold",
    )
    layer: RoutingLayer = Field(..., description="Layer that rejected candidate")
    reason: str = Field(default="", description="Rejection reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "confidence": self.confidence,
            "layer": self.layer.value,
            "reason": self.reason,
        }


class LayerDetail(BaseModel):
    """Detailed diagnostic for a single routing layer attempt.

    Attributes:
        layer: Which routing layer this represents
        matched: Whether this layer produced a match
        reason: Human-readable explanation of the layer's decision
        duration_ms: How long this layer took
        diagnostics: Layer-specific diagnostic data (scores, skip reasons, etc.)
        rejected_candidates: Candidates that were close but didn't meet threshold
    """

    model_config = {"arbitrary_types_allowed": True}

    layer: RoutingLayer = Field(..., description="Routing layer")
    matched: bool = Field(default=False, description="Whether layer matched")
    reason: str = Field(default="", description="Human-readable decision reason")
    duration_ms: float = Field(default=0.0, description="Layer duration in ms")
    diagnostics: dict[str, Any] = Field(
        default_factory=dict,
        description="Layer-specific diagnostic data",
    )
    rejected_candidates: list[RejectedCandidate] = Field(
        default_factory=list,
        description="Candidates close to threshold but rejected",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "layer": self.layer.value,
            "matched": self.matched,
            "reason": self.reason,
            "duration_ms": self.duration_ms,
            "diagnostics": self.diagnostics,
            "rejected_candidates": [r.to_dict() for r in self.rejected_candidates],
        }


class RoutingResult(BaseModel):
    """Result of skill routing operation.

    Attributes:
        primary: Best matching skill (None if no match)
        alternatives: List of alternative matches
        routing_path: Which layers were consulted
        layer_details: Per-layer diagnostic details for transparency
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
    layer_details: list[LayerDetail] = Field(
        default_factory=list,
        description="Per-layer diagnostic details for transparency",
    )
    query: str = Field(default="", description="Original query")
    duration_ms: float = Field(default=0.0, description="Routing duration in ms")

    @property
    def has_match(self) -> bool:
        """Whether a match was found (excluding fallback)."""
        return self.primary is not None and self.primary.layer != RoutingLayer.FALLBACK_LLM

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "primary": self.primary.to_dict() if self.primary else None,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "routing_path": [layer.value for layer in self.routing_path],
            "layer_details": [d.to_dict() for d in self.layer_details],
            "query": self.query,
            "duration_ms": self.duration_ms,
            "has_match": self.has_match,
        }


class StepStatus(StrEnum):
    """Status of an execution step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class PlanStatus(StrEnum):
    """Status of an execution plan."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionMode(StrEnum):
    """Execution mode for a plan."""

    SEQUENTIAL = "sequential"  # Steps run one after another
    PARALLEL = "parallel"  # Independent steps run concurrently
    MIXED = "mixed"  # Automatically determine based on dependencies


class ExecutionStep(BaseModel):
    """A single step in a multi-skill execution plan.

    Attributes:
        step_id: Unique identifier for this step
        step_number: 1-based position in the plan
        skill_id: Target skill to use
        intent: Human-readable description of this step's intent
        input_query: Query to send to the skill
        output_as: Variable name for downstream steps to reference
        status: Current execution status
        result_summary: Brief result after execution (optional)
        started_at: ISO timestamp when step started
        completed_at: ISO timestamp when step completed
    """

    model_config = {"arbitrary_types_allowed": True}

    step_id: str = Field(..., description="Step UUID")
    step_number: int = Field(..., ge=1, description="Step position")
    skill_id: str = Field(..., description="Target skill ID")
    intent: str = Field(default="", description="Human-readable intent")
    input_query: str = Field(default="", description="Query for this step")
    output_as: str = Field(default="", description="Output variable name")
    status: StepStatus = Field(default=StepStatus.PENDING, description="Step status")
    result_summary: str | None = Field(default=None, description="Execution result summary")
    started_at: str | None = Field(default=None, description="Start timestamp")
    completed_at: str | None = Field(default=None, description="Completion timestamp")
    dependencies: list[str] = Field(
        default_factory=list,
        description="Step IDs this step depends on (empty = can run in parallel)",
    )
    can_parallel: bool = Field(
        default=True, description="Whether this step can run in parallel with independent steps"
    )
    parallel_group: int | None = Field(
        default=None,
        description="Group ID for parallel execution (steps in same group run together)",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_id": self.step_id,
            "step_number": self.step_number,
            "skill_id": self.skill_id,
            "intent": self.intent,
            "input_query": self.input_query,
            "output_as": self.output_as,
            "status": self.status.value,
            "result_summary": self.result_summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "dependencies": self.dependencies,
            "can_parallel": self.can_parallel,
            "parallel_group": self.parallel_group,
        }


class ExecutionPlan(BaseModel):
    """A multi-skill execution plan.

    Attributes:
        plan_id: Unique plan identifier
        original_query: The user's original request
        steps: Ordered list of execution steps
        detected_intents: List of intents detected in the original query
        reasoning: Why this decomposition was chosen
        created_at: ISO timestamp when plan was created
        status: Overall plan status
    """

    model_config = {"arbitrary_types_allowed": True}

    plan_id: str = Field(..., description="Plan UUID")
    original_query: str = Field(default="", description="Original user query")
    steps: list[ExecutionStep] = Field(default_factory=list, description="Execution steps")
    detected_intents: list[str] = Field(default_factory=list, description="Detected intents")
    reasoning: str = Field(default="", description="Decomposition reasoning")
    created_at: str = Field(default="", description="Creation timestamp")
    status: PlanStatus = Field(default=PlanStatus.PENDING, description="Plan status")
    execution_mode: ExecutionMode = Field(
        default=ExecutionMode.SEQUENTIAL, description="How steps should be executed"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "plan_id": self.plan_id,
            "original_query": self.original_query,
            "steps": [s.to_dict() for s in self.steps],
            "detected_intents": self.detected_intents,
            "reasoning": self.reasoning,
            "created_at": self.created_at,
            "status": self.status.value,
            "execution_mode": self.execution_mode.value,
        }

    def get_parallel_groups(self) -> list[list["ExecutionStep"]]:
        """Group steps into parallel batches based on dependencies.

        Returns:
            List of step groups, where each group can run in parallel.
            Example: [[step1], [step2, step3], [step4]] means:
                - step1 runs first
                - step2 and step3 run in parallel
                - step4 runs after step2 and step3 complete
        """
        if not self.steps:
            return []

        # If no dependencies defined, treat as sequential
        if not any(step.dependencies for step in self.steps):
            return [[step] for step in self.steps]

        # Build dependency graph and perform topological sort
        completed = set()
        groups = []

        while len(completed) < len(self.steps):
            # Find all steps whose dependencies are satisfied
            ready = [
                step
                for step in self.steps
                if step.step_id not in completed
                and all(dep in completed for dep in step.dependencies)
                and step.can_parallel
            ]

            if not ready:
                # No progress - likely circular dependency or remaining non-parallel steps
                remaining = [step for step in self.steps if step.step_id not in completed]
                groups.append(remaining)
                break

            groups.append(ready)
            completed.update(step.step_id for step in ready)

        return groups

    def get_execution_summary(self) -> dict[str, Any]:
        """Get summary of execution plan including parallel groups."""
        parallel_groups = self.get_parallel_groups()

        return {
            "plan_id": self.plan_id,
            "total_steps": len(self.steps),
            "execution_mode": self.execution_mode.value,
            "parallel_groups": len(parallel_groups),
            "max_parallel": max(len(g) for g in parallel_groups) if parallel_groups else 0,
            "groups": [
                {
                    "group_number": i + 1,
                    "step_count": len(group),
                    "step_ids": [s.step_id for s in group],
                }
                for i, group in enumerate(parallel_groups)
            ],
        }


class OrchestrationMode(StrEnum):
    """Mode of orchestration result."""

    SINGLE = "single"
    ORCHESTRATED = "orchestrated"


class OrchestrationResult(BaseModel):
    """Result of orchestration — either single skill or multi-step plan.

    This unifies single-skill routing and multi-skill orchestration
    into one return type for consumers.
    """

    model_config = {"arbitrary_types_allowed": True}

    mode: OrchestrationMode = Field(
        default=OrchestrationMode.SINGLE,
        description="Orchestration mode",
    )
    original_query: str = Field(default="", description="Original query")

    # SINGLE mode fields
    primary: SkillRoute | None = Field(default=None, description="Primary skill match")
    alternatives: list[SkillRoute] = Field(default_factory=list, description="Alternative matches")
    routing_path: list[RoutingLayer] = Field(default_factory=list, description="Routing path")
    layer_details: list[LayerDetail] = Field(default_factory=list, description="Layer details")
    duration_ms: float = Field(default=0.0, description="Routing duration in ms")

    # ORCHESTRATED mode fields
    execution_plan: ExecutionPlan | None = Field(default=None, description="Execution plan")
    single_fallback: SkillRoute | None = Field(
        default=None,
        description="Best single skill if user rejects plan",
    )

    @property
    def has_match(self) -> bool:
        """Whether any match was found (single or orchestrated), excluding fallback."""
        return (self.primary is not None and self.primary.layer != RoutingLayer.FALLBACK_LLM) or (
            self.execution_plan is not None and len(self.execution_plan.steps) > 0
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "mode": self.mode.value,
            "original_query": self.original_query,
            "primary": self.primary.to_dict() if self.primary else None,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "routing_path": [layer.value for layer in self.routing_path],
            "layer_details": [d.to_dict() for d in self.layer_details],
            "duration_ms": self.duration_ms,
            "execution_plan": self.execution_plan.to_dict() if self.execution_plan else None,
            "single_fallback": self.single_fallback.to_dict() if self.single_fallback else None,
            "has_match": self.has_match,
        }

    def to_routing_result(self) -> RoutingResult:
        """Extract a single-skill RoutingResult from this orchestration result.

        When mode=SINGLE, returns the routing result directly.
        When mode=ORCHESTRATED, returns the single_fallback as primary.
        """
        primary = (
            self.single_fallback if self.mode == OrchestrationMode.ORCHESTRATED else self.primary
        )

        # Build layer_details from the existing fields if present, otherwise empty
        layer_details = self.layer_details or []

        # Build routing_path from detected layers, falling back to NO_MATCH
        if self.routing_path:
            routing_path = self.routing_path
        elif self.primary and self.primary.layer:
            routing_path = [self.primary.layer]
        else:
            routing_path = [RoutingLayer.FALLBACK_LLM]

        return RoutingResult(
            primary=primary,
            alternatives=self.alternatives or [],
            routing_path=routing_path,
            layer_details=layer_details,
            duration_ms=self.duration_ms,
            query=self.original_query,
        )


class SkillDefinition(BaseModel):
    """Definition of a skill.

    Attributes:
        id: Unique skill identifier
        name: Human-readable name
        description: Skill description
        trigger_when: When this skill should be triggered
        metadata: Additional metadata
        lifecycle: Current lifecycle state (draft/active/deprecated/archived)
        scope: Availability scope (global or project-specific)
        enabled: Whether this skill is enabled for routing
        version: Skill version string
    """

    id: str = Field(..., min_length=1, description="Skill ID")
    name: str = Field(..., min_length=1, description="Skill name")
    description: str = Field(..., description="Skill description")
    trigger_when: str = Field(..., description="Trigger condition")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )
    lifecycle: SkillLifecycle = Field(
        default=SkillLifecycle.ACTIVE,
        description="Lifecycle state: draft, active, deprecated, archived",
    )
    scope: str = Field(
        default="global",
        description="Scope: global (all projects) or project (specific project)",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this skill is enabled for routing",
    )
    version: str = Field(
        default="1.0.0",
        description="Skill version",
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
    llm_provider: Literal["anthropic", "openai", "ollama"] = Field(
        default="ollama",
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


@dataclass
class StepManifest:
    """执行清单中单个步骤的完整信息。

    PlanExecutor 生成此结构，让 AI Agent 无需手动加载 SKILL.md
    即可获取执行单个步骤所需的全部上下文。

    Attributes:
        step_number: 1-based step position
        skill_id: Target skill identifier
        skill_name: Human-readable skill name
        skill_path: SKILL.md path on disk (str for serialization)
        skill_content: Full SKILL.md content (embedded so agent doesn't load it)
        input_context: Output summary from upstream steps (as context for this step)
        output_slot: Variable name for downstream steps to reference this step's output
        completion_marker: Standardized marker the agent must emit when done
        instruction: Concise execution instruction for this step
    """

    step_number: int
    skill_id: str
    skill_name: str = ""
    skill_path: str = ""
    skill_content: str = ""
    input_context: str = ""
    output_slot: str = ""
    completion_marker: str = ""
    instruction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "skill_path": self.skill_path,
            "skill_content": self.skill_content,
            "input_context": self.input_context,
            "output_slot": self.output_slot,
            "completion_marker": self.completion_marker,
            "instruction": self.instruction,
        }

    @staticmethod
    def completion_marker_for(step_number: int) -> str:
        """Build the standardized completion marker for a step."""
        return f"[StepCompleted:{step_number}]"


@dataclass
class ExecutionManifest:
    """完整的编排执行清单。

    包含编排计划中所有步骤的完整信息（含内嵌 SKILL.md 内容），
    AI Agent 读取此清单即可分步执行，无需手动加载技能文件或查找上下文。

    Attributes:
        plan_id: Plan UUID
        original_query: The user's original request
        strategy: Execution strategy (sequential | parallel | mixed)
        steps: Ordered list of StepManifest entries
        context_file: Path to .vibe/plans/{plan_id}/context.md
    """

    plan_id: str
    original_query: str = ""
    strategy: str = "sequential"
    steps: list[StepManifest] = field(default_factory=list)
    context_file: str = ""

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def has_parallel_groups(self) -> bool:
        return self.strategy in ("parallel", "mixed")

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "original_query": self.original_query,
            "strategy": self.strategy,
            "steps": [s.to_dict() for s in self.steps],
            "context_file": self.context_file,
            "total_steps": self.total_steps,
        }

    def to_markdown(self) -> str:
        """Render the manifest as a markdown execution sequence file.

        This file can be written to disk and read by the agent step-by-step.
        """
        lines = [
            f"# Execution Manifest: {self.original_query}",
            "",
            f"**Plan**: {self.plan_id}",
            f"**Strategy**: {self.strategy}",
            f"**Steps**: {self.total_steps}",
            "",
            "---",
            "",
            "## Execution Rules",
            "",
            "1. Execute steps in numbered order (step groups may be parallel)",
            "2. Each step includes the full SKILL.md content — read it before executing",
            "3. After completing a step, emit the completion marker exactly",
            "4. Data marked as `input_context` is output from an upstream step",
            "5. If a step fails, report the error before continuing",
            "",
            "---",
            "",
        ]

        for step in self.steps:
            lines.extend(
                [
                    f"## Step {step.step_number}: {step.skill_id}",
                    "",
                    f"**Skill**: {step.skill_name}",
                    "",
                ]
            )

            if step.input_context:
                lines.extend(
                    [
                        "### Input Context (from upstream steps)",
                        "",
                        step.input_context,
                        "",
                    ]
                )

            lines.extend(
                [
                    "### Instruction",
                    "",
                    step.instruction,
                    "",
                    "### Skill Content (SKILL.md inlined)",
                    "",
                    "```markdown",
                    step.skill_content,
                    "```",
                    "",
                    "### Completion",
                    "",
                    f"完成后必须输出: `<!-- {step.completion_marker} -->` 并附上结果摘要",
                    "",
                    "---",
                    "",
                ]
            )

        lines.extend(
            [
                "## Final Verification",
                "",
                "All steps completed. Verify:",
            ]
        )
        for step in self.steps:
            lines.append(
                f"- [ ] Step {step.step_number} — {step.skill_id}: `<!-- {step.completion_marker} -->`"
            )

        return "\n".join(lines)


# Type aliases for better readability
SkillId = str
ConfidenceScore = float
