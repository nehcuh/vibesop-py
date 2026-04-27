"""Router execution mixin - fallback result building.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

import logging
from typing import Any

from vibesop.core.models import (
    LayerDetail,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)

logger = logging.getLogger(__name__)


class RouterExecutionMixin:
    """Mixin providing fallback result building methods.

    Intended for use with UnifiedRouter. Expects the host class to provide
    the layer try-methods and related attributes via ``self``.
    """

    def _build_fallback_result(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        routing_path: list[RoutingLayer],
        layer_details: list[LayerDetail],
        duration_ms: float,
    ) -> RoutingResult:
        """Build a fallback result when no skill matches.

        Returns a FALLBACK_LLM route with nearest candidates as alternatives.
        """
        # Find nearest candidates (even if below threshold) for suggestions
        nearest: list[SkillRoute] = []
        try:
            from vibesop.core.routing import _pipeline
            nearest_primary, nearest_alts, _ = _pipeline.run_matcher_pipeline(
                self, query, candidates, None, collect_rejected=False
            )
            if nearest_primary:
                nearest = [nearest_primary, *nearest_alts]
        except (RuntimeError, ValueError):
            logger.debug("Failed to get nearest candidates for fallback")

        fallback_layer_detail = LayerDetail(
            layer=RoutingLayer.FALLBACK_LLM,
            matched=True,
            reason="No confident skill match; falling back to raw LLM",
        )

        return RoutingResult(
            primary=SkillRoute(
                skill_id="fallback-llm",
                confidence=1.0,
                layer=RoutingLayer.FALLBACK_LLM,
                source="builtin",
                metadata={
                    "reason": "No skill matched query",
                    "fallback_mode": self._config.fallback_mode,
                    "candidate_count": len(candidates),
                },
            ),
            alternatives=nearest,
            routing_path=[*routing_path, RoutingLayer.FALLBACK_LLM],
            layer_details=[*layer_details, fallback_layer_detail],
            query=query,
            duration_ms=duration_ms,
        )
