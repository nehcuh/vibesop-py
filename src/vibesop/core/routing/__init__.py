"""Routing module for VibeSOP.

Implements unified skill routing system.

**NEW (v3.0)**: Use UnifiedRouter for all routing operations.
    >>> from vibesop.core.routing import UnifiedRouter
    >>> router = UnifiedRouter()
    >>> result = router.route("your query")

**DEPRECATED (v2.x)**: SkillRouter, FuzzyMatcher, SemanticMatcher
    These will be removed in v4.0.0. Migrate to UnifiedRouter.
"""

import warnings

# New unified router (v3.0)
from vibesop.core.config.manager import RoutingConfig
from vibesop.core.routing.unified import (
    RoutingLayer,
    RoutingResult,
    SkillRoute,
    UnifiedRouter,
)

# Legacy components (deprecated)
from vibesop.core.config_module import ConfigLoader
from vibesop.core.routing.cache import CacheManager, CacheStats
from vibesop.core.routing.engine import SkillRouter
from vibesop.core.routing.fuzzy import FuzzyMatcher
from vibesop.core.routing.semantic import SemanticMatcher

__all__ = [
    # New (v3.0)
    "UnifiedRouter",
    "RoutingConfig",
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
    # Legacy (deprecated)
    "CacheManager",
    "CacheStats",
    "ConfigLoader",
    "FuzzyMatcher",
    "SemanticMatcher",
    "SkillRouter",
]

# Issue deprecation warnings when legacy classes are used
_LEGACY_CLASSES = {
    "SkillRouter": "UnifiedRouter",
    "FuzzyMatcher": "KeywordMatcher (from vibesop.core.matching)",
    "SemanticMatcher": "TFIDFMatcher (from vibesop.core.matching)",
}

_LEGACY_WARNED = set()


def __getattr__(name: str):
    """Issue deprecation warnings for legacy components."""
    if name in _LEGACY_CLASSES and name not in _LEGACY_WARNED:
        replacement = _LEGACY_CLASSES[name]
        warnings.warn(
            f"{name} is deprecated and will be removed in v4.0.0. "
            f"Use {replacement} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        _LEGACY_WARNED.add(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
