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
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from vibesop.core.matching import (
    IMatcher,
    KeywordMatcher,
    LevenshteinMatcher,
    MatchResult,
    MatcherConfig,
    MatcherType,
    RoutingContext,
    SimilarityMetric,
    TFIDFMatcher,
    tokenize,
)
from vibesop.core.config import ConfigManager, RoutingConfig as ConfigRoutingConfig
from vibesop.core.optimization import (
    CandidatePrefilter,
    PreferenceBooster,
    SkillClusterIndex,
)
from vibesop.core.routing.explicit_layer import check_explicit_override
from vibesop.core.routing.scenario_layer import load_scenarios, match_scenario


class RoutingLayer(str, Enum):
    """Routing layers in priority order."""

    AI_TRIAGE = "ai_triage"  # Layer 0: AI semantic analysis (95% accuracy)
    EXPLICIT = "explicit"  # Layer 1: User-specified skill
    SCENARIO = "scenario"  # Layer 2: Predefined patterns
    KEYWORD = "keyword"  # Layer 3: Fast keyword matching
    TFIDF = "tfidf"  # Layer 4: TF-IDF semantic
    EMBEDDING = "embedding"  # Layer 5: Vector embedding
    LEVENSHTEIN = "levenshtein"  # Layer 6: Fuzzy fallback
    NO_MATCH = "no_match"  # No suitable match found


@dataclass
class SkillRoute:
    """Single skill routing decision.

    Attributes:
        skill_id: The selected skill identifier
        confidence: Confidence score (0.0 to 1.0)
        layer: Which routing layer made this decision
        source: Where the skill came from (builtin, external, user)
        metadata: Additional routing metadata
    """

    skill_id: str
    confidence: float
    layer: RoutingLayer
    source: str = "builtin"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "skill_id": self.skill_id,
            "confidence": self.confidence,
            "layer": self.layer.value,
            "source": self.source,
            "metadata": self.metadata,
        }


@dataclass
class RoutingResult:
    """Result from routing a query.

    Attributes:
        primary: The primary selected skill
        alternatives: Alternative skills (next best matches)
        routing_path: Which layers were tried
        query: The original query (for reference)
        duration_ms: How long routing took
    """

    primary: SkillRoute | None
    alternatives: list[SkillRoute]
    routing_path: list[RoutingLayer]
    query: str
    duration_ms: float

    @property
    def has_match(self) -> bool:
        """Whether a match was found."""
        return self.primary is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "primary": self.primary.to_dict() if self.primary else None,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "routing_path": [l.value for l in self.routing_path],
            "query": self.query,
            "duration_ms": self.duration_ms,
            "has_match": self.has_match,
        }


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
    _LAYER_PRIORITY = [
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

        # Initialize preference booster
        pref_config = self._optimization_config.preference_boost
        self._preference_booster = PreferenceBooster(
            enabled=self._optimization_config.enabled and pref_config.enabled,
            weight=pref_config.weight,
            min_samples=pref_config.min_samples,
            storage_path=str(self.project_root / ".vibe" / "preferences.json"),
        )

    def _create_config_manager_from_config(self, config: ConfigRoutingConfig) -> ConfigManager:
        """Create a ConfigManager wrapper for a RoutingConfig.

        Args:
            config: RoutingConfig instance

        Returns:
            ConfigManager that wraps the RoutingConfig
        """
        # This is a simple wrapper - in production, you'd want to properly
        # integrate the config into the ConfigManager's source hierarchy
        manager = ConfigManager(project_root=self.project_root)
        manager.set_cli_override("routing.min_confidence", config.min_confidence)
        manager.set_cli_override("routing.auto_select_threshold", config.auto_select_threshold)
        manager.set_cli_override("routing.enable_ai_triage", config.enable_ai_triage)
        manager.set_cli_override("routing.enable_embedding", config.enable_embedding)
        manager.set_cli_override("routing.max_candidates", config.max_candidates)
        manager.set_cli_override("routing.use_cache", config.use_cache)
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

        # Auto-discover candidates if not provided
        if candidates is None:
            candidates = self._get_candidates(query)

        # === Layer 0: AI Triage ===
        ai_result = self._ai_triage(query, candidates)
        if ai_result:
            duration_ms = (time.perf_counter() - start_time) * 1000
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
        return self._no_match_result(query, routing_path, duration_ms)

    def score(
        self,
        query: str,
        skill_id: str,
        candidate: dict[str, Any],
        context: RoutingContext | None = None,
    ) -> float:
        """Score a single candidate against the query.

        Args:
            query: User's natural language query
            skill_id: The skill identifier
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
        query: str = "",
    ) -> list[dict[str, Any]]:
        """Get all available skill candidates.

        Args:
            query: Optional query to filter candidates

        Returns:
            List of skill candidates
        """
        return self._get_candidates(query)

    def _get_candidates(
        self,
        query: str = "",
    ) -> list[dict[str, Any]]:
        """Get skill candidates from all sources.

        This integrates:
        - Built-in skills (core/skills/)
        - External skills (~/.claude/skills/)
        - Project-specific skills (.vibe/skills/)

        Args:
            query: Optional query for filtering

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
        for skill_id, definition in definitions.items():
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

    def _get_skill_source(self, skill_id: str, namespace: str) -> str:
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
            "layers": [l.value for l in self._LAYER_PRIORITY],
            "matchers": [
                {"layer": l.value, "matcher": type(m).__name__} for l, m in self._matchers
            ],
            "config": {
                "min_confidence": self._config.min_confidence,
                "auto_select_threshold": self._config.auto_select_threshold,
                "enable_ai_triage": self._config.enable_ai_triage,
                "enable_embedding": self._config.enable_embedding,
            },
        }


# Convenience exports
__all__ = [
    "UnifiedRouter",
    "RoutingConfig",
    "RoutingLayer",
    "RoutingResult",
    "SkillRoute",
]
