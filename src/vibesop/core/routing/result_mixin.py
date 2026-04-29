"""Router result building and post-match enrichment mixin.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Protocol, cast

from vibesop.core.matching import MatchResult, MatcherType
from vibesop.core.models import (
    DegradationLevel,
    LayerDetail,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)

logger = logging.getLogger(__name__)


class _ResultHost(Protocol):
    """Protocol defining the interface expected by RouterResultMixin."""

    _degradation_manager: Any
    _skill_recommender: Any | None
    _candidate_manager: Any
    _config: Any
    project_root: Path

    def _apply_optimizations(self, matches: list[Any], query: str, context: Any | None) -> tuple[Any | None, list[Any]]: ...
    def _record_routing_decision(self, query: str, match: SkillRoute, context: Any | None) -> None: ...
    def _save_session_state(self, result: RoutingResult, context: Any | None) -> None: ...


class RouterResultMixin:
    """Mixin providing result construction, enrichment, and fallback building.

    Intended for use with UnifiedRouter. Expects the host class to provide
    degradation manager, candidate manager, skill recommender, and config.
    """

    def _build_match_result(
        self,
        query: str,
        primary: SkillRoute,
        alternatives: list[SkillRoute],
        routing_path: list[RoutingLayer],
        layer_details: list[LayerDetail],
        start_time: float,
        deprecated_warnings: list[str] | None,
        conversation: Any,
        original_query: str,
        context: Any = None,
    ) -> RoutingResult:
        """Build result for a successful match, applying optimizations for non-matcher layers."""
        host = cast(_ResultHost, self)

        # Early-layer matches (EXPLICIT/SCENARIO/AI_TRIAGE) bypass the
        # MatcherPipeline where OptimizationService normally runs.
        # Apply optimizations here so session stickiness, habit boost,
        # quality boost, and project context are consistent across
        # all layers.
        matcher_layers = {
            RoutingLayer.KEYWORD,
            RoutingLayer.TFIDF,
            RoutingLayer.EMBEDDING,
            RoutingLayer.LEVENSHTEIN,
        }
        if primary.layer not in matcher_layers:
            match_result = MatchResult(
                skill_id=primary.skill_id,
                confidence=primary.confidence,
                score_breakdown=primary.metadata.get("score_breakdown", {}),
                matcher_type=(
                    MatcherType.AI_TRIAGE
                    if primary.layer == RoutingLayer.AI_TRIAGE
                    else MatcherType.CUSTOM
                ),
                matched_keywords=[],
                matched_patterns=[],
                semantic_score=None,
                metadata=primary.metadata,
            )
            optimized_primary, _ = host._apply_optimizations([match_result], query, context)
            if optimized_primary is None:
                optimized_primary = match_result
            primary = SkillRoute(
                skill_id=optimized_primary.skill_id,
                confidence=optimized_primary.confidence,
                layer=primary.layer,
                source=primary.source,
                description=primary.description,
                metadata=optimized_primary.metadata,
            )

        # Apply degradation evaluation (skip for explicit/user-specified layers)
        if primary.layer not in (RoutingLayer.EXPLICIT, RoutingLayer.CUSTOM):
            degradation_level, degraded_primary = host._degradation_manager.evaluate(primary)
            if degradation_level == DegradationLevel.FALLBACK:
                primary = cast("SkillRoute | None", None)
            elif degradation_level == DegradationLevel.DEGRADE:
                primary = cast("SkillRoute | None", degraded_primary)
            if primary:
                primary.metadata["degradation_level"] = degradation_level.value
            else:
                return self._build_fallback_result(
                    query=original_query,
                    candidates=[],
                    routing_path=routing_path,
                    layer_details=layer_details,
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                )

        if primary is None:
            return self._build_fallback_result(
                query=original_query,
                candidates=[],
                routing_path=routing_path,
                layer_details=layer_details,
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        host._record_routing_decision(query, primary, None)

        # Enrich alternatives with SkillRecommender suggestions
        enriched_alternatives = list(alternatives) if alternatives else []
        try:
            if host._skill_recommender is None:
                from vibesop.integrations.skill_recommender import SkillRecommender

                host._skill_recommender = SkillRecommender()
            recommender = host._skill_recommender
            all_candidates = host._candidate_manager.get_cached_candidates()
            existing_ids = {primary.skill_id} | {a.skill_id for a in enriched_alternatives}
            recs = recommender.recommend(query, all_candidates, top_k=5)
            for rec in recs:
                if rec.skill_id not in existing_ids and rec.score >= 0.2:
                    enriched_alternatives.append(
                        SkillRoute(
                            skill_id=rec.skill_id,
                            confidence=rec.score,
                            layer=RoutingLayer.KEYWORD,
                            source=rec.namespace,
                            description=rec.intent,
                            metadata={"recommended": True, "reason": rec.reason},
                        )
                    )
        except (ImportError, KeyError, ValueError):
            pass

        # Update SkillConfig.usage_stats for stale-skill detection
        host._candidate_manager.record_usage(primary.skill_id, was_successful=True)

        # Ensure alternatives are populated from layer_details even without --explain
        if not alternatives:
            alternatives = self._collect_alternatives_from_details(layer_details)

        # Merge enriched recommendations (SkillRecommender) into alternatives
        existing_ids = {primary.skill_id} | {a.skill_id for a in alternatives}
        for rec in enriched_alternatives:
            if rec.skill_id not in existing_ids:
                alternatives.append(rec)

        # Proactive discovery: suggest unused skills matching current query domain
        try:
            if host._skill_recommender is None:
                from vibesop.integrations.skill_recommender import SkillRecommender

                host._skill_recommender = SkillRecommender()
            recommender = host._skill_recommender
            all_candidates = host._candidate_manager.get_cached_candidates()
            used_ids = existing_ids.copy()
            discoveries = recommender.discover(
                query, all_candidates, used_skill_ids=used_ids, top_k=3
            )
            for d in discoveries:
                if d.skill_id not in existing_ids and d.score >= 0.15:
                    alternatives.append(
                        SkillRoute(
                            skill_id=d.skill_id,
                            confidence=d.score,
                            layer=RoutingLayer.KEYWORD,
                            source=d.namespace,
                            description=d.intent,
                            metadata={"discovery": True, "reason": d.reason},
                        )
                    )
        except (ImportError, KeyError, ValueError):
            pass

        result = self._build_result(
            query=query,
            primary=primary,
            alternatives=alternatives,
            routing_path=routing_path,
            layer_details=layer_details,
            start_time=start_time,
            deprecated_warnings=deprecated_warnings if deprecated_warnings else None,
        )
        # Persist session state with the selected skill
        host._save_session_state(result, None)
        # Save conversation turn for multi-turn support
        if conversation:
            conversation.add_turn(
                original_query,
                skill_id=result.primary.skill_id if result.primary else None,
            )
        return result

    def _build_result(
        self,
        query: str,
        primary: SkillRoute,
        alternatives: list[SkillRoute],
        routing_path: list[RoutingLayer],
        layer_details: list[LayerDetail],
        start_time: float,
        deprecated_warnings: list[str] | None = None,
    ) -> RoutingResult:
        duration_ms = (time.perf_counter() - start_time) * 1000
        if deprecated_warnings and primary:
            primary.metadata["deprecated_warnings"] = deprecated_warnings

        from vibesop.core.routing.perf_monitor import get_perf_monitor

        if primary:
            get_perf_monitor().record(duration_ms, primary.layer.value)

        return RoutingResult(
            primary=primary,
            alternatives=alternatives,
            routing_path=routing_path,
            layer_details=layer_details,
            query=query,
            duration_ms=duration_ms,
        )

    def _build_fallback_result(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        routing_path: list[RoutingLayer],
        layer_details: list[LayerDetail],
        duration_ms: float,
    ) -> RoutingResult:
        """Build a fallback result when no skill matches.

        Returns a FALLBACK_LLM route with nearest candidates as alternatives.
        """
        host = cast(_ResultHost, self)
        # Find nearest candidates (even if below threshold) for suggestions
        nearest: list[SkillRoute] = []
        try:
            from vibesop.core.routing import _pipeline

            nearest_primary, nearest_alts, _ = _pipeline.run_matcher_pipeline(
                self, query, candidates, None, collect_rejected=False
            )
            if nearest_primary:
                nearest = [nearest_primary, *nearest_alts]
        except (RuntimeError, ValueError):
            logger.debug("Failed to get nearest candidates for fallback")

        fallback_layer_detail = LayerDetail(
            layer=RoutingLayer.FALLBACK_LLM,
            matched=True,
            reason="No confident skill match; falling back to raw LLM",
        )

        return RoutingResult(
            primary=SkillRoute(
                skill_id="fallback-llm",
                confidence=1.0,
                layer=RoutingLayer.FALLBACK_LLM,
                source="builtin",
                metadata={
                    "reason": "No skill matched query",
                    "fallback_mode": host._config.fallback_mode,
                    "candidate_count": len(candidates),
                },
            ),
            alternatives=nearest,
            routing_path=[*routing_path, RoutingLayer.FALLBACK_LLM],
            layer_details=[*layer_details, fallback_layer_detail],
            query=query,
            duration_ms=duration_ms,
        )

    def _collect_alternatives_from_details(
        self,
        layer_details: list[LayerDetail],
    ) -> list[SkillRoute]:
        """Extract rejected candidates from layer_details as alternative routes.

        Collects candidates that were close but didn't meet the confidence
        threshold, ordered by confidence descending. This ensures alternatives
        are available even when --explain/--verbose is not used.
        """
        best_confidence: dict[str, float] = {}
        best_layer: dict[str, RoutingLayer] = {}
        best_reason: dict[str, str | None] = {}

        for detail in layer_details:
            for rejected in detail.rejected_candidates:
                current = best_confidence.get(rejected.skill_id, -1.0)
                if rejected.confidence > current:
                    best_confidence[rejected.skill_id] = rejected.confidence
                    best_layer[rejected.skill_id] = rejected.layer
                    best_reason[rejected.skill_id] = rejected.reason

        alternatives: list[SkillRoute] = []
        for skill_id, confidence in best_confidence.items():
            alternatives.append(
                SkillRoute(
                    skill_id=skill_id,
                    confidence=confidence,
                    layer=best_layer[skill_id],
                    source="routing_rejected",
                    metadata={"reason": best_reason[skill_id]},
                )
            )

        # Sort by confidence descending
        alternatives.sort(key=lambda x: x.confidence, reverse=True)
        return alternatives
