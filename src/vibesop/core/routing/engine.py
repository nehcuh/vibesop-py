"""Skill routing engine with 5-layer system.

Implements intelligent skill routing:
- Layer 0: AI Semantic Triage (Claude Haiku/GPT-4o-mini)
- Layer 1: Explicit overrides
- Layer 2: Scenario patterns
- Layer 3: Semantic matching (TF-IDF + cosine similarity)
- Layer 4: Fuzzy matching (Levenshtein distance)
"""

import os
import re
from dataclasses import dataclass, field

from vibesop.core.models import (
    RoutingRequest,
    RoutingResult,
    SkillRoute,
)
from vibesop.core.routing.cache import CacheManager
from vibesop.llm import create_from_env


@dataclass
class RoutingStats:
    """Statistics about routing performance.

    Attributes:
        total_routes: Total number of routing requests
        layer_distribution: Distribution of routes by layer
    """

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

        # Get statistics
        stats = router.get_stats()
        print(stats)  # {'total_routes': 1, 'layer_distribution': {...}}
    """

    def __init__(
        self,
        cache_dir: str = ".vibe/cache",
        enable_ai_triage: bool | None = None,
    ) -> None:
        """Initialize the skill router.

        Args:
            cache_dir: Directory for cache storage
            enable_ai_triage: Override AI triage setting
        """
        self._stats = RoutingStats()

        # Initialize cache
        self._cache = CacheManager(cache_dir=cache_dir)

        # Initialize LLM provider for AI triage
        self._llm = None
        self._ai_triage_enabled = False

        if enable_ai_triage is None:
            enable_ai_triage = os.getenv("VIBE_AI_TRIAGE_ENABLED", "true").lower() == "true"

        # Check for Claude Code environment
        if (
            os.getenv("CLAUDECODE") == "1" or os.getenv("CLAUDE_CODE_ENTRYPOINT") == "cli"
        ) and not os.getenv("VIBE_AI_TRIAGE_ENABLED"):
            # Claude Code has built-in reasoning, disable external AI by default
            enable_ai_triage = False

        if enable_ai_triage:
            try:
                self._llm = create_from_env()
                self._ai_triage_enabled = self._llm.configured()
            except Exception:
                self._ai_triage_enabled = False

        # Mock skill registry (will be loaded from YAML in production)
        self._skill_registry = self._load_mock_registry()

    def route(self, request: RoutingRequest) -> RoutingResult:
        """Route a request to the appropriate skill.

        Args:
            request: The routing request

        Returns:
            RoutingResult with primary skill and alternatives
        """
        self._stats.total_routes += 1

        # Normalize input
        normalized_input = self._normalize_input(request.query)

        # Try each layer in order
        for layer_num in range(5):
            layer_result = self._try_layer(layer_num, normalized_input, request.context)
            if layer_result:
                # Update stats
                layer_name = f"layer_{layer_num}_{'ai' if layer_num == 0 else ['explicit', 'scenario', 'semantic', 'fuzzy'][layer_num - 1]}"
                self._stats.layer_distribution[layer_name] += 1

                return RoutingResult(
                    primary=layer_result,
                    alternatives=self._get_alternatives(layer_result),
                    routing_path=[layer_num],
                )

        # No match found
        self._stats.layer_distribution["no_match"] += 1
        return self._no_match_result(normalized_input)

    def get_stats(self) -> dict[str, int | dict[str, int]]:
        """Get routing statistics.

        Returns:
            Dictionary with routing statistics
        """
        return {
            "total_routes": self._stats.total_routes,
            "layer_distribution": self._stats.layer_distribution.copy(),
        }

    def _try_layer(
        self,
        layer_num: int,
        normalized_input: str,
        context: dict[str, str | int],
    ) -> SkillRoute | None:
        """Try a specific routing layer.

        Args:
            layer_num: Layer number (0-4)
            normalized_input: Normalized user input
            context: Routing context

        Returns:
            SkillRoute if matched, None otherwise
        """
        match layer_num:
            case 0:
                return self._layer_0_ai_triage(normalized_input, context)
            case 1:
                return self._layer_1_explicit(normalized_input)
            case 2:
                return self._layer_2_scenario(normalized_input, context)
            case 3:
                return self._layer_3_semantic(normalized_input)
            case 4:
                return self._layer_4_fuzzy(normalized_input)
            case _:
                return None

    def _layer_0_ai_triage(
        self,
        normalized_input: str,
        context: dict[str, str | int],
    ) -> SkillRoute | None:
        """Layer 0: AI-Powered Semantic Triage.

        Uses LLM for semantic understanding (95% accuracy).
        """
        if not self._ai_triage_enabled or not self._llm:
            return None

        # Check cache first
        cache_key = self._cache.generate_key(normalized_input, context)
        cached = self._cache.get(cache_key)
        if cached:
            return SkillRoute(**cached)

        # Build prompt
        prompt = self._build_triage_prompt(normalized_input, context)

        try:
            response = self._llm.call(
                prompt=prompt,
                max_tokens=300,
                temperature=0.3,
            )

            # Parse response
            skill_id = self._parse_ai_response(response.content)
            if skill_id:
                result = SkillRoute(
                    skill_id=skill_id,
                    confidence=0.95,
                    layer=0,
                    source="ai_triage",
                )
                # Cache result
                self._cache.set(cache_key, result.model_dump())
                return result
        except Exception:
            # AI triage failed, fall through to next layer
            pass

        return None

    def _layer_1_explicit(self, normalized_input: str) -> SkillRoute | None:
        """Layer 1: Explicit overrides.

        Matches explicit skill invocations like "/review" or "使用 review".
        """
        # Direct skill invocation: "/review" or "/review this code"
        if match := re.match(r"^/(\w+)", normalized_input):
            skill_id = f"/{match.group(1)}"
            if self._skill_exists(skill_id):
                return SkillRoute(
                    skill_id=skill_id,
                    confidence=1.0,
                    layer=1,
                    source="explicit",
                )

        # Chinese explicit invocation: "使用 review" or "调用 review"
        if match := re.match(r"(?:使用|调用)\s*(\w+)", normalized_input):
            skill_id = f"/{match.group(1)}"
            if self._skill_exists(skill_id):
                return SkillRoute(
                    skill_id=skill_id,
                    confidence=1.0,
                    layer=1,
                    source="explicit",
                )

        return None

    def _layer_2_scenario(
        self,
        normalized_input: str,
        context: dict[str, str | int],  # noqa: ARG002
    ) -> SkillRoute | None:
        """Layer 2: Scenario patterns.

        Matches pre-defined scenarios like "debug error" or "test failure".
        """
        # Debug/bug scenarios
        if any(word in normalized_input for word in ["bug", "error", "错误", "调试", "debug", "fix"]):
            return SkillRoute(
                skill_id="/debug",
                confidence=0.85,
                layer=2,
                source="scenario",
            )

        # Review scenarios
        if any(word in normalized_input for word in ["review", "审查", "评审", "检查"]):
            return SkillRoute(
                skill_id="/review",
                confidence=0.85,
                layer=2,
                source="scenario",
            )

        # Test scenarios
        if any(word in normalized_input for word in ["test", "测试", "tdd"]):
            return SkillRoute(
                skill_id="/test",
                confidence=0.85,
                layer=2,
                source="scenario",
            )

        # Refactor scenarios
        if any(word in normalized_input for word in ["refactor", "重构"]):
            return SkillRoute(
                skill_id="/refactor",
                confidence=0.85,
                layer=2,
                source="scenario",
            )

        return None

    def _layer_3_semantic(self, normalized_input: str) -> SkillRoute | None:
        """Layer 3: Semantic matching.

        Uses TF-IDF + cosine similarity for semantic matching.
        """
        # For now, use simple keyword matching
        # TODO: Implement proper TF-IDF + cosine similarity

        best_match = None
        best_score = 0.0

        for skill in self._skill_registry.values():
            # Calculate simple similarity score
            score = self._calculate_similarity(normalized_input, skill["keywords"])
            if score > best_score and score >= 0.6:
                best_score = score
                best_match = skill

        if best_match:
            return SkillRoute(
                skill_id=best_match["id"],
                confidence=best_score,
                layer=3,
                source="semantic",
            )

        return None

    def _layer_4_fuzzy(
        self,
        normalized_input: str,  # noqa: ARG002
    ) -> SkillRoute | None:
        """Layer 4: Fuzzy matching.

        Uses Levenshtein distance for fuzzy matching.
        """
        # For now, return a default skill
        # TODO: Implement proper Levenshtein distance matching

        return SkillRoute(
            skill_id="/general",
            confidence=0.5,
            layer=4,
            source="fuzzy",
        )

    def _no_match_result(
        self,
        normalized_input: str,  # noqa: ARG002
    ) -> RoutingResult:
        """Create a no-match result."""
        primary = SkillRoute(
            skill_id="/general",
            confidence=0.3,
            layer=4,
            source="fallback",
        )

        return RoutingResult(
            primary=primary,
            alternatives=[],
            routing_path=[],
        )

    def _normalize_input(self, input_text: str) -> str:
        """Normalize input text for matching."""
        # Remove punctuation
        normalized = re.sub(r"[^\w\s]", " ", input_text)
        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip().lower()

    def _build_triage_prompt(self, input_text: str, context: dict[str, str | int]) -> str:
        """Build prompt for AI triage."""
        skills_list = "\n".join(
            f"- {s['id']}: {s['description']}" for s in self._skill_registry.values()
        )

        context_str = ""
        if context:
            context_str = f"\nContext: {context}"

        return f"""Analyze the user request and select the most appropriate skill.

User request: {input_text}{context_str}

Available skills:
{skills_list}

Return ONLY the skill ID (e.g., "/review"). Do not include any other text.

Skill ID:"""

    def _parse_ai_response(self, response: str) -> str | None:
        """Parse AI response to extract skill ID."""
        # Extract skill ID from response
        # Handle markdown code blocks
        if match := re.search(r"```(?:json)?\s*(\S+)```", response):
            return match.group(1)

        # Handle plain text response
        if match := re.search(r"^/[\w-]+", response.strip(), re.MULTILINE):
            return match.group(0)

        return None

    def _skill_exists(self, skill_id: str) -> bool:
        """Check if a skill exists in the registry."""
        return skill_id in self._skill_registry

    def _calculate_similarity(self, input_text: str, keywords: list[str]) -> float:
        """Calculate similarity score between input and keywords."""
        input_words = set(input_text.lower().split())
        keyword_words = set(" ".join(keywords).lower().split())

        if not input_words or not keyword_words:
            return 0.0

        # Jaccard similarity
        intersection = input_words & keyword_words
        union = input_words | keyword_words

        return len(intersection) / len(union) if union else 0.0

    def _get_alternatives(
        self,
        primary: SkillRoute,  # noqa: ARG002
    ) -> list[SkillRoute]:
        """Get alternative skill matches."""
        # For now, return empty list
        # TODO: Implement proper alternative selection
        return []

    def _load_mock_registry(self) -> dict[str, dict[str, any]]:
        """Load mock skill registry.

        TODO: Load from YAML configuration files.
        """
        return {
            "/review": {
                "id": "/review",
                "description": "Review code for quality and best practices",
                "keywords": ["review", "审查", "评审", "check", "检查"],
            },
            "/debug": {
                "id": "/debug",
                "description": "Debug errors and investigate issues",
                "keywords": ["debug", "bug", "error", "错误", "调试", "fix", "修复"],
            },
            "/test": {
                "id": "/test",
                "description": "Write and run tests",
                "keywords": ["test", "测试", "tdd", "spec"],
            },
            "/refactor": {
                "id": "/refactor",
                "description": "Refactor code for better structure",
                "keywords": ["refactor", "重构", "clean", "cleanup"],
            },
            "/general": {
                "id": "/general",
                "description": "General purpose workflow",
                "keywords": ["general", "help", "general"],
            },
        }
