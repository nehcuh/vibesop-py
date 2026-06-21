"""Orchestration module for multi-skill task decomposition and execution planning.

Provides:
- MultiIntentDetector: heuristic + LLM-based multi-intent detection
- TaskDecomposer: LLM-based query decomposition into sub-tasks
- PlanBuilder: converts sub-tasks to ExecutionPlan with skill routing
- PlanTracker: persists and retrieves plan state
- ParallelScheduler: executes plans with parallel step support
- OrchestrationCallbacks: streaming progress callbacks
- generate_execution_summary: human-readable plan summary
- ClassifierAgent: dynamic workflow pattern selection (v6.0.0)
- VerifierAgent: independent verification for adversarial workflow (v6.1.0)
- VerificationLoop: retry logic for NEEDS_REVISION status (v6.1.0)
- WorkflowEngine: dynamic execution for loop-until-dry and tournament (v6.2.0)
- Reorchestrator: post-step analysis for runtime re-evaluation (v6.2.0)
- TournamentRunner: multi-contestant comparison with judge (v6.2.0)
"""

from __future__ import annotations

from vibesop.core.orchestration.callbacks import (
    ErrorPolicy,
    NoOpCallbacks,
    OrchestrationCallbacks,
    OrchestrationPhase,
    PhaseInfo,
    StepResult,
)
from vibesop.core.orchestration.classifier import ClassifierAgent
from vibesop.core.orchestration.multi_intent_detector import MultiIntentDetector
from vibesop.core.orchestration.parallel_scheduler import (
    ParallelScheduler,
    execute_plan_sync,
)
from vibesop.core.orchestration.plan_builder import PlanBuilder
from vibesop.core.orchestration.plan_tracker import PlanTracker
from vibesop.core.orchestration.reorchestrator import ReorchestrationAnalysis, Reorchestrator
from vibesop.core.orchestration.summary import generate_execution_summary
from vibesop.core.orchestration.task_decomposer import SubTask, TaskDecomposer
from vibesop.core.orchestration.tournament import (
    ComparisonResult,
    TournamentConfig,
    TournamentResult,
    TournamentRunner,
)
from vibesop.core.orchestration.verification_loop import (
    VerificationLoop,
    VerificationLoopAction,
    VerificationLoopConfig,
    VerificationLoopState,
    execute_plan_with_verification,
)
from vibesop.core.orchestration.verifier import (
    VerificationIssue,
    VerificationResult,
    VerificationStatus,
    VerificationStrictness,
    VerifierAgent,
    verify_step_with_retry,
)
from vibesop.core.orchestration.workflow_engine import (
    DynamicExecutionResult,
    WorkflowEngine,
    WorkflowEngineConfig,
)

__all__ = [
    "ClassifierAgent",
    "ComparisonResult",
    "DynamicExecutionResult",
    "ErrorPolicy",
    "MultiIntentDetector",
    "NoOpCallbacks",
    "OrchestrationCallbacks",
    "OrchestrationPhase",
    "ParallelScheduler",
    "PhaseInfo",
    "PlanBuilder",
    "PlanTracker",
    "ReorchestrationAnalysis",
    "Reorchestrator",
    "StepResult",
    "SubTask",
    "TaskDecomposer",
    "TournamentConfig",
    "TournamentResult",
    "TournamentRunner",
    "VerificationIssue",
    "VerificationLoop",
    "VerificationLoopAction",
    "VerificationLoopConfig",
    "VerificationLoopState",
    "VerificationResult",
    "VerificationStatus",
    "VerificationStrictness",
    "VerifierAgent",
    "WorkflowEngine",
    "WorkflowEngineConfig",
    "execute_plan_sync",
    "execute_plan_with_verification",
    "generate_execution_summary",
    "verify_step_with_retry",
]
