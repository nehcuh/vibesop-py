# pyright: reportPrivateUsage=false
"""Layer execution functions for UnifiedRouter.

Extracted from explicit_layer.py, scenario_layer.py, and triage_mixin.py.
Each function returns (SkillRoute | None, LayerDetail).

NOTE: Do NOT add `from vibesop.core.routing import ...` at the module level.
This module is imported BY `vibesop.core.routing.__init__`, which re-exports
from `unified.py`. Circular imports will occur if this rule is violated.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from vibesop.core.matching import RoutingContext
from vibesop.core.models import LayerDetail, RoutingLayer, SkillRoute
from vibesop.core.routing._protocols import RoutingCore
from vibesop.core.routing.explicit_layer import check_explicit_override
from vibesop.core.routing.project_config import load_merged_scenario_config
from vibesop.core.routing.scenario_layer import match_scenario
from vibesop.core.skills.indexer import SkillIndexer

logger = logging.getLogger(__name__)


def try_explicit_layer(
    router: RoutingCore,
    query: str,
    candidates: list[dict[str, Any]],
) -> tuple[SkillRoute | None, LayerDetail]:
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

    # Honor the scenario's declared primary_source: when a scenario pins its
    # primary to a specific namespace (e.g. primary_source: gstack), only a
    # candidate from that namespace may resolve it. Without this check a bare
    # "/review" resolved to the FIRST installed pack skill with that name
    # (e.g. mattpocock/review) at a fixed 0.9 confidence, hijacking every
    # "review/评审/pr/merge" query on machines where the intended pack is not
    # installed. Fail closed instead: no candidate in the declared namespace
    # means the scenario does not match, and lower layers arbitrate.
    primary_source = scenario.get("primary_source")

    def _source_ok(c: dict[str, Any]) -> bool:
        if not primary_source:
            return True
        cid = str(c.get("id", ""))
        namespace = str(c.get("namespace", ""))
        prefix = cid.split("/", maxsplit=1)[0] if "/" in cid else ""
        return primary_source in (namespace, prefix)

    candidate = next((c for c in candidates if c["id"] == target_skill and _source_ok(c)), None)
    if not candidate:
        candidate = next(
            (c for c in candidates if c["id"].endswith(f"/{target_skill}") and _source_ok(c)),
            None,
        )
    if not candidate and target_skill.startswith("/"):
        short_name = target_skill[1:]
        candidate = next(
            (c for c in candidates if c["id"].endswith(f"/{short_name}") and _source_ok(c)),
            None,
        )
        if not candidate:
            candidate = next(
                (c for c in candidates if c["id"].endswith(f"-{short_name}") and _source_ok(c)),
                None,
            )
        if not candidate:
            candidate = next(
                (c for c in candidates if c["id"] == short_name and _source_ok(c)),
                None,
            )
    if not candidate and primary_source:
        # By design, not a failure worth a warning: the scenario simply stays
        # inert on machines without the declared pack installed.
        logger.debug(
            "Scenario '%s' inert: declared primary_source '%s' has no installed "
            "candidate for target '%s' (fail-closed; not substituting an "
            "unrelated pack skill)",
            scenario.get("scenario"),
            primary_source,
            target_skill,
        )
        return None, LayerDetail(
            layer=RoutingLayer.SCENARIO,
            matched=False,
            reason=(
                f"Scenario matched '{target_skill}' but declared primary_source "
                f"'{primary_source}' has no installed candidate; refusing to "
                f"substitute an unrelated pack skill"
            ),
            diagnostics={
                "scenario": scenario.get("scenario"),
                "target_skill": target_skill,
                "primary_source": primary_source,
            },
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
    return LayerDetail(
        layer=RoutingLayer.FALLBACK_LLM,
        matched=True,
        reason="No confident skill match; falling back to raw LLM",
    )


def _get_ai_triage_skip_reason(router: RoutingCore) -> str:
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
    import re

    tokens: set[str] = set()
    # English words
    for word in re.findall(r"[a-zA-Z]{2,}", query.lower()):
        tokens.add(word)
    # CJK bigrams over contiguous CJK runs (e.g. "提交代码" → {提交, 交代, 代码}).
    # Single-char tokenization made Jaccard overlap near-noise for CJK queries
    # ("提交代码" vs "提交PR" shared most chars); bigrams restore selectivity.
    # A lone CJK char keeps its unigram so single-char queries still match.
    for run in re.findall(r"[一-鿿]+", query):
        if len(run) == 1:
            tokens.add(run)
        else:
            for i in range(len(run) - 1):
                tokens.add(run[i : i + 2])
    return tokens


def _compute_index_score(  # pyright: ignore[reportUnusedFunction]
    query_tokens: set[str], profile: Any
) -> float:
    if not query_tokens:
        return 0.0

    all_text = " ".join(profile.query_patterns + profile.scenarios + profile.confidence_boosters)
    profile_tokens = _tokenize_query(all_text)

    return _score_overlap(query_tokens, profile_tokens)


def _score_overlap(query_tokens: set[str], profile_tokens: set[str]) -> float:
    if not query_tokens or not profile_tokens:
        return 0.0

    overlap = query_tokens & profile_tokens
    # Jaccard-like score weighted by overlap density
    score = len(overlap) / max(len(query_tokens), len(profile_tokens) * 0.5)
    return min(score, 1.0)


def _build_profile_token_index(index: dict[str, Any]) -> dict[str, set[str]]:
    tokens_by_id: dict[str, set[str]] = {}
    for skill_id, profile in index.items():
        all_text = " ".join(
            profile.query_patterns + profile.scenarios + profile.confidence_boosters
        )
        tokens_by_id[skill_id] = _tokenize_query(all_text)
    return tokens_by_id


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b + 1e-10)


def _cfg_float(config: Any, name: str) -> float:
    """Read a float RoutingConfig knob, tolerating MagicMock configs in tests.

    ``getattr`` on a MagicMock always succeeds, so a plain ``getattr(...,
    default)`` would return a MagicMock (not the default) when a test only
    sets the knobs it cares about. Fall back to the RoutingConfig Field
    default in that case — single source of truth, so this fallback can never
    diverge from the declared default.
    """
    value = getattr(config, name, None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        from vibesop.core.config.manager import RoutingConfig

        field = RoutingConfig.model_fields.get(name)
        default = getattr(field, "default", None) if field is not None else None
        return float(default) if isinstance(default, (int, float)) else 0.0
    return float(value)


# Namespaces whose skills are curated by this repo or the project itself
# (core/skills and .vibe/skills — the project-local skills here declare
# namespace "custom"/"cross-cutting" in their frontmatter). Everything else
# (superpowers, omx, mattpocock, ...) is an external pack.
_TRUSTED_INDEX_NAMESPACES = frozenset({"builtin", "project", "custom", "cross-cutting"})


def _try_embedding_fallback(
    router: RoutingCore,
    query: str,
    index: dict[str, Any],
    candidates: list[dict[str, Any]],
    index_start: float,
) -> tuple[SkillRoute | None, LayerDetail]:
    profiles_with_emb: dict[str, Any] = {
        sid: prof for sid, prof in index.items() if getattr(prof, "embedding", None) is not None
    }
    if not profiles_with_emb:
        return None, LayerDetail(
            layer=RoutingLayer.SEMANTIC_INDEX,
            matched=False,
            reason="No embeddings in index",
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    # Lazy-load the model once per router instance.
    model = getattr(router, "_index_embedding_model", None)
    if model is None:
        try:
            from sentence_transformers import (
                SentenceTransformer,  # pyright: ignore[reportMissingImports]
            )

            model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            router._index_embedding_model = model
        except Exception:
            return None, LayerDetail(
                layer=RoutingLayer.SEMANTIC_INDEX,
                matched=False,
                reason="sentence-transformers not available for embedding fallback",
                duration_ms=(time.perf_counter() - index_start) * 1000,
            )

    try:
        raw_emb = model.encode([query], show_progress_bar=False)[0]
        query_emb = raw_emb.tolist() if hasattr(raw_emb, "tolist") else list(raw_emb)
    except Exception:
        return None, LayerDetail(
            layer=RoutingLayer.SEMANTIC_INDEX,
            matched=False,
            reason="Query embedding failed",
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    # Rank only profiles whose skill is actually installed: an uninstalled
    # profile can never be routed, and letting it occupy the top-1/top-2
    # slots would both report a dead match and corrupt the margin below.
    candidate_ids = {str(c.get("id", "")) for c in candidates}
    best_skill_id: str | None = None
    best_similarity = 0.0
    second_similarity = 0.0
    for skill_id, profile in profiles_with_emb.items():
        if skill_id not in candidate_ids:
            continue
        sim = _cosine_similarity(query_emb, profile.embedding)
        if sim > best_similarity:
            second_similarity = best_similarity
            best_similarity = sim
            best_skill_id = skill_id
        elif sim > second_similarity:
            second_similarity = sim

    embedding_threshold = _cfg_float(router._config, "index_embedding_threshold")
    if best_similarity < embedding_threshold or not best_skill_id:
        return None, LayerDetail(
            layer=RoutingLayer.SEMANTIC_INDEX,
            matched=False,
            reason=(
                f"Embedding fallback: no match above threshold "
                f"({best_similarity:.2f} < {embedding_threshold})"
            ),
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    # Margin gate: argmax over a large catalog of LLM-generated profiles
    # always finds a nearest neighbor, even for unrelated queries — the
    # top-1 then sits inside the model's noise band just above the absolute
    # threshold. Genuine intent separates clearly from the runner-up; noise
    # does not. Require a minimum top1-minus-top2 gap. The gate is
    # deliberately namespace-blind: a noisy builtin argmax is no more
    # trustworthy than a noisy pack one, and abstaining here does not dead-end
    # the query — it defers to AI triage, which is the intended escalation
    # for genuinely ambiguous semantic matches.
    min_margin = _cfg_float(router._config, "index_embedding_min_margin")
    margin = best_similarity - second_similarity
    if margin < min_margin:
        return None, LayerDetail(
            layer=RoutingLayer.SEMANTIC_INDEX,
            matched=False,
            reason=(
                f"Embedding fallback: '{best_skill_id}' too close to runner-up "
                f"(margin {margin:.3f} < {min_margin:.2f}); treating as noise"
            ),
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    candidate = next((c for c in candidates if c["id"] == best_skill_id), None)
    if not candidate:
        return None, LayerDetail(
            layer=RoutingLayer.SEMANTIC_INDEX,
            matched=False,
            reason=f"Embedding matched '{best_skill_id}' but skill not in candidates",
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    # Guarded skills (session-end, riper-workflow, ...) require explicit user
    # intent; embedding similarity alone must not select them (same criterion
    # as the AI-triage guard — e.g. "似乎有其他进程没有关闭，帮我先关闭了"
    # embedded closest to session-end at 0.52 without any exit intent).
    if not router._triage_service.has_explicit_guard_signal(query, candidates, best_skill_id):
        return None, LayerDetail(
            layer=RoutingLayer.SEMANTIC_INDEX,
            matched=False,
            reason=(
                f"Embedding matched guarded skill '{best_skill_id}' but the query "
                f"carries no explicit signal for it"
            ),
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    # Scale similarity [threshold..1.0] → confidence [0.65..0.95]
    confidence = 0.65 + (best_similarity - embedding_threshold) / (1.0 - embedding_threshold) * 0.30

    match = SkillRoute(
        skill_id=best_skill_id,
        confidence=round(confidence, 2),
        layer=RoutingLayer.SEMANTIC_INDEX,
        source=router._get_skill_source(best_skill_id, candidate.get("namespace", "builtin")),
        description=str(candidate.get("description", "")),
        metadata={
            "index_hit": True,
            "index_score": round(best_similarity, 3),
            "embedding_match": True,
            "scenarios": index[best_skill_id].scenarios[:3],
        },
    )
    detail = LayerDetail(
        layer=RoutingLayer.SEMANTIC_INDEX,
        matched=True,
        reason=(f"Embedding match: '{best_skill_id}' (similarity {best_similarity:.2f})"),
        duration_ms=(time.perf_counter() - index_start) * 1000,
    )
    return match, detail


def try_index_layer(
    router: RoutingCore,
    query: str,
    candidates: list[dict[str, Any]],
) -> tuple[SkillRoute | None, LayerDetail]:
    """Try skill semantic index layer."""
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
                layer=RoutingLayer.SEMANTIC_INDEX,
                matched=False,
                reason="Skill semantic index not built (run 'vibe init' to build)",
                duration_ms=(time.perf_counter() - index_start) * 1000,
            )
        router._index_layer_cache = indexer.load_index()
        router._index_profile_tokens = _build_profile_token_index(router._index_layer_cache)
        cached = router._index_layer_cache

    index = cached
    if not index:
        return None, LayerDetail(
            layer=RoutingLayer.SEMANTIC_INDEX,
            matched=False,
            reason="Skill semantic index is empty",
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    profile_tokens_by_id_raw = getattr(router, "_index_profile_tokens", None)
    profile_tokens_by_id: dict[str, set[str]] = (
        profile_tokens_by_id_raw if isinstance(profile_tokens_by_id_raw, dict) else {}
    )
    query_tokens = _tokenize_query(query)

    # Namespace-aware hit threshold. External pack profiles are LLM-generated
    # per installed pack, dozens at a time, with heavily overlapping
    # vocabulary — a marginal bigram overlap with one is much weaker evidence
    # than the same overlap with a curated builtin/project profile, so packs
    # must clear a higher bar (index_external_match_threshold).
    ns_by_id = {str(c.get("id", "")): str(c.get("namespace", "")) for c in candidates}
    threshold = _cfg_float(router._config, "index_match_threshold")
    external_threshold = max(
        threshold,
        _cfg_float(router._config, "index_external_match_threshold"),
    )

    def _threshold_for(skill_id: str) -> float:
        if ns_by_id.get(skill_id) in _TRUSTED_INDEX_NAMESPACES:
            return threshold
        return external_threshold

    # Eligibility-first selection over INSTALLED skills only: each profile
    # competes only if it clears its own bar; the winner is the highest
    # scorer among the eligible. Stale profiles for uninstalled skills are
    # skipped up front (same installed-only invariant as the embedding
    # fallback) — a stale winner would otherwise hard-miss at the candidate
    # check below and pre-empt the embedding fallback entirely.
    best_skill_id: str | None = None
    best_score = 0.0

    for skill_id in index:
        if skill_id not in ns_by_id:
            continue
        profile_tokens = profile_tokens_by_id.get(skill_id)
        if profile_tokens is None:
            # Cache miss for a profile (e.g. cache populated by older code path);
            # fall back to on-the-fly compute. Cheap once, persists for next time.
            profile_tokens = _build_profile_token_index({skill_id: index[skill_id]})[skill_id]
            profile_tokens_by_id[skill_id] = profile_tokens
        score = _score_overlap(query_tokens, profile_tokens)
        if score >= _threshold_for(skill_id) and score > best_score:
            best_score = score
            best_skill_id = skill_id

    if not best_skill_id:
        # Token overlap missed — try semantic embedding fallback when available.
        emb_match, emb_detail = _try_embedding_fallback(
            router, query, index, candidates, index_start
        )
        if emb_match is not None:
            return emb_match, emb_detail
        # Fallback ran but also missed; return its (more informative) detail.
        return None, emb_detail

    # Defensive: unreachable while the loop above filters to installed
    # candidates; kept so a future caller-side change degrades to a clean
    # no-match instead of routing to a skill that is not installed.
    candidate = next((c for c in candidates if c["id"] == best_skill_id), None)
    if not candidate:
        return None, LayerDetail(
            layer=RoutingLayer.SEMANTIC_INDEX,
            matched=False,
            reason=f"Index matched '{best_skill_id}' but skill not in candidates",
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    # Guarded skills (session-end, riper-workflow, ...) require explicit user
    # intent; token overlap alone must not select them. Treat a guarded
    # best-match without an explicit signal like a token miss: fall through
    # to the embedding fallback, which applies the same guard.
    if not router._triage_service.has_explicit_guard_signal(query, candidates, best_skill_id):
        emb_match, emb_detail = _try_embedding_fallback(
            router, query, index, candidates, index_start
        )
        if emb_match is not None:
            return emb_match, emb_detail
        return None, LayerDetail(
            layer=RoutingLayer.SEMANTIC_INDEX,
            matched=False,
            reason=(
                f"Index matched guarded skill '{best_skill_id}' but the query "
                f"carries no explicit signal for it"
            ),
            duration_ms=(time.perf_counter() - index_start) * 1000,
        )

    # Confidence: scale score [winner_threshold..1.0] → [0.65..0.95]
    # Lower bound 0.65 (vs SCENARIO's fixed 0.9) signals "weaker" match,
    # so a strong scenario keyword hit can still take precedence when it follows.
    # The scale starts at the winner's own bar (external skills clear a higher
    # one), so a marginal external hit is not inflated by the lower builtin bar.
    winner_threshold = _threshold_for(best_skill_id)
    confidence = 0.65 + (best_score - winner_threshold) / (1.0 - winner_threshold) * 0.30

    match = SkillRoute(
        skill_id=best_skill_id,
        confidence=round(confidence, 2),
        # Skill Semantic Index (token-overlap + embedding) — NOT AI Triage (LLM).
        # Has its own enum value since Phase 5 (was mislabeled AI_TRIAGE pre-v8.1).
        layer=RoutingLayer.SEMANTIC_INDEX,
        source=router._get_skill_source(best_skill_id, candidate.get("namespace", "builtin")),
        description=str(candidate.get("description", "")),
        metadata={
            "index_hit": True,
            "index_score": round(best_score, 3),
            "scenarios": index[best_skill_id].scenarios[:3],
        },
    )
    return match, LayerDetail(
        layer=RoutingLayer.SEMANTIC_INDEX,
        matched=True,
        reason=f"Index match: '{best_skill_id}' (score {best_score:.2f})",
        duration_ms=(time.perf_counter() - index_start) * 1000,
    )
