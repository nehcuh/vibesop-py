"""Cost tracking for AI Triage (Layer 0) LLM calls.

Records token usage and estimated cost per call to a JSONL log.
Supports budget enforcement and monthly aggregation.

Moved to vibesop.core.routing.cost_tracker — this module re-exports for backward compatibility.
"""

from vibesop.core.routing.cost_tracker import (  # noqa: F401
    TriageCallRecord,
    TriageCostTracker,
    _estimate_cost,
)
