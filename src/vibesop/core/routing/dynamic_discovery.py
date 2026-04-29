"""Dynamic skill discovery from central storage.

Bridges ExternalSkillLoader (disk discovery) into the routing engine
so that externally installed packs are automatically available for routing
without manual registry.yaml updates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredSkill:
    """A skill discovered from an external pack on disk.

    Attributes:
        id: Fully qualified skill ID (e.g., "gstack/review")
        name: Human-readable name
        description: Short description
        namespace: Pack namespace (e.g., "gstack", "omx")
        source_path: Path to the skill directory on disk
        triggers: Trigger phrases for routing
    """

    id: str
    name: str
    description: str
    namespace: str
    source_path: Path
    triggers: list[str]


class DynamicSkillDiscovery:
    """Discovers installed skills from central storage for routing.

    Bridges ExternalSkillLoader (disk discovery) into the routing engine
    so that externally installed packs are automatically available for routing
    without manual registry.yaml updates.

    Example:
        >>> discovery = DynamicSkillDiscovery()
        >>> skills = discovery.discover()
        >>> for skill in skills:
        ...     print(f"{skill.id}: {skill.name}")
    """

    def discover(self) -> list[DiscoveredSkill]:
        """Scan ~/.config/skills/ for installed packs.

        Returns:
            List of DiscoveredSkill for all installed external packs
        """
        from vibesop.core.skills.external_loader import ExternalSkillLoader
        from vibesop.core.skills.parser import parse_skill_md

        loader = ExternalSkillLoader()
        raw = loader.discover_all()

        discovered: list[DiscoveredSkill] = []
        for skill_id, meta in raw.items():
            if not skill_id or "/" not in skill_id:
                continue

            parts = skill_id.split("/", 1)
            namespace = parts[0]
            skill_name = parts[1]

            skill_file = meta.install_path / "SKILL.md" if meta.install_path else None
            triggers: list[str] = []
            if skill_file and skill_file.exists():
                parsed = parse_skill_md(skill_file)
                if parsed and parsed.triggers:
                    triggers = parsed.triggers

            discovered.append(
                DiscoveredSkill(
                    id=skill_id,
                    name=meta.base_metadata.name or skill_name,
                    description=meta.base_metadata.description or "",
                    namespace=namespace,
                    source_path=meta.install_path or Path(),
                    triggers=triggers,
                )
            )

        return discovered

    def merge_with_registry(
        self, registry_skills: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Merge dynamically discovered skills with static registry entries.

        Discovered skills supplement registry entries.
        If a skill exists in both, the registry entry takes precedence.

        Args:
            registry_skills: Existing registry skill dicts with "id", "name", etc.

        Returns:
            Merged list of skill dicts
        """
        registry_ids = {s["id"] for s in registry_skills}
        discovered = self.discover()

        merged = list(registry_skills)
        for skill in discovered:
            if skill.id not in registry_ids:
                merged.append(
                    {
                        "id": skill.id,
                        "name": skill.name,
                        "description": skill.description,
                        "namespace": skill.namespace,
                        "entrypoint": "external",
                        "priority": "P3",
                        "triggers": skill.triggers,
                    }
                )

        return merged
