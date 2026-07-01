"""Routing layer result types.

Defines ``LayerResult``, the result type returned by routing layer functions in
``_layers.py``. The UnifiedRouter evaluates layers via a 4-stage branched cascade
(see ``unified.py::_try_layers``), not a strict priority-ordered first-match loop.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from vibesop.core.models import RoutingLayer, SkillRoute


class LayerResult(BaseModel):
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
    alternatives: list[SkillRoute] = Field(default_factory=list)
    layer: RoutingLayer = RoutingLayer.NO_MATCH
    should_stop: bool = True
    matched: bool = False
    reason: str = ""
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=False)
