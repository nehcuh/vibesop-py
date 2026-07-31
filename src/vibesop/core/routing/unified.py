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
    OrchestrationMode,
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
from vibesop.core.routing.matcher_pipeline import MatcherPipeline, filter_management_candidates
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


def _maybe_wrap_for_spans(provider: Any) -> Any:
    """Best-effort wrap an injected provider with SpanWrappedProvider.

    Returns the provider unchanged if:
    * it is already a SpanWrappedProvider (idempotent),
    * it lacks the LLMProvider shape (no ``provider_name`` / ``default_model``
      / ``configured``) — these are duck-typed callers from agent runtimes
      and don't fit the LLMProvider ABC; span emission is skipped for them.

    Otherwise wraps in SpanWrappedProvider so llm-spans get emitted from
    third-party injections (closes v8.2 P2 §24.5 #2).
    """
    # Lazy imports to avoid circulars at module load time.
    from vibesop.llm.span_wrapped import SpanWrappedProvider

    # Already wrapped (or the noop disabled-tracer variant) — leave alone.
    if isinstance(provider, SpanWrappedProvider):
        return provider

    # Duck-typed callers from agent runtimes may pass objects that quack
    # like ``call(prompt)`` but lack the LLMProvider surface. Don't force
    # them through SpanWrappedProvider (it requires provider_name etc.).
    required = ("provider_name", "default_model", "configured", "call")
    if not all(hasattr(provider, attr) for attr in required):
        return provider

    # Don't wrap if the LLMProvider ABC already rejected it (defensive).
    try:
        return SpanWrappedProvider(provider)
    except Exception as e:  # best-effort wrap; never block injection
        logger.warning(
            "set_llm: provider has LLMProvider shape but SpanWrappedProvider "
            "wrap failed (%s). Using unwrapped — llm-spans will NOT be emitted "
            "for this provider.",
            e,
        )
        return provider


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
        RoutingLayer.SEMANTIC_INDEX,
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

        # Layer 0.5: Explicit session-end signal detection.
        # Short session-end signals (e.g. "拜拜", "I'm done") would otherwise be
        # bypassed by the short-query threshold, so we check them up-front.
        match, detail = self._try_session_end_layer(query, candidates)
        routing_path.append(RoutingLayer.KEYWORD)
        layer_details.append(detail)
        self._tracer.record_layer(RoutingLayer.KEYWORD, detail, len(candidates))
        if match:
            self._record_layer(RoutingLayer.KEYWORD)
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

        # Management gate for the early layers (scenario / semantic index):
        # slash-* management skills must not win non-management queries here
        # (EXPLICIT above is intentionally exempt; matcher layers gate
        # themselves via apply_prefilter).
        early_candidates = filter_management_candidates(query, candidates)

        # Step 1: Early layers (scenario+index best-of for keyword, index only for LLM)
        early_match = self._try_early_layers(
            query, early_candidates, routing_path, layer_details, use_keyword
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

    def _try_session_end_layer(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> tuple[SkillRoute | None, LayerDetail]:
        """Fast-path explicit session-end signals before short-query bypass.

        Session-end signals are often very short (e.g. "拜拜", "I'm done").
        Without this layer they would be bypassed by the AI Triage short-query
        threshold and then missed by the matcher pipeline.  We detect them
        early using the skill's declared triggers.
        """
        if not self._triage_service.is_explicit_session_end_signal(query, candidates):
            return None, LayerDetail(
                layer=RoutingLayer.KEYWORD,
                matched=False,
                reason="No explicit session-end signal detected",
            )

        candidate = next(
            (c for c in candidates if self._triage_service.is_session_end_skill(c.get("id", ""))),
            None,
        )
        if candidate is None:
            return None, LayerDetail(
                layer=RoutingLayer.KEYWORD,
                matched=False,
                reason="Session-end signal detected but skill not in candidates",
            )

        skill_id = candidate.get("id", "builtin/session-end")
        match = SkillRoute(
            skill_id=skill_id,
            confidence=0.95,
            layer=RoutingLayer.KEYWORD,
            source=self._get_skill_source(skill_id, candidate.get("namespace", "builtin")),
            description=str(candidate.get("description", "")),
            metadata={"session_end_signal": True},
        )
        return match, LayerDetail(
            layer=RoutingLayer.KEYWORD,
            matched=True,
            reason=f"Explicit session-end signal matched '{skill_id}'",
        )

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
        *,
        record_telemetry: bool = True,
    ) -> RoutingResult:
        """Route a query to the best matching skill (single-skill fast path).

        For multi-intent queries, prefer orchestrate() which detects compound
        requests and builds an ExecutionPlan.

        Args:
            query: User's natural language query.
            candidates: Optional skill candidates list (uses cached if None).
            context: Optional routing context with conversation/memory state.
            record_telemetry: Internal escape hatch for meta-callers that route
                the same user query more than once per request (e.g.
                AgentRouter.detect_intents) — pass False on the auxiliary pass
                so analytics/miss-counter see the query exactly once.

        Returns:
            RoutingResult with primary match or no-match sentinel.
        """
        result = self._single_skill_route(query, candidates, context)
        # P1 telemetry — the single exit point for the single-route path (hit,
        # low-confidence, and no-match/fallback all land here). Both writes are
        # fault-tolerant and never affect the returned result:
        #   - opt-in analytics execution record (F-06)
        #   - always-on hash-only miss counter (no raw query persisted)
        # The orchestration path does NOT pass through here (Orchestrator calls
        # _single_skill_route directly and records via _record_execution), so
        # orchestrated queries are not double-recorded.
        if record_telemetry:
            self._record_single_route_execution(query, result)
            self._record_route_miss(query, result)
            # Sprint 1: low-conf / no-match → routing pending (human accept/dismiss)
            self._maybe_enqueue_routing_pending(query, result)
        return result

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
        conversation_id: str | None = None,
        storage_dir: Any = None,
    ) -> OrchestrationResult:
        """Orchestrate a query — detect multi-intent and build execution plan if needed.

        Delegates to Orchestrator to keep UnifiedRouter focused on routing.
        ``conversation_id`` + ``storage_dir`` (v3 Phase A Task 5) trigger
        best-effort writeback of orchestration_id + trace_id into the
        conversation metadata file for cross-process join.
        """
        return self._get_orchestrator().orchestrate(
            query,
            candidates,
            context,
            callbacks,
            conversation_id=conversation_id,
            storage_dir=storage_dir,
        )

    # ================================================================
    # Result building
    # ================================================================

    # ================================================================
    # Analytics and execution recording
    # ================================================================

    def _analytics_enabled(self) -> bool:
        """F-06: analytics persistence is opt-in (default off).

        Env vars are returned as raw strings by ConfigManager, so string values
        like "false" must be parsed, not truthiness-checked.
        """
        enabled = self._config_manager.get("analytics.enabled", False)
        if isinstance(enabled, str):  # env vars are returned as raw strings
            enabled = enabled.strip().lower() in ("true", "1", "yes", "on")
        return bool(enabled)

    def _record_execution(
        self,
        query: str,
        result: OrchestrationResult,
        user_modified: bool = False,
        user_satisfied: bool | None = None,
    ) -> None:
        # F-06: analytics persistence is opt-in (default off) — do not write the
        # user's query to .vibe/analytics.jsonl unless explicitly enabled.
        if not self._analytics_enabled():
            return
        from vibesop.core.analytics import AnalyticsStore, ExecutionRecord

        # Carry degradation telemetry onto the execution record so analytics can
        # join degradation level ↔ user satisfaction (Phase 5).
        degradation_meta: dict[str, Any] = {}
        if result.primary and result.primary.metadata:
            for key in ("degradation_level", "degradation_confidence"):
                if key in result.primary.metadata:
                    degradation_meta[key] = result.primary.metadata[key]

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
            metadata=degradation_meta,
        )
        store.record(record)

    def _record_single_route_execution(self, query: str, result: RoutingResult) -> None:
        """Record a single-route execution to analytics (opt-in, F-06).

        Single-route counterpart to ``_record_execution`` (which is coupled to
        ``OrchestrationResult``): builds the ``ExecutionRecord`` directly from
        the ``RoutingResult`` of the ``route()`` fast path. Called once per
        ``route()`` — hit, low-confidence, and no-match/fallback alike, since
        misses are the primary signal for the skill-market feedback loop.
        """
        if not self._analytics_enabled():
            return
        try:
            from vibesop.core.analytics import AnalyticsStore, ExecutionRecord

            # Same degradation telemetry extraction as _record_execution.
            degradation_meta: dict[str, Any] = {}
            if result.primary and result.primary.metadata:
                for key in ("degradation_level", "degradation_confidence"):
                    if key in result.primary.metadata:
                        degradation_meta[key] = result.primary.metadata[key]

            record = ExecutionRecord(
                query=query,
                mode=OrchestrationMode.SINGLE.value,
                primary_skill=result.primary.skill_id if result.primary else None,
                plan_steps=[],
                step_count=0,
                duration_ms=result.duration_ms,
                routing_layers=[layer.value for layer in result.routing_path],
                metadata=degradation_meta,
            )
            AnalyticsStore(storage_dir=self.project_root / ".vibe").record(record)
        except Exception as e:  # telemetry must never break routing
            logger.debug("Failed to record single-route execution: %s", e)

    def _record_route_miss(self, query: str, result: RoutingResult) -> None:
        """Always-on miss telemetry: hash-only counter, no raw query persisted.

        Fires only when the route ended in no-match/fallback (no primary, or a
        FALLBACK_LLM sentinel) — exactly the queries VibeSOP cannot serve.
        """
        if result.has_match:
            return
        try:
            from vibesop.core.skills.miss_counter import MissCounter

            MissCounter(self.project_root).record(query)
        except Exception as e:  # telemetry must never break routing
            logger.debug("Failed to record route miss: %s", e)

    def _maybe_enqueue_routing_pending(self, query: str, result: RoutingResult) -> None:
        """Sprint 1: enqueue low-confidence / no-match routes for human review.

        Does **not** auto-call ``record_outcome`` on every hit (would poison
        Wilson confidence). Accept/dismiss via ``vibe instinct accept|dismiss``
        is the explicit reward signal. Failures never break routing.
        """
        try:
            from vibesop.core.instinct.routing_pending import (
                RoutingPendingStore,
                build_reason_zh,
                should_enqueue_from_route,
            )
            from vibesop.utils.redaction import redact_sensitive

            kind = should_enqueue_from_route(
                has_match=bool(result.has_match),
                confidence=float(result.primary.confidence) if result.primary else 0.0,
            )
            if kind is None:
                return

            skill_id = result.primary.skill_id if result.primary else None
            confidence = float(result.primary.confidence) if result.primary else 0.0
            safe_query = redact_sensitive(query)
            learner = self._get_instinct_learner()
            query_hash = learner.generate_id(safe_query.lower().strip())

            store = RoutingPendingStore(
                self.project_root / ".vibe" / "instincts" / "routing_pending.jsonl"
            )
            item = store.try_enqueue(
                query=safe_query,
                skill_id=skill_id,
                confidence=confidence,
                kind=kind,
                reason_zh=build_reason_zh(
                    kind, skill_id=skill_id, confidence=confidence
                ),
                query_hash=query_hash,
            )
            if item is not None:
                logger.debug(
                    "routing pending enqueued id=%s kind=%s skill=%s conf=%.2f",
                    item.id,
                    kind,
                    skill_id,
                    confidence,
                )
        except Exception as e:  # pending must never break routing
            logger.debug("Failed to enqueue routing pending: %s", e)

    def _record_routing_decision(
        self,
        query: str,
        match: SkillRoute,
        context: RoutingContext | None,
    ) -> None:
        # F-06 (Kimi review #2): redact PII/secrets before the query is persisted
        # to the instinct/preference learners (instincts.jsonl, preferences.json)
        # — same plaintext-PII leak class as analytics; non-PII queries are
        # unchanged so instinct pattern-matching is preserved for the common case.
        from vibesop.utils.redaction import redact_sensitive

        query = redact_sensitive(query)
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
        *,
        record_telemetry: bool = True,
    ) -> RoutingResult:
        """Route a query to the best matching skill (public entry point).

        Alias for :meth:`route` — kept as the single exit point so
        single-route telemetry fires exactly once per call.
        """
        return self.route(query, candidates, context, record_telemetry=record_telemetry)

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

        Notes:
            v8.2 P2 §24.5 #2: if ``llm_provider`` looks like an LLMProvider
            (has ``provider_name`` / ``default_model`` / ``configured``) but
            is not already a ``SpanWrappedProvider``, we auto-wrap it so
            third-party injections still emit llm-spans. If the wrap fails
            (missing attributes), we log a warning and use the provider
            as-is — span emission is best-effort, not a hard requirement.
        """
        wrapped = _maybe_wrap_for_spans(llm_provider)
        self._llm = wrapped
        self._triage_service._llm = wrapped

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

    def set_llm_factory(self, factory: Any) -> None:
        """Inject an LLM factory for agent-driven AI triage configuration.

        Args:
            factory: Object with ``create_provider()`` or ``create_from_env()``
                method that returns an LLM provider with a ``call(prompt, ...)``
                method returning an object with a ``content`` attribute.
        """
        self._llm_factory = factory
        self._triage_service._llm_factory = factory

    def get_skill_loader(self) -> Any:
        """Return the skill loader used for discovering and loading skills.

        Prefers the router's own ``_skill_loader``, falling back to the
        ``_candidate_manager``'s loader when the primary loader is absent.
        """
        loader = getattr(self, "_skill_loader", None)
        if loader is not None:
            return loader
        cm = getattr(self, "_candidate_manager", None)
        if cm is not None:
            return getattr(cm, "_skill_loader", None)
        return None


__all__ = [
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
    "UnifiedRouter",
]
