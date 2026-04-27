"""Confidence-gated layered degradation for skill routing.

Replaces binary fallback (match/no-match) with a 4-level degradation strategy:
- AUTO: confidence >= auto_threshold → auto-select
- SUGGEST: auto_threshold > confidence >= suggest_threshold → show with alternatives
- DEGRADE: suggest_threshold > confidence >= degrade_threshold → use but warn
- FALLBACK: confidence < degrade_threshold → raw LLM
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vibesop.core.models import DegradationLevel, SkillRoute

if TYPE_CHECKING:
    from vibesop.core.config.manager import RoutingConfig


class DegradationManager:
    """Evaluate routing match confidence and assign a degradation level."""

    def __init__(self, config: RoutingConfig) -> None:
        self._enabled = getattr(config, "degradation_enabled", True)
        self._auto_threshold = getattr(config, "degradation_auto_threshold", 0.6)
        self._suggest_threshold = getattr(config, "degradation_suggest_threshold", 0.4)
        self._degrade_threshold = getattr(config, "degradation_degrade_threshold", 0.2)
        self._always_ask = getattr(config, "degradation_fallback_always_ask", True)

    def evaluate(
        self, primary: SkillRoute | None
    ) -> tuple[DegradationLevel, SkillRoute | None]:
        """Evaluate a routing match and return (level, route).

        Returns (FALLBACK, None) when no route exists or confidence is below
        the degrade threshold.
        """
        if primary is None:
            return DegradationLevel.FALLBACK, None

        if not self._enabled:
            return DegradationLevel.AUTO, primary

        confidence = primary.confidence

        if confidence >= self._auto_threshold:
            return DegradationLevel.AUTO, primary

        if confidence >= self._suggest_threshold:
            return DegradationLevel.SUGGEST, primary

        if confidence >= self._degrade_threshold:
            degraded = SkillRoute(
                skill_id=primary.skill_id,
                confidence=primary.confidence,
                layer=primary.layer,
                source=primary.source,
                description=primary.description,
                metadata={**primary.metadata, "degraded": True, "degradation_level": "degrade"},
            )
            return DegradationLevel.DEGRADE, degraded

        return DegradationLevel.FALLBACK, None

    @property
    def always_ask_on_fallback(self) -> bool:
        return self._always_ask
