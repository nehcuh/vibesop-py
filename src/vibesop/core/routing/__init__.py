"""Routing module for VibeSOP.

Implements unified skill routing system.

    >>> from vibesop.core.routing import UnifiedRouter
    >>> router = UnifiedRouter()
    >>> result = router.route("your query")

WARNING: This module exports from `unified.py`, while `unified.py` imports
`_layers` and `_pipeline` from `vibesop.core.routing`. Avoid adding imports
from `vibesop.core.routing` at the top of `_layers.py` or `_pipeline.py`
to prevent circular import cycles.
"""

from vibesop.core.config import ConfigManager
from vibesop.core.config.manager import RoutingConfig
from vibesop.core.routing.cache import CacheManager, CacheStats
from vibesop.core.routing.conflict import (
    ConfidenceGapStrategy,
    ConflictResolution,
    ConflictResolver,
    ExplicitOverrideStrategy,
    FallbackStrategy,
    NamespacePriorityStrategy,
    RecencyStrategy,
    ResolutionStrategy,
)
from vibesop.core.routing.layers import IRouteLayer, LayerResult
from vibesop.core.routing.unified import (
    RoutingLayer,
    RoutingResult,
    SkillRoute,
    UnifiedRouter,
)

__all__ = [
    "CacheManager",
    "CacheStats",
    "ConfidenceGapStrategy",
    "ConfigManager",
    "ConflictResolution",
    "ConflictResolver",
    "ExplicitOverrideStrategy",
    "FallbackStrategy",
    "IRouteLayer",
    "LayerResult",
    "NamespacePriorityStrategy",
    "RecencyStrategy",
    "ResolutionStrategy",
    "RoutingConfig",
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
    "UnifiedRouter",
]
