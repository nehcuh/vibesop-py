"""Unified configuration management for VibeSOP.

This module provides a single source of truth for all configuration,
replacing the fragmented config system across multiple files.

Configuration Sources (priority order):
1. defaults - Built-in defaults
2. global - ~/.vibe/config.yaml
3. project - .vibe/config.yaml
4. preferences - .vibe/preferences.json (legacy)
5. env - Environment variables
6. cli - Command-line arguments

Example:
    >>> from vibesop.core.config import ConfigManager
    >>> manager = ConfigManager(project_root=".")
    >>> routing_config = manager.get_routing_config()
    >>> print(routing_config.min_confidence)
"""

from vibesop.core.config.manager import (
    ConfigManager,
    ConfigSource,
    ConfigSourcePriority,
    RoutingConfig,
    SecurityConfig,
    SemanticConfig,
)

__all__ = [
    "ConfigManager",
    "ConfigSource",
    "ConfigSourcePriority",
    "RoutingConfig",
    "SecurityConfig",
    "SemanticConfig",
]
