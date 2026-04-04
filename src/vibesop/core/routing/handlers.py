"""Routing layer handlers.

Each layer of the 5-layer routing system is implemented as a
separate handler class with a common interface.
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from typing import Any

from vibesop.core.models import SkillRoute


class RoutingHandler(ABC):
    """Base class for routing layer handlers."""

    @property
    @abstractmethod
    def layer_number(self) -> int:
        """Return the layer number (0-4)."""

    @property
    @abstractmethod
    def layer_name(self) -> str:
        """Return human-readable layer name."""

    @abstractmethod
    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],
    ) -> SkillRoute | None:
        """Try to match the input.

        Args:
            normalized_input: Normalized user input
            context: Routing context

        Returns:
            SkillRoute if matched, None otherwise
        """


class AITriageHandler(RoutingHandler):
    """Layer 0: AI-Powered Semantic Triage using LLM."""

    def __init__(self, llm_client: Any, cache: Any, config: Any) -> None:
        self._llm = llm_client
        self._cache = cache
        self._config = config
        self._ai_triage_enabled = llm_client is not None

    @property
    def layer_number(self) -> int:
        return 0

    @property
    def layer_name(self) -> str:
        return "ai"

    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],
    ) -> SkillRoute | None:
        if not self._ai_triage_enabled or not self._llm:
            return None

        cache_key = self._cache.generate_key(normalized_input, context)
        cached = self._cache.get(cache_key)
        if cached:
            return SkillRoute(**cached)

        prompt = self._build_prompt(normalized_input, context)

        try:
            response = self._llm.call(prompt=prompt, max_tokens=300, temperature=0.3)
            skill_id = self._parse_response(response.content)
            if skill_id:
                skill = self._config.get_skill_by_id(skill_id)
                if skill:
                    result = SkillRoute(
                        skill_id=skill["id"],
                        confidence=0.95,
                        layer=0,
                        source="ai_triage",
                    )
                    self._cache.set(cache_key, result.model_dump())
                    return result
        except (TimeoutError, ConnectionError, ValueError, KeyError) as e:
            if os.getenv("VIBE_DEBUG"):
                import warnings

                warnings.warn(f"AI triage call failed: {e}")

        return None

    def _build_prompt(self, input_text: str, context: dict[str, str | int]) -> str:
        skills_list = self._config.get_all_skills()
        skills_summary = "\n".join(
            f"- {s['id']}: {s.get('intent', 'N/A')}" for s in skills_list[:20]
        )
        context_str = f"\nContext: {context}" if context else ""
        return (
            f"Analyze the user request and select the most appropriate skill.\n\n"
            f"User request: {input_text}{context_str}\n\n"
            f"Available skills (top 20):\n{skills_summary}\n\n"
            f'Return ONLY the skill ID (e.g., "gstack/review" or "systematic-debugging"). '
            f"Do not include any other text.\n\nSkill ID:"
        )

    def _parse_response(self, response: str) -> str | None:
        if match := re.search(r"```(?:json)?\s*(\S+)```", response):
            return match.group(1)
        if match := re.search(r"^[\w/-]+", response.strip(), re.MULTILINE):
            return match.group(0)
        return None


class ExplicitHandler(RoutingHandler):
    """Layer 1: Explicit skill invocation (/review, 使用 review)."""

    def __init__(self, config: Any) -> None:
        self._config = config

    @property
    def layer_number(self) -> int:
        return 1

    @property
    def layer_name(self) -> str:
        return "explicit"

    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],  # noqa: ARG002
    ) -> SkillRoute | None:
        # Direct: /review
        if match := re.match(r"^/(\w+)", normalized_input):
            skill_id = f"/{match.group(1)}"
            skill = self._config.get_skill_by_id(skill_id)
            if skill:
                return SkillRoute(skill_id=skill["id"], confidence=1.0, layer=1, source="explicit")

        # Chinese: 使用 review / 调用 review
        if match := re.match(r"(?:使用|调用)\s*(\w+)", normalized_input):
            skill_id = f"/{match.group(1)}"
            skill = self._config.get_skill_by_id(skill_id)
            if skill:
                return SkillRoute(skill_id=skill["id"], confidence=1.0, layer=1, source="explicit")

        return None


class ScenarioHandler(RoutingHandler):
    """Layer 2: Scenario pattern matching (debug, test, review, refactor)."""

    def __init__(self, config: Any) -> None:
        self._config = config

    @property
    def layer_number(self) -> int:
        return 2

    @property
    def layer_name(self) -> str:
        return "scenario"

    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],  # noqa: ARG002
    ) -> SkillRoute | None:
        scenarios = [
            {
                "keywords": ["bug", "error", "错误", "调试", "debug", "fix", "修复"],
                "skill_id": "systematic-debugging",
            },
            {
                "keywords": ["review", "审查", "评审", "检查"],
                "skill_id": "gstack/review",
                "fallback_id": "/review",
            },
            {
                "keywords": ["test", "测试", "tdd"],
                "skill_id": "superpowers/tdd",
                "fallback_id": "/test",
            },
            {
                "keywords": ["refactor", "重构"],
                "skill_id": "superpowers/refactor",
            },
        ]

        for rule in scenarios:
            if any(kw in normalized_input for kw in rule["keywords"]):
                skill = self._config.get_skill_by_id(rule["skill_id"])
                if not skill and "fallback_id" in rule:
                    skill = self._config.get_skill_by_id(rule["fallback_id"])
                if skill:
                    return SkillRoute(
                        skill_id=skill["id"],
                        confidence=0.85,
                        layer=2,
                        source="scenario",
                    )
        return None


class SemanticHandler(RoutingHandler):
    """Layer 3: TF-IDF semantic matching."""

    def __init__(self, matcher: Any) -> None:
        self._matcher = matcher

    @property
    def layer_number(self) -> int:
        return 3

    @property
    def layer_name(self) -> str:
        return "semantic"

    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],  # noqa: ARG002
    ) -> SkillRoute | None:
        matches = self._matcher.match(normalized_input, top_k=1)
        if matches and matches[0].score >= 0.5:
            match = matches[0]
            return SkillRoute(
                skill_id=match.skill_id,
                confidence=match.score,
                layer=3,
                source="semantic",
            )
        return None


class FuzzyHandler(RoutingHandler):
    """Layer 4: Levenshtein fuzzy matching."""

    def __init__(self, matcher: Any) -> None:
        self._matcher = matcher

    @property
    def layer_number(self) -> int:
        return 4

    @property
    def layer_name(self) -> str:
        return "fuzzy"

    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],  # noqa: ARG002
    ) -> SkillRoute | None:
        matches = self._matcher.match(normalized_input, top_k=1)
        if matches and matches[0].score >= 0.7:
            match = matches[0]
            return SkillRoute(
                skill_id=match.skill_id,
                confidence=match.score,
                layer=4,
                source="fuzzy",
            )
        return None
