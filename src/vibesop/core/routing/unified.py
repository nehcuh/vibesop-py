"""Unified router - single entry point for all skill routing.

The UnifiedRouter delegates to independent layer handlers, each implementing
one matching strategy. Layers execute in priority order; the first confident
match wins.

Architecture:
    route() → [_try_explicit, _try_scenario, _try_ai_triage, _try_matchers]
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
import threading
import time
from pathlib import Path
from typing import Any, ClassVar

from vibesop.core.config import ConfigManager
from vibesop.core.config import RoutingConfig as ConfigRoutingConfig
from vibesop.core.exceptions import MatcherError
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
from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute
from vibesop.core.optimization import (
    CandidatePrefilter,
    PreferenceBooster,
    SkillClusterIndex,
)
from vibesop.core.routing.cache import CacheManager
from vibesop.core.routing.conflict import (
    ConfidenceGapStrategy,
    ConflictResolver,
    ExplicitOverrideStrategy,
    FallbackStrategy,
    NamespacePriorityStrategy,
    RecencyStrategy,
)
from vibesop.core.routing.explicit_layer import check_explicit_override
from vibesop.core.routing.layers import LayerResult
from vibesop.core.routing.matcher_pipeline import MatcherPipeline
from vibesop.core.routing.optimization_service import OptimizationService
from vibesop.core.routing.scenario_layer import load_scenarios, match_scenario
from vibesop.core.routing.triage_service import TriageService
from vibesop.llm.cost_tracker import TriageCostTracker

logger = logging.getLogger(__name__)


class UnifiedRouter:
    """Unified router for skill selection.

    Single entry point for all routing operations.
    Each layer is a clearly separated service that returns a LayerResult | None.

    Example:
        >>> router = UnifiedRouter()
        >>> result = router.route("扫描安全漏洞")
        >>> if result.has_match:
        ...     print(f"Matched: {result.primary.skill_id}")
    """

    _LAYER_PRIORITY: ClassVar[list[RoutingLayer]] = [
        RoutingLayer.EXPLICIT,
        RoutingLayer.SCENARIO,
        RoutingLayer.AI_TRIAGE,
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

        # Warm up matchers to prevent cold-start latency on first route()
        # This ensures EmbeddingMatcher model is loaded during initialization
        self._matchers_warmed = False

        self._optimization_config = self._config_manager.get_optimization_config()
        self._cluster_index = SkillClusterIndex()
        self._prefilter = CandidatePrefilter(cluster_index=self._cluster_index)

        # Production-grade conflict resolver
        self._conflict_resolver = ConflictResolver()
        self._conflict_resolver.add_strategy(ExplicitOverrideStrategy())
        self._conflict_resolver.add_strategy(
            ConfidenceGapStrategy(
                gap_threshold=self._optimization_config.clustering.confidence_gap_threshold,
            ),
        )
        self._conflict_resolver.add_strategy(NamespacePriorityStrategy())
        self._conflict_resolver.add_strategy(
            RecencyStrategy(
                storage_path=str(self.project_root / ".vibe" / "preferences.json"),
            ),
        )
        self._conflict_resolver.add_strategy(FallbackStrategy())

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

        # Explicitly init _llm for type checker and test mocking
        self._llm: Any | None = None

        # Build sub-services
        self._optimization_service = OptimizationService(
            config=self._config,
            optimization_config=self._optimization_config,
            preference_booster=self._preference_booster,
            cluster_index=self._cluster_index,
            conflict_resolver=self._conflict_resolver,
            get_instinct_learner=self._get_instinct_learner,
        )

        self._triage_service = TriageService(
            config=self._config,
            cost_tracker=self._cost_tracker,
            prefilter=self._prefilter,
            cache_manager=self._cache_manager,
            get_skill_source=self._get_skill_source,
        )

        self._matcher_pipeline = MatcherPipeline(
            matchers=self._matchers,
            config=self._config,
            optimization_config=self._optimization_config,
            prefilter=self._prefilter,
            optimization_service=self._optimization_service,
            get_skill_source=self._get_skill_source,
        )

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
        # Layer 0: Explicit Override
        yield self._try_explicit(query, candidates) or LayerResult(
            layer=RoutingLayer.EXPLICIT
        )

        # Layer 1: Scenario Pattern
        yield self._try_scenario(query, candidates) or LayerResult(
            layer=RoutingLayer.SCENARIO
        )

        # Layer 2: AI Triage
        yield self._try_ai_triage(query, candidates, context) or LayerResult(
            layer=RoutingLayer.AI_TRIAGE
        )

        # Layers 3-6: Matcher pipeline (keyword, tfidf, embedding, levenshtein)
        matcher_result = self._try_matcher_pipeline(query, candidates, context)
        yield matcher_result or LayerResult(layer=RoutingLayer.LEVENSHTEIN)

    # ================================================================
    # Layer 0: Explicit Override
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
    # Layer 1: Scenario Pattern
    # ================================================================

    def _try_scenario(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> LayerResult | None:
        scenarios = load_scenarios(self.project_root)
        scenario = match_scenario(query, scenarios)
        if not scenario:
            return None

        target_skill = scenario.get("skill")
        if not target_skill:
            return None

        candidate = next((c for c in candidates if c["id"] == target_skill), None)
        if not candidate:
            return None

        # Build alternatives from related skills in the same scenario
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
                        source=self._get_skill_source(rid, rel.get("namespace", "builtin")),
                        metadata={"scenario": scenario.get("scenario")},
                    )
                )

        return LayerResult(
            match=SkillRoute(
                skill_id=target_skill,
                confidence=0.9,
                layer=RoutingLayer.SCENARIO,
                source=self._get_skill_source(
                    target_skill, candidate.get("namespace", "builtin")
                ),
                metadata={"scenario": scenario.get("scenario")},
            ),
            alternatives=alternatives,
            layer=RoutingLayer.SCENARIO,
        )

    # ================================================================
    # Memory and instinct helpers
    # ================================================================

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
        except (OSError, ValueError, RuntimeError) as e:
            logger.debug(f"Failed to record routing decision: {e}")

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
    # Candidate management
    # ================================================================

    def score(
        self,
        query: str,
        _skill_id: str,
        candidate: dict[str, Any],
        context: RoutingContext | None = None,
    ) -> float:
        """Score a specific candidate against a query using the matcher pipeline."""
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
                # Initialize prefilter with dynamic namespace discovery
                # This eliminates hardcoded NAMESPACE_KEYWORDS limitation
                self._prefilter = CandidatePrefilter.from_candidates(
                    self._candidates_cache,
                    cluster_index=self._cluster_index,
                )
                # Sync the updated prefilter into the matcher pipeline so
                # that apply_prefilter uses the dynamically discovered namespaces.
                self._matcher_pipeline.set_prefilter(self._prefilter)
                # Warm up matchers to prevent cold-start latency
                # This loads EmbeddingMatcher model during initialization
                self._warm_up_matchers(self._candidates_cache)
            return self._candidates_cache

    def _warm_up_matchers(self, candidates: list[dict[str, Any]]) -> None:
        """Warm up matchers by initializing lazy-loaded components.

        This prevents cold-start latency on the first route() call by
        pre-loading heavy components like the EmbeddingMatcher model.
        """
        if self._matchers_warmed:
            return

        try:
            for _layer, matcher in self._matchers:
                try:
                    matcher.warm_up(candidates)
                except Exception as e:
                    logger.warning(
                        "Matcher %s warm-up failed: %s",
                        type(matcher).__name__,
                        e,
                    )
        finally:
            self._matchers_warmed = True

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

    # ================================================================
    # Backward compatibility proxies for extracted services
    # ================================================================

    def _try_ai_triage(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None = None,
    ) -> Any:
        # Sync mock LLM set by tests
        if self._llm is not None:  # type: ignore[reportPrivateUsage]
            self._triage_service._llm = self._llm  # type: ignore[reportPrivateUsage]
        return self._triage_service.try_ai_triage(query, candidates, context)

    def _prefilter_ai_triage_candidates(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        max_skills: int,
    ) -> list[dict[str, Any]]:
        return self._triage_service.prefilter_ai_triage_candidates(query, candidates, max_skills)

    def _build_ai_triage_prompt(self, query: str, skills_summary: str) -> str:
        return self._triage_service.build_ai_triage_prompt(query, skills_summary)

    def _init_llm_client(self) -> Any:
        return self._triage_service.init_llm_client()

    def _parse_ai_triage_response(self, response: str) -> dict[str, Any]:
        return self._triage_service.parse_ai_triage_response(response)

    def _try_matcher_pipeline(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
    ) -> Any:
        return self._matcher_pipeline.try_matcher_pipeline(query, candidates, context)

    def _apply_prefilter(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return self._matcher_pipeline.apply_prefilter(query, candidates)

    def _apply_optimizations(
        self,
        matches: Any,
        query: str,
        context: RoutingContext | None = None,
    ) -> Any:
        return self._optimization_service.apply_optimizations(matches, query, context)

    def _resolve_conflicts(self, matches: Any, query: str) -> Any:
        return self._optimization_service.resolve_conflicts(matches, query)

    def _apply_instinct_boost(
        self,
        matches: Any,
        query: str,
        context: RoutingContext | None,
    ) -> Any:
        return self._optimization_service.apply_instinct_boost(matches, query, context)

    def _ensure_cluster_index(self, candidates: list[dict[str, Any]]) -> None:
        self._optimization_service.ensure_cluster_index(candidates)


__all__ = [
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
    "UnifiedRouter",
]
