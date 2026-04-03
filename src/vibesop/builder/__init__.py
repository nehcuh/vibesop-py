"""Configuration builder module.

This module provides functionality for building configuration
manifests and rendering platform-specific configurations.

Classes:
    - ManifestBuilder: Build manifests from various sources
    - QuickBuilder: Convenience methods for common scenarios
    - OverlayMerger: Merge overlay customizations with manifests
    - ConfigRenderer: High-level rendering interface
    - RenderProgressTracker: Track rendering progress

Functions:
    - create_overlay: Create overlay YAML files
    - validate_overlay: Validate overlay files
"""

from vibesop.builder.manifest import ManifestBuilder, QuickBuilder
from vibesop.builder.overlay import OverlayMerger, create_overlay, validate_overlay
from vibesop.builder.renderer import ConfigRenderer, RenderProgressTracker
from vibesop.builder.dynamic_renderer import ConfigDrivenRenderer, RenderRule
from vibesop.builder.doc_renderer import DocRenderer, DocType, DocConfig, DocSection

__all__ = [
    "ManifestBuilder",
    "QuickBuilder",
    "OverlayMerger",
    "ConfigRenderer",
    "RenderProgressTracker",
    "ConfigDrivenRenderer",
    "RenderRule",
    "DocRenderer",
    "DocType",
    "DocConfig",
    "DocSection",
    "create_overlay",
    "validate_overlay",
]

__version__ = "0.1.0"
