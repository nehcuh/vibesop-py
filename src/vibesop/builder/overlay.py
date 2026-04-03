"""Overlay merging utilities for customizing manifests.

This module provides functionality for merging overlay configurations
with base manifests to enable customization.
"""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from vibesop.adapters.models import Manifest


class OverlayMerger:
    """Merges overlay configurations with manifests.

    Overlays allow customization of manifests without modifying
    the base configuration. This is useful for:
    - Environment-specific settings
    - User preferences
    - Local customizations

    Example:
        >>> merger = OverlayMerger()
        >>> custom_manifest = merger.merge(base_manifest, "overlay.yaml")
    """

    def __init__(self) -> None:
        """Initialize the overlay merger."""
        self.yaml = YAML()
        self.yaml.preserve_quotes = True

    def merge(
        self,
        manifest: Manifest,
        overlay_path: Path,
    ) -> Manifest:
        """Merge overlay with manifest.

        Args:
            manifest: Base manifest to customize
            overlay_path: Path to overlay YAML file

        Returns:
            Customized manifest with overlay applied

        Raises:
            FileNotFoundError: If overlay file doesn't exist
            ValueError: If overlay is invalid
        """
        overlay_path = Path(overlay_path)

        if not overlay_path.exists():
            msg = f"Overlay file not found: {overlay_path}"
            raise FileNotFoundError(msg)

        # Load overlay
        overlay_data = self._load_overlay(overlay_path)

        # Apply overlay to manifest
        return self._apply_overlay(manifest, overlay_data)

    def _load_overlay(self, overlay_path: Path) -> dict[str, Any]:
        """Load overlay from YAML file.

        Args:
            overlay_path: Path to overlay file

        Returns:
            Overlay data dictionary

        Raises:
            ValueError: If file is invalid
        """
        try:
            with overlay_path.open("r", encoding="utf-8") as f:
                data = self.yaml.load(f)

            return data or {}

        except Exception as e:
            msg = f"Failed to load overlay from {overlay_path}: {e}"
            raise ValueError(msg) from e

    def _apply_overlay(
        self,
        manifest: Manifest,
        overlay: dict[str, Any],
    ) -> Manifest:
        """Apply overlay data to manifest.

        Args:
            manifest: Base manifest
            overlay: Overlay data

        Returns:
            Modified manifest
        """
        # Convert manifest to dict for easier manipulation
        manifest_dict = self._manifest_to_dict(manifest)

        # Merge overlay
        merged = self._deep_merge(manifest_dict, overlay)

        # Convert back to Manifest
        return self._dict_to_manifest(merged)

    def _manifest_to_dict(self, manifest: Manifest) -> dict[str, Any]:
        """Convert Manifest to dict.

        Args:
            manifest: Manifest object

        Returns:
            Dictionary representation
        """
        from pydantic import BaseModel

        def model_to_dict(obj: Any) -> Any:
            """Convert Pydantic model to dict recursively."""
            if isinstance(obj, BaseModel):
                return {k: model_to_dict(v) for k, v in obj.model_dump().items()}
            elif isinstance(obj, list):
                return [model_to_dict(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: model_to_dict(v) for k, v in obj.items()}
            else:
                return obj

        return model_to_dict(manifest)

    def _dict_to_manifest(self, data: dict[str, Any]) -> Manifest:
        """Convert dict to Manifest.

        Args:
            data: Dictionary representation

        Returns:
            Manifest object
        """
        # This is a simplified version - in practice you might want
        # to use the ManifestBuilder's _dict_to_manifest method
        from vibesop.adapters.models import (
            Manifest,
            ManifestMetadata,
            PolicySet,
            RoutingConfig,
            SecurityPolicy,
            SkillDefinition,
        )
        from vibesop.core.models import SkillDefinition as CoreSkillDefinition

        # Convert metadata
        metadata_dict = data.get("metadata", {})
        metadata = ManifestMetadata(**metadata_dict)

        # Convert skills
        skills_dicts = data.get("skills", [])
        skills = [
            SkillDefinition(**s) if isinstance(s, dict) else s
            for s in skills_dicts
        ]

        # Convert policies
        policies_dict = data.get("policies", {})
        policies = PolicySet(
            security=SecurityPolicy(**policies_dict.get("security", {})),
            routing=RoutingConfig(**policies_dict.get("routing", {})),
            behavior=policies_dict.get("behavior", {}),
            custom=policies_dict.get("custom", {}),
        )

        # Create manifest
        return Manifest(
            skills=skills,
            policies=policies,
            metadata=metadata,
            overlay=data.get("overlay"),
        )

    def _deep_merge(
        self,
        base: dict[str, Any],
        overlay: dict[str, Any],
    ) -> dict[str, Any]:
        """Deep merge overlay into base.

        Args:
            base: Base dictionary
            overlay: Overlay dictionary

        Returns:
            Merged dictionary
        """
        result = base.copy()

        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = self._deep_merge(result[key], value)
            elif key in result and isinstance(result[key], list) and isinstance(value, list):
                # For lists, replace by default
                # Could implement list merging logic if needed
                result[key] = value
            else:
                # Replace or add value
                result[key] = value

        return result


def create_overlay(
    output_path: Path,
    skills: list[str] | None = None,
    security: dict[str, Any] | None = None,
    routing: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Create an overlay YAML file.

    Convenience function for creating overlay files.

    Args:
        output_path: Path to write overlay file
        skills: List of skill IDs to include (None = all)
        security: Security policy overrides
        routing: Routing config overrides
        metadata: Metadata overrides
    """
    yaml = YAML()

    overlay: dict[str, Any] = {}

    if skills is not None:
        overlay["skills"] = [{"id": sid} for sid in skills]

    if security:
        overlay["security"] = security

    if routing:
        overlay["routing"] = routing

    if metadata:
        overlay["metadata"] = metadata

    # Write overlay file
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        yaml.dump(overlay, f)


def validate_overlay(overlay_path: Path) -> list[str]:
    """Validate an overlay file.

    Args:
        overlay_path: Path to overlay file

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    overlay_path = Path(overlay_path)

    if not overlay_path.exists():
        errors.append(f"Overlay file not found: {overlay_path}")
        return errors

    try:
        merger = OverlayMerger()
        overlay_data = merger._load_overlay(overlay_path)

        # Validate structure
        if not isinstance(overlay_data, dict):
            errors.append("Overlay must be a dictionary")
            return errors

        # Validate known keys
        valid_keys = {"skills", "security", "routing", "metadata", "policies"}
        for key in overlay_data:
            if key not in valid_keys:
                errors.append(f"Unknown overlay key: {key}")

    except Exception as e:
        errors.append(f"Failed to validate overlay: {e}")

    return errors
