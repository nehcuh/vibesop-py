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
        self._matchers.append(
            (RoutingLayer.LEVENSHTEIN, LevenshteinMatcher(matcher_config))
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
                    # Found a good match
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    # Get namespace from match metadata or infer from skill_id
                    primary_namespace = matches[0].metadata.get("namespace", "builtin")
                    primary_source = self._get_skill_source(matches[0].skill_id, primary_namespace)

                    return RoutingResult(
                        primary=SkillRoute(
                            skill_id=matches[0].skill_id,
                            confidence=matches[0].confidence,
                            layer=layer,
                            source=primary_source,
                            metadata=matches[0].metadata,
                        ),
                        alternatives=[
                            SkillRoute(
                                skill_id=m.skill_id,
                                confidence=m.confidence,
                                layer=layer,
                                source=self._get_skill_source(
                                    m.skill_id,
                                    m.metadata.get("namespace", "builtin")
                                ),
                                metadata=m.metadata,
                            )
                            for m in matches[1 : self._config.max_candidates + 1]
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
                {"layer": l.value, "matcher": type(m).__name__}
                for l, m in self._matchers
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
