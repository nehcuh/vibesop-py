"""RouterTriageMixin - AI triage and matcher pipeline proxy methods.

These thin wrappers are kept for backward compatibility and will be
removed in a future major version. Callers should migrate to the
underlying services directly (e.g. TriageService, MatcherPipeline).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibesop.core.matching import RoutingContext


class RouterTriageMixin:
    """Mixin providing backward-compatible proxy methods for triage and matcher pipeline."""

    def _try_ai_triage(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None = None,
    ) -> Any:
        """Proxy to TriageService (kept for backward compatibility)."""
        if self._llm is not None:  # type: ignore[reportPrivateUsage]
            self._triage_service._llm = self._llm  # type: ignore[reportPrivateUsage]
        return self._triage_service.try_ai_triage(query, candidates, context)

    def _try_matcher_pipeline(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None,
        collect_rejected: bool = False,
    ) -> Any:
        """Proxy to MatcherPipeline (kept for backward compatibility)."""
        return self._matcher_pipeline.try_matcher_pipeline(
            query, candidates, context, collect_rejected=collect_rejected
        )

    def _prefilter_ai_triage_candidates(
        self, query: str, candidates: list[dict[str, Any]], max_skills: int
    ) -> list[dict[str, Any]]:
        return self._triage_service.prefilter_ai_triage_candidates(query, candidates, max_skills)

    def _build_ai_triage_prompt(self, query: str, skills_summary: str) -> str:
        return self._triage_service.build_ai_triage_prompt(query, skills_summary)

    def _init_llm_client(self) -> Any:
        return self._triage_service.init_llm_client()

    def _parse_ai_triage_response(self, response: str) -> dict[str, Any]:
        return self._triage_service.parse_ai_triage_response(response)
