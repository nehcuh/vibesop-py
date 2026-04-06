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

from vibesop.builder.doc_generators import DocContentGenerator
from vibesop.builder.doc_renderer import DocConfig, DocRenderer, DocSection
from vibesop.builder.doc_templates import DocTemplates, DocType
from vibesop.builder.dynamic_renderer import ConfigDrivenRenderer, RenderRule
from vibesop.builder.manifest import ManifestBuilder, QuickBuilder
from vibesop.builder.overlay import OverlayMerger, create_overlay, validate_overlay
from vibesop.builder.renderer import ConfigRenderer, RenderProgressTracker

__all__ = [
    "ConfigDrivenRenderer",
    # Configuration rendering
    "ConfigRenderer",
    "DocConfig",
    "DocContentGenerator",
    # Documentation
    "DocRenderer",
    "DocSection",
    "DocTemplates",
    "DocType",
    # Manifest builders
    "ManifestBuilder",
    # Overlay management
    "OverlayMerger",
    "QuickBuilder",
    "RenderProgressTracker",
    "RenderRule",
    "create_overlay",
    "validate_overlay",
]

from vibesop._version import __version__
