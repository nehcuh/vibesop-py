# pyright: reportPrivateUsage=false
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

import atexit
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from vibesop.core.config import ConfigManager
from vibesop.core.config import RoutingConfig as ConfigRoutingConfig
from vibesop.core.exceptions import MatcherError
from vibesop.core.matching import (
    IMatcher,
    KeywordMatcher,
    LevenshteinMatcher,
    MatcherConfig,
    RoutingContext,
    TFIDFMatcher,
)
from vibesop.core.models import (
    LayerDetail,
    OrchestrationMode,
    OrchestrationResult,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)
from vibesop.core.optimization import (
    CandidatePrefilter,
    PreferenceBooster,
    SkillClusterIndex,
)
from vibesop.core.routing.cache import CacheManager
from vibesop.core.routing.candidate_manager import CandidateManager
from vibesop.core.routing.tracer import RoutingTracer
from vibesop.core.routing.conflict import (
    ConfidenceGapStrategy,
    ConflictResolver,
    ExplicitOverrideStrategy,
    FallbackStrategy,
    NamespacePriorityStrategy,
    RecencyStrategy,
)
from vibesop.core.routing.context_mixin import RouterContextMixin
from vibesop.core.routing.cost_tracker import TriageCostTracker
from vibesop.core.routing.degradation import DegradationManager
from vibesop.core.routing.matcher_pipeline import MatcherPipeline
from vibesop.core.routing.optimization_service import OptimizationService
from vibesop.core.routing.orchestration_mixin import RouterOrchestrationMixin
from vibesop.core.routing.result_mixin import RouterResultMixin
from vibesop.core.routing.stats_mixin import RouterStatsMixin
from vibesop.core.routing.triage_service import TriageService

if TYPE_CHECKING:
    from vibesop.core.instinct import InstinctLearner
    from vibesop.core.memory import MemoryManager
    from vibesop.core.orchestration import MultiIntentDetector, PlanBuilder, PlanTracker
    from vibesop.core.orchestration.task_decomposer import TaskDecomposer

logger = logging.getLogger(__name__)


class UnifiedRouter(
    RouterStatsMixin,
    RouterResultMixin,
    RouterOrchestrationMixin,
    RouterContextMixin,
):
    """Unified router for skill selection — single entry point for all routing.

    Layers execute in priority order; first confident match wins:
        EXPLICIT > SCENARIO > AI_TRIAGE > KEYWORD > TFIDF > EMBEDDING > LEVENSHTEIN > CUSTOM

    Example:
        >>> router = UnifiedRouter()
        >>> result = router.orchestrate("扫描安全漏洞")
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
        RoutingLayer.CUSTOM,
    ]
    _matchers: list[tuple[RoutingLayer, IMatcher]]

    def __init__(
        self,
        project_root: str | Path = ".",
        config: ConfigRoutingConfig | ConfigManager | None = None,
        skill_loader: Any | None = None,
        llm_factory: Any | None = None,
        prompt_builder: Any | None = None,
    ):
        self.project_root = Path(project_root).resolve()

        if isinstance(config, ConfigManager):
            self._config_manager = config
        elif config is None:
            self._config_manager = ConfigManager(project_root=self.project_root)
        else:
            self._config_manager = self._create_config_manager_from_config(config)

        self._config: ConfigRoutingConfig = self._config_manager.get_routing_config()
        self._llm_factory = llm_factory
        self._prompt_builder = prompt_builder
        if skill_loader is not None:
            self._skill_loader = skill_loader

        matcher_config = MatcherConfig(
            min_confidence=self._config.min_confidence,
            use_cache=self._config.use_cache,
        )

        self._matchers: list[tuple[RoutingLayer, IMatcher]] = [  # pyright: ignore[reportAttributeAccessIssue]
            (RoutingLayer.KEYWORD, KeywordMatcher(matcher_config)),
            (RoutingLayer.TFIDF, TFIDFMatcher(matcher_config)),
        ]

        self._embedding_enabled = self._config.enable_embedding
        if self._embedding_enabled:
            from vibesop.core.matching.lazy_matcher import LazyEmbeddingMatcher

            self._matchers.append((RoutingLayer.EMBEDDING, LazyEmbeddingMatcher(matcher_config)))  # pyright: ignore[reportArgumentType]

        self._matchers.append((RoutingLayer.LEVENSHTEIN, LevenshteinMatcher(matcher_config)))  # pyright: ignore[reportArgumentType]

        # Load custom matcher plugins from .vibe/matchers/
        self._plugin_registry = None
        try:
            from vibesop.core.matching.plugin import MatcherPluginRegistry

            self._plugin_registry = MatcherPluginRegistry(self.project_root)
            for plugin in self._plugin_registry.list_plugins():
                self._matchers.append((RoutingLayer.CUSTOM, plugin))  # pyright: ignore[reportArgumentType]
        except ImportError:
            pass

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

        # Cached SkillRecommender instance (from integrations)
        self._skill_recommender: Any = None

        # Memory and instinct systems for context-aware routing (lazy init)
        self._memory_manager: MemoryManager | None = None
        self._instinct_learner: InstinctLearner | None = None

        self._cache_manager = CacheManager(cache_dir=self.project_root / ".vibe" / "cache")
        self._candidate_manager = CandidateManager(self.project_root)

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
            llm_factory=llm_factory,
            prompt_builder=prompt_builder,
        )

        self._matcher_pipeline = MatcherPipeline(
            matchers=self._matchers,
            config=self._config,
            optimization_config=self._optimization_config,
            prefilter=self._prefilter,
            optimization_service=self._optimization_service,
            get_skill_source=self._get_skill_source,
        )

        self._degradation_manager = DegradationManager(self._config)

        self._total_routes = 0
        self._layer_distribution: dict[str, int] = {}
        self._stats_lock = threading.Lock()

        self._scenario_cache: dict[str, Any] | None = None

        # Project analyzer cache (expensive: ~2s filesystem scan)
        self._project_analyzer: Any | None = None

        # Orchestration components (lazy init)
        self._multi_intent_detector: MultiIntentDetector | None = None
        self._task_decomposer: TaskDecomposer | None = None
        self._plan_builder: PlanBuilder | None = None
        self._plan_tracker: PlanTracker | None = None

        # Session context for multi-turn state persistence (lazy init)
        self._session_context = None

        # Routing tracer for per-layer diagnostic traces
        self._tracer = RoutingTracer(
            enabled=False,
            traces_dir=self.project_root / ".vibe" / "traces",
        )

        # Flush usage buffer on normal exit to prevent data loss.
        # Use a weak reference so the atexit handler does not keep the
        # CandidateManager (and thus the router) alive indefinitely.
        import weakref

        _cm_ref = weakref.ref(self._candidate_manager)

        def _flush_usage_buffer() -> None:
            cm = _cm_ref()
            if cm is not None:
                cm._flush_usage_buffer()

        atexit.register(_flush_usage_buffer)

        # Router-level coarse lock for thread safety
        self._route_lock = threading.Lock()

    # ================================================================
    # Candidate and matcher lifecycle
    # ================================================================

    def _get_cached_candidates(self) -> list[dict[str, Any]]:
        """Get cached candidates, initializing prefilter and warming matchers on first call."""
        candidates = self._candidate_manager.get_cached_candidates()
        if not self._matchers_warmed:
            self._prefilter = CandidatePrefilter.from_candidates(
                candidates,
                cluster_index=self._cluster_index,
            )
            self._matcher_pipeline.set_prefilter(self._prefilter)
            self._warm_up_matchers(candidates)
        return candidates

    def _warm_up_matchers(self, candidates: list[dict[str, Any]]) -> None:
        if self._matchers_warmed:
            return
        try:
            for _layer, matcher in self._matchers:
                try:
                    matcher.warm_up(candidates)
                except (OSError, RuntimeError, ValueError, ImportError) as e:
                    logger.warning(
                        "Matcher %s warm-up failed: %s",
                        type(matcher).__name__,
                        e,
                    )
        finally:
            self._matchers_warmed = True

    def reload_candidates(self) -> int:
        return self._candidate_manager.reload()

    def invalidate_project_cache(self) -> None:
        self._project_analyzer = None

    def _get_skill_source(self, _skill_id: str, namespace: str) -> str:
        if namespace == "project":
            return "project"
        if namespace == "builtin":
            return "builtin"
        return "external"

    def get_candidates(self, _query: str = "") -> list[dict[str, Any]]:
        return self._candidate_manager.get_candidates()

    def _get_candidates(self, _query: str = "") -> list[dict[str, Any]]:
        return self.get_candidates(_query)

    def _build_decomposition_skills(
        self,
        candidates: list[dict[str, Any]] | None = None,
        limit: int = 50,
        query: str | None = None,
    ) -> list[str]:
        """Build the 'skill_id: description' list fed to TaskDecomposer.

        Centralized here so orchestrate(), agent.decompose(), agent.build_plan(),
        and `vibe decompose` use the exact same skill catalog. When no skill list
        reaches the LLM, the decomposer can't pre-assign skill_id and PlanBuilder
        falls back to lightweight (skip_ai_triage) routing — which causes the
        "all sub-tasks → wrong skill" symptom.

        When *query* is provided, candidates are relevance-ranked so the most
        pertinent skills appear first (and within the limit).  This prevents
        generic skills from crowding out specialized ones when the catalog is
        large.
        """
        skill_candidates = candidates or self._get_cached_candidates()

        if query:
            query_lower = query.lower()
            # Extract simple tokens (words >= 2 chars)
            import re
            tokens = set(re.findall(r"[a-zA-Z\-]{2,}", query_lower))
            # Also include common CJK analysis keywords as whole substrings
            cjk_keywords = ["分析", "审查", "设计", "调试", "优化", "规划", "测试", " review", " analyze", " debug", " design", " plan", " test"]

            def _relevance_score(c: dict[str, Any]) -> float:
                score = 0.0
                cid = c.get("id", "").lower()
                desc = c.get("description", "").lower()
                intent = c.get("intent", "").lower()
                keywords = [k.lower() for k in c.get("keywords", [])]
                triggers = [t.lower() for t in c.get("triggers", [])]

                # ID match (highest weight)
                for t in tokens:
                    if t in cid:
                        score += 3.0

                # Keyword / trigger match
                for t in tokens:
                    if any(t in k for k in keywords):
                        score += 2.5
                    if any(t in tr for tr in triggers):
                        score += 2.0

                # Description / intent match
                for t in tokens:
                    if t in desc:
                        score += 1.0
                    if t in intent:
                        score += 1.0

                # CJK / common substrings
                for kw in cjk_keywords:
                    kw_lower = kw.lower().strip()
                    if kw_lower in cid or kw_lower in desc or kw_lower in intent:
                        score += 2.0
                    if any(kw_lower in k for k in keywords):
                        score += 2.0

                # Boost P0 skills slightly so high-priority builtins stay visible
                if c.get("priority") == "P0":
                    score += 0.5

                return score

            skill_candidates = sorted(
                skill_candidates,
                key=_relevance_score,
                reverse=True,
            )

        return [
            f"{c['id']}: {c.get('description', c.get('intent', 'N/A'))}"
            for c in skill_candidates[:limit]
        ]

    # ================================================================
    # Main routing entry point
    # ================================================================

    def _single_skill_route(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
    ) -> RoutingResult:
        """Internal: route a query to the best matching skill."""
        start_time = time.perf_counter()
        with self._stats_lock:
            self._total_routes += 1

        # Start routing trace if enabled
        self._tracer.start_trace(query, mode="single")

        original_query = query
        conversation = None
        if context and context.conversation_id:
            from vibesop.core.conversation import ConversationContext

            conversation = ConversationContext(
                conversation_id=context.conversation_id,
                storage_dir=self.project_root / ".vibe" / "conversations",
            )
            enriched = conversation.build_contextual_query(query)
            if enriched:
                query = enriched

        context = self._enrich_context(context, query)

        if candidates is None:
            candidates = self._get_cached_candidates()

        candidates, deprecated_warnings = self._candidate_manager.filter_routable(candidates)

        routing_path: list[RoutingLayer] = []
        layer_details: list[LayerDetail] = []

        result = self._try_layers(
            query, candidates, context, routing_path, layer_details,
            start_time, deprecated_warnings, conversation, original_query,
        )
        if result is not None:
            trace = self._tracer.finish_trace(
                final_skill=result.primary.skill_id if result.primary else None,
                final_confidence=result.primary.confidence if result.primary else 0.0,
                final_layer=result.primary.layer.value if result.primary else None,
                alternatives=[a.to_dict() for a in result.alternatives],
            )
            self._tracer.save(trace)
            return result

        duration_ms = (time.perf_counter() - start_time) * 1000
        final_result = self._finalize_no_match(
            query, original_query, candidates, context,
            routing_path, layer_details, duration_ms,
        )
        trace = self._tracer.finish_trace(
            final_skill=None,
            final_confidence=0.0,
            final_layer="no_match",
        )
        self._tracer.save(trace)
        return final_result

    def _try_layers(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
        routing_path: list[RoutingLayer],
        layer_details: list[LayerDetail],
        start_time: float,
        deprecated_warnings: list[str] | None,
        conversation: Any,
        original_query: str,
    ) -> RoutingResult | None:
        from vibesop.core.routing import _layers, _pipeline

        # Layer 0: Explicit Override (always first)
        match, detail = _layers.try_explicit_layer(self, query, candidates)  # pyright: ignore[reportArgumentType]
        routing_path.append(RoutingLayer.EXPLICIT)
        layer_details.append(detail)
        self._tracer.record_layer(RoutingLayer.EXPLICIT, detail, len(candidates))
        if match:
            self._record_layer(RoutingLayer.EXPLICIT)
            return self._build_match_result(
                query, match, [], routing_path, layer_details,
                start_time, deprecated_warnings, conversation, original_query, context,
            )

        use_keyword = self._should_use_keyword_routing(query, context)

        # Step 1: Early layers (scenario+index best-of for keyword, index only for LLM)
        early_match = self._try_early_layers(
            query, candidates, routing_path, layer_details, use_keyword
        )
        if early_match is not None:
            self._record_layer(early_match.layer)
            return self._build_match_result(
                query, early_match, [], routing_path, layer_details,
                start_time, deprecated_warnings, conversation, original_query, context,
            )

        # Step 2: AI Triage (force for long/LLM queries, normal for keyword)
        match, detail = _layers.try_ai_triage_layer(
            self, query, candidates, context,  # pyright: ignore[reportArgumentType]
            force=not use_keyword,
        )
        routing_path.append(RoutingLayer.AI_TRIAGE)
        layer_details.append(detail)
        self._tracer.record_layer(RoutingLayer.AI_TRIAGE, detail, len(candidates))
        if match and match.confidence >= self._config.min_confidence:
            self._record_layer(RoutingLayer.AI_TRIAGE)
            return self._build_match_result(
                query, match, [], routing_path, layer_details,
                start_time, deprecated_warnings, conversation, original_query, context,
            )

        # Step 3: Matcher pipeline (shared fallback)
        primary, alternatives, detail = _pipeline.run_matcher_pipeline(
            self, query, candidates, context, collect_rejected=True
        )
        routing_path.append(detail.layer)
        layer_details.append(detail)
        self._tracer.record_layer(detail.layer, detail, len(candidates))
        if primary:
            self._record_layer(detail.layer)
            return self._build_match_result(
                query, primary, alternatives, routing_path, layer_details,
                start_time, deprecated_warnings, conversation, original_query,
            )

        return None

    def _try_early_layers(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        routing_path: list[RoutingLayer],
        layer_details: list[LayerDetail],
        use_keyword: bool,
    ) -> SkillRoute | None:
        """Try early layers: scenario+index best-of (keyword) or index alone (LLM)."""
        from vibesop.core.routing import _layers

        if use_keyword:
            # Scenario + Index best-of
            scen_match, scen_detail = _layers.try_scenario_layer(self, query, candidates)  # pyright: ignore[reportArgumentType]
            routing_path.append(RoutingLayer.SCENARIO)
            layer_details.append(scen_detail)
            self._tracer.record_layer(RoutingLayer.SCENARIO, scen_detail, len(candidates))

            idx_match, idx_detail = _layers.try_index_layer(self, query, candidates)  # pyright: ignore[reportArgumentType]
            routing_path.append(RoutingLayer.AI_TRIAGE)
            layer_details.append(idx_detail)
            self._tracer.record_layer(RoutingLayer.AI_TRIAGE, idx_detail, len(candidates))

            best = max(
                (m for m in (scen_match, idx_match) if m is not None),
                key=lambda m: m.confidence,
                default=None,
            )
            if best and best.confidence >= self._config.min_confidence:
                return best
        else:
            # Index standalone
            match, detail = _layers.try_index_layer(self, query, candidates)  # pyright: ignore[reportArgumentType]
            routing_path.append(RoutingLayer.AI_TRIAGE)
            layer_details.append(detail)
            self._tracer.record_layer(RoutingLayer.AI_TRIAGE, detail, len(candidates))
            if match and match.confidence >= self._config.min_confidence:
                return match

        return None

    def enable_trace(self) -> None:
        """Enable per-layer routing trace recording.

        When enabled, every route() call captures per-layer decisions
        and saves them to .vibe/traces/. Inspired by SkillTree's
        routing trace mode.
        """
        self._tracer.enabled = True

    def disable_trace(self) -> None:
        """Disable routing trace recording."""
        self._tracer.enabled = False

    @property
    def tracer(self) -> RoutingTracer:
        """Access the routing tracer for listing past traces."""
        return self._tracer

    def _should_use_keyword_routing(self, query: str, context: RoutingContext | None = None) -> bool:
        """Determine whether to use keyword-based routing or LLM semantic triage."""
        keyword_max_chars = getattr(self._config, "keyword_match_max_chars", 5)
        use_keyword = len(query) <= keyword_max_chars

        # Respect skip_ai_triage from context (used by PlanBuilder for sub-task routing)
        if context and getattr(context, "skip_ai_triage", False):
            return True

        llm_available = (
            self._llm is not None or self._triage_service._llm is not None
        ) and self._config.enable_ai_triage

        if not llm_available and self._config.enable_ai_triage:
            self._triage_service._llm = self._triage_service.init_llm_client()
            llm_available = (
                self._triage_service._llm is not None
                and self._triage_service._llm.configured()
            )

        if not use_keyword and not llm_available:
            use_keyword = True

        return use_keyword

    def _finalize_no_match(
        self,
        query: str,
        original_query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
        routing_path: list[RoutingLayer],
        layer_details: list[LayerDetail],
        duration_ms: float,
    ) -> RoutingResult:
        from vibesop.core.routing import _pipeline

        self._record_layer(RoutingLayer.NO_MATCH)

        if self._config.fallback_mode == "disabled":
            result = RoutingResult(
                primary=None,
                alternatives=[],
                routing_path=routing_path,
                layer_details=layer_details,
                query=query,
                duration_ms=duration_ms,
            )
        elif self._config.fallback_mode == "silent":
            nearest: list[SkillRoute] = []
            try:
                nearest_primary, nearest_alts, _ = _pipeline.run_matcher_pipeline(
                    self, query, candidates, context, collect_rejected=False
                )
                if nearest_primary:
                    nearest = [nearest_primary, *nearest_alts]
            except (RuntimeError, ValueError):
                pass
            result = RoutingResult(
                primary=None,
                alternatives=nearest,
                routing_path=routing_path,
                layer_details=layer_details,
                query=query,
                duration_ms=duration_ms,
            )
        else:
            result = self._build_fallback_result(
                query=query,
                candidates=candidates,
                routing_path=routing_path,
                layer_details=layer_details,
                duration_ms=duration_ms,
            )

        self._save_session_state(result, context)
        # Save conversation turn for multi-turn support
        if context and context.conversation_id:
            from vibesop.core.conversation import ConversationContext
            conversation = ConversationContext(
                conversation_id=context.conversation_id,
                storage_dir=self.project_root / ".vibe" / "conversations",
            )
            conversation.add_turn(
                original_query,
                skill_id=result.primary.skill_id if result.primary else None,
            )

        from vibesop.core.routing.perf_monitor import get_perf_monitor
        get_perf_monitor().record(
            result.duration_ms,
            result.primary.layer.value if result.primary else RoutingLayer.NO_MATCH.value,
        )
        return result


    def route(
        self,
        query: str,
        candidates: list[Any] | None = None,
        context: RoutingContext | None = None,
    ) -> RoutingResult:
        """Route a query to the best matching skill (single-skill fast path).

        For multi-intent queries, prefer orchestrate() which detects compound
        requests and builds an ExecutionPlan.

        Args:
            query: User's natural language query.
            candidates: Optional skill candidates list (uses cached if None).
            context: Optional routing context with conversation/memory state.

        Returns:
            RoutingResult with primary match or no-match sentinel.
        """
        return self._single_skill_route(query, candidates, context)

    def orchestrate(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
        callbacks: Any | None = None,
    ) -> OrchestrationResult:
        """Orchestrate a query — detect multi-intent and build execution plan if needed.

        Single-skill queries route directly. Multi-intent queries are decomposed
        into an ExecutionPlan with dependency-ordered steps.

        Args:
            query: User's natural language query.
            candidates: Optional skill candidates list.
            context: Optional routing context for conversation/memory state.
            callbacks: Optional orchestration callbacks for streaming progress.
        """
        from vibesop.core.orchestration.callbacks import (
            ErrorPolicy,
            NoOpCallbacks,
            OrchestrationPhase,
            PhaseInfo,
        )

        cb = callbacks if callbacks is not None else NoOpCallbacks()
        start_time = time.perf_counter()

        # 1. Single-skill routing (fast path)
        cb.on_phase_start(
            PhaseInfo(
                phase=OrchestrationPhase.ROUTING,
                message="Analyzing query for skill match...",
                progress=0.0,
            )
        )
        single_result = self._single_skill_route(query, candidates, context)
        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.ROUTING,
                message=f"Single-skill match: {single_result.primary.skill_id if single_result.primary else 'none'}",
                progress=0.2,
                metadata={
                    "primary_confidence": single_result.primary.confidence
                    if single_result.primary
                    else 0.0
                },
            )
        )

        # 2. Check if orchestration is enabled
        if not self._config.enable_orchestration:
            return self._to_orchestration_result(single_result, query)

        # 3. Multi-intent detection
        cb.on_phase_start(
            PhaseInfo(
                phase=OrchestrationPhase.DETECTION,
                message="Detecting multiple intents...",
                progress=0.2,
            )
        )
        detector = self._get_multi_intent_detector()
        should_decompose = detector.should_decompose(query, single_result, llm_client=self._llm)
        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.DETECTION,
                message=f"Multi-intent detected: {should_decompose}",
                progress=0.4,
                metadata={"should_decompose": should_decompose},
            )
        )

        if not should_decompose:
            return self._to_orchestration_result(single_result, query)

        # 4. Decompose into sub-tasks
        cb.on_phase_start(
            PhaseInfo(
                phase=OrchestrationPhase.DECOMPOSITION,
                message="Decomposing query into sub-tasks...",
                progress=0.4,
            )
        )
        decomposer = self._get_task_decomposer()
        try:
            skills = self._build_decomposition_skills(candidates, query=query)
            sub_tasks = decomposer.decompose(query, skills=skills)
        except Exception as e:
            policy = cb.on_phase_error(
                PhaseInfo(
                    phase=OrchestrationPhase.DECOMPOSITION,
                    message="Task decomposition failed",
                    progress=0.4,
                ),
                e,
                ErrorPolicy.ABORT,
            )
            if policy == ErrorPolicy.ABORT:
                return self._to_orchestration_result(single_result, query)
            sub_tasks = []

        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.DECOMPOSITION,
                message=f"Decomposed into {len(sub_tasks)} sub-tasks",
                progress=0.6,
                metadata={"sub_task_count": len(sub_tasks)},
            )
        )

        if len(sub_tasks) <= 1:
            return self._to_orchestration_result(single_result, query)

        # 5. Build execution plan
        cb.on_phase_start(
            PhaseInfo(
                phase=OrchestrationPhase.PLAN_BUILDING,
                message="Building execution plan...",
                progress=0.6,
            )
        )
        builder = self._get_plan_builder()
        try:
            plan = builder.build_plan(query, sub_tasks)
        except Exception as e:
            policy = cb.on_phase_error(
                PhaseInfo(
                    phase=OrchestrationPhase.PLAN_BUILDING,
                    message="Plan building failed",
                    progress=0.6,
                ),
                e,
                ErrorPolicy.ABORT,
            )
            if policy == ErrorPolicy.ABORT:
                return self._to_orchestration_result(single_result, query)
            plan = cast("Any", None)

        if not plan or not plan.steps:
            cb.on_phase_complete(
                PhaseInfo(
                    phase=OrchestrationPhase.PLAN_BUILDING,
                    message="No valid plan could be built, falling back to single skill",
                    progress=0.8,
                )
            )
            return self._to_orchestration_result(single_result, query)

        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.PLAN_BUILDING,
                message=f"Execution plan built with {len(plan.steps)} steps",
                progress=0.9,
                metadata={"step_count": len(plan.steps), "strategy": plan.execution_mode.value},
            )
        )

        duration_ms = (time.perf_counter() - start_time) * 1000

        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query=query,
            execution_plan=plan,
            single_fallback=single_result.primary,
            layer_details=single_result.layer_details,
            duration_ms=duration_ms,
        )

        # Record execution analytics
        self._record_execution(query, result)

        cb.on_plan_ready(plan)
        cb.on_phase_complete(
            PhaseInfo(
                phase=OrchestrationPhase.COMPLETE,
                message="Orchestration complete",
                progress=1.0,
            )
        )

        return result

    # ================================================================
    # Result building
    # ================================================================

    def _create_config_manager_from_config(self, config: ConfigRoutingConfig) -> ConfigManager:
        manager = ConfigManager(project_root=self.project_root)
        for field_name in type(config).model_fields:
            value = getattr(config, field_name)
            manager.set_cli_override(f"routing.{field_name}", value)
        return manager

    # ================================================================
    # Analytics and execution recording
    # ================================================================

    def _record_execution(
        self,
        query: str,
        result: OrchestrationResult,
        user_modified: bool = False,
        user_satisfied: bool | None = None,
    ) -> None:
        from vibesop.core.analytics import AnalyticsStore, ExecutionRecord

        store = AnalyticsStore(storage_dir=self.project_root / ".vibe")
        record = ExecutionRecord(
            query=query,
            mode=result.mode.value,
            primary_skill=result.primary.skill_id if result.primary else None,
            plan_steps=[s.skill_id for s in result.execution_plan.steps]
            if result.execution_plan
            else [],
            step_count=len(result.execution_plan.steps) if result.execution_plan else 0,
            duration_ms=result.duration_ms,
            user_modified=user_modified,
            user_satisfied=user_satisfied,
            routing_layers=[layer.value for layer in result.routing_path],
        )
        store.record(record)

    def _record_routing_decision(
        self,
        query: str,
        match: SkillRoute,
        context: RoutingContext | None,
    ) -> None:
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

            # Record to preference learner for personalization
            try:
                learner = self._preference_booster.get_learner()
                learner.record_selection(match.skill_id, query, was_helpful=True)
            except Exception as e:
                logger.debug("Failed to record preference selection: %s", e)
        except (OSError, ValueError, RuntimeError) as e:
            logger.debug("Failed to record routing decision: %s", e)

    # ================================================================
    # Alternatives collection
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

    # ================================================================
    # Utilities
    # ================================================================

    def set_llm(self, llm_provider: Any) -> None:
        """Inject an LLM provider for AI triage.

        Args:
            llm_provider: Object with a ``call(prompt, max_tokens, temperature)``
                method that returns a response with a ``content`` attribute.

        Example:
            >>> class AgentLLM:
            ...     def call(self, prompt, max_tokens=100, temperature=0.1):
            ...         return type("R", (), {"content": agent_generate(prompt)})()
            >>> router = UnifiedRouter()
            >>> router.set_llm(AgentLLM())
        """
        self._llm = llm_provider
        self._triage_service._llm = llm_provider

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

    def _apply_optimizations(self, matches: Any, query: str, context: Any = None) -> Any:
        from vibesop.core.routing import _pipeline

        return _pipeline.apply_optimizations(self, matches, query, context)

    def _try_ai_triage(self, query: str, candidates: list[dict[str, Any]], context: Any = None):
        from vibesop.core.routing import _layers

        match, _ = _layers.try_ai_triage_layer(self, query, candidates, context)  # pyright: ignore[reportArgumentType]
        if match is None:
            return None
        from vibesop.core.routing.layers import LayerResult

        return LayerResult(match=match, layer=match.layer)

    def _build_ai_triage_prompt(self, query: str, skills_summary: str) -> str:
        return self._triage_service.build_ai_triage_prompt(query, skills_summary)


__all__ = [
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
    "UnifiedRouter",
]
