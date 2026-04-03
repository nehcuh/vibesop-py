"""Workflow execution modules for VibeSOP.

This package provides capabilities for executing complex
multi-step workflows with dependencies and error handling,
as well as A/B testing and experiment management.
"""

from vibesop.workflow.cascade import (
    CascadeExecutor,
    WorkflowStep,
    WorkflowConfig,
    StepResult,
    StepStatus,
    ExecutionStrategy,
)
from vibesop.workflow.experiment import (
    ExperimentManager,
    Experiment,
    Variant,
    ExperimentStatus,
    VariantStatus,
)
from vibesop.workflow.instinct import (
    InstinctManager,
    Decision,
    DecisionContext,
    Pattern,
    ActionType,
    ConfidenceLevel,
)
from vibesop.workflow.models import (
    StageStatus,
    PipelineStage,
    WorkflowResult,
    WorkflowExecutionContext,
    RetryPolicy,
    RecoveryStrategy,
    WorkflowDefinition,
)
from vibesop.workflow.pipeline import WorkflowPipeline
from vibesop.workflow.manager import WorkflowManager
from vibesop.workflow.state import WorkflowStateManager, WorkflowState
from vibesop.workflow.exceptions import WorkflowError, StageError

__all__ = [
    # Legacy cascade system
    "CascadeExecutor",
    "WorkflowStep",
    "WorkflowConfig",
    "StepResult",
    "StepStatus",
    "ExecutionStrategy",
    # Experiment system
    "ExperimentManager",
    "Experiment",
    "Variant",
    "ExperimentStatus",
    "VariantStatus",
    # Instinct system
    "InstinctManager",
    "Decision",
    "DecisionContext",
    "Pattern",
    "ActionType",
    "ConfidenceLevel",
    # New v2.0 workflow system
    "StageStatus",
    "PipelineStage",
    "WorkflowResult",
    "WorkflowExecutionContext",
    "RetryPolicy",
    "RecoveryStrategy",
    "WorkflowDefinition",
    "WorkflowPipeline",
    "WorkflowManager",
    "WorkflowStateManager",
    "WorkflowState",
    "WorkflowError",
    "StageError",
]
