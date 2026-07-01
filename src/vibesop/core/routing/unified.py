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
    RoutingContext,
)
from vibesop.core.models import (
    LayerDetail,
    OrchestrationResult,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)
from vibesop.core.optimization import (
    CandidatePrefilter,
)
from vibesop.core.routing import _layers, _pipeline
from vibesop.core.routing._protocols import LLMFactory, PromptBuilder, SkillLoaderProtocol
from vibesop.core.routing.context_mixin import RouterContextMixin
from vibesop.core.routing.degradation import DegradationManager
from vibesop.core.routing.matcher_pipeline import MatcherPipeline
from vibesop.core.routing.optimization_service import OptimizationService
from vibesop.core.routing.orchestration_mixin import RouterOrchestrationMixin
from vibesop.core.routing.orchestrator import Orchestrator
from vibesop.core.routing.result_mixin import RouterResultMixin
from vibesop.core.routing.router_factory import RouterFactory
from vibesop.core.routing.stats_mixin import RouterStatsMixin
from vibesop.core.routing.tracer import RoutingTracer
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

    # NOTE: This priority list is used for DISPLAY/sorting and get_capabilities()
    # only — it does NOT drive execution order. The real pipeline is a 4-stage
    # branched cascade; see `_try_layers()`:
    #   Stage 1: EXPLICIT (short-circuit on hit)
    #   Stage 2: SCENARIO + Semantic Index (best-of-N, keyword/short-query path)
    #   Stage 3: AI_TRIAGE (LLM, long-query path)
    #   Stage 4: Matcher aggregation (keyword/tfidf/embedding/levenshtein run in
    #            parallel, max confidence wins — not serial fallback)
    # NO_MATCH and FALLBACK_LLM are terminal states, not matching layers.
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
        skill_loader: SkillLoaderProtocol | None = None,
        llm_factory: LLMFactory | None = None,
        prompt_builder: PromptBuilder | None = None,
    ):
        self.project_root = Path(project_root).resolve()
        self._llm_factory = llm_factory
        self._prompt_builder = prompt_builder
        if skill_loader is not None:
            self._skill_loader = skill_loader

        # =====================================================================
        # Component construction via RouterFactory
        # =====================================================================
        factory = RouterFactory(self.project_root)

        self._config_manager = factory.build_config_manager(config)
        self._config: ConfigRoutingConfig = self._config_manager.get_routing_config()

        self._matchers, self._embedding_enabled, self._plugin_registry = factory.build_matchers(
            self._config,
        )
        self._matchers_warmed = False

        self._optimization_config = self._config_manager.get_optimization_config()
        (
            self._cluster_index,
            self._prefilter,
            self._conflict_resolver,
            self._preference_booster,
        ) = factory.build_optimization_infrastructure(self._optimization_config)

        self._cache_manager, self._candidate_manager, self._cost_tracker = (
            factory.build_infrastructure()
        )

        self._tracer = factory.build_tracer()
        factory.register_atexit(self._candidate_manager)

        # =====================================================================
        # Services (depend on self methods, kept in __init__ for now)
        # =====================================================================
        self._llm: Any | None = None
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

        # =====================================================================
        # State & lazy-init placeholders
        # =====================================================================
        self._total_routes = 0
        self._layer_distribution: dict[str, int] = {}
        self._stats_lock = threading.Lock()
        self._scenario_cache: dict[str, Any] | None = None
        self._project_analyzer: Any | None = None

        # Orchestrator (lazy init)
        self._orchestrator: Orchestrator | None = None

        # Orchestration components (lazy init)
        self._multi_intent_detector: MultiIntentDetector | None = None
        self._task_decomposer: TaskDecomposer | None = None
        self._plan_builder: PlanBuilder | None = None
        self._plan_tracker: PlanTracker | None = None

        # Session context for multi-turn state persistence (lazy init)
        self._session_context = None

        # Cached SkillRecommender instance (from integrations)
        self._skill_recommender: Any = None

        # Memory and instinct systems for context-aware routing (lazy init)
        self._memory_manager: MemoryManager | None = None
        self._instinct_learner: InstinctLearner | None = None

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
            cjk_keywords = [
                "分析",
                "审查",
                "设计",
                "调试",
                "优化",
                "规划",
                "测试",
                " review",
                " analyze",
                " debug",
                " design",
                " plan",
                " test",
            ]

            def _relevance_score(c: dict[str, Any]) -> float:
                score = 0.0
                cid = c.get("id", "").lower()
                desc = c.get("description", "").lower()
                intent = (c.get("intent") or "").lower()
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
            query,
            candidates,
            context,
            routing_path,
            layer_details,
            start_time,
            deprecated_warnings,
            conversation,
            original_query,
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
            query,
            original_query,
            candidates,
            context,
            routing_path,
            layer_details,
            duration_ms,
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
        # Layer 0: Explicit Override (always first)
        match, detail = _layers.try_explicit_layer(self, query, candidates)  # pyright: ignore[reportArgumentType]
        routing_path.append(RoutingLayer.EXPLICIT)
        layer_details.append(detail)
        self._tracer.record_layer(RoutingLayer.EXPLICIT, detail, len(candidates))
        if match:
            self._record_layer(RoutingLayer.EXPLICIT)
            return self._build_match_result(
                query,
                match,
                [],
                routing_path,
                layer_details,
                start_time,
                deprecated_warnings,
                conversation,
                original_query,
                context,
            )

        use_keyword = self._should_use_keyword_routing(query, context)

        # Step 1: Early layers (scenario+index best-of for keyword, index only for LLM)
        early_match = self._try_early_layers(
            query, candidates, routing_path, layer_details, use_keyword
        )
        if early_match is not None:
            self._record_layer(early_match.layer)
            return self._build_match_result(
                query,
                early_match,
                [],
                routing_path,
                layer_details,
                start_time,
                deprecated_warnings,
                conversation,
                original_query,
                context,
            )

        # Step 2: AI Triage (force for long/LLM queries, normal for keyword)
        match, detail = _layers.try_ai_triage_layer(
            self,
            query,
            candidates,
            context,  # pyright: ignore[reportArgumentType]
            force=not use_keyword,
        )
        routing_path.append(RoutingLayer.AI_TRIAGE)
        layer_details.append(detail)
        self._tracer.record_layer(RoutingLayer.AI_TRIAGE, detail, len(candidates))
        if match and match.confidence >= self._config.min_confidence:
            self._record_layer(RoutingLayer.AI_TRIAGE)
            return self._build_match_result(
                query,
                match,
                [],
                routing_path,
                layer_details,
                start_time,
                deprecated_warnings,
                conversation,
                original_query,
                context,
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
                query,
                primary,
                alternatives,
                routing_path,
                layer_details,
                start_time,
                deprecated_warnings,
                conversation,
                original_query,
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

    def _should_use_keyword_routing(
        self, query: str, context: RoutingContext | None = None
    ) -> bool:
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
                self._triage_service._llm is not None and self._triage_service._llm.configured()
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

    def _get_orchestrator(self) -> Orchestrator:
        """Lazy-init Orchestrator to avoid heavy construction during router init."""
        if self._orchestrator is None:
            self._orchestrator = Orchestrator(self)
        return self._orchestrator

    def orchestrate(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
        callbacks: Any | None = None,
    ) -> OrchestrationResult:
        """Orchestrate a query — detect multi-intent and build execution plan if needed.

        Delegates to Orchestrator to keep UnifiedRouter focused on routing.
        """
        return self._get_orchestrator().orchestrate(query, candidates, context, callbacks)

    # ================================================================
    # Result building
    # ================================================================

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

    @property
    def llm(self) -> Any | None:
        """Currently injected LLM provider, or None."""
        return self._llm

    @property
    def routing_config(self) -> ConfigRoutingConfig:
        """Active routing configuration."""
        return self._config

    @routing_config.setter
    def routing_config(self, value: ConfigRoutingConfig) -> None:
        self._config = value

    @property
    def triage_service(self) -> TriageService:
        """The AI triage service used by this router."""
        return self._triage_service

    def route_single(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
    ) -> RoutingResult:
        """Route a query to the best matching skill (public entry point).

        This is the public counterpart to ``_single_skill_route``.
        """
        return self._single_skill_route(query, candidates, context)

    def build_decomposition_skills(
        self,
        candidates: list[dict[str, Any]] | None = None,
        limit: int = 50,
        query: str | None = None,
    ) -> list[str]:
        """Build the skill catalog string list for task decomposition.

        Public counterpart to ``_build_decomposition_skills``.
        """
        return self._build_decomposition_skills(candidates, limit, query)

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
        return _pipeline.apply_optimizations(self, matches, query, context)

    def _try_ai_triage(self, query: str, candidates: list[dict[str, Any]], context: Any = None):
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
