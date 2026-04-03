"""Hook system for VibeSOP.

This module provides the hook framework for executing custom code
at specific points in the AI assistant workflow.

Classes:
    - HookPoint: Enum defining standard hook points
    - Hook: Abstract base class for all hooks
    - ScriptHook: Simple script-based hooks
    - TemplateHook: Jinja2 template-based hooks

Functions:
    - create_hook: Convenience function for creating hooks
    - get_hook_definitions: Get hooks for a platform
    - is_hook_supported: Check if hook is supported

Example:
    >>> from vibesop.hooks import Hook, HookPoint, create_hook
    >>>
    >>> hook = create_hook("my-hook", HookPoint.PRE_SESSION_END, "#!/bin/bash\\necho 'Hello'")
    >>> hook.render_to_file(Path("/tmp/hook.sh"))
"""

from vibesop.hooks.base import Hook, ScriptHook, TemplateHook, create_hook
from vibesop.hooks.installer import HookInstaller
from vibesop.hooks.points import (
    HookPoint,
    get_hook_definitions,
    is_hook_supported,
)

__all__ = [
    # Enums
    "HookPoint",
    # Classes
    "Hook",
    "ScriptHook",
    "TemplateHook",
    "HookInstaller",
    # Functions
    "create_hook",
    "get_hook_definitions",
    "is_hook_supported",
]

__version__ = "0.1.0"
