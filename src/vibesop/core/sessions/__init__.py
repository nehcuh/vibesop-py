"""Session management for intelligent re-routing.

This module provides conversation context tracking and intelligent
re-routing suggestions for AI agents across multiple platforms.

Platforms supported:
- Claude Code (via hooks)
- OpenCode (via CLI commands)
- Generic/Any platform (via CLI commands)

Usage:
    >>> from vibesop.core.sessions import get_tracker
    >>>
    >>> # Auto-detect platform
    >>> tracker = get_tracker()
    >>>
    >>> # Or specify platform
    >>> tracker = get_tracker(platform="claude-code")
    >>>
    >>> # Record tool usage
    >>> tracker.record_tool_use("read", skill="systematic-debugging")
    >>>
    >>> # Check for re-routing
    >>> suggestion = tracker.check_reroute("design new architecture")
    >>> if suggestion.should_reroute:
    ...     print(f"Consider switching to: {suggestion.recommended_skill}")
"""

from vibesop.core.sessions.context import (
    ContextChange,
    RoutingSuggestion,
    SessionContext,
    ToolUseEvent,
)
from vibesop.core.sessions.tracker import (
    GenericSessionTracker,
    HookBasedSessionTracker,
    SessionTracker,
    _detect_platform,
    get_tracker,
)

__all__ = [
    # Core types
    "ContextChange",
    "RoutingSuggestion",
    "SessionContext",
    "ToolUseEvent",
    # Platform abstraction
    "SessionTracker",
    "GenericSessionTracker",
    "HookBasedSessionTracker",
    "get_tracker",
    "_detect_platform",
]
