"""Optimization service for routing: preference boost, instinct boost, conflict resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from vibesop.core.exceptions import MatcherError
from vibesop.core.matching import MatchResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from vibesop.core.config import OptimizationConfig, RoutingConfig
    from vibesop.core.instinct import InstinctLearner
    from vibesop.core.matching import RoutingContext
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
        self._evaluator = None

    def apply_optimizations(
        self,
        matches: list[MatchResult],
        query: str,
        context: RoutingContext | None = None,
    ) -> tuple[MatchResult, list[MatchResult]]:
        """Apply preference boost, instinct boost, session stickiness, and production conflict resolution."""
        if self._optimization_config.enabled and self._optimization_config.preference_boost.enabled:
            try:
                matches = self._preference_booster.boost(matches, query)
            except (OSError, ValueError, RuntimeError) as e:
                logger.debug(f"Preference boost failed, continuing without: {e}")

        # Apply instinct-based boosting
        matches = self.apply_instinct_boost(matches, query, context)

        # Apply session stickiness: slight boost to current skill for continuity
        matches = self._apply_session_stickiness(matches, context)

        # Apply habit boost: favor skills the user consistently chooses
        matches = self._apply_habit_boost(matches, context)

        # Apply quality boost: favor high-grade skills based on evaluator data
        matches = self._apply_quality_boost(matches)

        # Apply project context boost: favor skills matching detected project type/tech stack
        matches = self._apply_project_context_boost(matches, context)

        if not matches:
            raise ValueError("apply_optimizations received empty matches list")
        if len(matches) == 1:
            return matches[0], []

        return self.resolve_conflicts(matches, query)

    def _apply_session_stickiness(
        self,
        matches: list[MatchResult],
        context: RoutingContext | None,
    ) -> list[MatchResult]:
        """Slight confidence boost to current skill for multi-turn continuity.

        This provides continuity across CLI invocations by gently favoring
        the skill selected in the previous turn, unless the new query clearly
        indicates a different intent.
        """
        if not context or not context.current_skill:
            return matches

        current_skill = context.current_skill
        stickiness_boost = getattr(self._config, "session_stickiness_boost", 0.03)

        if stickiness_boost <= 0:
            return matches

        boosted: list[MatchResult] = []
        for m in matches:
            if m.skill_id == current_skill:
                # Create a new MatchResult with boosted confidence
                boosted_match = MatchResult(
                    skill_id=m.skill_id,
                    confidence=min(m.confidence + stickiness_boost, 1.0),
                    score_breakdown={**m.score_breakdown, "session_stickiness": stickiness_boost},
                    matcher_type=m.matcher_type,
                    matched_keywords=m.matched_keywords,
                    matched_patterns=m.matched_patterns,
                    semantic_score=m.semantic_score,
                    metadata={**m.metadata, "session_boost": True},
                )
                boosted.append(boosted_match)
            else:
                boosted.append(m)

        # Re-sort by confidence after boosting
        boosted.sort(key=lambda x: x.confidence, reverse=True)
        return boosted

    def _apply_habit_boost(
        self,
        matches: list[MatchResult],
        context: RoutingContext | None,
    ) -> list[MatchResult]:
        """Boost skills that the user consistently chooses for similar queries.

        Habit patterns are learned from session route history.
        """
        if not context or not context.habit_boosts:
            return matches

        boosted: list[MatchResult] = []
        for m in matches:
            boost = context.habit_boosts.get(m.skill_id, 0.0)
            if boost > 0.0:
                boosted_match = MatchResult(
                    skill_id=m.skill_id,
                    confidence=min(m.confidence + boost, 1.0),
                    score_breakdown={**m.score_breakdown, "habit_boost": boost},
                    matcher_type=m.matcher_type,
                    matched_keywords=m.matched_keywords,
                    matched_patterns=m.matched_patterns,
                    semantic_score=m.semantic_score,
                    metadata={**m.metadata, "habit_boost": True},
                )
                boosted.append(boosted_match)
            else:
                boosted.append(m)

        boosted.sort(key=lambda x: x.confidence, reverse=True)
        return boosted

    def _apply_quality_boost(
        self,
        matches: list[MatchResult],
    ) -> list[MatchResult]:
        """Boost or demote skills based on evaluator quality scores.

        Grade A skills receive a small boost; Grade F skills are demoted.
        Only skills with sufficient usage history (>=3 routes) are adjusted
        to avoid penalizing new skills.
        """
        if not matches:
            return matches

        try:
            from vibesop.core.skills.evaluator import RoutingEvaluator
        except ImportError:
            return matches

        if self._evaluator is None:
            self._evaluator = RoutingEvaluator()
        evaluator = self._evaluator
        grade_adjustment = {"A": 0.05, "B": 0.02, "C": 0.0, "D": -0.02, "F": -0.05}

        boosted: list[MatchResult] = []
        for m in matches:
            try:
                evaluation = evaluator.evaluate_skill(m.skill_id)
            except (OSError, ValueError, RuntimeError):
                evaluation = None

            if evaluation and evaluation.total_routes >= 3:
                adjustment = grade_adjustment.get(evaluation.grade, 0.0)
                if adjustment != 0.0:
                    boosted_match = MatchResult(
                        skill_id=m.skill_id,
                        confidence=min(max(m.confidence + adjustment, 0.0), 1.0),
                        score_breakdown={
                            **m.score_breakdown,
                            "quality_adjustment": adjustment,
                        },
                        matcher_type=m.matcher_type,
                        matched_keywords=m.matched_keywords,
                        matched_patterns=m.matched_patterns,
                        semantic_score=m.semantic_score,
                        metadata={
                            **m.metadata,
                            "quality_boost": True,
                            "grade": evaluation.grade,
                        },
                    )
                    boosted.append(boosted_match)
                else:
                    boosted.append(m)
            else:
                boosted.append(m)

        # Re-sort by confidence after quality adjustments
        boosted.sort(key=lambda x: x.confidence, reverse=True)
        return boosted

    def _apply_project_context_boost(
        self,
        matches: list[MatchResult],
        context: RoutingContext | None,
    ) -> list[MatchResult]:
        """Boost skills that match the detected project type or tech stack.

        Provides context-aware routing by slightly favoring skills
        that are relevant to the user's project technology.
        """
        if not context or not context.project_type:
            return matches

        project_type = context.project_type
        tech_stack = context.recent_files or []
        boosted: list[MatchResult] = []

        for m in matches:
            boost = 0.0
            skill_text = " ".join(m.matched_keywords or []).lower()

            # Boost if skill keywords mention the project type
            if project_type.lower() in skill_text:
                boost += 0.04

            # Boost if skill keywords mention any detected tech stack
            for tech in tech_stack:
                if tech.lower() in skill_text:
                    boost += 0.02

            if boost > 0.0:
                boosted_match = MatchResult(
                    skill_id=m.skill_id,
                    confidence=min(m.confidence + boost, 1.0),
                    score_breakdown={
                        **m.score_breakdown,
                        "project_context": boost,
                    },
                    matcher_type=m.matcher_type,
                    matched_keywords=m.matched_keywords,
                    matched_patterns=m.matched_patterns,
                    semantic_score=m.semantic_score,
                    metadata={
                        **m.metadata,
                        "project_type": project_type,
                        "project_boost": True,
                    },
                )
                boosted.append(boosted_match)
            else:
                boosted.append(m)

        # Re-sort by confidence after project context adjustments
        boosted.sort(key=lambda x: x.confidence, reverse=True)
        return boosted

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
