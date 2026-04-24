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
from vibesop.core.routing.candidate_mixin import RouterCandidateMixin
from vibesop.core.routing.config_mixin import RouterConfigMixin
from vibesop.core.routing.conflict import (
    ConfidenceGapStrategy,
    ConflictResolver,
    ExplicitOverrideStrategy,
    FallbackStrategy,
    NamespacePriorityStrategy,
    RecencyStrategy,
)
from vibesop.core.routing.context_mixin import RouterContextMixin
from vibesop.core.routing.execution_mixin import RouterExecutionMixin
from vibesop.core.routing.matcher_mixin import RouterMatcherMixin
from vibesop.core.routing.matcher_pipeline import MatcherPipeline
from vibesop.core.routing.optimization_mixin import RouterOptimizationMixin
from vibesop.core.routing.optimization_service import OptimizationService
from vibesop.core.routing.orchestration_mixin import RouterOrchestrationMixin
from vibesop.core.routing.stats_mixin import RouterStatsMixin
from vibesop.core.routing.triage_mixin import RouterTriageMixin
from vibesop.core.routing.triage_service import TriageService
from vibesop.llm.cost_tracker import TriageCostTracker

if TYPE_CHECKING:
    from vibesop.core.instinct import InstinctLearner
    from vibesop.core.memory import MemoryManager
    from vibesop.core.orchestration import MultiIntentDetector, PlanBuilder, PlanTracker
    from vibesop.core.orchestration.task_decomposer import TaskDecomposer

logger = logging.getLogger(__name__)


class UnifiedRouter(RouterStatsMixin, RouterExecutionMixin, RouterCandidateMixin, RouterMatcherMixin, RouterTriageMixin, RouterOptimizationMixin, RouterOrchestrationMixin, RouterContextMixin, RouterConfigMixin):
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

        if self._config.enable_embedding:
            try:
                from vibesop.core.matching import EmbeddingMatcher

                self._matchers.append(
                    (RoutingLayer.EMBEDDING, EmbeddingMatcher(config=matcher_config))
                )
            except ImportError:
                pass

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

        self._scenario_cache: dict[str, Any] | None = None

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

    def route(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
    ) -> RoutingResult:
        """Route a query to the best matching skill.

        Executes layers in priority order. The first confident match wins.
        Integrates memory and instinct for context-aware routing.
        Records the full routing path and per-layer diagnostics for transparency.
        Supports multi-turn conversation context for follow-up queries.
        """
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
            candidates = self._get_cached_candidates()

        # Filter by enablement, scope, and lifecycle state
        # External callers can bypass by passing their own candidate list
        filtered_candidates: list[dict[str, Any]] = []
        deprecated_warnings: list[str] = []
        for c in candidates:
            if not c.get("enabled", True):
                continue
            # Skip archived skills
            lifecycle = c.get("lifecycle", "active")
            if lifecycle == "archived":
                continue
            # Collect deprecated skills for warning
            if lifecycle == "deprecated":
                deprecated_warnings.append(str(c.get("id", "")))
            scope = c.get("scope", "project")
            if scope == "project":
                source_file = c.get("source_file")
                if source_file:
                    try:
                        Path(source_file).resolve().relative_to(self.project_root.resolve())
                    except ValueError:
                        # Skill is project-scoped but not from this project, skip
                        continue
            filtered_candidates.append(c)
        candidates = filtered_candidates

        routing_path: list[RoutingLayer] = []
        for layer_result, layer_details in self._execute_layers(
            query, candidates, context
        ):
            routing_path.append(layer_result.layer)
            if layer_result.match is not None:
                self._record_layer(layer_result.layer)
                # Record this routing decision for memory/learning
                self._record_routing_decision(query, layer_result.match, context)
                result = self._build_result(
                    query=query,
                    primary=layer_result.match,
                    alternatives=layer_result.alternatives,
                    routing_path=routing_path,
                    layer_details=layer_details,
                    start_time=start_time,
                    deprecated_warnings=deprecated_warnings if deprecated_warnings else None,
                )
                # Persist session state with the selected skill
                self._save_session_state(result, context)
                # Save conversation turn for multi-turn support
                if conversation:
                    conversation.add_turn(
                        original_query,
                        skill_id=result.primary.skill_id if result.primary else None,
                    )
                return result

        duration_ms = (time.perf_counter() - start_time) * 1000
        self._record_layer(RoutingLayer.NO_MATCH)
        # Collect layer details even on no-match by running all layers
        layer_details = self._collect_layer_details(query, candidates, context)

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
                matcher_result = self._try_matcher_pipeline(query, candidates, context)
                if matcher_result and matcher_result.match:
                    nearest = [matcher_result.match, *matcher_result.alternatives]
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
        return result

    def orchestrate(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
    ) -> OrchestrationResult:
        """Orchestrate a query — detect multi-intent and build execution plan if needed.

        Falls back to single-skill routing when:
        - orchestration is disabled
        - query is clearly single-intent
        - decomposition fails
        """
        start_time = time.perf_counter()

        # 1. Always do single-skill routing first (fast path)
        single_result = self.route(query, candidates, context)

        # 2. Check if orchestration is enabled
        if not self._config.enable_orchestration:
            return self._to_orchestration_result(single_result, query)

        # 3. Multi-intent detection
        detector = self._get_multi_intent_detector()
        if not detector.should_decompose(query, single_result):
            return self._to_orchestration_result(single_result, query)

        # 4. Decompose into sub-tasks
        decomposer = self._get_task_decomposer()
        sub_tasks = decomposer.decompose(query)

        if len(sub_tasks) <= 1:
            # Decomposition produced nothing useful, fall back
            return self._to_orchestration_result(single_result, query)

        # 5. Build execution plan
        builder = self._get_plan_builder()
        plan = builder.build_plan(query, sub_tasks)

        if not plan.steps:
            # No valid steps could be built, fall back
            return self._to_orchestration_result(single_result, query)

        duration_ms = (time.perf_counter() - start_time) * 1000

        return OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query=query,
            execution_plan=plan,
            single_fallback=single_result.primary,
            duration_ms=duration_ms,
        )

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
        layer_details: list[LayerDetail],
        start_time: float,
        deprecated_warnings: list[str] | None = None,
    ) -> RoutingResult:
        duration_ms = (time.perf_counter() - start_time) * 1000
        if deprecated_warnings and primary:
            primary.metadata["deprecated_warnings"] = deprecated_warnings
        return RoutingResult(
            primary=primary,
            alternatives=alternatives,
            routing_path=routing_path,
            layer_details=layer_details,
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

__all__ = [
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
    "UnifiedRouter",
]
