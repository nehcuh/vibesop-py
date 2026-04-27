# pyright: ignore[reportArgumentType]
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
from typing import TYPE_CHECKING, Any, ClassVar

from vibesop.core.config import ConfigManager
from vibesop.core.config import RoutingConfig as ConfigRoutingConfig
from vibesop.core.exceptions import MatcherError
from vibesop.core.matching import (
    IMatcher,
    KeywordMatcher,
    LevenshteinMatcher,
    MatchResult,
    MatcherConfig,
    MatcherType,
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
    DegradationLevel,
)
from vibesop.core.optimization import (
    CandidatePrefilter,
    PreferenceBooster,
    SkillClusterIndex,
)
from vibesop.core.routing.cache import CacheManager
from vibesop.core.routing.candidate_manager import CandidateManager
from vibesop.core.routing.conflict import (
    ConfidenceGapStrategy,
    ConflictResolver,
    ExplicitOverrideStrategy,
    FallbackStrategy,
    NamespacePriorityStrategy,
    RecencyStrategy,
)
from vibesop.core.routing.execution_mixin import RouterExecutionMixin
from vibesop.core.routing.matcher_pipeline import MatcherPipeline
from vibesop.core.routing.optimization_service import OptimizationService
from vibesop.core.routing.orchestration_mixin import RouterOrchestrationMixin
from vibesop.core.routing.stats_mixin import RouterStatsMixin
from vibesop.core.routing.triage_service import TriageService
from vibesop.core.routing.degradation import DegradationManager
from vibesop.llm.cost_tracker import TriageCostTracker

if TYPE_CHECKING:
    from vibesop.core.instinct import InstinctLearner
    from vibesop.core.memory import MemoryManager
    from vibesop.core.orchestration import MultiIntentDetector, PlanBuilder, PlanTracker
    from vibesop.core.orchestration.task_decomposer import TaskDecomposer

logger = logging.getLogger(__name__)


class _LazyEmbeddingMatcher:
    """Lazy proxy that defers EmbeddingMatcher construction until warm-up.

    EmbeddingMatcher loads a SentenceTransformer model (~100-200ms),
    so deferring to warm-up keeps UnifiedRouter.__init__ fast.
    """

    def __init__(self, config: MatcherConfig):
        self._config = config
        self._real: IMatcher | None = None

    def _ensure_real(self) -> IMatcher:
        if self._real is None:
            from vibesop.core.matching import EmbeddingMatcher
            self._real = EmbeddingMatcher(config=self._config)
        return self._real

    def warm_up(self, candidates: list[dict[str, Any]]) -> None:
        self._ensure_real().warm_up(candidates)

    def match(
        self, query: str, candidates: list[dict[str, Any]], context: Any = None
    ) -> list[tuple[str, float]]:
        return self._ensure_real().match(query, candidates, context)

    def preprocess(self, query: str) -> str:
        return self._ensure_real().preprocess(query)

    def __getattr__(self, name: str):
        return getattr(self._ensure_real(), name)


class UnifiedRouter(RouterStatsMixin, RouterExecutionMixin, RouterOrchestrationMixin):
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
        RoutingLayer.CUSTOM,
    ]

    def __init__(
        self,
        project_root: str | Path = ".",
        config: ConfigRoutingConfig | ConfigManager | None = None,
        skill_loader: Any | None = None,
    ):
        self.project_root = Path(project_root).resolve()

        if isinstance(config, ConfigManager):
            self._config_manager = config
        elif config is None:
            self._config_manager = ConfigManager(project_root=self.project_root)
        else:
            self._config_manager = self._create_config_manager_from_config(config)

        self._config: ConfigRoutingConfig = self._config_manager.get_routing_config()
        if skill_loader is not None:
            self._skill_loader = skill_loader

        matcher_config = MatcherConfig(
            min_confidence=self._config.min_confidence,
            use_cache=self._config.use_cache,
        )

        self._matchers: list[tuple[RoutingLayer, IMatcher]] = [
            (RoutingLayer.KEYWORD, KeywordMatcher(matcher_config)),
            (RoutingLayer.TFIDF, TFIDFMatcher(matcher_config)),
        ]

        self._embedding_enabled = self._config.enable_embedding
        if self._embedding_enabled:
            self._matchers.append(
                (RoutingLayer.EMBEDDING, _LazyEmbeddingMatcher(matcher_config))
            )

        self._matchers.append((RoutingLayer.LEVENSHTEIN, LevenshteinMatcher(matcher_config)))

        # Load custom matcher plugins from .vibe/matchers/
        self._plugin_registry = None
        try:
            from vibesop.core.matching.plugin import MatcherPluginRegistry

            self._plugin_registry = MatcherPluginRegistry(self.project_root)
            for plugin in self._plugin_registry.list_plugins():
                self._matchers.append((RoutingLayer.CUSTOM, plugin))
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

    # ================================================================
    # Main routing entry point
    # ================================================================

    def _route(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
    ) -> RoutingResult:
        """Internal: route a query to the best matching skill (single-skill mode).

        Prefer orchestrate() for the full multi-skill pipeline.
        This method executes layers in priority order; the first confident match wins.
        """
        from vibesop.core.routing import _layers, _pipeline

        start_time = time.perf_counter()
        self._total_routes += 1

        # Multi-turn support: detect follow-up queries and enrich with context
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

        # Enrich context with memory and session state if available
        context = self._enrich_context(context, query)

        if candidates is None:
            candidates = self._candidate_manager.get_cached_candidates()

        # Filter by enablement, scope, and lifecycle state
        # External callers can bypass by passing their own candidate list
        candidates, deprecated_warnings = self._candidate_manager.filter_routable(candidates)

        routing_path: list[RoutingLayer] = []
        layer_details: list[LayerDetail] = []

        # Layer 0: Explicit Override
        match, detail = _layers.try_explicit_layer(self, query, candidates)
        routing_path.append(RoutingLayer.EXPLICIT)
        layer_details.append(detail)
        if match:
            self._record_layer(RoutingLayer.EXPLICIT)
            result = self._build_match_result(
                query, match, [], routing_path, layer_details,
                start_time, deprecated_warnings, conversation, original_query
            )
            return result

        # Keyword routing threshold: for queries longer than this character count,
        # skip keyword-based layers (scenario, keyword, TF-IDF, levenshtein)
        # and rely on LLM semantic triage instead.
        # Short queries (<=N chars) are likely explicit skill names or keywords,
        # which keyword matchers handle faster and more accurately.
        keyword_max_chars = getattr(self._config, "keyword_match_max_chars", 5)
        use_keyword_routing = len(query) <= keyword_max_chars

        if use_keyword_routing:
            # Layer 1: Scenario Pattern
            match, detail = _layers.try_scenario_layer(self, query, candidates)
            routing_path.append(RoutingLayer.SCENARIO)
            layer_details.append(detail)
            if match:
                self._record_layer(RoutingLayer.SCENARIO)
                result = self._build_match_result(
                    query, match, [], routing_path, layer_details,
                    start_time, deprecated_warnings, conversation, original_query
                )
                return result

            # Layer 2: AI Triage (may be bypassed for very short queries)
            match, detail = _layers.try_ai_triage_layer(self, query, candidates, context)
            routing_path.append(RoutingLayer.AI_TRIAGE)
            layer_details.append(detail)
            if match:
                self._record_layer(RoutingLayer.AI_TRIAGE)
                result = self._build_match_result(
                    query, match, [], routing_path, layer_details,
                    start_time, deprecated_warnings, conversation, original_query
                )
                return result

            # Layers 3-6: Matcher pipeline (keyword, tfidf, embedding, levenshtein)
            primary, alternatives, detail = _pipeline.run_matcher_pipeline(
                self, query, candidates, context, collect_rejected=True
            )
            routing_path.append(detail.layer)
            layer_details.append(detail)
            if primary:
                self._record_layer(detail.layer)
                result = self._build_match_result(
                    query, primary, alternatives, routing_path, layer_details,
                    start_time, deprecated_warnings, conversation, original_query
                )
                return result
        else:
            # Long query: skip keyword-based layers, use LLM semantic triage
            match, detail = _layers.try_ai_triage_layer(
                self, query, candidates, context, force=True
            )
            routing_path.append(RoutingLayer.AI_TRIAGE)
            layer_details.append(detail)
            if match:
                self._record_layer(RoutingLayer.AI_TRIAGE)
                result = self._build_match_result(
                    query, match, [], routing_path, layer_details,
                    start_time, deprecated_warnings, conversation, original_query
                )
                return result

        # No match found
        duration_ms = (time.perf_counter() - start_time) * 1000
        self._record_layer(RoutingLayer.NO_MATCH)

        # Fallback mode: transparent or silent fallback to raw LLM
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
            # Silent: return no-match but include nearest candidates as alternatives
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
        if conversation:
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

    def _build_match_result(
        self,
        query: str,
        primary: SkillRoute,
        alternatives: list[SkillRoute],
        routing_path: list[RoutingLayer],
        layer_details: list[LayerDetail],
        start_time: float,
        deprecated_warnings: list[str] | None,
        conversation: Any,
        original_query: str,
    ) -> RoutingResult:
        """Build result for a successful match, applying optimizations for non-matcher layers."""

        # Early-layer matches (EXPLICIT/SCENARIO/AI_TRIAGE) bypass the
        # MatcherPipeline where OptimizationService normally runs.
        # Apply optimizations here so session stickiness, habit boost,
        # quality boost, and project context are consistent across
        # all layers.
        matcher_layers = {
            RoutingLayer.KEYWORD,
            RoutingLayer.TFIDF,
            RoutingLayer.EMBEDDING,
            RoutingLayer.LEVENSHTEIN,
        }
        if primary.layer not in matcher_layers:
            match_result = MatchResult(
                skill_id=primary.skill_id,
                confidence=primary.confidence,
                score_breakdown=primary.metadata.get("score_breakdown", {}),
                matcher_type=(
                    MatcherType.AI_TRIAGE
                    if primary.layer == RoutingLayer.AI_TRIAGE
                    else MatcherType.CUSTOM
                ),
                matched_keywords=[],
                matched_patterns=[],
                semantic_score=None,
                metadata=primary.metadata,
            )
            optimized_primary, _ = self._apply_optimizations(
                [match_result], query, None
            )
            primary = SkillRoute(
                skill_id=optimized_primary.skill_id,
                confidence=optimized_primary.confidence,
                layer=primary.layer,
                source=primary.source,
                description=primary.description,
                metadata=optimized_primary.metadata,
            )

        # Record this routing decision for memory/learning

        # Apply degradation evaluation (skip for explicit/user-specified layers)
        if primary.layer not in (RoutingLayer.EXPLICIT, RoutingLayer.CUSTOM):
            degradation_level, degraded_primary = self._degradation_manager.evaluate(primary)
            if degradation_level == DegradationLevel.FALLBACK:
                primary = None
            elif degradation_level == DegradationLevel.DEGRADE:
                primary = degraded_primary
            if primary:
                primary.metadata["degradation_level"] = degradation_level.value
            else:
                return self._build_fallback_result(
                    query=original_query,
                    candidates=[],
                    routing_path=routing_path,
                    layer_details=layer_details,
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                )

        if primary is None:
            return self._build_fallback_result(
                query=original_query,
                candidates=[],
                routing_path=routing_path,
                layer_details=layer_details,
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        self._record_routing_decision(query, primary, None)

        # Update SkillConfig.usage_stats for stale-skill detection
        self._candidate_manager.record_usage(primary.skill_id, was_successful=True)

        # Ensure alternatives are populated from layer_details even without --explain
        if not alternatives:
            alternatives = self._collect_alternatives_from_details(layer_details)

        result = self._build_result(
            query=query,
            primary=primary,
            alternatives=alternatives,
            routing_path=routing_path,
            layer_details=layer_details,
            start_time=start_time,
            deprecated_warnings=deprecated_warnings if deprecated_warnings else None,
        )
        # Persist session state with the selected skill
        self._save_session_state(result, None)
        # Save conversation turn for multi-turn support
        if conversation:
            conversation.add_turn(
                original_query,
                skill_id=result.primary.skill_id if result.primary else None,
            )
        return result

    def route(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
    ) -> RoutingResult:
        """Single-skill routing — fast path for single-intent queries.

        Directly runs the 10-layer routing pipeline without multi-intent
        detection or task decomposition overhead.

        For multi-intent queries, use orchestrate() directly.
        """
        return self._route(query, candidates, context)

    def orchestrate(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
        callbacks: Any | None = None,
    ) -> OrchestrationResult:
        """Orchestrate a query — detect multi-intent and build execution plan if needed.

        Falls back to single-skill routing when:
        - orchestration is disabled
        - query is clearly single-intent
        - decomposition fails

        Args:
            query: User's natural language query
            candidates: Optional skill candidates list
            context: Optional routing context
            callbacks: Optional orchestration callbacks for streaming progress
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
        cb.on_phase_start(PhaseInfo(
            phase=OrchestrationPhase.ROUTING,
            message="Analyzing query for skill match...",
            progress=0.0,
        ))
        single_result = self._route(query, candidates, context)
        cb.on_phase_complete(PhaseInfo(
            phase=OrchestrationPhase.ROUTING,
            message=f"Single-skill match: {single_result.primary.skill_id if single_result.primary else 'none'}",
            progress=0.2,
            metadata={"primary_confidence": single_result.primary.confidence if single_result.primary else 0.0},
        ))

        # 2. Check if orchestration is enabled
        if not self._config.enable_orchestration:
            return self._to_orchestration_result(single_result, query)

        # 3. Multi-intent detection
        cb.on_phase_start(PhaseInfo(
            phase=OrchestrationPhase.DETECTION,
            message="Detecting multiple intents...",
            progress=0.2,
        ))
        detector = self._get_multi_intent_detector()
        should_decompose = detector.should_decompose(query, single_result, llm_client=self._llm)
        cb.on_phase_complete(PhaseInfo(
            phase=OrchestrationPhase.DETECTION,
            message=f"Multi-intent detected: {should_decompose}",
            progress=0.4,
            metadata={"should_decompose": should_decompose},
        ))

        if not should_decompose:
            return self._to_orchestration_result(single_result, query)

        # 4. Decompose into sub-tasks
        cb.on_phase_start(PhaseInfo(
            phase=OrchestrationPhase.DECOMPOSITION,
            message="Decomposing query into sub-tasks...",
            progress=0.4,
        ))
        decomposer = self._get_task_decomposer()
        try:
            sub_tasks = decomposer.decompose(query)
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

        cb.on_phase_complete(PhaseInfo(
            phase=OrchestrationPhase.DECOMPOSITION,
            message=f"Decomposed into {len(sub_tasks)} sub-tasks",
            progress=0.6,
            metadata={"sub_task_count": len(sub_tasks)},
        ))

        if len(sub_tasks) <= 1:
            return self._to_orchestration_result(single_result, query)

        # 5. Build execution plan
        cb.on_phase_start(PhaseInfo(
            phase=OrchestrationPhase.PLAN_BUILDING,
            message="Building execution plan...",
            progress=0.6,
        ))
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
            plan = None  # type: ignore[assignment]

        if not plan or not plan.steps:
            cb.on_phase_complete(PhaseInfo(
                phase=OrchestrationPhase.PLAN_BUILDING,
                message="No valid plan could be built, falling back to single skill",
                progress=0.8,
            ))
            return self._to_orchestration_result(single_result, query)

        cb.on_phase_complete(PhaseInfo(
            phase=OrchestrationPhase.PLAN_BUILDING,
            message=f"Execution plan built with {len(plan.steps)} steps",
            progress=0.9,
            metadata={"step_count": len(plan.steps), "strategy": plan.execution_mode.value},
        ))

        duration_ms = (time.perf_counter() - start_time) * 1000

        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query=query,
            execution_plan=plan,
            single_fallback=single_result.primary,
            duration_ms=duration_ms,
        )

        # Record execution analytics
        self._record_execution(query, result)

        cb.on_plan_ready(plan)
        cb.on_phase_complete(PhaseInfo(
            phase=OrchestrationPhase.COMPLETE,
            message="Orchestration complete",
            progress=1.0,
        ))

        return result

    def _record_execution(
        self,
        query: str,
        result: OrchestrationResult,
        user_modified: bool = False,
        user_satisfied: bool | None = None,
    ) -> None:
        """Record execution to analytics store."""
        from vibesop.core.analytics import AnalyticsStore, ExecutionRecord

        store = AnalyticsStore(storage_dir=self.project_root / ".vibe")
        record = ExecutionRecord(
            query=query,
            mode=result.mode.value,
            primary_skill=result.primary.skill_id if result.primary else None,
            plan_steps=[s.skill_id for s in result.execution_plan.steps] if result.execution_plan else [],
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

            # Record to preference learner for personalization
            try:
                learner = self._preference_booster.get_learner()
                learner.record_selection(match.skill_id, query, was_helpful=True)
            except Exception:
                pass
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
        layer_details: list[LayerDetail],
        start_time: float,
        deprecated_warnings: list[str] | None = None,
    ) -> RoutingResult:
        duration_ms = (time.perf_counter() - start_time) * 1000
        if deprecated_warnings and primary:
            primary.metadata["deprecated_warnings"] = deprecated_warnings

        from vibesop.core.routing.perf_monitor import get_perf_monitor
        if primary:
            get_perf_monitor().record(duration_ms, primary.layer.value)

        return RoutingResult(
            primary=primary,
            alternatives=alternatives,
            routing_path=routing_path,
            layer_details=layer_details,
            query=query,
            duration_ms=duration_ms,
        )

    # ================================================================
    # Candidate management (delegated to CandidateManager)
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
        """Warm up matchers by initializing lazy-loaded components."""
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
        """Invalidate cached project analysis."""
        self._project_analyzer = None

    def _get_skill_source(self, _skill_id: str, namespace: str) -> str:
        """Determine skill source based on namespace."""
        if namespace == "project":
            return "project"
        if namespace == "builtin":
            return "builtin"
        return "external"

    def get_candidates(self, _query: str = "") -> list[dict[str, Any]]:
        return self._candidate_manager.get_candidates()

    def _get_candidates(self, _query: str = "") -> list[dict[str, Any]]:
        """Backward-compatible alias for get_candidates."""
        return self.get_candidates(_query)

    # ================================================================
    # Context management (from former context_mixin)
    # ================================================================

    def _get_memory_manager(self) -> MemoryManager:
        if self._memory_manager is None:
            from vibesop.core.memory import MemoryManager

            self._memory_manager = MemoryManager(
                storage_dir=self.project_root / ".vibe" / "memory"
            )
        return self._memory_manager

    def _get_session_context(self):
        """Lazy-load session context for multi-turn state persistence."""
        if self._session_context is None:
            from vibesop.core.sessions import SessionContext

            self._session_context = SessionContext.load(
                session_id="default",  # resolved internally via _resolve_session_id
                project_root=str(self.project_root),
                router=self,
            )
        return self._session_context

    def _save_session_state(self, result: RoutingResult, _context: RoutingContext | None) -> None:
        """Persist session state after routing."""
        if not self._config.session_aware:
            return

        try:
            session = self._get_session_context()
            if result.has_match and result.primary is not None:
                session.set_current_skill(result.primary.skill_id)
                session.record_route_decision(result.query, result.primary.skill_id)
            # Note: fallback/no-match does NOT erase current_skill — preserves context
            session.save()
        except (OSError, ValueError, RuntimeError) as e:
            logger.debug(f"Failed to save session state: {e}")

    def _get_instinct_learner(self) -> InstinctLearner:
        if self._instinct_learner is None:
            from vibesop.core.instinct import InstinctLearner

            self._instinct_learner = InstinctLearner(
                storage_path=self.project_root / ".vibe" / "instincts.jsonl"
            )
        return self._instinct_learner

    def _enrich_context(self, context: RoutingContext | None, query: str = "") -> RoutingContext:
        """Enrich routing context with memory, session state, recent conversation history, and project context."""
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

        # Load session state for multi-turn awareness
        if self._config.session_aware:
            session = self._get_session_context()
            if session:
                if not context.current_skill and session._current_skill:
                    context.current_skill = session._current_skill
                # Load habit boosts for learned patterns
                if not context.habit_boosts and query:
                    context.habit_boosts = session.get_habit_boost(query)

        # Detect project type and tech stack for context-aware routing
        if not context.project_type:
            if self._project_analyzer is None:
                from vibesop.core.project_analyzer import ProjectAnalyzer
                self._project_analyzer = ProjectAnalyzer(self.project_root)
            analyzer = self._project_analyzer
            profile = analyzer.analyze()
            if profile.project_type:
                context.project_type = profile.project_type
                context.recent_files = profile.tech_stack  # Reuse field for tech stack

        return context

    # ================================================================
    # Config management (from former config_mixin)
    # ================================================================

    def _create_config_manager_from_config(
        self, config: ConfigRoutingConfig
    ) -> ConfigManager:
        manager = ConfigManager(project_root=self.project_root)
        for field_name in type(config).model_fields:
            value = getattr(config, field_name)
            manager.set_cli_override(f"routing.{field_name}", value)
        return manager

    # ================================================================
    # Alternatives collection
    # ================================================================

    def _collect_alternatives_from_details(
        self,
        layer_details: list[LayerDetail],
    ) -> list[SkillRoute]:
        """Extract rejected candidates from layer_details as alternative routes.

        Collects candidates that were close but didn't meet the confidence
        threshold, ordered by confidence descending. This ensures alternatives
        are available even when --explain/--verbose is not used.
        """
        best_confidence: dict[str, float] = {}
        best_layer: dict[str, RoutingLayer] = {}
        best_reason: dict[str, str | None] = {}

        for detail in layer_details:
            for rejected in detail.rejected_candidates:
                current = best_confidence.get(rejected.skill_id, -1.0)
                if rejected.confidence > current:
                    best_confidence[rejected.skill_id] = rejected.confidence
                    best_layer[rejected.skill_id] = rejected.layer
                    best_reason[rejected.skill_id] = rejected.reason

        alternatives: list[SkillRoute] = []
        for skill_id, confidence in best_confidence.items():
            alternatives.append(
                SkillRoute(
                    skill_id=skill_id,
                    confidence=confidence,
                    layer=best_layer[skill_id],
                    source="routing_rejected",
                    metadata={"reason": best_reason[skill_id]},
                )
            )

        # Sort by confidence descending
        alternatives.sort(key=lambda x: x.confidence, reverse=True)
        return alternatives

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

    # ================================================================
    # Utilities
    # ================================================================

    def set_llm(self, llm_provider: Any) -> None:
        """Inject an LLM provider for AI triage.

        This allows the router to use an external LLM (e.g., Claude Code's
        internal LLM) instead of requiring a separate API key configuration.

        Args:
            llm_provider: An object with a `call(prompt, max_tokens, temperature)` method
                          that returns a response object with a `content` attribute.

        Example:
            >>> class AgentLLM:
            ...     def call(self, prompt, max_tokens=100, temperature=0.1):
            ...         return AgentResponse(content=agent_generate_text(prompt))
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
        """Apply optimization strategies to match results."""
        from vibesop.core.routing import _pipeline
        return _pipeline.apply_optimizations(self, matches, query, context)

    def _try_ai_triage(self, query: str, candidates: list[dict[str, Any]], context: Any = None):
        """Backward-compatible proxy to TriageService.try_ai_triage."""
        from vibesop.core.routing import _layers
        match, _ = _layers.try_ai_triage_layer(self, query, candidates, context)
        if match is None:
            return None
        from vibesop.core.routing.layers import LayerResult
        return LayerResult(match=match, layer=match.layer)

    def _build_ai_triage_prompt(self, query: str, skills_summary: str) -> str:
        """Backward-compatible proxy to TriageService.build_ai_triage_prompt."""
        return self._triage_service.build_ai_triage_prompt(query, skills_summary)

__all__ = [
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
    "UnifiedRouter",
]
