"""Layer execution functions for UnifiedRouter.

Extracted from explicit_layer.py, scenario_layer.py, and triage_mixin.py.
Each function returns (SkillRoute | None, LayerDetail).
"""

from __future__ import annotations

import time
from typing import Any

from vibesop.core.matching import RoutingContext
from vibesop.core.models import LayerDetail, RoutingLayer, SkillRoute
from vibesop.core.routing._protocols import RoutingCore
from vibesop.core.routing.explicit_layer import check_explicit_override
from vibesop.core.routing.project_config import load_merged_scenario_config
from vibesop.core.routing.scenario_layer import match_scenario


def try_explicit_layer(
    router: RoutingCore,
    query: str,
    candidates: list[dict[str, Any]],
) -> tuple[SkillRoute | None, LayerDetail]:
    """Try explicit override layer."""
    explicit_skill, cleaned_query = check_explicit_override(query, candidates)
    if not explicit_skill:
        return None, LayerDetail(
            layer=RoutingLayer.EXPLICIT,
            matched=False,
            reason="No @skill_id syntax detected",
        )

    candidate = next((c for c in candidates if c["id"] == explicit_skill), None)
    if not candidate:
        return None, LayerDetail(
            layer=RoutingLayer.EXPLICIT,
            matched=False,
            reason=f"@{explicit_skill} specified but skill not found in candidates",
            diagnostics={"cleaned_query": cleaned_query},
        )

    source = router._get_skill_source(explicit_skill, candidate.get("namespace", "builtin"))
    match = SkillRoute(
        skill_id=explicit_skill,
        confidence=1.0,
        layer=RoutingLayer.EXPLICIT,
        source=source,
        description=str(candidate.get("description", "")),
        metadata={"override": True, "cleaned_query": cleaned_query},
    )
    return match, LayerDetail(
        layer=RoutingLayer.EXPLICIT,
        matched=True,
        reason=f"Explicit override: @{explicit_skill}",
        diagnostics={"cleaned_query": cleaned_query},
    )


def try_scenario_layer(
    router: RoutingCore,
    query: str,
    candidates: list[dict[str, Any]],
) -> tuple[SkillRoute | None, LayerDetail]:
    """Try scenario pattern layer."""
    if router._scenario_cache is None:
        router._scenario_cache = load_merged_scenario_config(router.project_root)
    scenarios = router._scenario_cache.get("strategies", [])
    keywords = router._scenario_cache.get("keywords", {})
    scenario = match_scenario(query, scenarios, keywords)
    if not scenario:
        return None, LayerDetail(
            layer=RoutingLayer.SCENARIO,
            matched=False,
            reason="No scenario keywords matched",
        )

    target_skill = scenario.get("skill") or scenario.get("primary") or scenario.get("skill_id")
    if not target_skill:
        return None, LayerDetail(
            layer=RoutingLayer.SCENARIO,
            matched=False,
            reason=f"Scenario '{scenario.get('scenario', 'unknown')}' matched but no target skill defined",
            diagnostics={"scenario": scenario.get("scenario")},
        )

    candidate = next((c for c in candidates if c["id"] == target_skill), None)
    if not candidate:
        candidate = next(
            (c for c in candidates if c["id"].endswith(f"/{target_skill}")),
            None,
        )
    if not candidate and target_skill.startswith("/"):
        short_name = target_skill[1:]
        candidate = next(
            (c for c in candidates if c["id"].endswith(f"/{short_name}")),
            None,
        )
        if not candidate:
            candidate = next(
                (c for c in candidates if c["id"].endswith(f"-{short_name}")),
                None,
            )
        if not candidate:
            candidate = next(
                (c for c in candidates if c["id"] == short_name),
                None,
            )
    if not candidate:
        return None, LayerDetail(
            layer=RoutingLayer.SCENARIO,
            matched=False,
            reason=f"Scenario matched '{target_skill}' but skill not in candidates",
            diagnostics={"scenario": scenario.get("scenario"), "target_skill": target_skill},
        )

    # Build alternatives from related skills
    alternatives: list[SkillRoute] = []
    related = scenario.get("related_skills", [])
    for rid in related:
        rel = next((c for c in candidates if c["id"] == rid), None)
        if rel:
            alternatives.append(
                SkillRoute(
                    skill_id=rid,
                    confidence=0.75,
                    layer=RoutingLayer.SCENARIO,
                    source=router._get_skill_source(rid, rel.get("namespace", "builtin")),
                    description=str(rel.get("description", "")),
                    metadata={"scenario": scenario.get("scenario")},
                )
            )

    scenario_name = scenario.get("scenario", "unknown")
    match = SkillRoute(
        skill_id=target_skill,
        confidence=0.9,
        layer=RoutingLayer.SCENARIO,
        source=router._get_skill_source(target_skill, candidate.get("namespace", "builtin")),
        description=str(candidate.get("description", "")),
        metadata={"scenario": scenario_name},
    )
    return match, LayerDetail(
        layer=RoutingLayer.SCENARIO,
        matched=True,
        reason=f"Scenario matched: '{scenario_name}'",
        diagnostics={
            "scenario": scenario_name,
            "related_skills": related,
            "alternatives_count": len(alternatives),
        },
    )


def try_ai_triage_layer(
    router: RoutingCore,
    query: str,
    candidates: list[dict[str, Any]],
    context: RoutingContext | None,
    force: bool = False,
) -> tuple[SkillRoute | None, LayerDetail]:
    """Try AI triage layer.

    Args:
        force: If True, skip the short-query word-count bypass.
               Used when keyword routing is already disabled for long queries.
    """
    triage_start = time.perf_counter()

    # Short-query bypass: queries under N chars skip AI Triage
    # because short queries are usually explicit skill names or keywords,
    # which the traditional matchers handle faster and more accurately.
    # Uses character count (not word count) to correctly handle CJK
    # and other languages that don't use whitespace word boundaries.
    # When forced (long queries where keyword routing is disabled),
    # this bypass is skipped.
    if not force:
        bypass_chars = getattr(router._config, "ai_triage_short_query_bypass_chars", 15)
        if len(query) < bypass_chars:
            return None, LayerDetail(
                layer=RoutingLayer.AI_TRIAGE,
                matched=False,
                reason=f"Short-query bypass (<{bypass_chars} chars): falling through to traditional matchers",
                duration_ms=(time.perf_counter() - triage_start) * 1000,
            )

    if router._llm is not None:
        router._triage_service._llm = router._llm

    triage = router._triage_service.try_ai_triage(query, candidates, context)
    triage_duration_ms = (time.perf_counter() - triage_start) * 1000

    if triage is not None and triage.match is not None:
        return triage.match, LayerDetail(
            layer=RoutingLayer.AI_TRIAGE,
            matched=True,
            reason=f"AI triage selected '{triage.match.skill_id}' (confidence: {triage.match.confidence:.0%})",
            duration_ms=triage_duration_ms,
            diagnostics=triage.diagnostics,
        )

    skip_reason = _get_ai_triage_skip_reason(router)
    return None, LayerDetail(
        layer=RoutingLayer.AI_TRIAGE,
        matched=False,
        reason=skip_reason,
        duration_ms=triage_duration_ms,
    )


def build_fallback_detail(_config: Any) -> LayerDetail:
    """Build fallback layer detail."""
    return LayerDetail(
        layer=RoutingLayer.FALLBACK_LLM,
        matched=True,
        reason="No confident skill match; falling back to raw LLM",
    )


def _get_ai_triage_skip_reason(router: RoutingCore) -> str:
    """Determine why AI triage was skipped."""
    if not router._config.enable_ai_triage:
        return "AI triage disabled in config"
    if getattr(router._triage_service, "_llm", None) is None:
        return "LLM not initialized"
    if getattr(router._triage_service, "_circuit_breaker", None) and not router._triage_service._circuit_breaker.can_execute():
        return "Circuit breaker open (too many failures)"
    monthly_cost = getattr(router._cost_tracker, "get_monthly_cost", lambda: 0.0)()
    if monthly_cost >= router._config.ai_triage_budget_monthly:
        return f"Monthly AI triage budget exhausted (${monthly_cost:.2f} / ${router._config.ai_triage_budget_monthly:.2f})"
    return "AI triage did not produce a match"
