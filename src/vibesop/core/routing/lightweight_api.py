"""LightweightRouter — minimal routing API for sub-agent consumption.

Provides a zero-friction interface for sub-agents and scripts to query
the VibeSOP routing system. Designed for:

- Fast response (<50ms for keyword routing)
- Sub-agent friendliness: results are simple dicts, easy to parse
- Batch support: route multiple queries in one call
- No side effects: purely returns routing results, never writes files

Usage from CLI:
    vibe route "debug this error" --json --minimal

Usage from Python:
    router = LightweightRouter(project_root=".")
    result = router.route("debug this error")
    print(result["skill_id"])  # "systematic-debugging"
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LightweightRouter:
    """Lightweight routing API for sub-agent consumption.

    Wraps UnifiedRouter's keyword/fast-path routing only — no LLM calls,
    ensuring sub-50ms response times. Falls back gracefully when the
    full router is unavailable.

    Args:
        project_root: Project root directory for config resolution.
    """

    def __init__(self, project_root: str | Path = ".") -> None:
        self._project_root = Path(project_root).resolve()
        self._router: Any = None

    def _get_router(self) -> Any:
        """Lazily initialize the UnifiedRouter."""
        if self._router is not None:
            return self._router

        try:
            from vibesop.core.routing import UnifiedRouter

            self._router = UnifiedRouter(project_root=self._project_root)
        except Exception as e:
            logger.debug("Failed to initialize UnifiedRouter: %s", e)
            self._router = None
        return self._router

    def route(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Route a single query.

        Args:
            query: Natural language query.
            context: Optional context (phase, step, conversation_id).

        Returns:
            Dict with skill_id, confidence, reasoning, layer, alternatives.
        """
        router = self._get_router()
        if router is None:
            return self._fallback_result()

        try:
            from vibesop.core.matching import RoutingContext

            ctx = RoutingContext(skip_ai_triage=True)
            if context:
                if "conversation_id" in context:
                    ctx.conversation_id = context["conversation_id"]
                if "phase" in context:
                    ctx.strategy_hint = f"phase:{context['phase']}"

            result = router.orchestrate(query, context=ctx)
            return self._format_result(result)
        except Exception as e:
            logger.debug("LightweightRouter.route failed: %s", e)
            return self._fallback_result(str(e))

    def route_batch(
        self,
        queries: list[str],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Route multiple queries.

        Args:
            queries: List of natural language queries.
            context: Shared context for all queries.

        Returns:
            List of routing result dicts, one per query.
        """
        return [self.route(q, context) for q in queries]

    @staticmethod
    def _format_result(result: Any) -> dict[str, Any]:
        """Format orchestration result into a minimal dict."""
        if result.mode.value == "orchestrated" and result.execution_plan:
            plan = result.execution_plan
            steps = []
            for s in plan.steps:
                steps.append(
                    {
                        "step": s.step_number,
                        "skill_id": s.skill_id,
                        "intent": s.intent,
                        "query": s.input_query,
                    }
                )
            return {
                "mode": "orchestrated",
                "pattern": plan.workflow_pattern.value,
                "plan_id": plan.plan_id,
                "steps": steps,
                "skill_id": steps[0]["skill_id"] if steps else "",
                "confidence": 0.9,
                "reasoning": f"Multi-intent: {len(steps)} steps",
            }

        # Single skill match
        primary = result.primary
        if primary is None:
            return {
                "mode": "no_match",
                "skill_id": "",
                "confidence": 0.0,
                "reasoning": "No matching skill found",
            }

        alternatives = []
        for alt in getattr(result, "alternatives", []) or []:
            alternatives.append(
                {
                    "skill_id": alt.skill_id,
                    "confidence": alt.confidence,
                }
            )

        return {
            "mode": "single",
            "skill_id": primary.skill_id,
            "confidence": primary.confidence,
            "reasoning": getattr(primary, "reasoning", ""),
            "layer": primary.layer.value if hasattr(primary, "layer") else "",
            "alternatives": alternatives[:5],
        }

    @staticmethod
    def _fallback_result(
        error: str = "",
    ) -> dict[str, Any]:
        """Fallback when router is unavailable."""
        return {
            "mode": "fallback",
            "skill_id": "",
            "confidence": 0.0,
            "reasoning": f"Router unavailable: {error}" if error else "Router unavailable",
        }

    def route_json(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Route and return JSON string (for CLI consumption).

        Args:
            query: Natural language query.
            context: Optional context.

        Returns:
            JSON string with routing result.
        """
        result = self.route(query, context)
        return json.dumps(result, ensure_ascii=False)
