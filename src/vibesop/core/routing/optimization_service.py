"""Optimization service for routing: preference boost, instinct boost, conflict resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from vibesop.core.exceptions import MatcherError

if TYPE_CHECKING:
    from collections.abc import Callable

    from vibesop.core.config import OptimizationConfig, RoutingConfig
    from vibesop.core.instinct import InstinctLearner
    from vibesop.core.matching import MatchResult, RoutingContext
    from vibesop.core.optimization import PreferenceBooster, SkillClusterIndex
    from vibesop.core.routing.conflict import ConflictResolver

logger = logging.getLogger(__name__)


class OptimizationService:
    """Apply preference boost, instinct boost, and conflict resolution to matcher results."""

    def __init__(
        self,
        config: RoutingConfig,
        optimization_config: OptimizationConfig,
        preference_booster: PreferenceBooster,
        cluster_index: SkillClusterIndex,
        conflict_resolver: ConflictResolver,
        get_instinct_learner: Callable[[], InstinctLearner],
    ) -> None:
        self._config = config
        self._optimization_config = optimization_config
        self._preference_booster = preference_booster
        self._cluster_index = cluster_index
        self._cluster_built = False
        self._conflict_resolver = conflict_resolver
        self._get_instinct_learner = get_instinct_learner

    def apply_optimizations(
        self,
        matches: list[MatchResult],
        query: str,
        context: RoutingContext | None = None,
    ) -> tuple[MatchResult, list[MatchResult]]:
        """Apply preference boost, instinct boost, and production conflict resolution."""
        if self._optimization_config.enabled and self._optimization_config.preference_boost.enabled:
            try:
                matches = self._preference_booster.boost(matches, query)
            except (OSError, ValueError, RuntimeError) as e:
                logger.debug(f"Preference boost failed, continuing without: {e}")

        # Apply instinct-based boosting
        matches = self.apply_instinct_boost(matches, query, context)

        if len(matches) <= 1:
            return matches[0], []

        return self.resolve_conflicts(matches, query)

    def resolve_conflicts(
        self, matches: list[MatchResult], query: str
    ) -> tuple[MatchResult, list[MatchResult]]:
        """Resolve conflicts using the production ConflictResolver framework."""
        try:
            resolution = self._conflict_resolver.resolve(
                matches,
                query,
                context={},
            )
        except (OSError, ValueError, RuntimeError, MatcherError) as e:
            logger.debug(f"Conflict resolution failed, using raw matches: {e}")
            return matches[0], matches[1 : self._config.max_candidates + 1]

        if resolution.primary:
            primary_match = next(
                (m for m in matches if getattr(m, "skill_id", str(m)) == resolution.primary),
                matches[0],
            )
            alternative_ids = set(resolution.alternatives)
            alternatives = [
                m
                for m in matches
                if getattr(m, "skill_id", str(m)) in alternative_ids
                and getattr(m, "skill_id", str(m)) != resolution.primary
            ][: self._config.max_candidates]
        else:
            primary_match = matches[0]
            alternatives = matches[1 : self._config.max_candidates + 1]

        return primary_match, alternatives

    def apply_instinct_boost(
        self,
        matches: list[MatchResult],
        query: str,
        context: RoutingContext | None,
    ) -> list[MatchResult]:
        """Boost matches based on learned instincts."""
        if not matches:
            return matches

        # Build augmented query from memory context
        search_query = query
        if context and context.recent_queries and (
            len(query) < 15
            or any(
                p in query.lower()
                for p in ("还是", "再", "继续", "也", "另外", "还有", "不行", "不对")
            )
        ):
            search_query = " ".join([*context.recent_queries[-2:], query])

        try:
            instincts = self._get_instinct_learner().find_matching(search_query, min_confidence=0.6)
        except (OSError, ValueError, RuntimeError) as e:
            logger.debug(f"Instinct lookup failed, continuing without boost: {e}")
            return matches

        if not instincts:
            return matches

        # Extract skill suggestions from instinct actions
        boost_map: dict[str, float] = {}
        for instinct in instincts:
            action = instinct.action.lower()
            # Match patterns like "suggest systematic-debugging skill" or "use gstack/review"
            for candidate in matches:
                sid = candidate.skill_id
                if sid.lower() in action or sid.replace("/", " ").lower() in action:
                    boost_map[sid] = max(boost_map.get(sid, 0.0), instinct.confidence * 0.15)

        if not boost_map:
            return matches

        boosted: list[MatchResult] = []
        for match_obj in matches:
            boost = boost_map.get(match_obj.skill_id, 0.0)
            boosted_match = match_obj.with_boost(boost, source="instinct") if boost > 0 else match_obj
            boosted.append(boosted_match)

        # Re-sort by boosted confidence
        boosted.sort(key=lambda m: m.confidence, reverse=True)
        return boosted

    def ensure_cluster_index(self, candidates: list[dict[str, Any]]) -> None:
        if (
            self._optimization_config.enabled
            and self._optimization_config.clustering.enabled
            and not self._cluster_built
            and len(candidates) >= self._optimization_config.clustering.min_skills_for_clustering
        ):
            self._cluster_index.build(candidates)
            self._cluster_built = True
