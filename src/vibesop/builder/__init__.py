"""Configuration builder module.

This module provides functionality for building configuration
manifests and rendering platform-specific configurations.

Classes:
    - ManifestBuilder: Build manifests from various sources
    - QuickBuilder: Convenience methods for common scenarios
    - OverlayMerger: Merge overlay customizations with manifests
    - ConfigRenderer: High-level rendering interface
    - RenderProgressTracker: Track rendering progress
    - DocRenderer: Documentation renderer
    - DocContentGenerator: Documentation content generator
    - DocTemplates: Documentation template manager

Functions:
    - create_overlay: Create overlay YAML files
    - validate_overlay: Validate overlay files
"""

from vibesop.builder.manifest import ManifestBuilder, QuickBuilder
from vibesop.builder.overlay import OverlayMerger, create_overlay, validate_overlay
from vibesop.builder.renderer import ConfigRenderer, RenderProgressTracker
from vibesop.builder.dynamic_renderer import ConfigDrivenRenderer, RenderRule
from vibesop.builder.doc_renderer import DocRenderer, DocSection, DocConfig
from vibesop.builder.doc_templates import DocType, DocTemplates
from vibesop.builder.doc_generators import DocContentGenerator

__all__ = [
    # Manifest builders
    "ManifestBuilder",
    "QuickBuilder",
    # Overlay management
    "OverlayMerger",
    "create_overlay",
    "validate_overlay",
    # Configuration rendering
    "ConfigRenderer",
    "RenderProgressTracker",
    "ConfigDrivenRenderer",
    "RenderRule",
    # Documentation
    "DocRenderer",
    "DocTemplates",
    "DocContentGenerator",
    "DocType",
    "DocConfig",
    "DocSection",
]

from vibesop._version import __version__  # noqa: E402
