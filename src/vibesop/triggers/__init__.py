"""VibeSOP-Py Intelligent Keyword Trigger System.

⚠️ **DEPRECATED** - This module is deprecated as of v3.0.0.

The functionality in this module has been consolidated into the new
unified matching system:

    >>> from vibesop.core.matching import KeywordMatcher
    >>> from vibesop.core.routing import UnifiedRouter

    # Use UnifiedRouter for all routing operations
    >>> router = UnifiedRouter()
    >>> result = router.route("扫描安全漏洞")

Migration guide:
    - KeywordDetector → KeywordMatcher (vibesop.core.matching)
    - DEFAULT_PATTERNS → Built-in skill discovery
    - SkillActivator → UnifiedRouter.route()

This module will be removed in v4.0.0.
"""

import warnings

warnings.warn(
    "The 'vibesop.triggers' module is deprecated as of v3.0.0 "
    "and will be removed in v4.0.0. "
    "Use 'vibesop.core.matching' and 'vibesop.core.routing' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from vibesop.triggers.models import (
    TriggerPattern,
    PatternMatch,
    PatternCategory,
)
from vibesop.triggers.detector import KeywordDetector
from vibesop.triggers.patterns import DEFAULT_PATTERNS
from vibesop.triggers.activator import SkillActivator, auto_activate

__all__ = [
    "TriggerPattern",
    "PatternMatch",
    "PatternCategory",
    "KeywordDetector",
    "DEFAULT_PATTERNS",
    "SkillActivator",
    "auto_activate",
]

# Version info
__version__ = "2.0.0"  # Last version before deprecation
