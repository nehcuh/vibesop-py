"""Routing module for VibeSOP.

Implements unified skill routing system.

    >>> from vibesop.core.routing import UnifiedRouter
    >>> router = UnifiedRouter()
    >>> result = router.route("your query")
"""

import warnings

from vibesop.core.config import ConfigManager
from vibesop.core.config.manager import RoutingConfig
from vibesop.core.routing.cache import CacheManager, CacheStats
from vibesop.core.routing.conflict import (
    ConflictResolver,
    ConflictResolution,
    ConfidenceGapStrategy,
    ExplicitOverrideStrategy,
    FallbackStrategy,
    NamespacePriorityStrategy,
    RecencyStrategy,
    ResolutionStrategy,
)
from vibesop.core.routing.unified import (
    RoutingLayer,
    RoutingResult,
    SkillRoute,
    UnifiedRouter,
)

__all__ = [
    "CacheManager",
    "CacheStats",
    "ConfigManager",
    "ConflictResolver",
    "ConflictResolution",
    "ConfidenceGapStrategy",
    "ExplicitOverrideStrategy",
    "FallbackStrategy",
    "NamespacePriorityStrategy",
    "RecencyStrategy",
    "ResolutionStrategy",
    "RoutingConfig",
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
    "UnifiedRouter",
]

_DEPRECATED_CLASSES = {
    "SkillRouter": "UnifiedRouter",
    "FuzzyMatcher": "KeywordMatcher (from vibesop.core.matching)",
    "SemanticMatcher": "TFIDFMatcher (from vibesop.core.matching)",
}

_DEPRECATED_WARNED = set()


def __getattr__(name: str):
    if name in _DEPRECATED_CLASSES and name not in _DEPRECATED_WARNED:
        replacement = _DEPRECATED_CLASSES[name]
        warnings.warn(
            f"{name} is deprecated and will be removed in v4.0.0. Use {replacement} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        _DEPRECATED_WARNED.add(name)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
