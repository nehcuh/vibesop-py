"""Router execution mixin - layer execution and fallback result building.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from vibesop.core.models import (
    LayerDetail,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)
from vibesop.core.routing.layers import LayerResult

if TYPE_CHECKING:
    from vibesop.core.matching import RoutingContext

logger = logging.getLogger(__name__)


class RouterExecutionMixin:
    """Mixin providing layer execution and fallback result building methods.

    Intended for use with UnifiedRouter. Expects the host class to provide
    the layer try-methods and related attributes via ``self``.
    """

    def _execute_layers(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
    ):
        """Generator that yields (LayerResult, list[LayerDetail]) tuples.

        Collects diagnostic details for each layer to enable routing transparency.
        """
        layer_details: list[LayerDetail] = []

        # Layer 0: Explicit Override
        explicit = self._try_explicit(query, candidates)
        if explicit is not None:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.EXPLICIT,
                    matched=explicit.match is not None,
                    reason=explicit.reason or (
                        f"Explicit override: @{explicit.match.skill_id}"
                        if explicit.match else "No @skill_id syntax detected"
                    ),
                    diagnostics=explicit.diagnostics,
                )
            )
            if explicit.match is not None:
                yield explicit, layer_details
                return
            yield explicit, layer_details
        else:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.EXPLICIT,
                    matched=False,
                    reason="No @skill_id syntax detected",
                )
            )
            yield LayerResult(layer=RoutingLayer.EXPLICIT), layer_details

        # Layer 1: Scenario Pattern
        scenario = self._try_scenario(query, candidates)
        if scenario is not None:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.SCENARIO,
                    matched=scenario.match is not None,
                    reason=scenario.reason or (
                        f"Scenario matched: {scenario.match.metadata.get('scenario', 'unknown')}"
                        if scenario.match else "No scenario keywords matched"
                    ),
                    diagnostics=scenario.diagnostics,
                )
            )
            if scenario.match is not None:
                yield scenario, layer_details
                return
            yield scenario, layer_details
        else:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.SCENARIO,
                    matched=False,
                    reason="No scenario keywords matched",
                )
            )
            yield LayerResult(layer=RoutingLayer.SCENARIO), layer_details

        # Layer 2: AI Triage
        triage_start = time.perf_counter()
        triage = self._try_ai_triage(query, candidates, context)
        triage_duration_ms = (time.perf_counter() - triage_start) * 1000
        if triage is not None:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.AI_TRIAGE,
                    matched=triage.match is not None,
                    reason=triage.reason or (
                        f"AI triage selected '{triage.match.skill_id}' (confidence: {triage.match.confidence:.0%})"
                        if triage.match else "AI triage did not select any skill"
                    ),
                    duration_ms=triage_duration_ms,
                    diagnostics=triage.diagnostics,
                )
            )
            if triage.match is not None:
                yield triage, layer_details
                return
            yield triage, layer_details
        else:
            skip_reason = self._get_ai_triage_skip_reason()
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.AI_TRIAGE,
                    matched=False,
                    reason=skip_reason,
                    duration_ms=triage_duration_ms,
                )
            )
            yield LayerResult(layer=RoutingLayer.AI_TRIAGE), layer_details

        # Layers 3-6: Matcher pipeline (keyword, tfidf, embedding, levenshtein)
        matcher_start = time.perf_counter()
        matcher_result = self._try_matcher_pipeline(
            query, candidates, context, collect_rejected=True
        )
        matcher_duration_ms = (time.perf_counter() - matcher_start) * 1000
        if matcher_result is not None and matcher_result.match is not None:
            layer_details.append(
                LayerDetail(
                    layer=matcher_result.layer,
                    matched=True,
                    reason=matcher_result.reason or (
                        f"Matcher selected '{matcher_result.match.skill_id}' (confidence: {matcher_result.match.confidence:.0%})"
                    ),
                    duration_ms=matcher_duration_ms,
                    diagnostics=matcher_result.diagnostics,
                )
            )
            yield matcher_result, layer_details
        else:
            rejected = []
            if matcher_result and matcher_result.diagnostics:
                raw_rejected = matcher_result.diagnostics.get("rejected_candidates", [])
                from vibesop.core.models import RejectedCandidate
                for r in raw_rejected:
                    rejected.append(RejectedCandidate(
                        skill_id=r["skill_id"],
                        confidence=r["confidence"],
                        layer=RoutingLayer(r["layer"].value if hasattr(r["layer"], "value") else str(r["layer"])),
                        reason=r.get("reason", ""),
                    ))
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.LEVENSHTEIN,
                    matched=False,
                    reason=matcher_result.reason if matcher_result else "No matcher produced a confident match",
                    duration_ms=matcher_duration_ms,
                    diagnostics=matcher_result.diagnostics if matcher_result else {},
                    rejected_candidates=rejected,
                )
            )
            yield matcher_result or LayerResult(
                layer=RoutingLayer.LEVENSHTEIN
            ), layer_details

    def _get_ai_triage_skip_reason(self) -> str:
        """Determine why AI triage was skipped."""
        if not self._config.enable_ai_triage:
            return "AI triage disabled in config"
        if getattr(self._triage_service, "_llm", None) is None:
            return "LLM not initialized"
        if getattr(self._triage_service, "_circuit_breaker", None) and not self._triage_service._circuit_breaker.can_execute():
            return "Circuit breaker open (too many failures)"
        monthly_cost = getattr(self._cost_tracker, "get_monthly_cost", lambda: 0.0)()
        if monthly_cost >= self._config.ai_triage_budget_monthly:
            return f"Monthly AI triage budget exhausted (${monthly_cost:.2f} / ${self._config.ai_triage_budget_monthly:.2f})"
        return "AI triage did not produce a match"

    def _collect_layer_details(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
    ) -> list[LayerDetail]:
        """Collect layer details for no-match scenarios.

        Runs all layers non-destructively to gather diagnostics.
        """
        layer_details: list[LayerDetail] = []

        # Explicit
        explicit = self._try_explicit(query, candidates)
        layer_details.append(
            LayerDetail(
                layer=RoutingLayer.EXPLICIT,
                matched=False,
                reason=explicit.reason if explicit else "No @skill_id syntax detected",
                diagnostics=explicit.diagnostics if explicit else {},
            )
        )

        # Scenario
        scenario = self._try_scenario(query, candidates)
        layer_details.append(
            LayerDetail(
                layer=RoutingLayer.SCENARIO,
                matched=False,
                reason=scenario.reason if scenario else "No scenario keywords matched",
                diagnostics=scenario.diagnostics if scenario else {},
            )
        )

        # AI Triage
        triage_start = time.perf_counter()
        triage = self._try_ai_triage(query, candidates, context)
        triage_duration_ms = (time.perf_counter() - triage_start) * 1000
        if triage is not None:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.AI_TRIAGE,
                    matched=False,
                    reason=triage.reason or "AI triage did not select any skill",
                    duration_ms=triage_duration_ms,
                    diagnostics=triage.diagnostics,
                )
            )
        else:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.AI_TRIAGE,
                    matched=False,
                    reason=self._get_ai_triage_skip_reason(),
                    duration_ms=triage_duration_ms,
                )
            )

        # Matchers
        matcher_start = time.perf_counter()
        matcher_result = self._try_matcher_pipeline(query, candidates, context)
        matcher_duration_ms = (time.perf_counter() - matcher_start) * 1000
        if matcher_result is not None and matcher_result.match is not None:
            layer_details.append(
                LayerDetail(
                    layer=matcher_result.layer,
                    matched=True,
                    reason=matcher_result.reason or f"Matcher selected '{matcher_result.match.skill_id}'",
                    duration_ms=matcher_duration_ms,
                    diagnostics=matcher_result.diagnostics,
                )
            )
        else:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.LEVENSHTEIN,
                    matched=False,
                    reason=matcher_result.reason if matcher_result else "No matcher produced a confident match",
                    duration_ms=matcher_duration_ms,
                    diagnostics=matcher_result.diagnostics if matcher_result else {},
                )
            )

        return layer_details

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
        # Find nearest candidates (even if below threshold) for suggestions
        nearest: list[SkillRoute] = []
        try:
            matcher_result = self._try_matcher_pipeline(query, candidates, None)
            if matcher_result and matcher_result.match:
                nearest = [matcher_result.match, *matcher_result.alternatives]
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
                    "fallback_mode": self._config.fallback_mode,
                    "candidate_count": len(candidates),
                },
            ),
            alternatives=nearest,
            routing_path=[*routing_path, RoutingLayer.FALLBACK_LLM],
            layer_details=[*layer_details, fallback_layer_detail],
            query=query,
            duration_ms=duration_ms,
        )
