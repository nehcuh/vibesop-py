"""VibeSOP - Modern Python Edition.

A battle-tested, multi-platform workflow SOP for AI-assisted development.

This project is a complete rewrite of the Ruby version, leveraging:
- Python 3.12+ type system
- Pydantic v2 for runtime validation
- Modern async/await patterns
- Type-safe LLM clients
"""

from vibesop._version import __version__

__author__ = "nehcuh"
__license__ = "MIT"

# Core public API
from vibesop.core.models import (
    RoutingLayer,
    RoutingRequest,
    RoutingResult,
    SkillRegistry,
    SkillRoute,
)

__all__ = [
    "RoutingLayer",
    "RoutingRequest",
    "RoutingResult",
    "SkillRegistry",
    "SkillRoute",
    "__version__",
]
