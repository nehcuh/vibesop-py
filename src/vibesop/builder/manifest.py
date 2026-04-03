"""Manifest builder for creating configuration manifests.

This module provides functionality for building Manifest objects
from various sources including registry files, policy files, and overlays.
"""

from pathlib import Path
from typing import Any

from vibesop.adapters.models import (
    Manifest,
    ManifestMetadata,
    PolicySet,
    RenderResult,
    RoutingConfig,
    SecurityPolicy,
    SkillDefinition,
)
from vibesop.core.config import ConfigLoader


class ManifestBuilder:
    """Builder for creating configuration manifests.

    Loads skills, policies, and metadata from various sources
    and combines them into a complete Manifest.

    Example:
        >>> builder = ManifestBuilder()
        >>> manifest = builder.build()
        >>> print(f"Built manifest with {len(manifest.skills)} skills")
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:
        """Initialize the manifest builder.

        Args:
            project_root: Path to project root containing core/ directory
        """
        self.project_root = Path(project_root).resolve()
        self.config_loader = ConfigLoader(project_root)

    def build(
        self,
        overlay_path: Path | None = None,
        platform: str = "claude-code",
        version: str = "1.0.0",
    ) -> Manifest:
        """Build a complete manifest from all sources.

        Args:
            overlay_path: Optional path to overlay file for customization
            platform: Target platform
            version: Manifest version

        Returns:
            Complete Manifest with skills, policies, and metadata
        """
        # Load skills from registry
        skills = self._load_skills()

        # Load policies
        policies = self._load_policies()

        # Create metadata
        metadata = ManifestMetadata(
            platform=platform,
            version=version,
        )

        # Create manifest
        manifest = Manifest(
            skills=skills,
            policies=policies,
            metadata=metadata,
        )

        # Apply overlay if provided
        if overlay_path:
            manifest = self.apply_overlay(manifest, overlay_path)

        return manifest

    def build_from_registry(
        self,
        platform: str = "claude-code",
        version: str = "1.0.0",
    ) -> Manifest:
        """Build manifest from registry only (no custom policies).

        Args:
            platform: Target platform
            version: Manifest version

        Returns:
            Manifest with skills from registry and default policies
        """
        return self.build(
            overlay_path=None,
            platform=platform,
            version=version,
        )

    def build_from_file(
        self,
        manifest_path: Path,
    ) -> Manifest:
        """Build manifest from a manifest YAML file.

        Args:
            manifest_path: Path to manifest YAML file

        Returns:
            Manifest loaded from file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is invalid
        """
        from ruamel.yaml import YAML

        yaml = YAML()
        manifest_path = Path(manifest_path)

        if not manifest_path.exists():
            msg = f"Manifest file not found: {manifest_path}"
            raise FileNotFoundError(msg)

        try:
            with manifest_path.open("r", encoding="utf-8") as f:
                data = yaml.load(f)

            # Convert to Manifest
            return self._dict_to_manifest(data or {})

        except Exception as e:
            msg = f"Failed to load manifest from {manifest_path}: {e}"
            raise ValueError(msg) from e

    def _load_skills(self) -> list[SkillDefinition]:
        """Load skills from registry.

        Returns:
            List of SkillDefinition objects
        """
        try:
            skill_dicts = self.config_loader.get_all_skills()

            skills = []
            for skill_dict in skill_dicts:
                try:
                    skill_id = skill_dict.get("id", "")
                    skill = SkillDefinition(
                        id=skill_id,
                        name=skill_dict.get("name") or skill_id,  # Fallback to id if name is empty
                        description=skill_dict.get("description", ""),
                        trigger_when=skill_dict.get("trigger_when", ""),
                        metadata=skill_dict.get("metadata", {}),
                    )
                    skills.append(skill)
                except Exception as e:
                    # Skip invalid skills
                    print(f"Warning: Failed to load skill {skill_dict.get('id')}: {e}")

            return skills

        except Exception as e:
            print(f"Warning: Failed to load skills from registry: {e}")
            return []

    def _load_policies(self) -> PolicySet:
        """Load policies from config files.

        Returns:
            PolicySet with loaded or default policies
        """
        try:
            policy_dict = self.config_loader.load_policy()

            # Convert to PolicySet
            security = self._dict_to_security_policy(
                policy_dict.get("security", {})
            )
            routing = self._dict_to_routing_config(
                policy_dict.get("routing", {})
            )
            behavior = policy_dict.get("behavior", {})
            custom = policy_dict.get("custom", {})

            return PolicySet(
                security=security,
                routing=routing,
                behavior=behavior,
                custom=custom,
            )

        except Exception as e:
            print(f"Warning: Failed to load policies, using defaults: {e}")
            return PolicySet()

    def _dict_to_security_policy(self, data: dict[str, Any]) -> SecurityPolicy:
        """Convert dict to SecurityPolicy.

        Args:
            data: Dictionary with security policy values

        Returns:
            SecurityPolicy instance
        """
        return SecurityPolicy(
            scan_external_content=data.get("scan_external_content", True),
            allow_path_traversal=data.get("allow_path_traversal", False),
            max_file_size=data.get("max_file_size", 10 * 1024 * 1024),
            require_signed_skills=data.get("require_signed_skills", False),
        )

    def _dict_to_routing_config(self, data: dict[str, Any]) -> RoutingConfig:
        """Convert dict to RoutingConfig.

        Args:
            data: Dictionary with routing config values

        Returns:
            RoutingConfig instance
        """
        # Handle candidate_selection
        candidate_selection = data.get("candidate_selection", {})
        preference_learning = data.get("preference_learning", {})

        return RoutingConfig(
            enable_ai_routing=data.get("enable_ai_routing", True),
            confidence_threshold=data.get("confidence_threshold", 0.6),
            max_candidates=data.get("max_candidates", 3),
            enable_preference_learning=preference_learning.get("enabled", True),
        )

    def _dict_to_manifest(self, data: dict[str, Any]) -> Manifest:
        """Convert dict to Manifest.

        Args:
            data: Dictionary with manifest data

        Returns:
            Manifest instance
        """
        # Convert metadata
        metadata_dict = data.get("metadata", {})
        metadata = ManifestMetadata(
            platform=metadata_dict.get("platform", "claude-code"),
            version=metadata_dict.get("version", "1.0.0"),
            author=metadata_dict.get("author", ""),
            description=metadata_dict.get("description", ""),
        )

        # Convert skills
        skills_dicts = data.get("skills", [])
        skills = [
            SkillDefinition(
                id=s.get("id", ""),
                name=s.get("name") or s.get("id", ""),  # Fallback to id if name is empty
                description=s.get("description", ""),
                trigger_when=s.get("trigger_when", ""),
                metadata=s.get("metadata", {}),
            )
            for s in skills_dicts
        ]

        # Convert policies
        policies_dict = data.get("policies", {})
        policies = PolicySet(
            security=self._dict_to_security_policy(policies_dict.get("security", {})),
            routing=self._dict_to_routing_config(policies_dict.get("routing", {})),
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

    def apply_overlay(
        self,
        manifest: Manifest,
        overlay_path: Path,
    ) -> Manifest:
        """Apply overlay customizations to manifest.

        Args:
            manifest: Base manifest
            overlay_path: Path to overlay YAML file

        Returns:
            Modified manifest with overlay applied

        Raises:
            FileNotFoundError: If overlay file doesn't exist
            ValueError: If overlay is invalid
        """
        from vibesop.builder.overlay import OverlayMerger

        merger = OverlayMerger()
        return merger.merge(manifest, overlay_path)


class QuickBuilder:
    """Quick builder for common manifest scenarios.

    Provides convenience methods for building manifests without
    needing to configure ManifestBuilder.

    Example:
        >>> manifest = QuickBuilder.default()
        >>> manifest = QuickBuilder.with_skills(["skill-1", "skill-2"])
    """

    @staticmethod
    def default(platform: str = "claude-code") -> Manifest:
        """Create a default manifest.

        Args:
            platform: Target platform

        Returns:
            Default manifest with registry skills and default policies
        """
        builder = ManifestBuilder()
        return builder.build_from_registry(platform=platform)

    @staticmethod
    def minimal(platform: str = "claude-code") -> Manifest:
        """Create a minimal manifest (no skills).

        Args:
            platform: Target platform

        Returns:
            Minimal manifest with no skills
        """
        metadata = ManifestMetadata(platform=platform)
        return Manifest(
            skills=[],
            policies=PolicySet(),
            metadata=metadata,
        )

    @staticmethod
    def with_custom_policies(
        security: dict[str, Any] | None = None,
        routing: dict[str, Any] | None = None,
        platform: str = "claude-code",
    ) -> Manifest:
        """Create manifest with custom policies.

        Args:
            security: Security policy overrides
            routing: Routing config overrides
            platform: Target platform

        Returns:
            Manifest with custom policies
        """
        builder = ManifestBuilder()
        base_manifest = builder.build_from_registry(platform=platform)

        # Apply custom policies
        if security:
            policy = base_manifest.get_effective_security_policy()
            for key, value in security.items():
                setattr(policy, key, value)

        if routing:
            config = base_manifest.get_effective_routing_config()
            for key, value in routing.items():
                setattr(config, key, value)

        return base_manifest
