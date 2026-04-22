"""Orchestration module for multi-skill task decomposition and execution planning.

Provides:
- MultiIntentDetector: heuristic + LLM-based multi-intent detection
- TaskDecomposer: LLM-based query decomposition into sub-tasks
- PlanBuilder: converts sub-tasks to ExecutionPlan with skill routing
- PlanTracker: persists and retrieves plan state
"""

from __future__ import annotations

from vibesop.core.orchestration.multi_intent_detector import MultiIntentDetector
from vibesop.core.orchestration.plan_builder import PlanBuilder
from vibesop.core.orchestration.plan_tracker import PlanTracker
from vibesop.core.orchestration.task_decomposer import SubTask, TaskDecomposer

__all__ = [
    "MultiIntentDetector",
    "PlanBuilder",
    "PlanTracker",
    "SubTask",
    "TaskDecomposer",
]
