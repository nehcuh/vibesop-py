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
from vibesop.core.orchestration import MultiIntentDetector, PlanBuilder, PlanTracker
from vibesop.core.orchestration.task_decomposer import TaskDecomposer
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
from vibesop.core.routing.project_config import load_merged_scenario_config
from vibesop.core.routing.scenario_layer import match_scenario
from vibesop.core.routing.stats_mixin import RouterStatsMixin
from vibesop.core.routing.triage_service import TriageService
from vibesop.llm.cost_tracker import TriageCostTracker

logger = logging.getLogger(__name__)


class UnifiedRouter(RouterStatsMixin):
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
        Records the full routing path and per-layer diagnostics for transparency.
        """
        start_time = time.perf_counter()
        self._total_routes += 1

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

    def _to_orchestration_result(
        self, result: RoutingResult, query: str
    ) -> OrchestrationResult:
        """Convert a single RoutingResult to OrchestrationResult."""
        return OrchestrationResult(
            mode=OrchestrationMode.SINGLE,
            original_query=query,
            primary=result.primary,
            alternatives=result.alternatives,
            routing_path=result.routing_path,
            layer_details=result.layer_details,
            duration_ms=result.duration_ms,
        )

    # ================================================================
    # Orchestration component lazy initializers
    # ================================================================

    def _get_multi_intent_detector(self) -> MultiIntentDetector:
        if self._multi_intent_detector is None:
            self._multi_intent_detector = MultiIntentDetector()
        return self._multi_intent_detector

    def _get_task_decomposer(self) -> TaskDecomposer:
        if self._task_decomposer is None:
            # Share LLM with triage service if available
            llm = getattr(self._triage_service, "_llm", None)
            self._task_decomposer = TaskDecomposer(llm_client=llm)
        return self._task_decomposer

    def _get_plan_builder(self) -> PlanBuilder:
        if self._plan_builder is None:
            self._plan_builder = PlanBuilder(router=self)
        return self._plan_builder

    def _get_plan_tracker(self) -> PlanTracker:
        if self._plan_tracker is None:
            self._plan_tracker = PlanTracker(storage_dir=self.project_root / ".vibe")
        return self._plan_tracker

    def _execute_layers(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
    ):
        """Generator that yields (LayerResult, list[LayerDetail]) tuples.

        Collects diagnostic details for each layer to enable routing transparency.
        """
        layer_details: list[LayerDetail] = []

        # Layer 0: Explicit Override
        explicit = self._try_explicit(query, candidates)
        if explicit is not None:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.EXPLICIT,
                    matched=explicit.match is not None,
                    reason=explicit.reason or (
                        f"Explicit override: @{explicit.match.skill_id}"
                        if explicit.match else "No @skill_id syntax detected"
                    ),
                    diagnostics=explicit.diagnostics,
                )
            )
            if explicit.match is not None:
                yield explicit, layer_details
                return
            yield explicit, layer_details
        else:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.EXPLICIT,
                    matched=False,
                    reason="No @skill_id syntax detected",
                )
            )
            yield LayerResult(layer=RoutingLayer.EXPLICIT), layer_details

        # Layer 1: Scenario Pattern
        scenario = self._try_scenario(query, candidates)
        if scenario is not None:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.SCENARIO,
                    matched=scenario.match is not None,
                    reason=scenario.reason or (
                        f"Scenario matched: {scenario.match.metadata.get('scenario', 'unknown')}"
                        if scenario.match else "No scenario keywords matched"
                    ),
                    diagnostics=scenario.diagnostics,
                )
            )
            if scenario.match is not None:
                yield scenario, layer_details
                return
            yield scenario, layer_details
        else:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.SCENARIO,
                    matched=False,
                    reason="No scenario keywords matched",
                )
            )
            yield LayerResult(layer=RoutingLayer.SCENARIO), layer_details

        # Layer 2: AI Triage
        triage_start = time.perf_counter()
        triage = self._try_ai_triage(query, candidates, context)
        triage_duration_ms = (time.perf_counter() - triage_start) * 1000
        if triage is not None:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.AI_TRIAGE,
                    matched=triage.match is not None,
                    reason=triage.reason or (
                        f"AI triage selected '{triage.match.skill_id}' (confidence: {triage.match.confidence:.0%})"
                        if triage.match else "AI triage did not select any skill"
                    ),
                    duration_ms=triage_duration_ms,
                    diagnostics=triage.diagnostics,
                )
            )
            if triage.match is not None:
                yield triage, layer_details
                return
            yield triage, layer_details
        else:
            skip_reason = self._get_ai_triage_skip_reason()
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.AI_TRIAGE,
                    matched=False,
                    reason=skip_reason,
                    duration_ms=triage_duration_ms,
                )
            )
            yield LayerResult(layer=RoutingLayer.AI_TRIAGE), layer_details

        # Layers 3-6: Matcher pipeline (keyword, tfidf, embedding, levenshtein)
        matcher_start = time.perf_counter()
        matcher_result = self._try_matcher_pipeline(
            query, candidates, context, collect_rejected=True
        )
        matcher_duration_ms = (time.perf_counter() - matcher_start) * 1000
        if matcher_result is not None and matcher_result.match is not None:
            layer_details.append(
                LayerDetail(
                    layer=matcher_result.layer,
                    matched=True,
                    reason=matcher_result.reason or (
                        f"Matcher selected '{matcher_result.match.skill_id}' (confidence: {matcher_result.match.confidence:.0%})"
                    ),
                    duration_ms=matcher_duration_ms,
                    diagnostics=matcher_result.diagnostics,
                )
            )
            yield matcher_result, layer_details
        else:
            rejected = []
            if matcher_result and matcher_result.diagnostics:
                raw_rejected = matcher_result.diagnostics.get("rejected_candidates", [])
                from vibesop.core.models import RejectedCandidate
                for r in raw_rejected:
                    rejected.append(RejectedCandidate(
                        skill_id=r["skill_id"],
                        confidence=r["confidence"],
                        layer=RoutingLayer(r["layer"].value if hasattr(r["layer"], "value") else str(r["layer"])),
                        reason=r.get("reason", ""),
                    ))
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.LEVENSHTEIN,
                    matched=False,
                    reason=matcher_result.reason if matcher_result else "No matcher produced a confident match",
                    duration_ms=matcher_duration_ms,
                    diagnostics=matcher_result.diagnostics if matcher_result else {},
                    rejected_candidates=rejected,
                )
            )
            yield matcher_result or LayerResult(
                layer=RoutingLayer.LEVENSHTEIN
            ), layer_details

    def _get_ai_triage_skip_reason(self) -> str:
        """Determine why AI triage was skipped."""
        if not self._config.enable_ai_triage:
            return "AI triage disabled in config"
        if getattr(self._triage_service, "_llm", None) is None:
            return "LLM not initialized"
        if getattr(self._triage_service, "_circuit_breaker", None) and not self._triage_service._circuit_breaker.can_execute():
            return "Circuit breaker open (too many failures)"
        monthly_cost = getattr(self._cost_tracker, "get_monthly_cost", lambda: 0.0)()
        if monthly_cost >= self._config.ai_triage_budget_monthly:
            return f"Monthly AI triage budget exhausted (${monthly_cost:.2f} / ${self._config.ai_triage_budget_monthly:.2f})"
        return "AI triage did not produce a match"

    def _collect_layer_details(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
    ) -> list[LayerDetail]:
        """Collect layer details for no-match scenarios.

        Runs all layers non-destructively to gather diagnostics.
        """
        layer_details: list[LayerDetail] = []

        # Explicit
        explicit = self._try_explicit(query, candidates)
        layer_details.append(
            LayerDetail(
                layer=RoutingLayer.EXPLICIT,
                matched=False,
                reason=explicit.reason if explicit else "No @skill_id syntax detected",
                diagnostics=explicit.diagnostics if explicit else {},
            )
        )

        # Scenario
        scenario = self._try_scenario(query, candidates)
        layer_details.append(
            LayerDetail(
                layer=RoutingLayer.SCENARIO,
                matched=False,
                reason=scenario.reason if scenario else "No scenario keywords matched",
                diagnostics=scenario.diagnostics if scenario else {},
            )
        )

        # AI Triage
        triage_start = time.perf_counter()
        triage = self._try_ai_triage(query, candidates, context)
        triage_duration_ms = (time.perf_counter() - triage_start) * 1000
        if triage is not None:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.AI_TRIAGE,
                    matched=False,
                    reason=triage.reason or "AI triage did not select any skill",
                    duration_ms=triage_duration_ms,
                    diagnostics=triage.diagnostics,
                )
            )
        else:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.AI_TRIAGE,
                    matched=False,
                    reason=self._get_ai_triage_skip_reason(),
                    duration_ms=triage_duration_ms,
                )
            )

        # Matchers
        matcher_start = time.perf_counter()
        matcher_result = self._try_matcher_pipeline(query, candidates, context)
        matcher_duration_ms = (time.perf_counter() - matcher_start) * 1000
        if matcher_result is not None and matcher_result.match is not None:
            layer_details.append(
                LayerDetail(
                    layer=matcher_result.layer,
                    matched=True,
                    reason=matcher_result.reason or f"Matcher selected '{matcher_result.match.skill_id}'",
                    duration_ms=matcher_duration_ms,
                    diagnostics=matcher_result.diagnostics,
                )
            )
        else:
            layer_details.append(
                LayerDetail(
                    layer=RoutingLayer.LEVENSHTEIN,
                    matched=False,
                    reason=matcher_result.reason if matcher_result else "No matcher produced a confident match",
                    duration_ms=matcher_duration_ms,
                    diagnostics=matcher_result.diagnostics if matcher_result else {},
                )
            )

        return layer_details

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
            return LayerResult(
                layer=RoutingLayer.EXPLICIT,
                matched=False,
                reason=f"@{explicit_skill} specified but skill not found in candidates",
            )

        source = self._get_skill_source(explicit_skill, candidate.get("namespace", "builtin"))
        return LayerResult(
            match=SkillRoute(
                skill_id=explicit_skill,
                confidence=1.0,
                layer=RoutingLayer.EXPLICIT,
                source=source,
                description=str(candidate.get("description", "")),
                metadata={"override": True, "cleaned_query": cleaned_query},
            ),
            layer=RoutingLayer.EXPLICIT,
            reason=f"Explicit override: @{explicit_skill}",
            diagnostics={"cleaned_query": cleaned_query},
        )

    # ================================================================
    # Layer 1: Scenario Pattern
    # ================================================================

    def _try_scenario(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> LayerResult | None:
        if self._scenario_cache is None:
            self._scenario_cache = load_merged_scenario_config(self.project_root)
        scenarios = self._scenario_cache.get("strategies", [])
        keywords = self._scenario_cache.get("keywords", {})
        scenario = match_scenario(query, scenarios, keywords)
        if not scenario:
            return None

        target_skill = scenario.get("skill") or scenario.get("primary") or scenario.get("skill_id")
        if not target_skill:
            return LayerResult(
                layer=RoutingLayer.SCENARIO,
                matched=False,
                reason=f"Scenario '{scenario.get('scenario', 'unknown')}' matched but no target skill defined",
            )

        candidate = next((c for c in candidates if c["id"] == target_skill), None)
        if not candidate:
            return LayerResult(
                layer=RoutingLayer.SCENARIO,
                matched=False,
                reason=f"Scenario matched '{target_skill}' but skill not in candidates",
            )

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
                        description=str(rel.get("description", "")),
                        metadata={"scenario": scenario.get("scenario")},
                    )
                )

        scenario_name = scenario.get("scenario", "unknown")
        return LayerResult(
            match=SkillRoute(
                skill_id=target_skill,
                confidence=0.9,
                layer=RoutingLayer.SCENARIO,
                source=self._get_skill_source(
                    target_skill, candidate.get("namespace", "builtin")
                ),
                description=str(candidate.get("description", "")),
                metadata={"scenario": scenario_name},
            ),
            alternatives=alternatives,
            layer=RoutingLayer.SCENARIO,
            reason=f"Scenario matched: '{scenario_name}'",
            diagnostics={
                "scenario": scenario_name,
                "related_skills": related,
                "alternatives_count": len(alternatives),
            },
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
            self._instinct_learner = InstinctLearner(
                storage_path=self.project_root / ".vibe" / "instincts.jsonl"
            )
        return self._instinct_learner

    def _enrich_context(self, context: RoutingContext | None, query: str = "") -> RoutingContext:
        """Enrich routing context with memory, session state, and recent conversation history."""
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

    def _build_fallback_result(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        routing_path: list[RoutingLayer],
        layer_details: list[LayerDetail],
        duration_ms: float,
    ) -> RoutingResult:
        """Build a fallback result when no skill matches.

        Returns a FALLBACK_LLM route with nearest candidates as alternatives.
        """
        # Find nearest candidates (even if below threshold) for suggestions
        nearest: list[SkillRoute] = []
        try:
            matcher_result = self._try_matcher_pipeline(query, candidates, None)
            if matcher_result and matcher_result.match:
                nearest = [matcher_result.match, *matcher_result.alternatives]
        except (RuntimeError, ValueError):
            logger.debug("Failed to get nearest candidates for fallback")

        fallback_layer_detail = LayerDetail(
            layer=RoutingLayer.FALLBACK_LLM,
            matched=True,
            reason="No confident skill match; falling back to raw LLM",
        )

        return RoutingResult(
            primary=SkillRoute(
                skill_id="fallback-llm",
                confidence=1.0,
                layer=RoutingLayer.FALLBACK_LLM,
                source="builtin",
                metadata={
                    "reason": "No skill matched query",
                    "fallback_mode": self._config.fallback_mode,
                    "candidate_count": len(candidates),
                },
            ),
            alternatives=nearest,
            routing_path=[*routing_path, RoutingLayer.FALLBACK_LLM],
            layer_details=[*layer_details, fallback_layer_detail],
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
        import vibesop
        from vibesop.core.optimization.cold_start import get_cold_start_strategy
        from vibesop.core.skills import SkillLoader
        from vibesop.core.skills.config_manager import SkillConfigManager

        if getattr(self, "_skill_loader", None) is None:
            # Always include VibeSOP's built-in skills regardless of project root
            builtin_skills_path = Path(vibesop.__file__).parent.parent.parent / "core" / "skills"
            search_paths = [
                self.project_root / ".vibe" / "skills",
                Path.home() / ".config" / "skills",
            ]
            if builtin_skills_path.exists() and builtin_skills_path not in search_paths:
                search_paths.insert(0, builtin_skills_path)
            self._skill_loader = SkillLoader(
                project_root=self.project_root,
                search_paths=search_paths,
            )

        definitions = self._skill_loader.discover_all()
        cold_start = get_cold_start_strategy(self.project_root)
        p0_skills = set(cold_start.get_p0_skills())
        candidates: list[dict[str, Any]] = []
        for _skill_id, definition in definitions.items():
            metadata = definition.metadata
            tags = metadata.tags or []
            # Auto-generate keywords from skill name when tags are empty
            if not tags:
                tags = _extract_name_keywords(metadata.name)

            # Load skill config for enablement/scope metadata
            skill_config = SkillConfigManager.get_skill_config(_skill_id)
            enabled = skill_config.enabled if skill_config else True
            scope = skill_config.scope if skill_config else "project"

            candidates.append(
                {
                    "id": metadata.id,
                    "name": metadata.name,
                    "description": metadata.description,
                    "intent": metadata.intent,
                    "keywords": tags,
                    "triggers": [metadata.trigger_when] if metadata.trigger_when else [],
                    "namespace": metadata.namespace,
                    "source": self._get_skill_source(metadata.id, metadata.namespace),
                    "priority": "P0" if metadata.id in p0_skills else "P2",
                    "enabled": enabled,
                    "scope": scope,
                    "source_file": str(definition.source_file) if definition.source_file else None,
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
                except (OSError, RuntimeError, ValueError, ImportError) as e:
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

    # ================================================================
    # Backward compatibility proxies for extracted services
    #
    # These thin wrappers are kept for test compatibility and will be
    # removed in a future major version. Callers should migrate to the
    # underlying services directly (e.g. TriageService, MatcherPipeline).
    # ================================================================

    def _try_ai_triage(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None = None,
    ) -> Any:
        """Proxy to TriageService (kept for backward compatibility)."""
        if self._llm is not None:  # type: ignore[reportPrivateUsage]
            self._triage_service._llm = self._llm  # type: ignore[reportPrivateUsage]
        return self._triage_service.try_ai_triage(query, candidates, context)

    def _try_matcher_pipeline(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
        collect_rejected: bool = False,
    ) -> Any:
        """Proxy to MatcherPipeline (kept for backward compatibility)."""
        return self._matcher_pipeline.try_matcher_pipeline(
            query, candidates, context, collect_rejected=collect_rejected
        )

    def _prefilter_ai_triage_candidates(
        self, query: str, candidates: list[dict[str, Any]], max_skills: int
    ) -> list[dict[str, Any]]:
        return self._triage_service.prefilter_ai_triage_candidates(query, candidates, max_skills)

    def _build_ai_triage_prompt(self, query: str, skills_summary: str) -> str:
        return self._triage_service.build_ai_triage_prompt(query, skills_summary)

    def _init_llm_client(self) -> Any:
        return self._triage_service.init_llm_client()

    def _parse_ai_triage_response(self, response: str) -> dict[str, Any]:
        return self._triage_service.parse_ai_triage_response(response)

    def _apply_prefilter(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._matcher_pipeline.apply_prefilter(query, candidates)

    def _apply_optimizations(self, matches: Any, query: str, context: RoutingContext | None = None) -> Any:
        return self._optimization_service.apply_optimizations(matches, query, context)

    def _resolve_conflicts(self, matches: Any, query: str) -> Any:
        return self._optimization_service.resolve_conflicts(matches, query)

    def _apply_instinct_boost(self, matches: Any, query: str, context: RoutingContext | None) -> Any:
        return self._optimization_service.apply_instinct_boost(matches, query, context)

    def _ensure_cluster_index(self, candidates: list[dict[str, Any]]) -> None:
        self._optimization_service.ensure_cluster_index(candidates)


def _extract_name_keywords(name: str) -> list[str]:
    """Extract searchable keywords from a skill name.

    Splits on common delimiters (hyphen, underscore, slash) and
    filters out very short tokens.
    """
    import re

    # Split on delimiters
    parts = re.split(r"[-_/]", name)
    keywords: list[str] = []
    for p in parts:
        stripped = p.strip()
        if len(stripped) > 1:
            keywords.append(stripped)
    return keywords


__all__ = [
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
    "UnifiedRouter",
]
