"""Orchestration module for multi-skill task decomposition and execution planning.

Provides:
- MultiIntentDetector: heuristic + LLM-based multi-intent detection
- TaskDecomposer: LLM-based query decomposition into sub-tasks
- PlanBuilder: converts sub-tasks to ExecutionPlan with skill routing
- PlanTracker: persists and retrieves plan state
- ParallelScheduler: executes plans with parallel step support
"""

from __future__ import annotations

from vibesop.core.orchestration.multi_intent_detector import MultiIntentDetector
from vibesop.core.orchestration.parallel_scheduler import (
    ParallelScheduler,
    execute_plan_sync,
)
from vibesop.core.orchestration.plan_builder import PlanBuilder
from vibesop.core.orchestration.plan_tracker import PlanTracker
from vibesop.core.orchestration.task_decomposer import SubTask, TaskDecomposer

__all__ = [
    "MultiIntentDetector",
    "ParallelScheduler",
    "PlanBuilder",
    "PlanTracker",
    "SubTask",
    "TaskDecomposer",
    "execute_plan_sync",
]
