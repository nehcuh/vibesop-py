"""Router candidate management mixin.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from vibesop.core.optimization import CandidatePrefilter
from vibesop.core.optimization.cold_start import get_cold_start_strategy
from vibesop.core.skills import SkillLoader
from vibesop.core.skills.config_manager import SkillConfigManager

logger = logging.getLogger(__name__)


class RouterCandidateMixin:
    """Mixin providing candidate discovery, caching, and warmup methods.

    Intended for use with UnifiedRouter. Expects the following attributes
    on the host class:
        - _skill_loader: SkillLoader | None
        - project_root: Path
        - _candidates_cache: list[dict[str, Any]] | None
        - _cache_lock: threading.Lock
        - _prefilter: CandidatePrefilter
        - _cluster_index: SkillClusterIndex
        - _matcher_pipeline: MatcherPipeline
        - _matchers: list[tuple[RoutingLayer, IMatcher]]
        - _matchers_warmed: bool
    """

    def _get_candidates(self, _query: str = "") -> list[dict[str, Any]]:
        import vibesop

        if getattr(self, "_skill_loader", None) is None:
            # Always include VibeSOP's built-in skills regardless of project root
            builtin_skills_path = Path(vibesop.__file__).parent.parent.parent / "core" / "skills"
            search_paths = [
                self.project_root / ".vibe" / "skills",
                Path.home() / ".config" / "skills",
            ]
            if builtin_skills_path.exists() and builtin_skills_path not in search_paths:
                search_paths.insert(0, builtin_skills_path)
            self._skill_loader = SkillLoader(
                project_root=self.project_root,
                search_paths=search_paths,
            )

        definitions = self._skill_loader.discover_all()
        cold_start = get_cold_start_strategy(self.project_root)
        p0_skills = set(cold_start.get_p0_skills())
        candidates: list[dict[str, Any]] = []
        for _skill_id, definition in definitions.items():
            metadata = definition.metadata
            tags = metadata.tags or []
            # Auto-generate keywords from skill name when tags are empty
            if not tags:
                tags = _extract_name_keywords(metadata.name)

            # Load skill config for enablement/scope metadata
            skill_config = SkillConfigManager.get_skill_config(_skill_id)
            enabled = skill_config.enabled if skill_config else True
            scope = skill_config.scope if skill_config else "project"

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
                    "source_file": str(definition.source_file) if definition.source_file else None,
                }
            )
        return candidates

    def _get_cached_candidates(self) -> list[dict[str, Any]]:
        if self._candidates_cache is not None:
            return self._candidates_cache
        with self._cache_lock:
            if self._candidates_cache is None:
                self._candidates_cache = self._get_candidates()
                # Initialize prefilter with dynamic namespace discovery
                # This eliminates hardcoded NAMESPACE_KEYWORDS limitation
                self._prefilter = CandidatePrefilter.from_candidates(
                    self._candidates_cache,
                    cluster_index=self._cluster_index,
                )
                # Sync the updated prefilter into the matcher pipeline so
                # that apply_prefilter uses the dynamically discovered namespaces.
                self._matcher_pipeline.set_prefilter(self._prefilter)
                # Warm up matchers to prevent cold-start latency
                # This loads EmbeddingMatcher model during initialization
                self._warm_up_matchers(self._candidates_cache)
            return self._candidates_cache

    def _warm_up_matchers(self, candidates: list[dict[str, Any]]) -> None:
        """Warm up matchers by initializing lazy-loaded components.

        This prevents cold-start latency on the first route() call by
        pre-loading heavy components like the EmbeddingMatcher model.
        """
        if self._matchers_warmed:
            return

        try:
            for _layer, matcher in self._matchers:
                try:
                    matcher.warm_up(candidates)
                except (OSError, RuntimeError, ValueError, ImportError) as e:
                    logger.warning(
                        "Matcher %s warm-up failed: %s",
                        type(matcher).__name__,
                        e,
                    )
        finally:
            self._matchers_warmed = True

    def reload_candidates(self) -> int:
        self._candidates_cache = None
        return len(self._get_cached_candidates())

    def _get_skill_source(self, _skill_id: str, namespace: str) -> str:
        """Determine skill source based on namespace.

        Project skills > external skills > built-in fallback.
        No hardcoded pack names — any unknown namespace is external.
        """
        if namespace == "project":
            return "project"
        if namespace == "builtin":
            return "builtin"
        return "external"


def _extract_name_keywords(name: str) -> list[str]:
    """Extract searchable keywords from a skill name.

    Splits on common delimiters (hyphen, underscore, slash) and
    filters out very short tokens.
    """
    import re

    # Split on delimiters
    parts = re.split(r"[-_/]", name)
    keywords: list[str] = []
    for p in parts:
        stripped = p.strip()
        if len(stripped) > 1:
            keywords.append(stripped)
    return keywords
