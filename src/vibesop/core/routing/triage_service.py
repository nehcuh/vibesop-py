"""AI Triage service for routing layer 2."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from vibesop.core.models import RoutingLayer, SkillRoute
from vibesop.core.routing.circuit_breaker import TriageCircuitBreaker
from vibesop.core.routing.layers import LayerResult
from vibesop.llm.factory import create_provider
from vibesop.llm.triage_prompts import TriagePromptRegistry

if TYPE_CHECKING:
    from collections.abc import Callable

    from vibesop.core.config import RoutingConfig
    from vibesop.core.optimization import CandidatePrefilter
    from vibesop.core.routing.cache import CacheManager
    from vibesop.llm.cost_tracker import TriageCostTracker

logger = logging.getLogger(__name__)


class TriageService:
    """AI Triage layer for skill routing."""

    def __init__(
        self,
        config: RoutingConfig,
        cost_tracker: TriageCostTracker,
        prefilter: CandidatePrefilter,
        cache_manager: CacheManager,
        get_skill_source: Callable[..., str],
    ) -> None:
        self._config = config
        self._cost_tracker = cost_tracker
        self._prefilter = prefilter
        self._cache_manager = cache_manager
        self._get_skill_source = get_skill_source
        self._llm: Any | None = None
        self._circuit_breaker = TriageCircuitBreaker(
            enabled=getattr(config, "ai_triage_circuit_breaker_enabled", True),
            failure_threshold=getattr(config, "ai_triage_circuit_breaker_failure_threshold", 3),
            latency_threshold_ms=getattr(
                config, "ai_triage_circuit_breaker_latency_threshold_ms", 500.0
            ),
            cooldown_seconds=getattr(
                config, "ai_triage_circuit_breaker_cooldown_seconds", 60
            ),
        )

    def try_ai_triage(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: Any | None = None,
    ) -> LayerResult | None:
        if not self._config.enable_ai_triage:
            return None

        if self._llm is None:
            self._llm = self.init_llm_client()

        if self._llm is None or not self._llm.configured():
            return None

        # Budget enforcement
        budget = getattr(self._config, "ai_triage_budget_monthly", 5.0)
        if budget > 0:
            monthly_cost = self._cost_tracker.get_monthly_cost()
            if monthly_cost >= budget:
                logger.debug(
                    f"AI triage skipped: monthly budget exhausted ({monthly_cost:.4f}/{budget:.4f} USD)"
                )
                self._circuit_breaker.trip("budget_exhausted")
                return None
            if monthly_cost >= budget * 0.9:
                logger.warning(
                    f"AI triage budget at {monthly_cost:.4f}/{budget:.4f} USD (90%+)")

        # Circuit breaker: fast-fail if recent calls have been slow or failing
        if not self._circuit_breaker.can_execute():
            logger.debug("AI triage skipped: circuit breaker is open")
            return None

        # Cost control: pre-filter candidates with keyword matcher before sending to LLM
        max_skills = self._config.ai_triage_max_skills
        triage_candidates = self.prefilter_ai_triage_candidates(query, candidates, max_skills)

        # Build augmented query with memory context
        augmented_query = query
        if context and context.recent_queries and (
            len(query) < 20 or any(
                p in query.lower() for p in ("还是", "再", "继续", "也", "另外", "还有")
            )
        ):
            augmented_query = "Conversation:\n" + "\n".join(
                f"- {q}" for q in context.recent_queries[-3:]
            ) + f"\nCurrent request: {query}"

        cache_key = f"ai_triage:{augmented_query}"
        cached = self._get_cache(cache_key)
        if cached:
            return LayerResult(match=cached, layer=RoutingLayer.AI_TRIAGE)

        skills_summary = "\n".join(
            f"- {c['id']}: {c.get('intent', c.get('description', 'N/A'))}"
            for c in triage_candidates
        )

        prompt = self.build_ai_triage_prompt(augmented_query, skills_summary)

        import time

        start_time = time.perf_counter()
        try:
            response = self._llm.call(
                prompt=prompt,
                max_tokens=self._config.ai_triage_max_tokens,
                temperature=0.1,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000

            parsed = self.parse_ai_triage_response(response.content)
            skill_id = parsed.get("skill_id")
            parsed_confidence = parsed.get("confidence")

            # Record cost if enabled
            log_calls = getattr(self._config, "ai_triage_log_calls", True)
            if log_calls:
                input_tokens = getattr(response, "input_tokens", None)
                output_tokens = getattr(response, "output_tokens", None)
                tokens_used = getattr(response, "tokens_used", None)
                if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
                    # Fallback to tokens_used if split counts aren't available
                    if isinstance(tokens_used, int):
                        input_tokens = tokens_used
                        output_tokens = 0
                    else:
                        input_tokens = 0
                        output_tokens = 0
                self._cost_tracker.record(
                    model=getattr(response, "model", "unknown"),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    query=query,
                    selected_skill=skill_id,
                )

            # Record success for circuit breaker
            self._circuit_breaker.record_success(latency_ms)
            self._circuit_breaker.maybe_trip_on_latency()

            if skill_id:
                candidate = next((c for c in candidates if c["id"] == skill_id), None)
                if candidate:
                    source = self._get_skill_source(
                        skill_id, candidate.get("namespace", "builtin")
                    )
                    # Dynamic confidence: structured JSON gets higher trust than regex fallback
                    confidence = 0.88 if parsed.get("structured") else 0.82
                    if isinstance(parsed_confidence, (int, float)) and 0.0 <= float(parsed_confidence) <= 1.0:
                        confidence = float(parsed_confidence)
                    result = SkillRoute(
                        skill_id=skill_id,
                        confidence=confidence,
                        layer=RoutingLayer.AI_TRIAGE,
                        source=source,
                        metadata={
                            "ai_triage": True,
                            "structured": parsed.get("structured", False),
                            "model": getattr(response, "model", "unknown"),
                            "candidates_sent": len(triage_candidates),
                        },
                    )
                    self._set_cache(cache_key, result.to_dict())
                    return LayerResult(match=result, layer=RoutingLayer.AI_TRIAGE)
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(f"AI triage failed, falling through to next layer: {e}")
            self._circuit_breaker.record_failure(latency_ms, reason=str(e))

        return None

    def prefilter_ai_triage_candidates(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        max_skills: int,
    ) -> list[dict[str, Any]]:
        """Pre-filter candidates for AI Triage using fast keyword matching.

        Instead of sending all candidates to the LLM (wasteful), we use the
        KeywordMatcher to rank them by relevance and only send the top N.
        """
        if len(candidates) <= max_skills:
            return candidates

        from vibesop.core.matching import KeywordMatcher, MatcherConfig

        matcher_config = MatcherConfig(
            min_confidence=0.0,
            use_cache=False,
        )
        matcher = KeywordMatcher(matcher_config)
        matches = matcher.match(query, candidates, top_k=max_skills)
        matched_ids = {m.skill_id for m in matches}

        # Preserve original order for matched candidates, then backfill if needed
        prefiltered = [c for c in candidates if c["id"] in matched_ids]
        if len(prefiltered) < max_skills:
            remaining = [c for c in candidates if c["id"] not in matched_ids]
            prefiltered.extend(remaining[: max_skills - len(prefiltered)])

        return prefiltered[:max_skills]

    def build_ai_triage_prompt(self, query: str, skills_summary: str) -> str:
        version = getattr(self._config, "ai_triage_prompt_version", "v2")
        return TriagePromptRegistry.render(
            query=query,
            skills_summary=skills_summary,
            version=version,
        )

    def init_llm_client(self) -> Any | None:
        # Allow explicit disable via env var
        if os.getenv("VIBE_AI_TRIAGE_ENABLED", "").lower() in ("0", "false", "no"):
            return None
        try:
            provider = create_provider()
            return provider
        except (OSError, ValueError, RuntimeError) as e:
            logger.debug(f"LLM client initialization failed: {e}")
            return None

    def parse_ai_triage_response(self, response: str) -> dict[str, Any]:
        """Parse AI Triage response with structured JSON priority + regex fallback.

        Returns a dict with:
            - skill_id: str | None
            - confidence: float | None
            - structured: bool (whether JSON was successfully parsed)
        """
        import json
        import re

        result: dict[str, Any] = {"skill_id": None, "confidence": None, "structured": False}

        # Try JSON first
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Strip markdown code fences
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        if cleaned.startswith("{"):
            try:
                data = json.loads(cleaned)
                if isinstance(data, dict):
                    result["skill_id"] = data.get("skill_id") if isinstance(data.get("skill_id"), str) else None
                    result["confidence"] = data.get("confidence")
                    result["structured"] = True
                    return result
            except (json.JSONDecodeError, ValueError):
                pass

        # Regex fallback
        if match := re.search(r"```(?:json)?\s*([\w/-]+)```", response):
            result["skill_id"] = match.group(1).strip()
            return result
        _MARKDOWN_FENCE_KEYWORDS = {"json", "yaml", "yml", "python", "py", "text", "markdown", "md"}
        if match := re.search(r"^[\w/-]{3,}$", response.strip(), re.MULTILINE):
            candidate = match.group(0).strip()
            if candidate.lower() not in _MARKDOWN_FENCE_KEYWORDS:
                result["skill_id"] = candidate
                return result

        return result

    def _get_cache(self, key: str) -> SkillRoute | None:
        data = self._cache_manager.get(key)
        if data:
            try:
                return SkillRoute(
                    skill_id=data["skill_id"],
                    confidence=data["confidence"],
                    layer=RoutingLayer(data["layer"]),
                    source=data["source"],
                    metadata=data.get("metadata", {}),
                )
            except (KeyError, TypeError) as e:
                logger.debug(f"Failed to deserialize cached SkillRoute: {e}")
        return None

    def _set_cache(self, key: str, data: dict[str, Any]) -> None:
        self._cache_manager.set(key, data, ttl=3600)
