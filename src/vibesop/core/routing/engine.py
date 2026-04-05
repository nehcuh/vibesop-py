"""Skill routing engine with 5-layer system.

Implements intelligent skill routing via pluggable handlers:
- Layer 0: AI Semantic Triage (Claude Haiku/GPT-4o-mini)
- Layer 1: Explicit overrides
- Layer 2: Scenario patterns
- Layer 3: Semantic matching (TF-IDF + cosine similarity)
- Layer 4: Fuzzy matching (Levenshtein distance)
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from vibesop.constants import RoutingThresholds
from vibesop.core.config_module import ConfigLoader
from vibesop.core.models import (
    RoutingRequest,
    RoutingResult,
    SkillRoute,
)
from vibesop.core.preference import PreferenceLearner
from vibesop.core.routing.cache import CacheManager
from vibesop.core.routing.fuzzy import FuzzyMatcher
from vibesop.core.routing.handlers import (
    AITriageHandler,
    ExplicitHandler,
    FuzzyHandler,
    RoutingHandler,
    ScenarioHandler,
    SemanticHandler,
)
from vibesop.core.routing.semantic import SemanticMatcher
from vibesop.llm import create_from_env


@dataclass
class RoutingStats:
    """Statistics about routing performance."""

    total_routes: int = 0
    layer_distribution: dict[str, int] = field(
        default_factory=lambda: {
            "layer_0_ai": 0,
            "layer_1_explicit": 0,
            "layer_2_scenario": 0,
            "layer_3_semantic": 0,
            "layer_4_fuzzy": 0,
            "no_match": 0,
        }
    )


class SkillRouter:
    """Intelligent skill router with 5-layer routing.

    Usage:
        router = SkillRouter()
        result = router.route(RoutingRequest(query="帮我评审代码"))
        print(result.primary.skill_id)  # '/review'
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        cache_dir: str = ".vibe/cache",
        enable_ai_triage: bool | None = None,
    ) -> None:
        self._stats = RoutingStats()
        self.project_root = Path(project_root).resolve()
        self._config = ConfigLoader(project_root=self.project_root)
        self._cache = CacheManager(cache_dir=cache_dir)

        # Initialize LLM provider for AI triage
        self._llm: Any = None
        if enable_ai_triage is None:
            enable_ai_triage = os.getenv("VIBE_AI_TRIAGE_ENABLED", "true").lower() == "true"

        if (
            os.getenv("CLAUDECODE") == "1" or os.getenv("CLAUDE_CODE_ENTRYPOINT") == "cli"
        ) and not os.getenv("VIBE_AI_TRIAGE_ENABLED"):
            enable_ai_triage = False

        if enable_ai_triage:
            try:
                self._llm = create_from_env()
                ai_enabled = self._llm.configured()
            except (ImportError, ValidationError, OSError) as e:
                ai_enabled = False
                if os.getenv("VIBE_DEBUG"):
                    import warnings

                    warnings.warn(f"AI triage disabled: {e}")
        else:
            ai_enabled = False

        # Initialize matchers
        self._semantic_matcher = SemanticMatcher(
            min_score=RoutingThresholds.SEMANTIC_SIMILARITY_MIN
        )
        self._fuzzy_matcher = FuzzyMatcher(
            min_similarity=RoutingThresholds.FUZZY_SIMILARITY_THRESHOLD, max_distance=2
        )

        # Initialize preference learner
        preference_path = self.project_root / ".vibe" / "preferences.json"
        self._preference_learner = PreferenceLearner(
            storage_path=preference_path,
            decay_days=30,
            min_samples=3,
        )

        # Build handler chain
        self._handlers: list[RoutingHandler] = [
            AITriageHandler(self._llm if ai_enabled else None, self._cache, self._config),
            ExplicitHandler(self._config),
            ScenarioHandler(self._config, str(self.project_root)),
            SemanticHandler(self._semantic_matcher),
            FuzzyHandler(self._fuzzy_matcher),
        ]

        # Load skills
        self._load_skills()

    def _load_skills(self) -> None:
        """Load and index skills from configuration."""
        try:
            skills = self._config.get_all_skills()
            if not skills:
                import warnings

                warnings.warn(
                    "No skills loaded from configuration. Router may not function properly."
                )
            self._semantic_matcher.index_skills(skills or [], self._config)
            self._fuzzy_matcher.index_skills(skills or [])
        except (FileNotFoundError, ValueError, KeyError) as e:
            import warnings

            warnings.warn(f"Failed to load skills from configuration: {e}")
            raise

    def route(self, request: RoutingRequest) -> RoutingResult:
        """Route a request to the appropriate skill."""
        self._stats.total_routes += 1
        normalized_input = self._normalize_input(request.query)

        for handler in self._handlers:
            result = handler.try_match(normalized_input, request.context)
            if result:
                layer_name = f"layer_{handler.layer_number}_{handler.layer_name}"
                self._stats.layer_distribution[layer_name] += 1
                boosted = self._apply_preference_boost(result, normalized_input)
                return RoutingResult(
                    primary=boosted,
                    alternatives=self._get_alternatives(boosted),
                    routing_path=[handler.layer_number],  # type: ignore[arg-type]
                )

        self._stats.layer_distribution["no_match"] += 1
        return self._no_match_result(normalized_input)

    def get_stats(self) -> dict[str, int | dict[str, int]]:
        """Get routing statistics."""
        return {
            "total_routes": self._stats.total_routes,
            "layer_distribution": self._stats.layer_distribution.copy(),
        }

    def _no_match_result(self, normalized_input: str) -> RoutingResult:  # noqa: ARG002
        """Create a no-match result."""
        skill = self._config.get_skill_by_id("riper-workflow")
        skill_id = skill["id"] if skill else "/riper-workflow"
        primary = SkillRoute(skill_id=skill_id, confidence=0.3, layer=4, source="fallback")
        return RoutingResult(primary=primary, alternatives=[], routing_path=[])

    def _normalize_input(self, input_text: str) -> str:
        """Normalize input text for matching."""
        normalized = re.sub(r"[^\w\s]", " ", input_text)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip().lower()

    # -- Preference learning --

    def record_selection(self, skill_id: str, query: str, was_helpful: bool = True) -> None:
        """Record a skill selection for preference learning."""
        self._preference_learner.record_selection(skill_id, query, was_helpful)

    def get_preference_stats(self) -> dict[str, Any]:
        """Get preference learning statistics."""
        return self._preference_learner.get_stats()

    def get_top_skills(self, limit: int = 5, min_selections: int = 2) -> list[Any]:
        """Get top preferred skills based on user history."""
        return self._preference_learner.get_top_skills(limit, min_selections)

    def clear_old_preferences(self, days: int = 90) -> int:
        """Clear old preference data."""
        return self._preference_learner.clear_old_data(days)

    def _apply_preference_boost(self, route: SkillRoute, query: str) -> SkillRoute:  # noqa: ARG002
        """Apply preference learning boost to a route."""
        pref_score = self._preference_learner.get_preference_score(route.skill_id)
        if pref_score == 0.0:
            return route

        boost = pref_score * 0.2
        boosted_confidence = min(1.0, route.confidence + boost)
        return SkillRoute(
            skill_id=route.skill_id,
            confidence=boosted_confidence,
            layer=route.layer,
            source=route.source,
            metadata={
                **route.metadata,
                "preference_boost": boost,
                "preference_score": pref_score,
            },
        )

    def _get_alternatives(self, primary: SkillRoute) -> list[SkillRoute]:
        """Get alternative skill matches based on similarity."""
        alternatives: list[SkillRoute] = []
        try:
            all_skills = self._config.get_all_skills()
            if not all_skills:
                return alternatives

            primary_skill_id = primary.skill_id
            primary_intent = ""
            for skill in all_skills:
                if skill["id"] == primary_skill_id:
                    primary_intent = skill.get("intent", skill.get("description", ""))
                    break

            if not primary_intent:
                return alternatives

            similar_skills: list[dict[str, Any]] = []
            for skill in all_skills:
                if skill["id"] == primary_skill_id:
                    continue
                skill_intent = skill.get("intent", skill.get("description", ""))
                primary_words = set(primary_intent.lower().split())
                skill_words = set(skill_intent.lower().split())
                if primary_words and skill_words:
                    intersection = primary_words & skill_words
                    union = primary_words | skill_words
                    similarity = len(intersection) / len(union) if union else 0
                    if similarity > 0.2:
                        similar_skills.append(
                            {
                                "skill_id": skill["id"],
                                "similarity": similarity,
                                "source": "semantic",
                            }
                        )

            similar_skills.sort(key=lambda x: x["similarity"], reverse=True)
            for skill_info in similar_skills[:3]:
                alternatives.append(
                    SkillRoute(
                        skill_id=skill_info["skill_id"],
                        confidence=skill_info["similarity"],
                        layer=primary.layer,
                        source="alternative",
                        metadata={"similarity": skill_info["similarity"]},
                    )
                )
        except (KeyError, AttributeError, TypeError) as e:
            if os.getenv("VIBE_DEBUG"):
                import warnings

                warnings.warn(f"Alternative selection failed: {e}")

        return alternatives
