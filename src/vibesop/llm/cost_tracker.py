"""Backward-compatible re-export — cost tracker moved to core/routing/.

.. deprecated:: Use ``vibesop.core.routing.cost_tracker`` instead.
"""

from vibesop.core.routing.cost_tracker import (  # noqa: F401
    TriageCallRecord,
    TriageCostTracker,
)
