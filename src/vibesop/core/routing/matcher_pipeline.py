"""Matcher pipeline for routing layers 3-6 (keyword, tfidf, embedding, levenshtein)."""

from __future__ import annotations

import logging
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
    ) -> LayerResult | None:
        filtered = self.apply_prefilter(query, candidates)
        self._optimization_service.ensure_cluster_index(filtered)

        for layer, matcher in self._matchers:
            if layer == RoutingLayer.EMBEDDING and not self._config.enable_embedding:
                continue

            try:
                matches = matcher.match(
                    query,
                    filtered,
                    context,
                    top_k=self._config.max_candidates + 1,
                )

                if not matches or matches[0].confidence < self._config.min_confidence:
                    continue

                primary_match, alternatives = self._optimization_service.apply_optimizations(
                    matches, query, context
                )

                primary_namespace = str(primary_match.metadata.get("namespace", "builtin"))
                return LayerResult(
                    match=SkillRoute(
                        skill_id=primary_match.skill_id,
                        confidence=primary_match.confidence,
                        layer=layer,
                        source=self._get_skill_source(primary_match.skill_id, primary_namespace),
                        metadata=primary_match.metadata,
                    ),
                    alternatives=[
                        SkillRoute(
                            skill_id=m.skill_id,
                            confidence=m.confidence,
                            layer=layer,
                            source=self._get_skill_source(
                                m.skill_id, str(m.metadata.get("namespace", "builtin"))
                            ),
                            metadata=m.metadata,
                        )
                        for m in alternatives
                    ],
                    layer=layer,
                )
            except (OSError, ValueError, KeyError, MatcherError) as e:
                logger.debug(f"Matcher {type(matcher).__name__} failed: {e}, trying next matcher")
                continue

        return None

    def apply_prefilter(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if self._optimization_config.enabled and self._optimization_config.prefilter.enabled:
            return self._prefilter.filter(query, candidates)
        return candidates
