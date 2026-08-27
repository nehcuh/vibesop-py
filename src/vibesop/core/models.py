"""Core Pydantic models for VibeSOP.

All data structures use Pydantic v2 for runtime validation and type safety.
This module is the single source of truth for routing models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from vibesop.spec import SkillSpec


class RoutingLayer(StrEnum):
    """Routing layers (4-stage cascade; layer_number is a display-only index)."""

    EXPLICIT = "explicit"  # Stage 1
    SCENARIO = "scenario"  # Stage 2
    SEMANTIC_INDEX = "semantic_index"  # Stage 2 (Skill Semantic Index: token-overlap + embedding)
    AI_TRIAGE = "ai_triage"  # Stage 3 (LLM triage)
    KEYWORD = "keyword"  # Stage 4
    TFIDF = "tfidf"  # Stage 4
    EMBEDDING = "embedding"  # Stage 4
    LEVENSHTEIN = "levenshtein"  # Stage 4
    CUSTOM = "custom"  # Stage 4
    NO_MATCH = "no_match"  # terminal
    FALLBACK_LLM = "fallback_llm"  # terminal

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
            # SEMANTIC_INDEX gets 10 (not inserted at 2) so the renumber does
            # NOT shift existing layers — persisted trace layer_numbers (tracer.py)
            # keep their meaning. (kimi HIGH #6: inserting at 2 broke old traces.)
            RoutingLayer.SEMANTIC_INDEX: 10,
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
    """Result of skill routing operation."""

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
    score_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="Per-matcher score contributions",
    )

    # Note: min_length=1 on the Field already enforces non-empty skill_id
    # No additional field_validator needed

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "confidence": self.confidence,
            "layer": self.layer.value,
            "source": self.source,
            "description": self.description,
            "metadata": self.metadata,
        }


class RoutingRequest(BaseModel):
    """Request for skill routing."""

    query: str = Field(..., min_length=1, description="User query")
    context: dict[str, str | int] = Field(
        default_factory=dict,
        description="Routing context",
    )


class RejectedCandidate(BaseModel):
    """A candidate that was considered but rejected by a routing layer."""

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
    """Detailed diagnostic for a single routing layer attempt."""

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
        return {
            "layer": self.layer.value,
            "matched": self.matched,
            "reason": self.reason,
            "duration_ms": self.duration_ms,
            "diagnostics": self.diagnostics,
            "rejected_candidates": [r.to_dict() for r in self.rejected_candidates],
        }


class RoutingResult(BaseModel):
    """Result of skill routing operation."""

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
    PARALLEL = "parallel"  # Steps grouped for concurrent execution (execution by Agent, not here)
    MIXED = "mixed"  # Automatically determine based on dependencies


class WorkflowPattern(StrEnum):
    """Dynamic workflow pattern for orchestration.

    Patterns are selected at plan-generation time by the ClassifierAgent
    based on query semantics.  Each pattern maps to a specific execution
    strategy without changing the underlying skill definitions.
    """

    SEQUENTIAL = "sequential"  # Default: steps run in order (existing behaviour)
    PARALLEL = "parallel"  # Independent steps run concurrently
    FAN_OUT = "fan_out"  # Multiple sub-tasks in parallel → synthesise results
    ADVERSARIAL = "adversarial"  # Execute → independent verification
    LOOP_UNTIL_DRY = "loop_until_dry"  # Iterative refinement until no new discoveries
    TOURNAMENT = "tournament"  # Multiple contestants → judge picks champion
    PROMPT_CHAIN = "prompt_chain"  # Generate structured prompt files for Claude Code Agent SDK
    AGENT_SQUAD = "agent_squad"  # Multi-role agent squad with per-role skills
    DEBATE = "debate"  # Contestants argue, orchestrator judges
    RED_TEAM = "red_team"  # Implement → red-team challenge → fix


class DynamicNodeStatus(StrEnum):
    """Status of a node in the dynamic execution graph."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_VERIFICATION = "awaiting_verification"
    COMPLETED = "completed"
    LOOPING = "looping"
    FAILED = "failed"


class ReorchestrationDecision(StrEnum):
    """Decision after re-orchestration analysis."""

    CONTINUE = "continue"  # Proceed to next planned step
    APPEND_STEPS = "append_steps"  # New sub-tasks discovered
    LOOP_BACK = "loop_back"  # Re-execute a previous step
    ESCALATE = "escalate"  # User intervention needed
    TERMINATE_EARLY = "terminate_early"  # All goals met


class TrustLevel(StrEnum):
    """Runtime trust level for agents and skills.

    Trust levels control the execution context and restrictions:
    - NORMAL: Default execution trust for routine agent steps
    - TRUSTED: Normal execution, can modify files and run commands
    - QUARANTINE: Read-only execution, cannot modify system state
    - SANDBOX: Full isolation, runs in temporary environment
    """

    NORMAL = "normal"  # Default execution trust for routine agent steps
    TRUSTED = "trusted"  # Normal execution, can modify files and run commands
    QUARANTINE = "quarantine"  # Read-only, no side effects (default for verifier)
    SANDBOX = "sandbox"  # Full isolation in temporary environment


class ExecutionStep(BaseModel):
    """A single step in a multi-skill execution plan."""

    model_config = {"arbitrary_types_allowed": True}

    step_id: str = Field(..., description="Step UUID")
    step_number: int = Field(..., ge=1, description="Step position")
    skill_id: str = Field(..., description="Target skill ID")
    intent: str = Field(default="", description="Human-readable intent")
    original_query_segment: str = Field(
        default="", description="Original query segment that triggered this step"
    )
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
    # Phase 2 (v6.1.0): Verification fields
    is_verification_step: bool = Field(
        default=False, description="Whether this step is a verification step (adversarial workflow)"
    )
    verification_result: dict[str, Any] | None = Field(
        default=None, description="Verification result (if this is a verification step)"
    )
    # Phase 2 (v6.1.0): Trust level for execution
    trust_level: TrustLevel = Field(
        default=TrustLevel.TRUSTED,
        description="Trust level for this step's execution",
    )
    # Phase 3 (v6.2.0): Dynamic execution fields
    dynamic_status: DynamicNodeStatus | None = Field(
        default=None, description="Dynamic graph node status (Phase 3 patterns only)"
    )
    loop_iteration: int = Field(
        default=0, description="Current loop iteration (for LOOP_UNTIL_DRY pattern)"
    )
    contestant_index: int | None = Field(
        default=None,
        description="Contestant index (for TOURNAMENT pattern, None = not a contestant)",
    )
    # Phase 7.0 (v7.0.0): Prompt Chain enrichment
    step_type: str = Field(
        default="implementation",
        description="步骤类型: analysis / quick_win / implementation / refactor / review / security",
    )
    estimated_risk: str = Field(
        default="low",
        description="预估风险: low / medium / high",
    )
    estimated_file_count: int = Field(
        default=0,
        description="预估涉及的文件数量",
    )
    source_files: list[str] = Field(
        default_factory=list,
        description="本步骤涉及的源文件路径列表",
    )
    # Phase 3 (v7.1.0): Agent squad fields
    assigned_role: str | None = Field(
        default=None,
        description="Role ID assigned to this step in an agent squad",
    )
    agent_squad_id: str | None = Field(
        default=None,
        description="Agent squad ID this step belongs to",
    )
    role_skills: list[str] = Field(
        default_factory=list,
        description="Skills available to the assigned role for this step",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Routing confidence for this step (0 when unknown)",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_number": self.step_number,
            "skill_id": self.skill_id,
            "intent": self.intent,
            "original_query_segment": self.original_query_segment,
            "input_query": self.input_query,
            "output_as": self.output_as,
            "status": self.status.value,
            "result_summary": self.result_summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "dependencies": self.dependencies,
            "can_parallel": self.can_parallel,
            "parallel_group": self.parallel_group,
            "is_verification_step": self.is_verification_step,
            "verification_result": self.verification_result,
            "trust_level": self.trust_level.value,
            "dynamic_status": self.dynamic_status.value if self.dynamic_status else None,
            "loop_iteration": self.loop_iteration,
            "contestant_index": self.contestant_index,
            "step_type": self.step_type,
            "estimated_risk": self.estimated_risk,
            "estimated_file_count": self.estimated_file_count,
            "source_files": self.source_files,
            "assigned_role": self.assigned_role,
            "agent_squad_id": self.agent_squad_id,
            "role_skills": self.role_skills,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionStep:
        """Reconstruct an ExecutionStep from ``to_dict()`` output.

        Tolerates missing keys by falling back to model defaults. Closes
        the v7.0.10 schema-drift gap where three call sites in
        ``agent/__init__.py`` each manually rebuilt ExecutionStep with a
        different subset of fields, silently dropping any field added
        after the original call site was written.

        Args:
            data: Dict shaped like ``ExecutionStep.to_dict()`` output.
                Stray keys are ignored; missing keys use model defaults.

        Returns:
            A fully-populated ExecutionStep.
        """
        return cls(
            step_id=data["step_id"],
            step_number=data["step_number"],
            skill_id=data["skill_id"],
            intent=data.get("intent", ""),
            original_query_segment=data.get("original_query_segment", ""),
            input_query=data.get("input_query", ""),
            output_as=data.get("output_as", ""),
            status=data.get("status", StepStatus.PENDING),
            result_summary=data.get("result_summary"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            dependencies=data.get("dependencies", []),
            can_parallel=data.get("can_parallel", True),
            parallel_group=data.get("parallel_group"),
            is_verification_step=data.get("is_verification_step", False),
            verification_result=data.get("verification_result"),
            trust_level=data.get("trust_level", TrustLevel.TRUSTED),
            dynamic_status=data.get("dynamic_status"),
            loop_iteration=data.get("loop_iteration", 0),
            contestant_index=data.get("contestant_index"),
            step_type=data.get("step_type", "implementation"),
            estimated_risk=data.get("estimated_risk", "low"),
            estimated_file_count=data.get("estimated_file_count", 0),
            source_files=data.get("source_files", []),
            assigned_role=data.get("assigned_role"),
            agent_squad_id=data.get("agent_squad_id"),
            role_skills=data.get("role_skills", []),
            confidence=data.get("confidence", 0.0),
        )


class ExecutionPlan(BaseModel):
    """A multi-skill execution plan."""

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
    workflow_pattern: WorkflowPattern = Field(
        default=WorkflowPattern.SEQUENTIAL,
        description="Dynamic workflow pattern selected by ClassifierAgent",
    )
    # Phase 3 (v6.2.0): Dynamic execution metadata
    is_dynamic: bool = Field(
        default=False, description="Whether this plan uses dynamic execution (WorkflowEngine)"
    )
    dry_threshold: int = Field(
        default=2, description="Consecutive rounds with no change to declare dry (LOOP_UNTIL_DRY)"
    )
    max_reorchestration_rounds: int = Field(
        default=5, description="Maximum re-orchestration rounds before forced termination"
    )
    reorchestration_history: list[dict[str, Any]] = Field(
        default_factory=list, description="History of re-orchestration decisions"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="额外元数据，如 review_type、dimensions 等",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "original_query": self.original_query,
            "steps": [s.to_dict() for s in self.steps],
            "detected_intents": self.detected_intents,
            "reasoning": self.reasoning,
            "created_at": self.created_at,
            "status": self.status.value,
            "execution_mode": self.execution_mode.value,
            "workflow_pattern": self.workflow_pattern.value,
            "is_dynamic": self.is_dynamic,
            "dry_threshold": self.dry_threshold,
            "max_reorchestration_rounds": self.max_reorchestration_rounds,
            "reorchestration_history": self.reorchestration_history,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionPlan:
        """Reconstruct an ExecutionPlan from ``to_dict()`` output.

        Recursively rebuilds each ``ExecutionStep`` via its own
        ``from_dict``. Closes the v7.0.10 schema-drift gap where three
        call sites in ``agent/__init__.py`` each manually rebuilt the
        plan with a different subset of fields, silently dropping any
        field added after the original call site was written (e.g.
        ``parallel_group``, ``metadata``, ``step_type``).

        Args:
            data: Dict shaped like ``ExecutionPlan.to_dict()`` output.

        Returns:
            A fully-populated ExecutionPlan.
        """
        steps_data = data.get("steps", [])
        return cls(
            plan_id=data["plan_id"],
            original_query=data.get("original_query", ""),
            steps=[ExecutionStep.from_dict(s) for s in steps_data],
            detected_intents=data.get("detected_intents", []),
            reasoning=data.get("reasoning", ""),
            created_at=data.get("created_at", ""),
            status=data.get("status", PlanStatus.PENDING),
            execution_mode=data.get("execution_mode", ExecutionMode.SEQUENTIAL),
            workflow_pattern=data.get("workflow_pattern", WorkflowPattern.SEQUENTIAL),
            is_dynamic=data.get("is_dynamic", False),
            dry_threshold=data.get("dry_threshold", 2),
            max_reorchestration_rounds=data.get("max_reorchestration_rounds", 5),
            reorchestration_history=data.get("reorchestration_history", []),
            metadata=data.get("metadata", {}),
        )

    def get_parallel_groups(self) -> list[list[ExecutionStep]]:
        """Group steps into parallel batches based on dependencies.

        Uses a topological sort to find steps that can run concurrently.
        Steps with satisfied dependencies and ``can_parallel=True`` are
        batched together. Non-parallel steps form singleton groups.

        Returns:
            List of step groups; each group can execute in parallel.
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
            "workflow_pattern": self.workflow_pattern.value,
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


class ClassifierResult(BaseModel):
    """Result from ClassifierAgent — dynamic workflow pattern selection.

    Attributes:
        pattern: Selected workflow pattern (sequential/parallel/fan_out/adversarial/prompt_chain)
        confidence: Confidence score for the pattern selection (0.0-1.0)
        reasoning: Human-readable explanation of why this pattern was chosen
        task_type: Primary task type detected (analysis, review, debug, etc.)
        complexity: Complexity level (simple, medium, complex)
        complexity_level: Execution complexity tier determining routing strategy:
            - simple: single skill suffices
            - composite: orchestration of multiple skills
            - multi_agent: generate Claude Code Prompt Chain (3+ skill domains)
    """

    model_config = {"arbitrary_types_allowed": True}

    pattern: WorkflowPattern = Field(
        default=WorkflowPattern.SEQUENTIAL,
        description="Selected workflow pattern",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Pattern selection confidence",
    )
    reasoning: str = Field(
        default="",
        description="Why this pattern was selected",
    )
    task_type: str = Field(
        default="",
        description="Primary task type (analysis, review, debug, etc.)",
    )
    complexity: str = Field(
        default="simple",
        description="Task complexity: simple, medium, complex",
    )
    complexity_level: str = Field(
        default="simple",
        description="Execution complexity tier: simple, composite, multi_agent",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra classification metadata (e.g. review dimensions, hints)",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "task_type": self.task_type,
            "complexity": self.complexity,
            "complexity_level": self.complexity_level,
            "metadata": self.metadata,
        }


class IntentAnalysis(BaseModel):
    """Semantic output from SemanticIntentAnalyzer.

    Describes the deep structure of a user request: complexity tier,
    semantic facets, whether a multi-agent squad is needed, recommended
    roles, collaboration protocol, per-agent skill bindings, handoff
    points, and the analyzer's confidence.
    """

    model_config = {"arbitrary_types_allowed": True}

    complexity: Literal["trivial", "simple", "composite", "multi_agent"] = Field(
        default="simple",
        description="Complexity tier: trivial/simple/composite/multi_agent",
    )
    facets: list[str] = Field(
        default_factory=list,
        description="Semantic facets of the request, e.g. ['architecture', 'security']",
    )
    squad_needed: bool = Field(
        default=False,
        description="Whether 2+ distinct professional facets require a squad",
    )
    suggested_roles: list[str] = Field(
        default_factory=list,
        description="Recommended agent roles: architect, implementer, reviewer, ...",
    )
    collaboration_protocol: str = Field(
        default="sequential",
        description="Collaboration protocol: sequential/parallel/debate/red_team/review_gate",
    )
    per_agent_skills: dict[str, list[str]] = Field(
        default_factory=dict,
        description="role -> list of recommended skill IDs",
    )
    handoff_points: list[int] = Field(
        default_factory=list,
        description="Step indices where upstream output must be handed off",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Analyzer confidence",
    )
    reasoning: str = Field(
        default="",
        description="Human-readable reasoning for the analysis",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "complexity": self.complexity,
            "facets": self.facets,
            "squad_needed": self.squad_needed,
            "suggested_roles": self.suggested_roles,
            "collaboration_protocol": self.collaboration_protocol,
            "per_agent_skills": self.per_agent_skills,
            "handoff_points": self.handoff_points,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


class OrchestrationMode(StrEnum):
    """Mode of orchestration result."""

    SINGLE = "single"
    ORCHESTRATED = "orchestrated"
    FALLBACK = "fallback"


class OrchestrationResult(BaseModel):
    """Result of orchestration — either single skill or multi-step plan."""

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
        """Extract a single-skill RoutingResult from this orchestration result."""
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


class AgentRole(BaseModel):
    """Definition of an agent role within a squad.

    A role captures a professional responsibility (e.g. architect) and the
    skills that role may, must, or must not use.
    """

    model_config = {"arbitrary_types_allowed": True}

    role_id: str = Field(..., min_length=1, description="Role identifier")
    name: str = Field(..., min_length=1, description="Human-readable role name")
    description: str = Field(default="", description="Role responsibilities")
    required_skills: list[str] = Field(
        default_factory=list,
        description="Skill IDs this role must have access to",
    )
    excluded_skills: list[str] = Field(
        default_factory=list,
        description="Skill IDs this role must not use",
    )
    system_prompt_template: str = Field(
        default="",
        description="Key or path to the system prompt template for this role",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "description": self.description,
            "required_skills": self.required_skills,
            "excluded_skills": self.excluded_skills,
            "system_prompt_template": self.system_prompt_template,
        }


class SquadStep(BaseModel):
    """A single step executed by a role inside an agent squad."""

    model_config = {"arbitrary_types_allowed": True}

    step_id: str = Field(..., min_length=1, description="Step identifier")
    role_id: str = Field(..., min_length=1, description="Role that executes this step")
    agent_platform: str = Field(
        default="claude-code",
        description="Target agent platform: claude-code, opencode, kimi-cli, ...",
    )
    skill_ids: list[str] = Field(
        default_factory=list,
        description="Skills available to this step",
    )
    input_from: list[str] = Field(
        default_factory=list,
        description="Upstream step IDs that feed into this step",
    )
    output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Expected structured output schema",
    )
    trust_level: TrustLevel = Field(
        default=TrustLevel.NORMAL,
        description="Runtime trust level for this step",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "role_id": self.role_id,
            "agent_platform": self.agent_platform,
            "skill_ids": self.skill_ids,
            "input_from": self.input_from,
            "output_schema": self.output_schema,
            "trust_level": self.trust_level.value,
        }


class AgentSquad(BaseModel):
    """A team of agent roles collaborating on a single user request."""

    model_config = {"arbitrary_types_allowed": True}

    squad_id: str = Field(..., min_length=1, description="Squad identifier")
    roles: list[AgentRole] = Field(default_factory=list, description="Roles in the squad")
    steps: list[SquadStep] = Field(default_factory=list, description="Squad execution steps")
    collaboration_protocol: str = Field(
        default="sequential",
        description="Collaboration protocol: sequential/parallel/debate/red_team/review_gate",
    )
    lead_role: str = Field(
        default="",
        description="Role ID that leads and finalizes outputs",
    )
    max_rounds: int = Field(
        default=3,
        ge=1,
        description="Maximum rounds for debate/review protocols",
    )
    execution_order: list[str] = Field(
        default_factory=list,
        description="Ordered step IDs defining execution sequence",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "squad_id": self.squad_id,
            "roles": [r.to_dict() for r in self.roles],
            "steps": [s.to_dict() for s in self.steps],
            "collaboration_protocol": self.collaboration_protocol,
            "lead_role": self.lead_role,
            "max_rounds": self.max_rounds,
            "execution_order": self.execution_order,
        }


class AgentSkillBinding(BaseModel):
    """Binding between an agent role/platform and its allowed skills."""

    model_config = {"arbitrary_types_allowed": True}

    role_id: str = Field(..., min_length=1, description="Role identifier")
    agent_platform: str = Field(
        default="claude-code",
        description="Agent platform for this binding",
    )
    skill_allowlist: list[str] = Field(
        default_factory=list,
        description="Skills this role/platform may use",
    )
    skill_denylist: list[str] = Field(
        default_factory=list,
        description="Skills this role/platform must not use",
    )
    required_skills: list[str] = Field(
        default_factory=list,
        description="Skills that must be present in the allowlist",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "role_id": self.role_id,
            "agent_platform": self.agent_platform,
            "skill_allowlist": self.skill_allowlist,
            "skill_denylist": self.skill_denylist,
            "required_skills": self.required_skills,
        }


class SkillRegistry(BaseModel):
    """Registry of all available skills.

    .. note::
        ``SkillDefinition`` (deprecated since v5.5.0) was removed in v7.1.0.
        Skills are now typed as ``vibesop.spec.SkillSpec`` — the canonical
        SKILL.md spec model. See ADR-004.
    """

    skills: dict[str, SkillSpec] = Field(
        default_factory=dict,
        description="Available skills keyed by id",
    )
    version: str = Field(default="1.0.0", description="Registry version")


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables."""

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
    """执行清单中单个步骤的完整信息。"""

    step_number: int
    skill_id: str
    skill_name: str = ""
    skill_path: str = ""
    skill_content: str = ""
    input_context: str = ""
    output_slot: str = ""
    completion_marker: str = ""
    instruction: str = ""
    intent: str = ""
    input_query: str = ""
    dependencies: list[str] = field(default_factory=list)

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
            "intent": self.intent,
            "input_query": self.input_query,
            "dependencies": self.dependencies,
        }

    @staticmethod
    def completion_marker_for(step_number: int) -> str:
        """Build the standardized completion marker for a step."""
        return f"[StepCompleted:{step_number}]"


@dataclass
class ExecutionManifest:
    """完整的编排执行清单。"""

    plan_id: str
    original_query: str = ""
    strategy: str = "sequential"
    steps: list[StepManifest] = field(default_factory=list)
    context_file: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

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
            "metadata": self.metadata,
        }

    def to_markdown(self) -> str:
        """Render the manifest as a markdown execution sequence file."""
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
