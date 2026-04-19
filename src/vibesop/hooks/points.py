"""Hook point definitions for VibeSOP.

This module defines the standard hook points in the AI assistant
workflow where custom code can be executed.
"""

from enum import Enum
from typing import Any


class HookPoint(Enum):
    """Standard hook points in the AI assistant workflow.

    Hooks allow execution of custom code at specific points
    during a session, enabling features like:
    - Memory flushing
    - Telemetry
    - Custom notifications
    - Session logging

    Attributes:
        PRE_SESSION_END: Execute before session ends
        PRE_TOOL_USE: Execute before using a tool
        POST_SESSION_START: Execute after session starts
    """

    PRE_SESSION_END = "pre-session-end"
    PRE_TOOL_USE = "pre-tool-use"
    POST_SESSION_START = "post-session-start"

    @classmethod
    def get_all(cls) -> list["HookPoint"]:
        """Get all defined hook points.

        Returns:
            List of all HookPoint values
        """
        return list(cls)

    @classmethod
    def get_description(cls, point: "HookPoint") -> str:
        """Get human-readable description for a hook point.

        Args:
            point: HookPoint to describe

        Returns:
            Description string
        """
        descriptions = {
            cls.PRE_SESSION_END: "Execute before AI session ends",
            cls.PRE_TOOL_USE: "Execute before a tool is used",
            cls.POST_SESSION_START: "Execute after AI session starts",
        }
        return descriptions.get(point, "Unknown hook point")

    @classmethod
    def is_standard(cls, point: "HookPoint") -> bool:
        """Check if a hook point is standard (built-in).

        Args:
            point: HookPoint to check

        Returns:
            True if standard, False if custom
        """
        return point in list(cls)


# Hook definitions by platform
HOOK_DEFINITIONS: dict[str, dict[str, dict[str, Any]]] = {
    "claude-code": {
        "pre-session-end": {
            "file": "hooks/pre-session-end.sh",
            "executable": True,
            "description": "Flush memory before session ends",
        },
        "pre-tool-use": {
            "file": "hooks/pre-tool-use.sh",
            "executable": True,
            "description": "Log tool usage before execution",
        },
        "post-session-start": {
            "file": "hooks/post-session-start.sh",
            "executable": True,
            "description": "Initialize session logging",
        },
    },
    "kimi-cli": {
        # Kimi Code CLI supports hooks via inline [[hooks]] arrays in config.toml,
        # which is a different mechanism from file-based hooks
    },
    "opencode": {
        # OpenCode doesn't support hooks yet
    },
}


def get_hook_definitions(platform: str) -> dict[str, dict[str, Any]]:
    """Get hook definitions for a platform.

    Args:
        platform: Platform identifier

    Returns:
        Dictionary of hook definitions (may be empty)
    """
    return HOOK_DEFINITIONS.get(platform, {})


def is_hook_supported(platform: str, hook_point: HookPoint) -> bool:
    """Check if a hook is supported on a platform.

    Args:
        platform: Platform identifier
        hook_point: HookPoint to check

    Returns:
        True if supported, False otherwise
    """
    definitions = get_hook_definitions(platform)
    return hook_point.value in definitions
