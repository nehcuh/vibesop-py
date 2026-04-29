"""Cold start strategy for routing without historical data.

This module provides default behavior for new installations or when
preference learning hasn't accumulated enough data yet.

Usage:
    from vibesop.core.optimization.cold_start import ColdStartStrategy

    strategy = ColdStartStrategy()
    default_weights = strategy.get_default_weights()
    mappings = strategy.get_builtin_mappings()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar


@dataclass
class QuerySkillMapping:
    """A mapping from query pattern to skill ID."""

    pattern: str
    skill_id: str
    confidence: float = 0.9
    keywords: list[str] = field(default_factory=list)


class ColdStartStrategy:
    """Provides default routing behavior when no historical data exists.

    This is used for:
    - New installations
    - Queries with no matching history
    - When preference learning is disabled

    Strategy:
    1. Use built-in query → skill mappings for common queries
    2. Apply default confidence weights to matchers
    3. Prioritize certain skills (P0 skills always included)
    """

    # Built-in mappings for common queries
    # These are used when no other routing information is available
    _BUILTIN_MAPPINGS: ClassVar[list[dict[str, Any]]] = [
        # Debugging scenarios
        {
            "pattern": "debug",
            "skill_id": "systematic-debugging",
            "keywords": ["debug", "调试", "bug", "error", "错误", "fix", "修复"],
        },
        {
            "pattern": "test fail",
            "skill_id": "systematic-debugging",
            "keywords": ["test failure", "测试失败", "failing test"],
        },
        # Code review
        {
            "pattern": "review",
            "skill_id": "gstack/review",
            "keywords": ["review", "审查", "code review", "代码审查"],
        },
        # Deployment
        {
            "pattern": "deploy",
            "skill_id": "gstack/ship",
            "keywords": ["deploy", "部署", "release", "发布"],
        },
        # Testing
        {
            "pattern": "test",
            "skill_id": "superpowers/tdd",
            "keywords": ["test", "测试", "testing", "tdd"],
        },
        # Brainstorming
        {
            "pattern": "brainstorm",
            "skill_id": "superpowers/brainstorm",
            "keywords": ["brainstorm", "头脑风暴", "ideas", "想法"],
        },
        # Architecture
        {
            "pattern": "design",
            "skill_id": "superpowers/architect",
            "keywords": ["architect", "架构", "design", "设计"],
        },
        # Planning
        {
            "pattern": "plan",
            "skill_id": "riper-workflow",
            "keywords": ["plan", "计划", "planning", "规划"],
        },
        # Optimization
        {
            "pattern": "optimize",
            "skill_id": "superpowers/optimize",
            "keywords": ["optimize", "优化", "performance", "性能"],
        },
        # Refactoring
        {
            "pattern": "refactor",
            "skill_id": "superpowers/refactor",
            "keywords": ["refactor", "重构", "clean up", "清理"],
        },
    ]

    # Default confidence weights for each matcher type
    # Used when no historical data suggests otherwise
    _DEFAULT_MATCHER_WEIGHTS: ClassVar[dict[str, float]] = {
        "keyword": 1.0,  # Trust exact keyword matches
        "scenario": 0.95,  # High trust in predefined scenarios
        "tfidf": 0.85,  # Good for semantic similarity
        "embedding": 0.9,  # High-quality semantic matching
        "levenshtein": 0.7,  # Fallback, lower confidence
    }

    # Priority skills to always include in candidate set
    _P0_SKILLS: ClassVar[list[str]] = [
        "systematic-debugging",
        "verification-before-completion",
        "session-end",
    ]

    # Default namespace priorities when query is ambiguous
    _NAMESPACE_PRIORITIES: ClassVar[dict[str, int]] = {
        "builtin": 100,  # Highest priority
        "superpowers": 80,
        "gstack": 70,
        "omx": 60,
        "external": 50,
    }

    def __init__(self, project_root: str | Path = "."):
        """Initialize cold start strategy.

        Args:
            project_root: Project root directory
        """
        self.project_root = Path(project_root).resolve()

    def get_builtin_mappings(self) -> list[QuerySkillMapping]:
        """Get built-in query → skill mappings.

        These mappings provide sensible defaults for common queries
        when no routing history exists.

        Returns:
            List of query-skill mappings
        """
        return [
            QuerySkillMapping(
                pattern=m["pattern"],
                skill_id=m["skill_id"],
                keywords=m.get("keywords", []),
            )
            for m in self._BUILTIN_MAPPINGS
        ]

    def get_mapping_for_query(self, query: str) -> QuerySkillMapping | None:
        """Get a built-in mapping for a specific query.

        Args:
            query: User's query

        Returns:
            Mapping if found, None otherwise
        """
        query_lower = query.lower()

        for mapping_dict in self._BUILTIN_MAPPINGS:
            # Check pattern match
            if mapping_dict["pattern"] in query_lower:
                return QuerySkillMapping(
                    pattern=mapping_dict["pattern"],
                    skill_id=mapping_dict["skill_id"],
                    keywords=mapping_dict.get("keywords", []),
                )

            # Check keyword match
            for keyword in mapping_dict.get("keywords", []):
                if keyword.lower() in query_lower:
                    return QuerySkillMapping(
                        pattern=mapping_dict["pattern"],
                        skill_id=mapping_dict["skill_id"],
                        keywords=mapping_dict.get("keywords", []),
                    )

        return None

    def get_default_weights(self) -> dict[str, float]:
        """Get default confidence weights for matchers.

        These weights are used when no historical preference
        data exists to inform matcher selection.

        Returns:
            Dictionary mapping matcher names to weights
        """
        return self._DEFAULT_MATCHER_WEIGHTS.copy()

    def get_p0_skills(self) -> list[str]:
        """Get priority skills that should always be included.

        These are core skills that are critical for the system
        to function properly.

        Returns:
            List of skill IDs
        """
        return self._P0_SKILLS.copy()

    def get_namespace_priority(self, namespace: str) -> int:
        """Get priority level for a namespace.

        Higher priority namespaces are preferred when queries
        are ambiguous.

        Args:
            namespace: Namespace name

        Returns:
            Priority score (higher = more important)
        """
        return self._NAMESPACE_PRIORITIES.get(namespace, 50)

    def should_warm_cache(self) -> bool:
        """Determine if cache should be warmed on startup.

        Returns:
            True if cache warming is recommended
        """
        # Check if this is first run (no preferences file)
        prefs_path = self.project_root / ".vibe" / "preferences.json"
        return not prefs_path.exists()


class _ColdStartStrategyCache:
    _instance: ColdStartStrategy | None = None

    @classmethod
    def get(cls, project_root: str | Path = ".") -> ColdStartStrategy:
        if cls._instance is None:
            cls._instance = ColdStartStrategy(project_root)
        return cls._instance


def get_cold_start_strategy(project_root: str | Path = ".") -> ColdStartStrategy:
    """Get or create the default cold start strategy.

    Args:
        project_root: Project root directory

    Returns:
        ColdStartStrategy instance
    """
    return _ColdStartStrategyCache.get(project_root)


__all__ = [
    "ColdStartStrategy",
    "QuerySkillMapping",
    "get_cold_start_strategy",
]
