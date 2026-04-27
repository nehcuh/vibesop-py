"""Pipeline execution functions for UnifiedRouter.

Extracted from matcher_mixin.py, matcher_pipeline.py, optimization_mixin.py,
and optimization_service.py. Provides standalone functions for matcher pipeline
and optimization logic.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from vibesop.core.exceptions import MatcherError
from vibesop.core.matching import RoutingContext
from vibesop.core.models import LayerDetail, RoutingLayer, SkillRoute
from vibesop.core.routing._protocols import RoutingCore

logger = logging.getLogger(__name__)


def run_matcher_pipeline(
    router: RoutingCore,
    query: str,
    candidates: list[dict[str, Any]],
    context: RoutingContext | None,
    collect_rejected: bool = False,
) -> tuple[SkillRoute | None, list[SkillRoute], LayerDetail]:
    """Run the matcher pipeline and return (primary, alternatives, layer_detail).

    Returns None primary if no confident match found.
    """
    matcher_start = time.perf_counter()
    pipeline = router._matcher_pipeline
    config = router._config

    filtered = pipeline.apply_prefilter(query, candidates)
    router._optimization_service.ensure_cluster_index(filtered)

    # Build skill_id -> description lookup
    desc_map: dict[str, str] = {
        str(c.get("id", "")): str(c.get("description", ""))
        for c in filtered
    }

    # Aggregate scores across all matchers
    best_scores: dict[str, tuple[float, RoutingLayer, dict[str, Any]]] = {}
    all_matches: list[Any] = []

    for layer, matcher in router._matchers:
        if layer == RoutingLayer.EMBEDDING and not config.enable_embedding:
            continue

        try:
            matches = matcher.match(
                query,
                filtered,
                context,
                top_k=config.max_candidates + 2,
            )
            for m in matches:
                sid = m.skill_id
                existing = best_scores.get(sid)
                if existing is None or m.confidence > existing[0]:
                    best_scores[sid] = (m.confidence, layer, m.metadata)
                all_matches.append(m)
        except (OSError, ValueError, KeyError, MatcherError) as e:
            logger.debug(f"Matcher {type(matcher).__name__} failed: {e}, trying next matcher")
            continue

    matcher_duration_ms = (time.perf_counter() - matcher_start) * 1000

    if not best_scores:
        return None, [], LayerDetail(
            layer=RoutingLayer.LEVENSHTEIN,
            matched=False,
            reason="No matcher produced a confident match",
            duration_ms=matcher_duration_ms,
        )

    # Deduplicate all_matches keeping highest confidence per skill
    seen: dict[str, Any] = {}
    for m in all_matches:
        sid = m.skill_id
        if sid not in seen or m.confidence > seen[sid].confidence:
            seen[sid] = m
    merged_matches = sorted(seen.values(), key=lambda x: x.confidence, reverse=True)

    if not merged_matches or merged_matches[0].confidence < config.min_confidence:
        return None, [], LayerDetail(
            layer=RoutingLayer.LEVENSHTEIN,
            matched=False,
            reason="No matcher produced a confident match",
            duration_ms=matcher_duration_ms,
        )

    primary_match, alternatives = router._optimization_service.apply_optimizations(
        merged_matches, query, context
    )

    # Collect rejected candidates
    rejected_candidates: list[dict[str, Any]] = []
    if collect_rejected and filtered:
        threshold = config.min_confidence
        near_miss_threshold = threshold * 0.5
        matched_ids = {m.skill_id for m in merged_matches}
        if router._matchers:
            first_layer, first_matcher = router._matchers[0]
            for c in filtered:
                sid = str(c.get("id", ""))
                if sid in matched_ids or not sid:
                    continue
                try:
                    score = first_matcher.score(query, c, context)
                    if near_miss_threshold <= score < threshold:
                        rejected_candidates.append({
                            "skill_id": sid,
                            "confidence": score,
                            "layer": first_layer,
                            "reason": f"below threshold ({threshold:.2f})",
                        })
                except (TypeError, ValueError):
                    pass
            rejected_candidates.sort(key=lambda x: x["confidence"], reverse=True)
            rejected_candidates = rejected_candidates[:5]

    primary_namespace = str(primary_match.metadata.get("namespace", "builtin"))
    winning_layer = best_scores.get(primary_match.skill_id, (0.0, RoutingLayer.KEYWORD, {}))[1]

    primary = SkillRoute(
        skill_id=primary_match.skill_id,
        confidence=primary_match.confidence,
        layer=winning_layer,
        source=router._get_skill_source(primary_match.skill_id, primary_namespace),
        description=desc_map.get(primary_match.skill_id, ""),
        metadata=primary_match.metadata,
    )

    alt_routes = [
        SkillRoute(
            skill_id=m.skill_id,
            confidence=m.confidence,
            layer=best_scores.get(m.skill_id, (0.0, RoutingLayer.KEYWORD, {}))[1],
            source=router._get_skill_source(
                m.skill_id, str(m.metadata.get("namespace", "builtin"))
            ),
            description=desc_map.get(m.skill_id, ""),
            metadata=m.metadata,
        )
        for m in alternatives
    ]

    from vibesop.core.models import RejectedCandidate

    rejected_routes = [
        RejectedCandidate(
            skill_id=rc["skill_id"],
            confidence=rc["confidence"],
            layer=rc["layer"],
            reason=rc.get("reason", ""),
        )
        for rc in rejected_candidates
    ]

    layer_detail = LayerDetail(
        layer=winning_layer,
        matched=True,
        reason=f"Matcher selected '{primary_match.skill_id}' (confidence: {primary_match.confidence:.0%})",
        duration_ms=matcher_duration_ms,
        rejected_candidates=rejected_routes,
        diagnostics={"rejected_candidates": rejected_candidates} if rejected_candidates else {},
    )

    return primary, alt_routes, layer_detail


def apply_optimizations(
    router: RoutingCore,
    matches: list[Any],
    query: str,
    context: RoutingContext | None = None,
) -> tuple[Any, list[Any]]:
    """Apply optimizations to matches. Thin wrapper around OptimizationService."""
    return router._optimization_service.apply_optimizations(matches, query, context)
