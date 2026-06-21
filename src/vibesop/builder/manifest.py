# pyright: reportMissingTypeArgument=false
"""Manifest builder for creating configuration manifests.

This module provides functionality for building Manifest objects
from various sources including registry files, policy files, and overlays.
"""

import logging
from pathlib import Path
from typing import Any

from vibesop.adapters.models import (
    Manifest,
    ManifestMetadata,
    PolicySet,
    RoutingPolicy,
    SecurityPolicy,
)
from vibesop.core.config import ConfigManager
from vibesop.spec import SkillSpec

logger = logging.getLogger(__name__)


class ManifestBuilder:
    """Builder for creating configuration manifests."""

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.config_loader = ConfigManager(project_root)

    def build(
        self,
        overlay_path: Path | None = None,
        platform: str = "claude-code",
        version: str = "1.0.0",
    ) -> Manifest:
        """Build a complete manifest from all sources."""
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
        return self.build(
            overlay_path=None,
            platform=platform,
            version=version,
        )

    def build_from_file(
        self,
        manifest_path: Path,
    ) -> Manifest:
        """Build manifest from a manifest YAML file."""
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

    def _load_skills(self) -> list[SkillSpec]:
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

                    skill = SkillSpec(
                        id=skill_id,
                        name=skill_dict.get("name") or skill_id,  # Fallback to id if name is empty
                        description=description,
                        trigger_when=trigger_when,
                        metadata=skill_dict.get("metadata", {}),
                    )
                    skills.append(skill)
                except Exception as e:
                    # Skip invalid skills
                    logger.warning("Failed to load skill %s: %s", skill_dict.get("id"), e)

            # Merge with dynamically discovered skills from central storage
            self._merge_discovered_skills(skills)

            return skills

        except Exception as e:
            logger.warning("Failed to load skills from registry: %s", e)
            return []

    def _load_skill_description(self, skill_id: str, _skill_dict: dict) -> str:
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

    def _merge_discovered_skills(self, existing_skills: list[SkillSpec]) -> None:
        try:
            from vibesop.core.routing.dynamic_discovery import DynamicSkillDiscovery

            discovery = DynamicSkillDiscovery()
            existing_ids = {s.id for s in existing_skills}
            discovered = discovery.discover()

            for skill in discovered:
                if skill.id not in existing_ids:
                    new_skill = SkillSpec(
                        id=skill.id,
                        name=skill.name or skill.id,
                        description=skill.description,
                        trigger_when=(skill.triggers[0] if skill.triggers else ""),
                        metadata={
                            "namespace": skill.namespace,
                            "entrypoint": "external",
                            "source_path": str(skill.source_path),
                        },
                    )
                    existing_skills.append(new_skill)
                    existing_ids.add(skill.id)
        except Exception as e:
            logger.warning("Dynamic skill discovery failed: %s", e)

    def _load_policies(self) -> PolicySet:
        try:
            policy_dict = self.config_loader.load_policy()

            # Convert to PolicySet
            security = self._dict_to_security_policy(policy_dict.get("security", {}))
            routing = self._dict_to_routing_policy(policy_dict.get("routing", {}))
            behavior = policy_dict.get("behavior", {})
            custom = policy_dict.get("custom", {})

            return PolicySet(
                security=security,
                routing=routing,
                behavior=behavior,
                custom=custom,
            )

        except Exception as e:
            logger.warning("Failed to load policies, using defaults: %s", e)
            return PolicySet()

    def _dict_to_security_policy(self, data: dict[str, Any]) -> SecurityPolicy:
        return SecurityPolicy(
            scan_external_content=data.get("scan_external_content", True),
            allow_path_traversal=data.get("allow_path_traversal", False),
            max_file_size=data.get("max_file_size", 10 * 1024 * 1024),
            require_signed_skills=data.get("require_signed_skills", False),
        )

    def _dict_to_routing_policy(self, data: dict[str, Any]) -> RoutingPolicy:
        preference_learning = data.get("preference_learning", {})

        return RoutingPolicy(
            enable_ai_routing=data.get("enable_ai_routing", True),
            confidence_threshold=data.get("confidence_threshold", 0.6),
            max_candidates=data.get("max_candidates", 3),
            enable_preference_learning=preference_learning.get("enabled", True),
        )

    def _dict_to_manifest(self, data: dict[str, Any]) -> Manifest:
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
            SkillSpec(
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
            routing=self._dict_to_routing_policy(policies_dict.get("routing", {})),
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
        """Apply overlay customizations to manifest."""
        from vibesop.builder.overlay import OverlayMerger

        merger = OverlayMerger()
        return merger.merge(manifest, overlay_path)


class QuickBuilder:
    """Quick builder for common manifest scenarios."""

    @staticmethod
    def default(platform: str = "claude-code") -> Manifest:
        builder = ManifestBuilder()
        return builder.build_from_registry(platform=platform)

    @staticmethod
    def minimal(platform: str = "claude-code") -> Manifest:
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
        builder = ManifestBuilder()
        base_manifest = builder.build_from_registry(platform=platform)

        # Apply custom policies
        if security:
            policy = base_manifest.get_effective_security_policy()
            for key, value in security.items():
                setattr(policy, key, value)

        if routing:
            config = base_manifest.get_effective_routing_policy()
            for key, value in routing.items():
                setattr(config, key, value)

        return base_manifest
