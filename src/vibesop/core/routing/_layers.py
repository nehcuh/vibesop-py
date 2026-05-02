"""Layer execution functions for UnifiedRouter.

Extracted from explicit_layer.py, scenario_layer.py, and triage_mixin.py.
Each function returns (SkillRoute | None, LayerDetail).

NOTE: Do NOT add `from vibesop.core.routing import ...` at the module level.
This module is imported BY `vibesop.core.routing.__init__`, which re-exports
from `unified.py`. Circular imports will occur if this rule is violated.
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
from vibesop.core.skills.indexer import SkillIndexer


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
    actual_skill_id = candidate.get("id", target_skill)
    match = SkillRoute(
        skill_id=actual_skill_id,
        confidence=0.9,
        layer=RoutingLayer.SCENARIO,
        source=router._get_skill_source(actual_skill_id, candidate.get("namespace", "builtin")),
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

    # Respect skip_ai_triage from context (used by PlanBuilder for sub-task routing)
    if context and getattr(context, "skip_ai_triage", False):
        return None, LayerDetail(
            layer=RoutingLayer.AI_TRIAGE,
            matched=False,
            reason="AI triage skipped (context.skip_ai_triage=True)",
            duration_ms=(time.perf_counter() - triage_start) * 1000,
        )

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
    if (
        getattr(router._triage_service, "_circuit_breaker", None)
        and not router._triage_service._circuit_breaker.can_execute()
    ):
        return "Circuit breaker open (too many failures)"
    monthly_cost = getattr(router._cost_tracker, "get_monthly_cost", lambda: 0.0)()
    if monthly_cost >= router._config.ai_triage_budget_monthly:
        return f"Monthly AI triage budget exhausted (${monthly_cost:.2f} / ${router._config.ai_triage_budget_monthly:.2f})"
    return "AI triage did not produce a match"


# --- Skill Semantic Index layer ---

def _tokenize_query(query: str) -> set[str]:
    """Tokenize a query for index matching.

    Handles both CJK (character-based) and Latin (word-based) text.
    """
    import re

    tokens: set[str] = set()
    # English words
    for word in re.findall(r"[a-zA-Z]{2,}", query.lower()):
        tokens.add(word)
    # CJK characters (each char is a meaningful token)
    for char in query:
        if "一" <= char <= "鿿":
            tokens.add(char)
    return tokens


def _compute_index_score(query_tokens: set[str], profile: Any) -> float:
    """Compute match score between query tokens and a skill profile.

    Returns a score between 0.0 and 1.0 based on keyword overlap.
    """
    if not query_tokens:
        return 0.0

    all_text = " ".join(profile.query_patterns + profile.scenarios + profile.confidence_boosters)
    profile_tokens = _tokenize_query(all_text)

    return _score_overlap(query_tokens, profile_tokens)


def _score_overlap(query_tokens: set[str], profile_tokens: set[str]) -> float:
    """Score overlap between two pre-tokenized sets.

    Extracted so the index layer can score against pre-tokenized profiles
    (cached once at index load) without re-tokenizing per route.
    """
    if not query_tokens or not profile_tokens:
        return 0.0

    overlap = query_tokens & profile_tokens
    # Jaccard-like score weighted by overlap density
    score = len(overlap) / max(len(query_tokens), len(profile_tokens) * 0.5)
    return min(score, 1.0)


def _build_profile_token_index(index: dict[str, Any]) -> dict[str, set[str]]:
    """Pre-tokenize each profile's combined text once.

    Tokenization over 100+ profiles per route call dominated INDEX latency
    (~370ms in the simple-route benchmark). Pre-computing once at first
    cache hit keeps subsequent routes O(profile-count * set-intersection).
    """
    tokens_by_id: dict[str, set[str]] = {}
    for skill_id, profile in index.items():
        all_text = " ".join(
            profile.query_patterns + profile.scenarios + profile.confidence_boosters
        )
        tokens_by_id[skill_id] = _tokenize_query(all_text)
    return tokens_by_id


def try_index_layer(
    router: RoutingCore,
    query: str,
    candidates: list[dict[str, Any]],
) -> tuple[SkillRoute | None, LayerDetail]:
    """Try skill semantic index layer.

    Uses the pre-built skill-index.json to match queries against skill
    scenarios and query patterns without calling an LLM. Fast, local,
    and complements AI Triage.

    Returns:
        (SkillRoute, LayerDetail) if index hit, (None, LayerDetail) otherwise.
        The match is reported as AI_TRIAGE layer with metadata["index_hit"]=True.
    """
    index_start = time.perf_counter()

    # Cache the loaded index on the router to avoid repeatedly re-parsing
    # ~1MB of JSON + reconstructing 100+ SkillProfile objects per route.
    # We also cache per-profile token sets so we don't re-tokenize ~100
    # profiles' combined text on every route. We check `isinstance(cached, dict)`
    # rather than `is None` so MagicMock-based unit tests (which auto-create
    # attributes on access) still take the load path on first call.
    cached = getattr(router, "_index_layer_cache", None)
    if not isinstance(cached, dict):
        indexer = SkillIndexer(project_root=router.project_root)
        if not indexer.has_index():
            router._index_layer_cache = {}  # mark as "tried, missing"
            router._index_profile_tokens = {}
            return None, LayerDetail(
                layer=RoutingLayer.AI_TRIAGE,
                matched=False,
                reason="Skill semantic index not built (run 'vibe init' to build)",
                duration_ms=(time.perf_counter() - index_start) * 1000,
            )
        router._index_layer_cache = indexer.load_index()
        router._index_profile_tokens = _build_profile_token_index(
            router._index_layer_cache
        )
        cached = router._index_layer_cache

    index = cached
    if not index:
        return None, LayerDetail(
            layer=RoutingLayer.AI_TRIAGE,
            matched=False,
            reason="Skill semantic index is empty",
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    profile_tokens_by_id_raw = getattr(router, "_index_profile_tokens", None)
    profile_tokens_by_id: dict[str, set[str]] = (
        profile_tokens_by_id_raw
        if isinstance(profile_tokens_by_id_raw, dict)
        else {}
    )
    query_tokens = _tokenize_query(query)
    best_skill_id: str | None = None
    best_score = 0.0

    for skill_id in index:
        profile_tokens = profile_tokens_by_id.get(skill_id)
        if profile_tokens is None:
            # Cache miss for a profile (e.g. cache populated by older code path);
            # fall back to on-the-fly compute. Cheap once, persists for next time.
            profile_tokens = _build_profile_token_index({skill_id: index[skill_id]})[
                skill_id
            ]
            profile_tokens_by_id[skill_id] = profile_tokens
        score = _score_overlap(query_tokens, profile_tokens)
        if score > best_score:
            best_score = score
            best_skill_id = skill_id

    threshold = getattr(router._config, "index_match_threshold", 0.20)
    if best_score < threshold or not best_skill_id:
        return None, LayerDetail(
            layer=RoutingLayer.AI_TRIAGE,
            matched=False,
            reason=f"No index match above threshold ({best_score:.2f} < {threshold})",
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    candidate = next((c for c in candidates if c["id"] == best_skill_id), None)
    if not candidate:
        return None, LayerDetail(
            layer=RoutingLayer.AI_TRIAGE,
            matched=False,
            reason=f"Index matched '{best_skill_id}' but skill not in candidates",
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    # Confidence: scale score [threshold..1.0] → [0.65..0.95]
    # Lower bound 0.65 (vs SCENARIO's fixed 0.9) signals "weaker" match,
    # so a strong scenario keyword hit can still take precedence when it follows.
    confidence = 0.65 + (best_score - threshold) / (1.0 - threshold) * 0.30

    match = SkillRoute(
        skill_id=best_skill_id,
        confidence=round(confidence, 2),
        layer=RoutingLayer.AI_TRIAGE,  # Report as AI_TRIAGE to avoid enum churn
        source=router._get_skill_source(best_skill_id, candidate.get("namespace", "builtin")),
        description=str(candidate.get("description", "")),
        metadata={
            "index_hit": True,
            "index_score": round(best_score, 3),
            "scenarios": index[best_skill_id].scenarios[:3],
        },
    )
    return match, LayerDetail(
        layer=RoutingLayer.AI_TRIAGE,
        matched=True,
        reason=f"Index match: '{best_skill_id}' (score {best_score:.2f})",
        duration_ms=(time.perf_counter() - index_start) * 1000,
    )
