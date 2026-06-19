"""VibeSOP Loop System — autonomous scheduled task execution.

Architecture (Phase 1 target):
    LoopStore (JSON persistence)
        ↕
    LoopExecutor → AgentRuntime.handle_query()
        ↕
    CronDaemon (time-based polling dispatcher)

Design decisions (from Phase 0 diagnostic, 2026-06-19):
    - Time-based loop (cron-like), distinct from the semantic LOOP_UNTIL_DRY
      pattern already implemented in WorkflowEngine.
    - Scheduling layer lives outside WorkflowEngine to avoid coupling
      time-based triggers with re-orchestration semantics.
    - Uses its own data models (LoopSpec, LoopState), not ExecutionPlan.
    - AgentRuntime.handle_query() already supports headless execution ✅.

This package is built up incrementally across Phase 1 sub-phases. Phase 1-1
exports only ``models``; later sub-phases add store / scheduler / executor.
"""

from vibesop.core.loop.executor import execute_loop_tick
from vibesop.core.loop.models import (
    LoopRunRecord,
    LoopSpec,
    LoopState,
    LoopStatus,
    LoopTrigger,
)
from vibesop.core.loop.scheduler import CronDaemon, CronExpr

__all__ = [
    "LoopSpec",
    "LoopState",
    "LoopRunRecord",
    "LoopStatus",
    "LoopTrigger",
    "CronExpr",
    "CronDaemon",
    "execute_loop_tick",
]
