"""RouterFactory — constructs UnifiedRouter sub-components.

Extracted from UnifiedRouter.__init__ to eliminate the God Class pattern
and enable testable, replaceable component construction.

Usage:
    factory = RouterFactory(project_root=Path("."))
    components = factory.build_components(config_manager)
    router = UnifiedRouter(components=components, ...)
"""

from __future__ import annotations

import logging
import weakref
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vibesop.core.config import ConfigManager
from vibesop.core.config import RoutingConfig as ConfigRoutingConfig
from vibesop.core.matching import (
    IMatcher,
    KeywordMatcher,
    LevenshteinMatcher,
    MatcherConfig,
    TFIDFMatcher,
)
from vibesop.core.models import RoutingLayer
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
from vibesop.core.routing.cost_tracker import TriageCostTracker
from vibesop.core.routing.tracer import RoutingTracer

if TYPE_CHECKING:
    from vibesop.core.config.manager import RoutingConfig

logger = logging.getLogger(__name__)


class RouterFactory:
    """Factory for constructing UnifiedRouter sub-components.

    Separates component lifecycle (construction) from routing logic,
    making both easier to test and evolve independently.
    """

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def build_config_manager(
        self,
        config: ConfigRoutingConfig | ConfigManager | None = None,
    ) -> ConfigManager:
        if isinstance(config, ConfigManager):
            return config
        if config is None:
            return ConfigManager(project_root=self.project_root)
        # Wrap a plain RoutingConfig in a ConfigManager
        return self._create_config_manager_from_config(config)

    def _create_config_manager_from_config(
        self,
        config: ConfigRoutingConfig,
    ) -> ConfigManager:
        """Build a ConfigManager that replicates a plain RoutingConfig via CLI overrides."""
        manager = ConfigManager(project_root=self.project_root)
        for field_name in type(config).model_fields:
            value = getattr(config, field_name)
            manager.set_cli_override(f"routing.{field_name}", value)
        return manager

    # ------------------------------------------------------------------
    # Matchers
    # ------------------------------------------------------------------
    def build_matchers(
        self,
        routing_config: RoutingConfig,
    ) -> tuple[list[tuple[RoutingLayer, IMatcher]], bool, Any | None]:
        """Return (matchers, embedding_enabled, plugin_registry)."""
        matcher_config = MatcherConfig(
            min_confidence=routing_config.min_confidence,
            use_cache=routing_config.use_cache,
            keyword_coverage_ref=routing_config.keyword_coverage_ref,
            keyword_anchor_idf_min=routing_config.keyword_anchor_idf_min,
            keyword_anchor_cap=routing_config.keyword_anchor_cap,
            keyword_multi_anchor_min=routing_config.keyword_multi_anchor_min,
            keyword_multi_anchor_cov_floor=routing_config.keyword_multi_anchor_cov_floor,
            keyword_name_idf_min=routing_config.keyword_name_idf_min,
            tfidf_anchor_gate_enabled=routing_config.tfidf_anchor_gate_enabled,
        )

        matchers: list[tuple[RoutingLayer, IMatcher]] = [  # pyright: ignore[reportAssignmentType]
            (RoutingLayer.KEYWORD, KeywordMatcher(matcher_config)),
            (RoutingLayer.TFIDF, TFIDFMatcher(matcher_config)),
        ]

        embedding_enabled = routing_config.enable_embedding
        if embedding_enabled:
            from vibesop.core.matching.lazy_matcher import LazyEmbeddingMatcher

            matchers.append(
                (RoutingLayer.EMBEDDING, LazyEmbeddingMatcher(matcher_config)),
            )

        matchers.append(
            (RoutingLayer.LEVENSHTEIN, LevenshteinMatcher(matcher_config)),
        )

        plugin_registry: Any | None = None
        try:
            from vibesop.core.matching.plugin import MatcherPluginRegistry

            plugin_registry = MatcherPluginRegistry(self.project_root)
            for plugin in plugin_registry.list_plugins():
                matchers.append((RoutingLayer.CUSTOM, plugin))
        except ImportError:
            pass

        return matchers, embedding_enabled, plugin_registry

    # ------------------------------------------------------------------
    # Optimization & Conflict Resolution
    # ------------------------------------------------------------------
    def build_optimization_infrastructure(
        self,
        optimization_config: Any,
    ) -> tuple[
        SkillClusterIndex,
        CandidatePrefilter,
        ConflictResolver,
        PreferenceBooster,
    ]:
        cluster_index = SkillClusterIndex()
        prefilter = CandidatePrefilter(cluster_index=cluster_index)

        conflict_resolver = ConflictResolver()
        conflict_resolver.add_strategy(ExplicitOverrideStrategy())
        conflict_resolver.add_strategy(
            ConfidenceGapStrategy(
                gap_threshold=optimization_config.clustering.confidence_gap_threshold,
            ),
        )
        conflict_resolver.add_strategy(NamespacePriorityStrategy())
        conflict_resolver.add_strategy(
            RecencyStrategy(
                storage_path=str(self.project_root / ".vibe" / "preferences.json"),
            ),
        )
        conflict_resolver.add_strategy(FallbackStrategy())

        pref_config = optimization_config.preference_boost
        preference_booster = PreferenceBooster(
            enabled=optimization_config.enabled and pref_config.enabled,
            weight=pref_config.weight,
            min_samples=pref_config.min_samples,
            storage_path=str(self.project_root / ".vibe" / "preferences.json"),
        )

        return cluster_index, prefilter, conflict_resolver, preference_booster

    # ------------------------------------------------------------------
    # Infrastructure (cache, candidates, cost tracking)
    # ------------------------------------------------------------------
    def build_infrastructure(self) -> tuple[CacheManager, CandidateManager, TriageCostTracker]:
        cache_manager = CacheManager(cache_dir=self.project_root / ".vibe" / "cache")
        candidate_manager = CandidateManager(self.project_root)
        cost_tracker = TriageCostTracker(storage_dir=self.project_root / ".vibe")
        return cache_manager, candidate_manager, cost_tracker

    # ------------------------------------------------------------------
    # Tracer
    # ------------------------------------------------------------------
    def build_tracer(self) -> RoutingTracer:
        return RoutingTracer(
            enabled=False,
            traces_dir=self.project_root / ".vibe" / "traces",
        )

    # ------------------------------------------------------------------
    # atexit handler
    # ------------------------------------------------------------------
    @staticmethod
    def register_atexit(candidate_manager: CandidateManager) -> None:
        """Register a weak-referenced atexit handler to flush usage buffers."""
        _cm_ref = weakref.ref(candidate_manager)

        def _flush_usage_buffer() -> None:
            cm = _cm_ref()
            if cm is not None:
                cm._flush_usage_buffer()

        import atexit

        atexit.register(_flush_usage_buffer)
