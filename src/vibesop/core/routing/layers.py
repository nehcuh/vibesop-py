"""Routing layer protocol and result types.

Each routing layer implements the IRouteLayer protocol and returns a LayerResult.
The UnifiedRouter executes layers in priority order and returns the first successful match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from vibesop.core.models import RoutingLayer, SkillRoute

if TYPE_CHECKING:
    from vibesop.core.matching import RoutingContext


@dataclass
class LayerResult:
    """Result from a single routing layer attempt.

    Attributes:
        match: The matched skill route, or None if this layer didn't match
        alternatives: Alternative matches found by this layer
        layer: Which layer produced this result
        should_stop: Whether to stop trying further layers
        reason: Human-readable explanation of this layer's decision
        diagnostics: Layer-specific diagnostic data
    """

    match: SkillRoute | None = None
    alternatives: list[SkillRoute] = field(default_factory=list)
    layer: RoutingLayer = RoutingLayer.NO_MATCH
    should_stop: bool = True
    matched: bool = False
    reason: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


class IRouteLayer(Protocol):
    """Protocol for a single routing layer.

    Each layer is responsible for one matching strategy.
    Returns a LayerResult indicating whether it matched.
    """

    @property
    def layer(self) -> RoutingLayer:
        """Which routing layer this implements."""
        ...

    def try_route(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
    ) -> LayerResult | None:
        """Attempt to route the query.

        Args:
            query: User's natural language query
            candidates: Available skill candidates
            context: Additional routing context

        Returns:
            LayerResult if this layer matched, None to defer to next layer
        """
        ...
