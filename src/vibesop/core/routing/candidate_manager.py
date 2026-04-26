"""Candidate management — skill discovery, filtering, and caching.

Extracted from UnifiedRouter to reduce God Object size.
"""

from __future__ import annotations

import importlib
import logging
import re
import threading
from pathlib import Path
from typing import Any

from vibesop.core.skills.lifecycle import SkillLifecycle, SkillLifecycleManager

logger = logging.getLogger(__name__)


class CandidateManager:
    """Manages skill candidate discovery, filtering, and caching.

    Handles:
    - Skill discovery from multiple search paths
    - Candidate caching with invalidation
    - Automatic keyword extraction from skill names
    - Skill source determination from namespace
    """

    def __init__(self, project_root: Path | str):
        self.project_root = Path(project_root).resolve()
        self._skill_loader: Any = None
        self._candidates_cache: list[dict[str, Any]] | None = None
        self._cache_lock = threading.Lock()

    def get_candidates(self) -> list[dict[str, Any]]:
        """Discover and return all skill candidates."""
        if self._skill_loader is None:
            import vibesop

            builtin_skills_path = (
                Path(vibesop.__file__).parent.parent.parent / "core" / "skills"
            )
            search_paths = [
                self.project_root / ".vibe" / "skills",
                Path.home() / ".config" / "skills",
            ]
            if builtin_skills_path.exists() and builtin_skills_path not in search_paths:
                search_paths.insert(0, builtin_skills_path)
            from vibesop.core.skills import SkillLoader

            self._skill_loader = SkillLoader(
                project_root=self.project_root,
                search_paths=search_paths,
            )

        definitions = self._skill_loader.discover_all()
        from vibesop.core.optimization.cold_start import get_cold_start_strategy
        from vibesop.core.skills.config_manager import SkillConfigManager

        cold_start = get_cold_start_strategy(self.project_root)
        p0_skills = set(cold_start.get_p0_skills())
        candidates: list[dict[str, Any]] = []
        for _skill_id, definition in definitions.items():
            metadata = definition.metadata
            tags = metadata.tags or []
            if not tags:
                tags = self._extract_name_keywords(metadata.name)

            skill_config = SkillConfigManager.get_skill_config(_skill_id)
            enabled = skill_config.enabled if skill_config else True
            scope = skill_config.scope if skill_config else "project"
            lifecycle = skill_config.lifecycle if skill_config else "active"

            candidates.append(
                {
                    "id": metadata.id,
                    "name": metadata.name,
                    "description": metadata.description,
                    "intent": metadata.intent,
                    "keywords": tags,
                    "triggers": [metadata.trigger_when] if metadata.trigger_when else [],
                    "namespace": metadata.namespace,
                    "source": self._get_skill_source(metadata.id, metadata.namespace),
                    "priority": "P0" if metadata.id in p0_skills else "P2",
                    "enabled": enabled,
                    "scope": scope,
                    "lifecycle": lifecycle,
                    "source_file": str(definition.source_file) if definition.source_file else None,
                }
            )
        return candidates

    def get_cached_candidates(self) -> list[dict[str, Any]]:
        """Return cached candidates, loading if necessary."""
        if self._candidates_cache is not None:
            return self._candidates_cache
        with self._cache_lock:
            if self._candidates_cache is None:
                self._candidates_cache = self.get_candidates()
            return self._candidates_cache

    def reload(self) -> int:
        """Invalidate cache and reload."""
        self._candidates_cache = None
        return len(self.get_cached_candidates())

    def invalidate(self) -> None:
        """Invalidate candidate cache without reloading."""
        self._candidates_cache = None

    @staticmethod
    def _get_skill_source(_skill_id: str, namespace: str) -> str:
        """Determine skill source based on namespace."""
        if namespace == "project":
            return "project"
        if namespace == "builtin":
            return "builtin"
        return "external"

    @staticmethod
    def _extract_name_keywords(name: str) -> list[str]:
        """Extract searchable keywords from a skill name."""
        parts = re.split(r"[-_/]", name)
        keywords: list[str] = []
        for p in parts:
            stripped = p.strip()
            if len(stripped) > 1:
                keywords.append(stripped)
        return keywords

    def filter_routable(
        self, candidates: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Filter candidates by enablement, scope, and lifecycle state.

        Returns:
            (filtered_candidates, deprecated_warnings)
        """
        filtered: list[dict[str, Any]] = []
        deprecated_warnings: list[str] = []

        for c in candidates:
            if not c.get("enabled", True):
                continue
            lifecycle_str = c.get("lifecycle", "active")
            try:
                lifecycle = SkillLifecycle(lifecycle_str)
            except ValueError:
                lifecycle = SkillLifecycle.ACTIVE
            if not SkillLifecycleManager.is_routable(lifecycle):
                continue
            if lifecycle == SkillLifecycle.DEPRECATED:
                deprecated_warnings.append(str(c.get("id", "")))
            scope = c.get("scope", "project")
            if scope == "project":
                source_file = c.get("source_file")
                if source_file:
                    try:
                        Path(source_file).resolve().relative_to(
                            self.project_root.resolve()
                        )
                    except ValueError:
                        continue
            filtered.append(c)

        return filtered, deprecated_warnings
