"""Platform adapters for generating configuration files.

This module provides adapters for different AI coding assistant platforms,
enabling generation of platform-specific configuration from a unified manifest.

Available Adapters:
    - Claude Code (hook-based via HookBasedAdapter)
    - Kimi Code CLI (file-based via FileBasedAdapter)
    - OpenCode (file-based via FileBasedAdapter)
    - Cursor IDE (file-based via FileBasedAdapter)
    - Pi Coding Agent (sdk-based via SdkBasedAdapter)

Reference Base Classes:
    - FileBasedAdapter: AGENTS.md + docs/ + skills/ symlinks
    - HookBasedAdapter: CLAUDE.md + Jinja2 rules/ + settings.json hooks
    - SdkBasedAdapter: AGENTS.md + TypeScript extensions + prompt templates

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
from vibesop.adapters.cursor import CursorAdapter
from vibesop.adapters.file_based import FileBasedAdapter
from vibesop.adapters.hook_based import HookBasedAdapter
from vibesop.adapters.kimi_cli import KimiCliAdapter
from vibesop.adapters.models import (
    Manifest,
    ManifestMetadata,
    PolicySet,
    RenderResult,
    RoutingPolicy,
    SecurityPolicy,
)
from vibesop.adapters.opencode import OpenCodeAdapter
from vibesop.adapters.pi_coding_agent import PiCodingAgentAdapter
from vibesop.adapters.protocol import AdapterProtocol
from vibesop.adapters.sdk_based import SdkBasedAdapter

__all__ = [
    "AdapterProtocol",
    # Adapters
    "ClaudeCodeAdapter",
    "CursorAdapter",
    # Base classes
    "FileBasedAdapter",
    "HookBasedAdapter",
    "KimiCliAdapter",
    # Models
    "Manifest",
    "ManifestMetadata",
    "OpenCodeAdapter",
    "PiCodingAgentAdapter",
    "PlatformAdapter",
    "PolicySet",
    "RenderResult",
    "RoutingPolicy",
    "SdkBasedAdapter",
    "SecurityPolicy",
]

from vibesop._version import __version__
