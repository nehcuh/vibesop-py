"""Platform adapters for generating configuration files.

This module provides adapters for different AI coding assistant platforms,
enabling generation of platform-specific configuration from a unified manifest.

Available Adapters:
    - Claude Code
    - OpenCode

Example:
    >>> from vibesop.adapters import ClaudeCodeAdapter, Manifest
    >>>
    >>> manifest = Manifest(...)
    >>> adapter = ClaudeCodeAdapter()
    >>> result = adapter.render_config(manifest, Path("~/.claude"))
    >>> print(f"Created {result.file_count} files")
"""

from vibesop.adapters.base import PlatformAdapter
from vibesop.adapters.claude_code import ClaudeCodeAdapter
from vibesop.adapters.models import (
    Manifest,
    ManifestMetadata,
    PolicySet,
    RenderResult,
    RoutingConfig,
    SecurityPolicy,
)
from vibesop.adapters.opencode import OpenCodeAdapter
from vibesop.adapters.protocol import AdapterProtocol

__all__ = [
    "AdapterProtocol",
    # Adapters
    "ClaudeCodeAdapter",
    # Models
    "Manifest",
    "ManifestMetadata",
    "OpenCodeAdapter",
    # Base classes
    "PlatformAdapter",
    "PolicySet",
    "RenderResult",
    "RoutingConfig",
    "SecurityPolicy",
]

from vibesop._version import __version__
