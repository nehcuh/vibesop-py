# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false, reportUnknownParameterType=false
"""Manifest builder for creating configuration manifests.

This module provides functionality for building Manifest objects
from various sources including registry files, policy files, and overlays.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from vibesop.adapters.models import (
    Manifest,
    ManifestMetadata,
    PolicySet,
    RoutingConfig,
    SecurityPolicy,
    SkillDefinition,
)
from vibesop.core.config import ConfigManager


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
        self.config_loader = ConfigManager(project_root)

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

                    # Try to load description from skill file
                    description = self._load_skill_description(skill_id, skill_dict)

                    # Extract trigger_when from description
                    trigger_when = self._extract_trigger_from_description(description)

                    # Use intent as fallback for description
                    if not description:
                        description = skill_dict.get("intent", "")

                    skill = SkillDefinition(
                        id=skill_id,
                        name=skill_dict.get("name") or skill_id,  # Fallback to id if name is empty
                        description=description,
                        trigger_when=trigger_when,
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

    def _load_skill_description(self, skill_id: str, _skill_dict: dict) -> str:
        """Load skill description from skill file.

        Args:
            skill_id: Skill identifier (e.g., "gstack/review")
            skill_dict: Skill dictionary from registry

        Returns:
            Description text from skill file (empty if not found)
        """
        # Try to find skill file
        # For external skills, check ~/.config/skills/
        skill_parts = skill_id.split("/")
        if len(skill_parts) >= 2:
            namespace = skill_parts[0]
            skill_name = skill_parts[1]

            # Check external skill paths
            external_paths = [
                Path(f"~/.config/skills/{namespace}/{skill_name}/SKILL.md"),
                Path(f"~/.config/skills/{skill_name}/SKILL.md"),
                Path(f".vibe/skills/{namespace}/{skill_name}/SKILL.md"),
                Path(f"skills/{namespace}/{skill_name}/SKILL.md"),
            ]

            for skill_path in external_paths:
                expanded_path = skill_path.expanduser()
                if expanded_path.exists():
                    try:
                        content = expanded_path.read_text(encoding="utf-8")

                        # Extract description from YAML frontmatter
                        if content.startswith("---"):
                            parts = content.split("---", 2)
                            if len(parts) >= 2:
                                from ruamel.yaml import YAML

                                yaml = YAML()
                                frontmatter = yaml.load(parts[1])
                                if isinstance(frontmatter, dict):
                                    desc = frontmatter.get("description", "")
                                    if desc:
                                        return desc

                        # If no frontmatter description, use first paragraph
                        lines = content.split("\n")
                        for raw_line in lines:
                            stripped = raw_line.strip()
                            if (
                                stripped
                                and not stripped.startswith("<!--")
                                and not stripped.startswith("#")
                                and len(stripped) > 20
                            ):
                                return stripped
                    except Exception as e:
                        logger.debug(f"Failed to extract description from {skill_path}: {e}")

        return ""

    def _extract_trigger_from_description(self, description: str) -> str:
        """Extract trigger conditions from skill description.

        Looks for patterns like:
        - "Use when asked to X, Y, Z"
        - "Triggered when X"
        - "Auto-trigger on X"

        Args:
            description: Skill description text

        Returns:
            Extracted trigger conditions (empty string if none found)
        """
        if not description:
            return ""

        import re

        # Pattern 1: "Use when asked to X, Y, Z"
        match = re.search(r"Use when asked to ([^.]+)", description, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Pattern 2: "Triggered when X"
        match = re.search(r"Triggered when ([^.]+)", description, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Pattern 3: "Auto-trigger on X"
        match = re.search(r"Auto-trigger on ([^.]+)", description, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Pattern 4: "Proactively suggest when X"
        match = re.search(r"Proactively suggest when ([^.]+)", description, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return ""

    def _load_policies(self) -> PolicySet:
        """Load policies from config files.

        Returns:
            PolicySet with loaded or default policies
        """
        try:
            policy_dict = self.config_loader.load_policy()

            # Convert to PolicySet
            security = self._dict_to_security_policy(policy_dict.get("security", {}))
            routing = self._dict_to_routing_config(policy_dict.get("routing", {}))
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
        # Handle preference_learning
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
