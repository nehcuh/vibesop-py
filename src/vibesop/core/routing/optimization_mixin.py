"""Router optimization mixin.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibesop.core.matching import RoutingContext


class RouterOptimizationMixin:
    """Mixin providing optimization delegation methods.

    Intended for use with UnifiedRouter. Expects the following attributes
    on the host class:
        - _matcher_pipeline: MatcherPipeline
        - _optimization_service: OptimizationService
    """

    def _apply_prefilter(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._matcher_pipeline.apply_prefilter(query, candidates)  # type: ignore[attr-defined]

    def _apply_optimizations(self, matches: Any, query: str, context: RoutingContext | None = None) -> Any:
        return self._optimization_service.apply_optimizations(matches, query, context)  # type: ignore[attr-defined]

    def _resolve_conflicts(self, matches: Any, query: str) -> Any:
        return self._optimization_service.resolve_conflicts(matches, query)  # type: ignore[attr-defined]

    def _apply_instinct_boost(self, matches: Any, query: str, context: RoutingContext | None) -> Any:
        return self._optimization_service.apply_instinct_boost(matches, query, context)  # type: ignore[attr-defined]

    def _ensure_cluster_index(self, candidates: list[dict[str, Any]]) -> None:
        self._optimization_service.ensure_cluster_index(candidates)  # type: ignore[attr-defined]
