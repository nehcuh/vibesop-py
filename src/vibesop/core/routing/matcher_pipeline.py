"""Matcher pipeline for routing layers 3-6 (keyword, tfidf, embedding, levenshtein)."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from vibesop.core.exceptions import MatcherError
from vibesop.core.models import RoutingLayer, SkillRoute
from vibesop.core.routing.layers import LayerResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from vibesop.core.config import OptimizationConfig, RoutingConfig
    from vibesop.core.matching import IMatcher, RoutingContext
    from vibesop.core.optimization import CandidatePrefilter
    from vibesop.core.routing.optimization_service import OptimizationService

logger = logging.getLogger(__name__)

# Queries matching this are considered skill/tool-management intents — only
# then may management-only (slash-*) skills compete in matcher layers.
_MANAGEMENT_INTENT_RE = re.compile(r"技能|skills?\b|vibe", re.IGNORECASE)


def _metadata_with_source(
    metadata: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    skill_id: str,
) -> dict[str, Any]:
    meta = dict(metadata or {})
    if meta.get("source_file"):
        return meta
    for c in candidates:
        if c.get("id") == skill_id and c.get("source_file"):
            meta["source_file"] = str(c["source_file"])
            break
    return meta


def filter_management_candidates(
    query: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Exclude management-only skills (slash-*) unless the query shows
    tool-management intent.

    Management skills (slash-route, slash-help, …) over-match everyday
    queries on superficial keyword overlap (e.g. "router.py" pulling in
    slash-route for a bug-fix request). They should only compete when the
    user is actually talking about skills/the tool itself. The EXPLICIT
    layer ("/route", "/help") must not pass candidates through this filter.
    """
    if _MANAGEMENT_INTENT_RE.search(query):
        return candidates
    # Very short queries ("help", "收工了") are treated as direct tool
    # commands — management skills stay eligible. (CJK single-phrase
    # queries have no spaces and also count as short.)
    if len(query.split()) <= 2:
        return candidates
    kept = [c for c in candidates if not c.get("management_only")]
    return kept or candidates


class MatcherPipeline:
    """Execute matcher layers and apply optimizations."""

    def __init__(
        self,
        matchers: list[tuple[RoutingLayer, IMatcher]],
        config: RoutingConfig,
        optimization_config: OptimizationConfig,
        prefilter: CandidatePrefilter,
        optimization_service: OptimizationService,
        get_skill_source: Callable[[str, str], str],
    ) -> None:
        self._matchers = matchers
        self._config = config
        self._optimization_config = optimization_config
        self._prefilter = prefilter
        self._optimization_service = optimization_service
        self._get_skill_source = get_skill_source

    def try_matcher_pipeline(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
        collect_rejected: bool = False,
    ) -> LayerResult | None:
        filtered = self.apply_prefilter(query, candidates)
        self._optimization_service.ensure_cluster_index(filtered)

        # Build skill_id -> description lookup from candidates
        desc_map: dict[str, str] = {
            str(c.get("id", "")): str(c.get("description", "")) for c in filtered
        }

        # Aggregate scores across all matchers so a strong TF-IDF match isn't
        # blocked by a weak keyword match.
        best_scores: dict[str, tuple[float, RoutingLayer, dict[str, Any]]] = {}
        all_matches: list[Any] = []

        for layer, matcher in self._matchers:
            if layer == RoutingLayer.EMBEDDING and not self._config.enable_embedding:
                continue

            try:
                matches = matcher.match(
                    query,
                    filtered,
                    context,
                    top_k=self._config.max_candidates + 2,
                )
                for m in matches:
                    sid = m.skill_id
                    existing = best_scores.get(sid)
                    if existing is None or m.confidence > existing[0]:
                        best_scores[sid] = (m.confidence, layer, m.metadata)
                    all_matches.append(m)

                # Early exit: high-confidence keyword match skips TF-IDF/Embedding/Levenshtein
                if layer == RoutingLayer.KEYWORD and best_scores:
                    top_confidence = max(c[0] for c in best_scores.values())
                    if top_confidence >= 0.95:
                        break

            except (OSError, ValueError, KeyError, MatcherError) as e:
                logger.debug(f"Matcher {type(matcher).__name__} failed: {e}, trying next matcher")
                continue

        if not best_scores:
            return None

        # Deduplicate all_matches keeping highest confidence per skill
        seen: dict[str, Any] = {}
        for m in all_matches:
            sid = m.skill_id
            if sid not in seen or m.confidence > seen[sid].confidence:
                seen[sid] = m
        merged_matches = sorted(seen.values(), key=lambda x: x.confidence, reverse=True)

        if not merged_matches or merged_matches[0].confidence < self._config.min_confidence:
            return None

        primary_match, alternatives = self._optimization_service.apply_optimizations(
            merged_matches, query, context
        )

        # Collect rejected candidates (near-misses) for transparency
        rejected_candidates: list[dict[str, Any]] = []
        if collect_rejected and filtered:
            threshold = self._config.min_confidence
            near_miss_threshold = threshold * 0.5
            matched_ids = {m.skill_id for m in merged_matches}
            # Use the first matcher (usually fast keyword matcher) to score rejects
            if self._matchers:
                first_layer, first_matcher = self._matchers[0]
                for c in filtered:
                    sid = str(c.get("id", ""))
                    if sid in matched_ids or not sid:
                        continue
                    try:
                        score = first_matcher.score(query, c, context)
                        if near_miss_threshold <= score < threshold:
                            rejected_candidates.append(
                                {
                                    "skill_id": sid,
                                    "confidence": score,
                                    "layer": first_layer,
                                    "reason": f"below threshold ({threshold:.2f})",
                                }
                            )
                    except (TypeError, ValueError):
                        pass
                # Sort by confidence desc and limit to top 5
                rejected_candidates.sort(key=lambda x: x["confidence"], reverse=True)
                rejected_candidates = rejected_candidates[:5]

        primary_namespace = str(primary_match.metadata.get("namespace", "builtin"))
        winning_layer = best_scores.get(primary_match.skill_id, (0.0, RoutingLayer.KEYWORD, {}))[1]
        return LayerResult(
            match=SkillRoute(
                skill_id=primary_match.skill_id,
                confidence=primary_match.confidence,
                layer=winning_layer,
                source=self._get_skill_source(primary_match.skill_id, primary_namespace),
                description=desc_map.get(primary_match.skill_id, ""),
                metadata=_metadata_with_source(
                    primary_match.metadata, candidates, primary_match.skill_id
                ),
            ),
            alternatives=[
                SkillRoute(
                    skill_id=m.skill_id,
                    confidence=m.confidence,
                    layer=best_scores.get(m.skill_id, (0.0, RoutingLayer.KEYWORD, {}))[1],
                    source=self._get_skill_source(
                        m.skill_id, str(m.metadata.get("namespace", "builtin"))
                    ),
                    description=desc_map.get(m.skill_id, ""),
                    metadata=_metadata_with_source(m.metadata, candidates, m.skill_id),
                )
                for m in alternatives
            ],
            layer=winning_layer,
            diagnostics={"rejected_candidates": rejected_candidates} if rejected_candidates else {},
        )

    def set_prefilter(self, prefilter: CandidatePrefilter) -> None:
        """Replace the candidate prefilter (used when candidates are reloaded)."""
        self._prefilter = prefilter

    def apply_prefilter(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if self._optimization_config.enabled and self._optimization_config.prefilter.enabled:
            candidates = self._prefilter.filter(query, candidates)
        return self._apply_management_gate(query, candidates)

    def _apply_management_gate(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Exclude management-only skills from matcher layers unless the query
        shows tool-management intent (see filter_management_candidates)."""
        return filter_management_candidates(query, candidates)
