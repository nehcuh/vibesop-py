# pyright: reportUnnecessaryIsInstance=false
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
        overlay_data = self.load_overlay(overlay_path)

        # Apply overlay to manifest
        return self._apply_overlay(manifest, overlay_data)

    def load_overlay(self, overlay_path: Path) -> dict[str, Any]:
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

        # Convert back to Manifest. Pass the original overlay so legacy
        # top-level security/routing can be read without beating policies.*.
        return self._dict_to_manifest(merged, source_overlay=overlay)

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

    def _dict_to_manifest(
        self,
        data: dict[str, Any],
        source_overlay: dict[str, Any] | None = None,
    ) -> Manifest:
        """Convert dict to Manifest.

        Args:
            data: Dictionary representation after the deep merge
            source_overlay: Original overlay mapping. Legacy top-level
                ``security``/``routing`` keys are still applied. Canonical
                ``policies.security``/``policies.routing`` wins on conflicts.

        Returns:
            Manifest object
        """
        # This is a simplified version - in practice you might want
        # to use the ManifestBuilder's _dict_to_manifest method
        from vibesop.adapters.models import (
            Manifest,
            ManifestMetadata,
            PolicySet,
            RoutingPolicy,
            SecurityPolicy,
        )
        from vibesop.spec import SkillSpec

        metadata_dict = data.get("metadata", {})
        metadata = ManifestMetadata(**metadata_dict)

        # Convert skills
        skills_dicts = data.get("skills", [])
        skills = [SkillSpec(**s) if isinstance(s, dict) else s for s in skills_dicts]

        # Convert policies. Base manifest dumps always contain policies.*,
        # so a legacy top-level key must be applied here or its values are lost.
        policies_raw = data.get("policies", {})
        policies_dict = policies_raw if isinstance(policies_raw, dict) else {}
        policies = PolicySet(
            security=SecurityPolicy(
                **self._resolve_policy_section(policies_dict, data, source_overlay, "security")
            ),
            routing=RoutingPolicy(
                **self._resolve_policy_section(policies_dict, data, source_overlay, "routing")
            ),
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

    @staticmethod
    def _resolve_policy_section(
        policies_dict: dict[str, Any],
        data: dict[str, Any],
        source_overlay: dict[str, Any] | None,
        name: str,
    ) -> dict[str, Any]:
        """Resolve one policy section, with legacy top-level fallback.

        Historical overlays stored ``security`` and ``routing`` at the top
        level. Those values still apply. When the same overlay also sets
        ``policies.<name>``, the canonical mapping wins key by key.
        """
        base = policies_dict.get(name)
        merged: dict[str, Any] = dict(base) if isinstance(base, dict) else {}

        legacy = source_overlay.get(name) if source_overlay is not None else data.get(name)
        if isinstance(legacy, dict):
            merged.update(legacy)

        if source_overlay is not None:
            overlay_policies = source_overlay.get("policies")
            if isinstance(overlay_policies, dict):
                canonical = overlay_policies.get(name)
                if isinstance(canonical, dict):
                    merged.update(canonical)
        return merged


def create_overlay(
    output_path: Path,
    skills: list[str] | None = None,
    security: dict[str, Any] | None = None,
    routing: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Create an overlay YAML file.

    Security and routing overrides are written under the canonical
    ``policies.security`` / ``policies.routing`` keys. Top-level
    ``security`` / ``routing`` is the historical shape and is not emitted.

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

    policies: dict[str, Any] = {}
    if security is not None:
        policies["security"] = security
    if routing is not None:
        policies["routing"] = routing
    if policies:
        overlay["policies"] = policies

    if metadata is not None:
        overlay["metadata"] = metadata

    # Write overlay file
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        yaml.dump(overlay, f)


def validate_overlay(overlay_path: Path) -> list[str]:
    """Validate an overlay file against the canonical schema.

    Accepted top-level keys are ``skills``, ``metadata``, and ``policies``.
    Historical top-level ``security`` / ``routing`` keys are not valid for
    new files (the merger can still read them). Policy field values are
    checked with ``SecurityPolicy`` and ``RoutingPolicy``.

    Args:
        overlay_path: Path to overlay file

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []
    overlay_path = Path(overlay_path)

    if not overlay_path.exists():
        errors.append(f"Overlay file not found: {overlay_path}")
        return errors

    try:
        merger = OverlayMerger()
        overlay_data = merger.load_overlay(overlay_path)

        # Validate structure
        if not isinstance(overlay_data, dict):
            errors.append("Overlay must be a dictionary")
            return errors

        # Canonical shape only. Top-level security/routing is legacy, not blessed.
        valid_keys = {"skills", "metadata", "policies"}
        for key in overlay_data:
            if key not in valid_keys:
                errors.append(f"Unknown overlay key: {key}")

        policies = overlay_data.get("policies")
        if policies is not None:
            if not isinstance(policies, dict):
                errors.append("policies must be a dictionary")
            else:
                errors.extend(_validate_policy_sections(policies))

    except Exception as e:
        errors.append(f"Failed to validate overlay: {e}")

    return errors


def _validate_policy_sections(policies: dict[str, Any]) -> list[str]:
    """Return errors for unknown policy sections or illegal field values."""
    from vibesop.adapters.models import RoutingPolicy, SecurityPolicy

    errors: list[str] = []
    valid_sections = {"security", "routing", "behavior", "custom"}
    for key in policies:
        if key not in valid_sections:
            errors.append(f"Unknown policies key: {key}")

    if "security" in policies:
        errors.extend(
            _validate_policy_model("policies.security", SecurityPolicy, policies.get("security"))
        )
    if "routing" in policies:
        errors.extend(
            _validate_policy_model("policies.routing", RoutingPolicy, policies.get("routing"))
        )
    for name in ("behavior", "custom"):
        if name in policies and not isinstance(policies[name], dict):
            errors.append(f"policies.{name} must be a dictionary")
    return errors


def _validate_policy_model(label: str, model: Any, raw: Any) -> list[str]:
    """Validate one policy mapping. Unknown fields and illegal values are errors."""
    from pydantic import BaseModel, ValidationError

    if not isinstance(model, type) or not issubclass(model, BaseModel):
        return [f"{label} validator is not a policy model"]
    policy_model: type[BaseModel] = model

    if not isinstance(raw, dict):
        return [f"{label} must be a dictionary"]

    known = set(policy_model.model_fields)
    errors = [f"Unknown {label} field: {name}" for name in sorted(set(raw) - known)]
    try:
        policy_model.model_validate(raw)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", ())) or label
            errors.append(f"Invalid {label}.{loc}: {err.get('msg', 'invalid value')}")
    return errors
