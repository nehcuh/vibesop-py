"""Unified router - single entry point for all skill routing.

This module consolidates routing logic from:
- triggers/ (keyword detection)
- core/routing/engine.py (skill routing)
- semantic/ (semantic matching)

The UnifiedRouter provides ONE canonical way to route queries to skills,
automatically selecting the best matching strategy.

Example:
    >>> router = UnifiedRouter(project_root=".")
    >>> result = router.route("帮我调试数据库连接错误")
    >>> print(result.primary.skill_id)  # e.g., "systematic-debugging"
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, ClassVar

from vibesop.core.config import ConfigManager
from vibesop.core.config import RoutingConfig as ConfigRoutingConfig
from vibesop.core.matching import (
    IMatcher,
    KeywordMatcher,
    LevenshteinMatcher,
    MatcherConfig,
    RoutingContext,
    TFIDFMatcher,
)
from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute
from vibesop.core.optimization import (
    CandidatePrefilter,
    PreferenceBooster,
    SkillClusterIndex,
)
from vibesop.core.routing.explicit_layer import check_explicit_override
from vibesop.core.routing.scenario_layer import load_scenarios, match_scenario


class UnifiedRouter:
    """Unified router for skill selection.

    This is the single entry point for all routing operations.
    It automatically selects the best strategy based on:
    1. Available candidates
    2. Query characteristics
    3. Configuration settings

    Example:
        >>> router = UnifiedRouter()
        >>> result = router.route("扫描安全漏洞")
        >>> if result.has_match:
        ...     print(f"Matched: {result.primary.skill_id}")
    """

    # Layer priority (fastest first, then more accurate)
    _LAYER_PRIORITY: ClassVar[list[RoutingLayer]] = [
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
        """Initialize the unified router.

        Args:
            project_root: Path to project root
            config: Routing configuration (RoutingConfig, ConfigManager, or None to auto-load)
        """
        self.project_root = Path(project_root).resolve()

        # Initialize ConfigManager if config is not provided
        if isinstance(config, ConfigManager):
            self._config_manager = config
        elif config is None:
            self._config_manager = ConfigManager(project_root=self.project_root)
        else:
            # RoutingConfig provided - create a simple ConfigManager wrapper
            self._config_manager = self._create_config_manager_from_config(config)

        # Get routing config
        self._config = (
            self._config_manager.get_routing_config()
            if isinstance(self._config_manager, ConfigManager)
            else config
        )

        # Create matcher config from routing config
        matcher_config = MatcherConfig(
            min_confidence=self._config.min_confidence,
            use_cache=self._config.use_cache,
        )

        # Initialize matchers in priority order
        self._matchers: list[tuple[RoutingLayer, IMatcher]] = [
            (RoutingLayer.KEYWORD, KeywordMatcher(matcher_config)),
            (RoutingLayer.TFIDF, TFIDFMatcher(matcher_config)),
        ]

        # Optional matchers (require dependencies or explicit enable)
        if self._config.enable_embedding:
            try:
                from vibesop.core.matching import EmbeddingMatcher

                self._matchers.append(
                    (RoutingLayer.EMBEDDING, EmbeddingMatcher(config=matcher_config))
                )
            except ImportError:
                pass  # sentence-transformers not available

        # Always add Levenshtein as fallback
        self._matchers.append((RoutingLayer.LEVENSHTEIN, LevenshteinMatcher(matcher_config)))

        # Initialize optimization layers
        self._optimization_config = self._config_manager.get_optimization_config()

        # Build cluster index
        self._cluster_index = SkillClusterIndex()
        self._cluster_built = False

        # Initialize prefilter
        self._prefilter = CandidatePrefilter(cluster_index=self._cluster_index)

        self._total_routes = 0
        self._layer_distribution: dict[str, int] = {}

        # Initialize preference booster
        pref_config = self._optimization_config.preference_boost
        self._preference_booster = PreferenceBooster(
            enabled=self._optimization_config.enabled and pref_config.enabled,
            weight=pref_config.weight,
            min_samples=pref_config.min_samples,
            storage_path=str(self.project_root / ".vibe" / "preferences.json"),
        )

        # Preload candidates for performance optimization
        # This avoids re-scanning skill directories on every route() call
        self._candidates_cache: list[dict[str, Any]] | None = None
        self._cache_lock = threading.Lock()  # Thread-safe cache loading

    def _create_config_manager_from_config(self, config: ConfigRoutingConfig) -> ConfigManager:
        """Create a ConfigManager wrapper for a RoutingConfig.

        Uses dynamic field reflection so new fields are automatically adapted.

        Args:
            config: RoutingConfig instance

        Returns:
            ConfigManager that wraps the RoutingConfig
        """
        manager = ConfigManager(project_root=self.project_root)
        for field_name in type(config).model_fields:
            value = getattr(config, field_name)
            manager.set_cli_override(f"routing.{field_name}", value)
        return manager

    def _ai_triage(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> SkillRoute | None:
        """Layer 0: AI semantic triage using LLM.

        Sends the query + top 20 skill candidates to an LLM for classification.
        Returns a SkillRoute with confidence=0.95 if the LLM selects a valid skill.

        Cost: ~$0.001-0.005 per call (Haiku/gpt-4o-mini).
        Cache: Results cached in .vibe/cache/ to avoid repeated calls.
        """
        if not self._config.enable_ai_triage:
            return None

        # Lazy-init LLM client
        if not hasattr(self, "_llm"):
            self._llm = self._init_llm_client()

        if self._llm is None or not self._llm.configured():
            return None

        # Check cache
        cache_key = f"ai_triage:{query}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        # Build prompt with top 20 candidates
        skills_summary = "\n".join(
            f"- {c['id']}: {c.get('intent', c.get('description', 'N/A'))}" for c in candidates[:20]
        )

        prompt = (
            f"Analyze the user request and select the most appropriate skill.\n\n"
            f"User request: {query}\n\n"
            f"Available skills:\n{skills_summary}\n\n"
            f'Return ONLY the skill ID (e.g., "gstack/review" or "systematic-debugging"). '
            f"Do not include any other text.\n\nSkill ID:"
        )

        try:
            response = self._llm.call(prompt=prompt, max_tokens=50, temperature=0.1)
            skill_id = self._parse_ai_triage_response(response.content)

            if skill_id:
                # Validate skill_id exists in candidates
                candidate = next((c for c in candidates if c["id"] == skill_id), None)
                if candidate:
                    source = self._get_skill_source(skill_id, candidate.get("namespace", "builtin"))
                    result = SkillRoute(
                        skill_id=skill_id,
                        confidence=0.95,
                        layer=RoutingLayer.AI_TRIAGE,
                        source=source,
                        metadata={"ai_triage": True, "model": response.model},
                    )
                    self._set_cache(cache_key, result.to_dict())
                    return result
        except Exception:
            pass  # Fall through to next layer

        return None

    def _init_llm_client(self):
        """Initialize LLM client from environment."""
        # Disable inside Claude Code by default (avoid recursive LLM calls)
        if (
            os.getenv("CLAUDECODE") == "1" or os.getenv("CLAUDE_CODE_ENTRYPOINT") == "cli"
        ) and not os.getenv("VIBE_AI_TRIAGE_ENABLED"):
            return None

        try:
            from vibesop.llm.factory import create_from_env

            llm = create_from_env()
            return llm if llm.configured() else None
        except Exception:
            return None

    def _parse_ai_triage_response(self, response: str) -> str | None:
        """Parse LLM response to extract skill ID."""
        # Try code block format
        if match := re.search(r"```(?:json)?\s*([\w/-]+)```", response):
            return match.group(1).strip()
        # Try first word that looks like a skill ID
        if match := re.search(r"^[\w/-]{3,}", response.strip(), re.MULTILINE):
            return match.group(0).strip()
        return None

    def _get_cache(self, key: str) -> SkillRoute | None:
        """Get cached result."""
        cache_dir = self.project_root / ".vibe" / "cache"
        cache_file = cache_dir / f"{hash(key) % 100000}.json"
        if cache_file.exists():
            try:
                with cache_file.open("r") as f:
                    data = json.load(f)
                # Simple TTL: 1 hour
                import time as _time

                if _time.time() - data.get("timestamp", 0) < 3600:
                    return SkillRoute(
                        skill_id=data["skill_id"],
                        confidence=data["confidence"],
                        layer=RoutingLayer(data["layer"]),
                        source=data["source"],
                        metadata=data.get("metadata", {}),
                    )
            except Exception:
                pass
        return None

    def _set_cache(self, key: str, data: dict[str, Any]) -> None:
        """Cache routing result."""
        import time as _time

        cache_dir = self.project_root / ".vibe" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{hash(key) % 100000}.json"
        data["timestamp"] = _time.time()
        try:
            with cache_file.open("w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def route(
        self,
        query: str,
        candidates: list[dict[str, Any]] | None = None,
        context: RoutingContext | None = None,
    ) -> RoutingResult:
        """Route a query to the best matching skill.

        Args:
            query: User's natural language query
            candidates: List of skill candidates (auto-discovered if None)
            context: Additional routing context

        Returns:
            RoutingResult with primary skill and alternatives
        """
        start_time = time.perf_counter()

        self._total_routes += 1

        # Auto-discover candidates if not provided
        if candidates is None:
            candidates = self._get_cached_candidates()

        # === Layer 0: AI Triage ===
        ai_result = self._ai_triage(query, candidates)
        if ai_result:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_layer(RoutingLayer.AI_TRIAGE)
            return RoutingResult(
                primary=ai_result,
                alternatives=[],
                routing_path=[RoutingLayer.AI_TRIAGE],
                query=query,
                duration_ms=duration_ms,
            )

        # === Layer 1: Explicit Override ===
        explicit_skill, cleaned_query = check_explicit_override(query, candidates)
        if explicit_skill:
            routing_path = [RoutingLayer.EXPLICIT]
            duration_ms = (time.perf_counter() - start_time) * 1000
            candidate = next((c for c in candidates if c["id"] == explicit_skill), None)
            if candidate:
                source = self._get_skill_source(
                    explicit_skill, candidate.get("namespace", "builtin")
                )
                self._record_layer(RoutingLayer.EXPLICIT)
                return RoutingResult(
                    primary=SkillRoute(
                        skill_id=explicit_skill,
                        confidence=1.0,
                        layer=RoutingLayer.EXPLICIT,
                        source=source,
                        metadata={"override": True, "cleaned_query": cleaned_query},
                    ),
                    alternatives=[],
                    routing_path=routing_path,
                    query=query,
                    duration_ms=duration_ms,
                )

        # === Layer 2: Scenario Pattern ===
        if not hasattr(self, "_scenarios"):
            self._scenarios = load_scenarios(self.project_root / "core" / "registry.yaml")
        scenario = match_scenario(query, self._scenarios)
        if scenario:
            routing_path = [RoutingLayer.SCENARIO]
            primary_id = scenario.get("primary")
            primary_candidate = next((c for c in candidates if c["id"] == primary_id), None)
            if primary_candidate:
                duration_ms = (time.perf_counter() - start_time) * 1000
                source = self._get_skill_source(
                    primary_id, primary_candidate.get("namespace", "builtin")
                )
                alternatives = []
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
                self._record_layer(RoutingLayer.SCENARIO)
                return RoutingResult(
                    primary=SkillRoute(
                        skill_id=primary_id,
                        confidence=0.8,
                        layer=RoutingLayer.SCENARIO,
                        source=source,
                        metadata={"scenario": scenario.get("scenario")},
                    ),
                    alternatives=alternatives,
                    routing_path=routing_path,
                    query=query,
                    duration_ms=duration_ms,
                )

        # === Pre-filtering (Optimization Layer 1) ===
        if self._optimization_config.enabled and self._optimization_config.prefilter.enabled:
            candidates = self._prefilter.filter(query, candidates)

        # === Build cluster index (Layer 3, lazy) ===
        if (
            self._optimization_config.enabled
            and self._optimization_config.clustering.enabled
            and not self._cluster_built
            and len(candidates) >= self._optimization_config.clustering.min_skills_for_clustering
        ):
            self._cluster_index.build(candidates)
            self._cluster_built = True

        routing_path: list[RoutingLayer] = []

        # Try each matcher in priority order
        for layer, matcher in self._matchers:
            routing_path.append(layer)

            # Skip disabled layers
            if layer == RoutingLayer.EMBEDDING and not self._config.enable_embedding:
                continue

            try:
                matches = matcher.match(
                    query,
                    candidates,
                    context,
                    top_k=self._config.max_candidates + 1,
                )

                if matches and matches[0].confidence >= self._config.min_confidence:
                    # === Preference boost (Layer 2) ===
                    if (
                        self._optimization_config.enabled
                        and self._optimization_config.preference_boost.enabled
                    ):
                        matches = self._preference_booster.boost(matches, query)

                    # === Cluster conflict resolution (Layer 3) ===
                    if (
                        self._optimization_config.enabled
                        and self._optimization_config.clustering.enabled
                        and self._optimization_config.clustering.auto_resolve
                        and len(matches) > 1
                    ):
                        confidences = {m.skill_id: m.confidence for m in matches}
                        match_ids = [m.skill_id for m in matches]
                        conflict_result = self._cluster_index.resolve_conflicts(
                            query,
                            match_ids,
                            confidences,
                            self._optimization_config.clustering.confidence_gap_threshold,
                        )
                        if conflict_result["primary"]:
                            primary_id = conflict_result["primary"]
                            primary_match = next(
                                (m for m in matches if m.skill_id == primary_id),
                                matches[0],
                            )
                            alternatives = [m for m in matches if m.skill_id != primary_id][
                                : self._config.max_candidates
                            ]
                        else:
                            primary_match = matches[0]
                            alternatives = matches[1 : self._config.max_candidates + 1]
                    else:
                        primary_match = matches[0]
                        alternatives = matches[1 : self._config.max_candidates + 1]

                    # Found a good match
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    # Get namespace from match metadata or infer from skill_id
                    primary_namespace = primary_match.metadata.get("namespace", "builtin")
                    primary_source = self._get_skill_source(
                        primary_match.skill_id, primary_namespace
                    )

                    self._record_layer(layer)

                    return RoutingResult(
                        primary=SkillRoute(
                            skill_id=primary_match.skill_id,
                            confidence=primary_match.confidence,
                            layer=layer,
                            source=primary_source,
                            metadata=primary_match.metadata,
                        ),
                        alternatives=[
                            SkillRoute(
                                skill_id=m.skill_id,
                                confidence=m.confidence,
                                layer=layer,
                                source=self._get_skill_source(
                                    m.skill_id, m.metadata.get("namespace", "builtin")
                                ),
                                metadata=m.metadata,
                            )
                            for m in alternatives
                        ],
                        routing_path=routing_path,
                        query=query,
                        duration_ms=duration_ms,
                    )

            except Exception:
                # Try next matcher on error
                continue

        # No match found
        duration_ms = (time.perf_counter() - start_time) * 1000
        self._record_layer(RoutingLayer.NO_MATCH)
        return self._no_match_result(query, routing_path, duration_ms)

    def score(
        self,
        query: str,
        _skill_id: str,
        candidate: dict[str, Any],
        context: RoutingContext | None = None,
    ) -> float:
        """Score a single candidate against the query.

        Args:
            query: User's natural language query
            _skill_id: The skill identifier (unused, for API compatibility)
            candidate: Skill candidate data
            context: Additional routing context

        Returns:
            Confidence score (0.0 to 1.0)
        """
        # Use the first available matcher
        for _, matcher in self._matchers:
            try:
                return matcher.score(query, candidate, context)
            except Exception:
                continue

        return 0.0

    def get_candidates(
        self,
        _query: str = "",
    ) -> list[dict[str, Any]]:
        """Get all available skill candidates.

        Args:
            _query: Optional query to filter candidates (reserved for future use)

        Returns:
            List of skill candidates
        """
        return self._get_candidates(_query)

    def _get_candidates(
        self,
        _query: str = "",
    ) -> list[dict[str, Any]]:
        """Get skill candidates from all sources.

        This integrates:
        - Built-in skills (core/skills/)
        - External skills (~/.claude/skills/)
        - Project-specific skills (.vibe/skills/)

        Args:
            _query: Optional query for filtering (reserved for future use)

        Returns:
            List of skill candidates
        """
        # Lazy import to avoid circular dependency
        from vibesop.core.skills import SkillLoader

        # Initialize loader if needed
        if not hasattr(self, "_skill_loader"):
            # Search in multiple locations
            search_paths = [
                self.project_root / "core" / "skills",  # Built-in
                self.project_root / ".vibe" / "skills",  # Project
                Path.home() / ".claude" / "skills",  # External
                Path.home() / ".config" / "skills",  # Central storage
            ]
            self._skill_loader = SkillLoader(
                project_root=self.project_root,
                search_paths=search_paths,
            )

        # Discover all skills
        definitions = self._skill_loader.discover_all()

        # Convert to candidate format for matchers
        candidates = []
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
        """Get cached candidates, loading on first call.

        This optimization avoids re-scanning skill directories on every route() call,
        significantly improving routing performance.

        Thread-safe: Uses double-checked locking for concurrent access.

        Returns:
            List of skill candidates
        """
        # Fast path: cache already loaded (no lock needed for read)
        if self._candidates_cache is not None:
            return self._candidates_cache

        # Slow path: load cache with lock
        with self._cache_lock:
            # Double-check: another thread might have loaded it while we waited
            if self._candidates_cache is None:
                self._candidates_cache = self._get_candidates()
            return self._candidates_cache

    def reload_candidates(self) -> int:
        """Reload skill candidates from disk.

        This invalidates the cache and rescans all skill directories.
        Call this after installing new skills or updating skill definitions.

        Returns:
            Number of candidates discovered
        """
        self._candidates_cache = None
        return len(self._get_cached_candidates())

    def _get_skill_source(self, _skill_id: str, namespace: str) -> str:
        """Determine where a skill comes from."""
        if namespace in ("superpowers", "gstack"):
            return "external"
        if namespace == "project":
            return "project"
        return "builtin"

    def _no_match_result(
        self,
        query: str,
        path: list[RoutingLayer],
        duration_ms: float,
    ) -> RoutingResult:
        """Create a result when no match is found."""
        return RoutingResult(
            primary=None,
            alternatives=[],
            routing_path=path,
            query=query,
            duration_ms=duration_ms,
        )

    def get_capabilities(self) -> dict[str, Any]:
        """Return router capabilities."""
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

    # -- Routing stats --

    def _record_layer(self, layer: RoutingLayer) -> None:
        key = layer.value
        self._layer_distribution[key] = self._layer_distribution.get(key, 0) + 1

    def get_stats(self) -> dict[str, Any]:
        """Get routing statistics including total routes and layer distribution."""
        return {
            "total_routes": self._total_routes,
            "layer_distribution": dict(self._layer_distribution),
            "cache_dir": str(self.project_root / ".vibe" / "cache"),
        }

    # -- Preference learning API --

    def record_selection(self, skill_id: str, query: str, was_helpful: bool = True) -> None:
        """Record a skill selection for preference learning."""
        learner = self._preference_booster._get_learner()
        learner.record_selection(skill_id, query, was_helpful)

    def get_preference_stats(self) -> dict[str, Any]:
        """Get preference learning statistics."""
        learner = self._preference_booster._get_learner()
        return learner.get_stats()

    def get_top_skills(self, limit: int = 5, min_selections: int = 2) -> list[Any]:
        """Get top preferred skills based on user history."""
        learner = self._preference_booster._get_learner()
        return learner.get_top_skills(limit, min_selections)

    def clear_old_preferences(self, days: int = 90) -> int:
        """Clear old preference data."""
        learner = self._preference_booster._get_learner()
        return learner.clear_old_data(days)


# Convenience exports
__all__ = [
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
    "UnifiedRouter",
]
