"""VibeSOP - Modern Python Edition.

A battle-tested, multi-platform workflow SOP for AI-assisted development.

This project is a complete rewrite of the Ruby version, leveraging:
- Python 3.12+ type system
- Pydantic v2 for runtime validation
- Modern async/await patterns
- Type-safe LLM clients
"""

import os
import sys


def _setup_windows_console() -> None:
    """Configure Windows console for UTF-8 output before Rich creates any Console."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    if not os.environ.get("PYTHONIOENCODING"):
        os.environ["PYTHONIOENCODING"] = "utf-8"
    # Reconfigure already-open stdout/stderr to use the new UTF-8 code page
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


_setup_windows_console()

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
