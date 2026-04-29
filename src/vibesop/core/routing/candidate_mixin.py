"""Router candidate and matcher lifecycle management mixin.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, cast

from vibesop.core.optimization import CandidatePrefilter, SkillClusterIndex

logger = logging.getLogger(__name__)


class _CandidateHost(Protocol):
    """Protocol defining the interface expected by RouterCandidateMixin."""

    _candidate_manager: Any
    _matchers_warmed: bool
    _prefilter: CandidatePrefilter
    _cluster_index: SkillClusterIndex
    _matcher_pipeline: Any
    _matchers: list[tuple[Any, Any]]
    _project_analyzer: Any | None


class RouterCandidateMixin:
    """Mixin providing candidate retrieval, caching, and matcher lifecycle.

    Intended for use with UnifiedRouter. Expects the following attributes
    on the host class:
        - _candidate_manager: CandidateManager
        - _matchers_warmed: bool
        - _prefilter: CandidatePrefilter
        - _cluster_index: SkillClusterIndex
        - _matcher_pipeline: MatcherPipeline
        - _matchers: list[tuple[RoutingLayer, IMatcher]]
        - _project_analyzer: ProjectAnalyzer | None
    """

    def _get_cached_candidates(self) -> list[dict[str, Any]]:
        """Get cached candidates, initializing prefilter and warming matchers on first call."""
        host = cast(_CandidateHost, self)
        candidates = host._candidate_manager.get_cached_candidates()
        if not host._matchers_warmed:
            host._prefilter = CandidatePrefilter.from_candidates(
                candidates,
                cluster_index=host._cluster_index,
            )
            host._matcher_pipeline.set_prefilter(host._prefilter)
            self._warm_up_matchers(candidates)
        return candidates

    def _warm_up_matchers(self, candidates: list[dict[str, Any]]) -> None:
        """Warm up matchers by initializing lazy-loaded components."""
        host = cast(_CandidateHost, self)
        if host._matchers_warmed:
            return
        try:
            for _layer, matcher in host._matchers:
                try:
                    matcher.warm_up(candidates)
                except (OSError, RuntimeError, ValueError, ImportError) as e:
                    logger.warning(
                        "Matcher %s warm-up failed: %s",
                        type(matcher).__name__,
                        e,
                    )
        finally:
            host._matchers_warmed = True

    def reload_candidates(self) -> int:
        host = cast(_CandidateHost, self)
        return host._candidate_manager.reload()

    def invalidate_project_cache(self) -> None:
        """Invalidate cached project analysis."""
        host = cast(_CandidateHost, self)
        host._project_analyzer = None

    def _get_skill_source(self, _skill_id: str, namespace: str) -> str:
        """Determine skill source based on namespace."""
        if namespace == "project":
            return "project"
        if namespace == "builtin":
            return "builtin"
        return "external"

    def get_candidates(self, _query: str = "") -> list[dict[str, Any]]:
        host = cast(_CandidateHost, self)
        return host._candidate_manager.get_candidates()

    def _get_candidates(self, _query: str = "") -> list[dict[str, Any]]:
        """Backward-compatible alias for get_candidates."""
        return self.get_candidates(_query)
