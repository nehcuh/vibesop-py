"""Pipeline execution functions for UnifiedRouter.

Thin wrappers around MatcherPipeline for backward compatibility.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from vibesop.core.models import LayerDetail, RejectedCandidate, RoutingLayer

logger = logging.getLogger(__name__)


def run_matcher_pipeline(
    router: Any,
    query: str,
    candidates: list[dict[str, Any]],
    context: Any | None,
    collect_rejected: bool = False,
) -> tuple[Any | None, list[Any], LayerDetail]:
    """Run the matcher pipeline and return (primary, alternatives, layer_detail).

    Returns None primary if no confident match found.
    """
    matcher_start = time.perf_counter()
    result = router._matcher_pipeline.try_matcher_pipeline(
        query, candidates, context, collect_rejected=collect_rejected
    )
    duration_ms = (time.perf_counter() - matcher_start) * 1000

    if result is None:
        return (
            None,
            [],
            LayerDetail(
                layer=RoutingLayer.LEVENSHTEIN,
                matched=False,
                reason="No matcher produced a confident match",
                duration_ms=duration_ms,
            ),
        )

    rejected = [
        RejectedCandidate(**rc)
        for rc in result.diagnostics.get("rejected_candidates", [])
    ]
    layer_detail = LayerDetail(
        layer=result.layer,
        matched=True,
        reason=f"Matcher selected '{result.match.skill_id}' (confidence: {result.match.confidence:.0%})",
        duration_ms=duration_ms,
        rejected_candidates=rejected,
        diagnostics={"rejected_candidates": result.diagnostics.get("rejected_candidates", [])} if rejected else {},
    )

    return result.match, result.alternatives, layer_detail


def apply_optimizations(
    router: Any,
    matches: list[Any],
    query: str,
    context: Any | None = None,
) -> tuple[Any, list[Any]]:
    """Apply optimizations to matches. Thin wrapper around OptimizationService."""
    return router._optimization_service.apply_optimizations(matches, query, context)
