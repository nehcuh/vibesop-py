"""Unified router - single entry point for all skill routing.

The UnifiedRouter delegates to independent layer handlers, each implementing
one matching strategy. Layers execute in priority order; the first confident
match wins.

Architecture:
    route() → [_try_ai_triage, _try_explicit, _try_scenario, _try_matchers]
                                                        ↓
                              matcher loop: keyword → tfidf → embedding → levenshtein
                                                        ↓
                              optimization: prefilter → preference_boost → conflict_resolution

Example:
    >>> router = UnifiedRouter(project_root=".")
    >>> result = router.route("帮我调试数据库连接错误")
    >>> print(result.primary.skill_id)  # e.g., "systematic-debugging"
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, ClassVar, cast

from vibesop.core.config import ConfigManager
from vibesop.core.config import RoutingConfig as ConfigRoutingConfig
from vibesop.core.exceptions import LLMError, MatcherError
from vibesop.core.instinct import InstinctLearner
from vibesop.core.matching import (
    IMatcher,
    KeywordMatcher,
    LevenshteinMatcher,
    MatcherConfig,
    RoutingContext,
    TFIDFMatcher,
)
from vibesop.core.memory import MemoryManager
from vibesop.core.matching import MatchResult
from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute
from vibesop.core.optimization import (
    CandidatePrefilter,
    PreferenceBooster,
    SkillClusterIndex,
)
from vibesop.core.routing.cache import CacheManager
from vibesop.core.routing.conflict import (
    ConflictResolver,
    ConfidenceGapStrategy,
    ExplicitOverrideStrategy,
    FallbackStrategy,
    NamespacePriorityStrategy,
    RecencyStrategy,
)
from vibesop.core.routing.explicit_layer import check_explicit_override
from vibesop.core.routing.layers import LayerResult
from vibesop.core.routing.scenario_layer import load_scenarios, match_scenario
from vibesop.llm.cost_tracker import TriageCostTracker
from vibesop.llm.triage_prompts import TriagePromptRegistry

logger = logging.getLogger(__name__)


class UnifiedRouter:
    """Unified router for skill selection.

    Single entry point for all routing operations.
    Each layer is a clearly separated method that returns a LayerResult | None.

    Example:
        >>> router = UnifiedRouter()
        >>> result = router.route("扫描安全漏洞")
        >>> if result.has_match:
        ...     print(f"Matched: {result.primary.skill_id}")
    """

    _LAYER_PRIORITY: ClassVar[list[RoutingLayer]] = [
        RoutingLayer.AI_TRIAGE,
        RoutingLayer.EXPLICIT,
        RoutingLayer.SCENARIO,
        RoutingLayer.KEYWORD,
        RoutingLayer.TFIDF,
        RoutingLayer.EMBEDDING,
        RoutingLayer.LEVENSHTEIN,
    ]

    def __init__(
        self,
        project_root: str | Path = ".",
        config: ConfigRoutingConfig | ConfigManager | None = None,
    ):
        self.project_root = Path(project_root).resolve()

        if isinstance(config, ConfigManager):
            self._config_manager = config
        elif config is None:
            self._config_manager = ConfigManager(project_root=self.project_root)
        else:
            self._config_manager = self._create_config_manager_from_config(config)

        self._config: ConfigRoutingConfig = self._config_manager.get_routing_config()

        matcher_config = MatcherConfig(
            min_confidence=self._config.min_confidence,
            use_cache=self._config.use_cache,
        )

        self._matchers: list[tuple[RoutingLayer, IMatcher]] = [
            (RoutingLayer.KEYWORD, KeywordMatcher(matcher_config)),
            (RoutingLayer.TFIDF, TFIDFMatcher(matcher_config)),
        ]

        if self._config.enable_embedding:
            try:
                from vibesop.core.matching import EmbeddingMatcher

                self._matchers.append(
                    (RoutingLayer.EMBEDDING, EmbeddingMatcher(config=matcher_config))
                )
            except ImportError:
                pass

        self._matchers.append((RoutingLayer.LEVENSHTEIN, LevenshteinMatcher(matcher_config)))

        self._optimization_config = self._config_manager.get_optimization_config()
        self._cluster_index = SkillClusterIndex()
        self._cluster_built = False
        self._prefilter = CandidatePrefilter(cluster_index=self._cluster_index)

        # Production-grade conflict resolver (replaces zombie ConflictResolver framework)
        self._conflict_resolver = ConflictResolver()
        self._conflict_resolver.add_strategy(
            ExplicitOverrideStrategy(),
        )
        self._conflict_resolver.add_strategy(
            ConfidenceGapStrategy(
                gap_threshold=self._optimization_config.clustering.confidence_gap_threshold,
            ),
        )
        self._conflict_resolver.add_strategy(
            NamespacePriorityStrategy(),
        )
        self._conflict_resolver.add_strategy(
            RecencyStrategy(
                storage_path=str(self.project_root / ".vibe" / "preferences.json"),
            ),
        )
        self._conflict_resolver.add_strategy(
            FallbackStrategy(),
        )

        pref_config = self._optimization_config.preference_boost
        self._preference_booster = PreferenceBooster(
            enabled=self._optimization_config.enabled and pref_config.enabled,
            weight=pref_config.weight,
            min_samples=pref_config.min_samples,
            storage_path=str(self.project_root / ".vibe" / "preferences.json"),
        )

        # Memory and instinct systems for context-aware routing (lazy init)
        self._memory_manager: MemoryManager | None = None
        self._instinct_learner: InstinctLearner | None = None

        self._cache_manager = CacheManager(cache_dir=self.project_root / ".vibe" / "cache")
        self._candidates_cache: list[dict[str, Any]] | None = None
        self._cache_lock = threading.Lock()

        self._cost_tracker = TriageCostTracker(storage_dir=self.project_root / ".vibe")

        self._total_routes = 0
        self._layer_distribution: dict[str, int] = {}
        self._stats_lock = threading.Lock()

    def _create_config_manager_from_config(self, config: ConfigRoutingConfig) -> ConfigManager:
        manager = ConfigManager(project_root=self.project_root)
        for field_name in type(config).model_fields:
            value = getattr(config, field_name)
            manager.set_cli_override(f"routing.{field_name}", value)
        return manager

    # ================================================================
    # Main routing entry point
    # ================================================================

    def route(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
    ) -> RoutingResult:
        """Route a query to the best matching skill.

        Executes layers in priority order. The first confident match wins.
        Integrates memory and instinct for context-aware routing.
        Records the full routing path for observability and debugging.
        """
        start_time = time.perf_counter()
        self._total_routes += 1

        # Enrich context with memory if available
        context = self._enrich_context(context)

        if candidates is None:
            candidates = self._get_cached_candidates()

        routing_path: list[RoutingLayer] = []
        for layer_result in self._execute_layers(query, candidates, context):
            routing_path.append(layer_result.layer)
            if layer_result.match is not None:
                self._record_layer(layer_result.layer)
                # Record this routing decision for memory/learning
                self._record_routing_decision(query, layer_result.match, context)
                return self._build_result(
                    query=query,
                    primary=layer_result.match,
                    alternatives=layer_result.alternatives,
                    routing_path=routing_path,
                    start_time=start_time,
                )

        duration_ms = (time.perf_counter() - start_time) * 1000
        self._record_layer(RoutingLayer.NO_MATCH)
        return RoutingResult(
            primary=None,
            alternatives=[],
            routing_path=routing_path,
            query=query,
            duration_ms=duration_ms,
        )

    def _execute_layers(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
    ):
        """Generator that yields LayerResults from each layer in priority order.

        Always yields a LayerResult so that route() can track the full decision path.
        """
        # Layer 0: AI Triage
        yield self._try_ai_triage(query, candidates, context) or LayerResult(
            layer=RoutingLayer.AI_TRIAGE
        )

        # Layer 1: Explicit Override
        yield self._try_explicit(query, candidates) or LayerResult(
            layer=RoutingLayer.EXPLICIT
        )

        # Layer 2: Scenario Pattern
        yield self._try_scenario(query, candidates) or LayerResult(
            layer=RoutingLayer.SCENARIO
        )

        # Layers 3-6: Matcher pipeline (keyword, tfidf, embedding, levenshtein)
        matcher_result = self._try_matcher_pipeline(query, candidates, context)
        yield matcher_result or LayerResult(layer=RoutingLayer.LEVENSHTEIN)

    # ================================================================
    # Layer 0: AI Triage
    # ================================================================

    def _try_ai_triage(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None = None,
    ) -> LayerResult | None:
        if not self._config.enable_ai_triage:
            return None

        if not hasattr(self, "_llm"):
            self._llm = self._init_llm_client()

        if self._llm is None or not self._llm.configured():
            return None

        # Budget enforcement
        budget = getattr(self._config, "ai_triage_budget_monthly", 5.0)
        if budget > 0:
            monthly_cost = self._cost_tracker.get_monthly_cost()
            if monthly_cost >= budget:
                logger.debug(
                    f"AI triage skipped: monthly budget exhausted ({monthly_cost:.4f}/{budget:.4f} USD)"
                )
                return None
            if monthly_cost >= budget * 0.9:
                logger.warning(
                    f"AI triage budget at {monthly_cost:.4f}/{budget:.4f} USD (90%+)"
                )

        # Cost control: pre-filter candidates with keyword matcher before sending to LLM
        max_skills = self._config.ai_triage_max_skills
        triage_candidates = self._prefilter_ai_triage_candidates(query, candidates, max_skills)

        # Build augmented query with memory context
        augmented_query = query
        if context and context.recent_queries and (
            len(query) < 20 or any(
                p in query.lower() for p in ("还是", "再", "继续", "也", "另外", "还有")
            )
        ):
            augmented_query = "Conversation:\n" + "\n".join(
                f"- {q}" for q in context.recent_queries[-3:]
            ) + f"\nCurrent request: {query}"

        cache_key = f"ai_triage:{augmented_query}"
        cached = self._get_cache(cache_key)
        if cached:
            return LayerResult(match=cached, layer=RoutingLayer.AI_TRIAGE)

        skills_summary = "\n".join(
            f"- {c['id']}: {c.get('intent', c.get('description', 'N/A'))}"
            for c in triage_candidates
        )

        prompt = self._build_ai_triage_prompt(augmented_query, skills_summary)

        try:
            response = self._llm.call(
                prompt=prompt,
                max_tokens=self._config.ai_triage_max_tokens,
                temperature=0.1,
            )
            parsed = self._parse_ai_triage_response(response.content)
            skill_id = parsed.get("skill_id")
            parsed_confidence = parsed.get("confidence")

            # Record cost if enabled
            log_calls = getattr(self._config, "ai_triage_log_calls", True)
            if log_calls:
                input_tokens = getattr(response, "input_tokens", None)
                output_tokens = getattr(response, "output_tokens", None)
                tokens_used = getattr(response, "tokens_used", None)
                if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
                    # Fallback to tokens_used if split counts aren't available
                    if isinstance(tokens_used, int):
                        input_tokens = tokens_used
                        output_tokens = 0
                    else:
                        input_tokens = 0
                        output_tokens = 0
                self._cost_tracker.record(
                    model=getattr(response, "model", "unknown"),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    query=query,
                    selected_skill=skill_id,
                )

            if skill_id:
                candidate = next((c for c in candidates if c["id"] == skill_id), None)
                if candidate:
                    source = self._get_skill_source(skill_id, candidate.get("namespace", "builtin"))
                    # Dynamic confidence: structured JSON gets higher trust than regex fallback
                    confidence = 0.88 if parsed.get("structured") else 0.82
                    if isinstance(parsed_confidence, (int, float)) and 0.0 <= float(parsed_confidence) <= 1.0:
                        confidence = float(parsed_confidence)
                    result = SkillRoute(
                        skill_id=skill_id,
                        confidence=confidence,
                        layer=RoutingLayer.AI_TRIAGE,
                        source=source,
                        metadata={
                            "ai_triage": True,
                            "structured": parsed.get("structured", False),
                            "model": getattr(response, "model", "unknown"),
                            "candidates_sent": len(triage_candidates),
                        },
                    )
                    self._set_cache(cache_key, result.to_dict())
                    return LayerResult(match=result, layer=RoutingLayer.AI_TRIAGE)
        except (OSError, LLMError, ValueError, RuntimeError, Exception) as e:
            logger.debug(f"AI triage failed, falling through to next layer: {e}")

        return None

    def _prefilter_ai_triage_candidates(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        max_skills: int,
    ) -> list[dict[str, Any]]:
        """Pre-filter candidates for AI Triage using fast keyword matching.

        Instead of sending all candidates to the LLM (wasteful), we use the
        KeywordMatcher to rank them by relevance and only send the top N.
        """
        if len(candidates) <= max_skills:
            return candidates

        from vibesop.core.matching import KeywordMatcher, MatcherConfig

        matcher_config = MatcherConfig(
            min_confidence=0.0,
            use_cache=False,
        )
        matcher = KeywordMatcher(matcher_config)
        matches = matcher.match(query, candidates, top_k=max_skills)
        matched_ids = {m.skill_id for m in matches}

        # Preserve original order for matched candidates, then backfill if needed
        prefiltered = [c for c in candidates if c["id"] in matched_ids]
        if len(prefiltered) < max_skills:
            remaining = [c for c in candidates if c["id"] not in matched_ids]
            prefiltered.extend(remaining[: max_skills - len(prefiltered)])

        return prefiltered[:max_skills]

    def _build_ai_triage_prompt(self, query: str, skills_summary: str) -> str:
        """Build a structured prompt for AI triage."""
        version = getattr(self._config, "ai_triage_prompt_version", "v2")
        return TriagePromptRegistry.render(
            query=query,
            skills_summary=skills_summary,
            version=version,
        )

    def _init_llm_client(self):
        """Initialize LLM client for AI triage."""
        # Allow explicit disable via env var
        if os.getenv("VIBE_AI_TRIAGE_ENABLED", "").lower() in ("0", "false", "no"):
            return None

        try:
            from vibesop.llm.factory import create_from_env

            llm = create_from_env()
            return llm if llm.configured() else None
        except (ImportError, OSError) as e:
            logger.debug(f"Failed to initialize LLM client: {e}")
            return None

    def _parse_ai_triage_response(self, response: str) -> dict[str, Any]:
        """Parse AI Triage response with structured JSON priority + regex fallback.

        Returns a dict with:
            - skill_id: str | None
            - confidence: float | None
            - structured: bool (whether JSON was successfully parsed)
        """
        import json

        result: dict[str, Any] = {"skill_id": None, "confidence": None, "structured": False}

        # Try JSON first
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Strip markdown code fences
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        if cleaned.startswith("{"):
            try:
                data = json.loads(cleaned)
                if isinstance(data, dict):
                    data = cast(dict[str, Any], data)
                    result["skill_id"] = data.get("skill_id") if isinstance(data.get("skill_id"), str) else None
                    result["confidence"] = data.get("confidence")
                    result["structured"] = True
                    return result
            except (json.JSONDecodeError, ValueError):
                pass

        # Regex fallback
        if match := re.search(r"```(?:json)?\s*([\w/-]+)```", response):
            result["skill_id"] = match.group(1).strip()
            return result
        if match := re.search(r"^[\w/-]{3,}", response.strip(), re.MULTILINE):
            result["skill_id"] = match.group(0).strip()
            return result

        return result

    # ================================================================
    # Layer 1: Explicit Override
    # ================================================================

    def _try_explicit(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> LayerResult | None:
        explicit_skill, cleaned_query = check_explicit_override(query, candidates)
        if not explicit_skill:
            return None

        candidate = next((c for c in candidates if c["id"] == explicit_skill), None)
        if not candidate:
            return None

        source = self._get_skill_source(explicit_skill, candidate.get("namespace", "builtin"))
        return LayerResult(
            match=SkillRoute(
                skill_id=explicit_skill,
                confidence=1.0,
                layer=RoutingLayer.EXPLICIT,
                source=source,
                metadata={"override": True, "cleaned_query": cleaned_query},
            ),
            layer=RoutingLayer.EXPLICIT,
        )

    # ================================================================
    # Layer 2: Scenario Pattern
    # ================================================================

    def _try_scenario(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> LayerResult | None:
        if not hasattr(self, "_scenarios"):
            self._scenarios = load_scenarios(self.project_root / "core" / "registry.yaml")

        scenario = match_scenario(query, self._scenarios)
        if not scenario:
            return None

        primary_id = scenario.get("primary")
        if not isinstance(primary_id, str):
            return None
        primary_candidate = next((c for c in candidates if c["id"] == primary_id), None)
        if not primary_candidate:
            return None

        source = self._get_skill_source(primary_id, primary_candidate.get("namespace", "builtin"))
        alternatives: list[SkillRoute] = []
        for alt in scenario.get("alternatives", []):
            alt_id = alt.get("skill", "").lstrip("/")
            alt_candidate = next((c for c in candidates if c["id"] == alt_id), None)
            if alt_candidate:
                alternatives.append(
                    SkillRoute(
                        skill_id=alt_id,
                        confidence=0.5,
                        layer=RoutingLayer.SCENARIO,
                        source=self._get_skill_source(
                            alt_id, alt_candidate.get("namespace", "builtin")
                        ),
                        metadata={"scenario": scenario.get("scenario")},
                    )
                )

        return LayerResult(
            match=SkillRoute(
                skill_id=primary_id,
                confidence=0.8,
                layer=RoutingLayer.SCENARIO,
                source=source,
                metadata={"scenario": scenario.get("scenario")},
            ),
            alternatives=alternatives,
            layer=RoutingLayer.SCENARIO,
        )

    # ================================================================
    # Layers 3-6: Matcher Pipeline (keyword, tfidf, embedding, levenshtein)
    # ================================================================

    def _try_matcher_pipeline(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
    ) -> LayerResult | None:
        filtered = self._apply_prefilter(query, candidates)
        self._ensure_cluster_index(filtered)

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

                primary_match, alternatives = self._apply_optimizations(matches, query, context)

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

    def _apply_prefilter(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if self._optimization_config.enabled and self._optimization_config.prefilter.enabled:
            return self._prefilter.filter(query, candidates)
        return candidates

    def _ensure_cluster_index(self, candidates: list[dict[str, Any]]) -> None:
        if (
            self._optimization_config.enabled
            and self._optimization_config.clustering.enabled
            and not self._cluster_built
            and len(candidates) >= self._optimization_config.clustering.min_skills_for_clustering
        ):
            self._cluster_index.build(candidates)
            self._cluster_built = True

    def _get_memory_manager(self) -> MemoryManager:
        if self._memory_manager is None:
            self._memory_manager = MemoryManager(
                storage_dir=self.project_root / ".vibe" / "memory"
            )
        return self._memory_manager

    def _get_instinct_learner(self) -> InstinctLearner:
        if self._instinct_learner is None:
            self._instinct_learner = InstinctLearner(
                storage_path=self.project_root / ".vibe" / "instincts.jsonl"
            )
        return self._instinct_learner

    def _enrich_context(self, context: RoutingContext | None) -> RoutingContext:
        """Enrich routing context with memory and recent conversation history."""
        if context is None:
            context = RoutingContext()

        # If no conversation_id set, try to use active conversation from memory
        if not context.conversation_id:
            active_id = self._get_memory_manager().get_active_conversation_id()
            if active_id:
                context.conversation_id = active_id

        # Load recent queries from memory if not already provided
        if context.conversation_id and not context.recent_queries:
            context.recent_queries = self._get_memory_manager().get_recent_queries(
                context.conversation_id, limit=3
            )

        return context

    def _apply_instinct_boost(
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
            len(query) < 15 or any(
                p in query.lower()
                for p in ("还是", "再", "继续", "也", "另外", "还有", "不行", "不对")
            )
        ):
            search_query = " ".join([*context.recent_queries[-2:], query])

        instincts = self._get_instinct_learner().find_matching(search_query, min_confidence=0.6)
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

    def _record_routing_decision(
        self,
        query: str,
        match: SkillRoute,
        context: RoutingContext | None,
    ) -> None:
        """Record successful routing decision to memory and instinct systems."""
        try:
            # Add to memory conversation if available
            if context and context.conversation_id:
                self._get_memory_manager().add_assistant_message(
                    context.conversation_id,
                    f"Routed to {match.skill_id} (confidence: {match.confidence:.2f})",
                    metadata={"skill_id": match.skill_id, "layer": match.layer.value},
                )

            # Extract a simple instinct: query pattern -> skill suggestion
            # Only record if query is non-trivial and confidence is high
            if match.confidence >= 0.7 and len(query) > 5:
                self._get_instinct_learner().learn(
                    pattern=query.lower(),
                    action=f"suggest {match.skill_id} skill",
                    context=match.layer.value,
                    tags=["routing", "auto_extracted"],
                    source="auto_routing",
                )
        except Exception as e:
            logger.debug(f"Failed to record routing decision: {e}")

    def _apply_optimizations(
        self,
        matches: list[MatchResult],
        query: str,
        context: RoutingContext | None = None,
    ) -> tuple[MatchResult, list[MatchResult]]:
        """Apply preference boost, instinct boost, and production conflict resolution."""
        if self._optimization_config.enabled and self._optimization_config.preference_boost.enabled:
            matches = self._preference_booster.boost(matches, query)

        # Apply instinct-based boosting
        matches = self._apply_instinct_boost(matches, query, context)

        if len(matches) <= 1:
            return matches[0], [] if len(matches) <= 1 else matches[1 : self._config.max_candidates + 1]

        return self._resolve_conflicts(matches, query)

    def _resolve_conflicts(self, matches: list[MatchResult], query: str) -> tuple[MatchResult, list[MatchResult]]:
        """Resolve conflicts using the production ConflictResolver framework."""
        resolution = self._conflict_resolver.resolve(
            matches,
            query,
            context={},
        )

        if resolution.primary:
            primary_match = next(
                (m for m in matches if getattr(m, "skill_id", str(m)) == resolution.primary),
                matches[0],
            )
            alternative_ids = set(resolution.alternatives)
            alternatives = [
                m for m in matches
                if getattr(m, "skill_id", str(m)) in alternative_ids
                and getattr(m, "skill_id", str(m)) != resolution.primary
            ][: self._config.max_candidates]
        else:
            primary_match = matches[0]
            alternatives = matches[1 : self._config.max_candidates + 1]

        return primary_match, alternatives

    # ================================================================
    # Result building
    # ================================================================

    def _build_result(
        self,
        query: str,
        primary: SkillRoute,
        alternatives: list[SkillRoute],
        routing_path: list[RoutingLayer],
        start_time: float,
    ) -> RoutingResult:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return RoutingResult(
            primary=primary,
            alternatives=alternatives,
            routing_path=routing_path,
            query=query,
            duration_ms=duration_ms,
        )

    # ================================================================
    # Cache helpers
    # ================================================================

    def _get_cache(self, key: str) -> SkillRoute | None:
        data = self._cache_manager.get(key)
        if data:
            try:
                return SkillRoute(
                    skill_id=data["skill_id"],
                    confidence=data["confidence"],
                    layer=RoutingLayer(data["layer"]),
                    source=data["source"],
                    metadata=data.get("metadata", {}),
                )
            except (KeyError, TypeError) as e:
                logger.debug(f"Failed to deserialize cached SkillRoute: {e}")
        return None

    def _set_cache(self, key: str, data: dict[str, Any]) -> None:
        self._cache_manager.set(key, data, ttl=3600)

    # ================================================================
    # Candidate management
    # ================================================================

    def score(
        self,
        query: str,
        _skill_id: str,
        candidate: dict[str, Any],
        context: RoutingContext | None = None,
    ) -> float:
        for _, matcher in self._matchers:
            try:
                return matcher.score(query, candidate, context)
            except (OSError, ValueError, KeyError, MatcherError) as e:
                logger.debug(f"Matcher {type(matcher).__name__}.score() failed: {e}, trying next")
                continue
        return 0.0

    def get_candidates(self, _query: str = "") -> list[dict[str, Any]]:
        return self._get_candidates(_query)

    def _get_candidates(self, _query: str = "") -> list[dict[str, Any]]:
        from vibesop.core.skills import SkillLoader

        if not hasattr(self, "_skill_loader"):
            search_paths = [
                self.project_root / "core" / "skills",
                self.project_root / ".vibe" / "skills",
                Path.home() / ".claude" / "skills",
                Path.home() / ".config" / "skills",
            ]
            self._skill_loader = SkillLoader(
                project_root=self.project_root,
                search_paths=search_paths,
            )

        definitions = self._skill_loader.discover_all()
        candidates: list[dict[str, Any]] = []
        for _skill_id, definition in definitions.items():
            metadata = definition.metadata
            candidates.append(
                {
                    "id": metadata.id,
                    "name": metadata.name,
                    "description": metadata.description,
                    "intent": metadata.intent,
                    "keywords": metadata.tags or [],
                    "triggers": [metadata.trigger_when] if metadata.trigger_when else [],
                    "namespace": metadata.namespace,
                    "source": self._get_skill_source(metadata.id, metadata.namespace),
                }
            )
        return candidates

    def _get_cached_candidates(self) -> list[dict[str, Any]]:
        if self._candidates_cache is not None:
            return self._candidates_cache
        with self._cache_lock:
            if self._candidates_cache is None:
                self._candidates_cache = self._get_candidates()
            return self._candidates_cache

    def reload_candidates(self) -> int:
        self._candidates_cache = None
        return len(self._get_cached_candidates())

    # ================================================================
    # Utilities
    # ================================================================

    def _get_skill_source(self, _skill_id: str, namespace: str) -> str:
        """Determine skill source based on namespace.

        Project skills > external skills > built-in fallback.
        No hardcoded pack names — any unknown namespace is external.
        """
        if namespace == "project":
            return "project"
        if namespace == "builtin":
            return "builtin"
        return "external"

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "type": "unified",
            "layers": [layer.value for layer in self._LAYER_PRIORITY],
            "matchers": [
                {"layer": layer.value, "matcher": type(m).__name__} for layer, m in self._matchers
            ],
            "config": {
                "min_confidence": self._config.min_confidence,
                "auto_select_threshold": self._config.auto_select_threshold,
                "enable_ai_triage": self._config.enable_ai_triage,
                "enable_embedding": self._config.enable_embedding,
            },
        }

    def _record_layer(self, layer: RoutingLayer) -> None:
        with self._stats_lock:
            self._layer_distribution[layer.value] = self._layer_distribution.get(layer.value, 0) + 1

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_routes": self._total_routes,
            "layer_distribution": dict(self._layer_distribution),
            "cache_dir": str(self.project_root / ".vibe" / "cache"),
            "ai_triage": self.get_ai_triage_stats(),
        }

    def get_ai_triage_stats(self) -> dict[str, Any]:
        """Get AI Triage usage and cost statistics."""
        stats = self._cost_tracker.get_stats(days=30)
        budget = getattr(self._config, "ai_triage_budget_monthly", 5.0)
        return {
            **stats,
            "budget_monthly_usd": budget,
            "budget_remaining_usd": round(max(0.0, budget - stats["total_cost_usd"]), 6),
        }

    def record_selection(self, skill_id: str, query: str, was_helpful: bool = True) -> None:
        learner = self._preference_booster.get_learner()
        learner.record_selection(skill_id, query, was_helpful)

    def get_preference_stats(self) -> dict[str, int | float | str]:
        learner = self._preference_booster.get_learner()
        return learner.get_stats()

    def get_top_skills(self, limit: int = 5, min_selections: int = 2) -> list[Any]:
        learner = self._preference_booster.get_learner()
        return learner.get_top_skills(limit, min_selections)

    def clear_old_preferences(self, days: int = 90) -> int:
        learner = self._preference_booster.get_learner()
        return learner.clear_old_data(days)


__all__ = [
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
    "UnifiedRouter",
]
