"""High-level skill management API.

**⚠️ POSITIONING**: VibeSOP is a ROUTING ENGINE, not an execution engine.

This module provides skill discovery and metadata access only:
- list_skills(): Discover available skills
- get_skill_info(): Get skill metadata
- search_skills(): Search by keyword
- get_skill_instance(): Get skill object for instantiation

For routing (discovery), use UnifiedRouter.route() instead:
    from vibesop.core.routing import UnifiedRouter
    router = UnifiedRouter()
    result = router.route("your query")
"""

import logging
from pathlib import Path
from typing import Any

from vibesop.core.config import ConfigManager
from vibesop.core.skills.base import Skill
from vibesop.core.skills.loader import SkillLoader

logger = logging.getLogger(__name__)


class SkillManager:
    """High-level API for skill management.

    **⚠️ POSITIONING**: VibeSOP is a routing engine, NOT an execution engine.

    This class provides skill discovery and metadata access for the routing engine.

    Core Functions:
        • list_skills()     - Discover available skills
        • get_skill_info()  - Get skill metadata
        • search_skills()   - Search by keyword
        • get_skill_instance() - Get skill object for instantiation

    Usage:
        manager = SkillManager()
        skills = manager.list_skills()
        info = manager.get_skill_info("systematic-debugging")

    For routing (discovery), use UnifiedRouter instead:
        from vibesop.core.routing import UnifiedRouter
        router = UnifiedRouter()
        result = router.route("debug this error")
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:
        """Initialize the skill manager.

        Args:
            project_root: Project root directory
        """
        self.project_root = Path(project_root).resolve()
        self._loader = SkillLoader(project_root=self.project_root)
        self._config = ConfigManager(project_root=self.project_root)

        # Discover skills on init
        self._loader.discover_all()

    def list_skills(
        self,
        namespace: str | None = None,
        include_registry: bool = True,
    ) -> list[dict[str, Any]]:
        """List all available skills.

        Args:
            namespace: Optional namespace filter
            include_registry: Include skills from YAML registry

        Returns:
            List of skill information dictionaries
        """
        # Get skills from filesystem
        definitions = self._loader.list_skills(namespace=namespace)

        skills = [
            {
                "id": d.metadata.id,
                "name": d.metadata.name,
                "description": d.metadata.description,
                "intent": d.metadata.intent,
                "namespace": d.metadata.namespace,
                "version": d.metadata.version,
                "tags": d.metadata.tags,
                "type": d.metadata.skill_type.value,
                "source": "filesystem",
            }
            for d in definitions
        ]

        # Also include skills from YAML registry
        if include_registry:
            try:
                registry_skills = self._config.get_all_skills()
                for skill in registry_skills:
                    skill_id = skill.get("id", "")
                    # Avoid duplicates
                    if not any(s["id"] == skill_id for s in skills):
                        skills.append(
                            {
                                "id": skill_id,
                                "name": skill.get("name", skill_id),
                                "description": skill.get("description", ""),
                                "intent": skill.get("intent", ""),
                                "namespace": skill.get("namespace", "builtin"),
                                "version": skill.get("version", "1.0.0"),
                                "tags": skill.get("tags"),
                                "type": "prompt",
                                "source": "registry",
                            }
                        )
            except Exception as e:
                logger.debug(f"Failed to load registry skills: {e}")

        return skills

    def get_skill_info(self, skill_id: str) -> dict[str, Any] | None:
        """Get information about a skill.

        Args:
            skill_id: Skill identifier

        Returns:
            Skill information or None if not found
        """
        # Try filesystem first
        definition = self._loader.get_skill(skill_id)
        if definition:
            return {
                "id": definition.metadata.id,
                "name": definition.metadata.name,
                "description": definition.metadata.description,
                "intent": definition.metadata.intent,
                "namespace": definition.metadata.namespace,
                "version": definition.metadata.version,
                "author": definition.metadata.author,
                "tags": definition.metadata.tags,
                "type": definition.metadata.skill_type.value,
                "source": "filesystem",
                "source_file": str(definition.source_file) if definition.source_file else None,
            }

        # Try registry
        skill = self._config.get_skill_by_id(skill_id)
        if skill:
            return {
                "id": skill.get("id", ""),
                "name": skill.get("name", skill.get("id", "")),
                "description": skill.get("description", ""),
                "intent": skill.get("intent", ""),
                "namespace": skill.get("namespace", "builtin"),
                "version": skill.get("version", "1.0.0"),
                "author": skill.get("author", ""),
                "tags": skill.get("tags"),
                "type": "prompt",
                "source": "registry",
            }

        return None

    def search_skills(self, query: str) -> list[dict[str, Any]]:
        """Search for skills by query.

        Args:
            query: Search query

        Returns:
            List of matching skills
        """
        all_skills = self.list_skills()
        query_lower = query.lower()

        results = []
        for skill in all_skills:
            # Search in name, description, intent, tags
            searchable_text = " ".join(
                [
                    skill.get("name", ""),
                    skill.get("description", ""),
                    skill.get("intent", ""),
                    " ".join(skill.get("tags") or []),
                ]
            ).lower()

            if query_lower in searchable_text:
                results.append(skill)

        return results

    def get_skill_instance(self, skill_id: str) -> Skill | None:
        """Get an instantiated skill.

        Args:
            skill_id: Skill identifier

        Returns:
            Skill instance or None if not found
        """
        return self._loader.instantiate(skill_id)

    def reload_skills(self) -> int:
        """Reload all skills from disk.

        Returns:
            Number of skills discovered
        """
        self._loader.clear_cache()
        self._config.clear_cache()
        definitions = self._loader.discover_all(force_reload=True)
        return len(definitions)

    def get_namespaces(self) -> list[str]:
        """Get all available namespaces.

        Returns:
            List of namespace names
        """
        skills = self.list_skills()
        namespaces = {s.get("namespace", "builtin") for s in skills}
        return sorted(namespaces)

    def get_stats(self) -> dict[str, Any]:
        """Get skill statistics.

        Returns:
            Dictionary with statistics
        """
        skills = self.list_skills()

        by_namespace: dict[str, int] = {}
        by_type: dict[str, int] = {}

        for skill in skills:
            ns = skill.get("namespace", "builtin")
            by_namespace[ns] = by_namespace.get(ns, 0) + 1

            st = skill.get("type", "prompt")
            by_type[st] = by_type.get(st, 0) + 1

        return {
            "total_skills": len(skills),
            "by_namespace": by_namespace,
            "by_type": by_type,
            "namespaces": sorted(by_namespace.keys()),
        }
