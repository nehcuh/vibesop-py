"""Router matcher mixin - explicit override and scenario pattern matching.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

from typing import Any

from vibesop.core.models import RoutingLayer, SkillRoute
from vibesop.core.routing.explicit_layer import check_explicit_override
from vibesop.core.routing.layers import LayerResult
from vibesop.core.routing.project_config import load_merged_scenario_config
from vibesop.core.routing.scenario_layer import match_scenario


class RouterMatcherMixin:
    """Mixin providing explicit override and scenario pattern matching.

    Intended for use with UnifiedRouter. Expects the following attributes
    on the host class:
        - project_root: Path
        - _scenario_cache: dict[str, Any] | None
    And the following method:
        - _get_skill_source(skill_id: str, namespace: str) -> str
    """

    def _try_explicit(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> LayerResult | None:
        explicit_skill, cleaned_query = check_explicit_override(query, candidates)
        if not explicit_skill:
            return None

        candidate = next((c for c in candidates if c["id"] == explicit_skill), None)
        if not candidate:
            return LayerResult(
                layer=RoutingLayer.EXPLICIT,
                matched=False,
                reason=f"@{explicit_skill} specified but skill not found in candidates",
            )

        source = self._get_skill_source(explicit_skill, candidate.get("namespace", "builtin"))
        return LayerResult(
            match=SkillRoute(
                skill_id=explicit_skill,
                confidence=1.0,
                layer=RoutingLayer.EXPLICIT,
                source=source,
                description=str(candidate.get("description", "")),
                metadata={"override": True, "cleaned_query": cleaned_query},
            ),
            layer=RoutingLayer.EXPLICIT,
            reason=f"Explicit override: @{explicit_skill}",
            diagnostics={"cleaned_query": cleaned_query},
        )

    def _try_scenario(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> LayerResult | None:
        if self._scenario_cache is None:
            self._scenario_cache = load_merged_scenario_config(self.project_root)
        scenarios = self._scenario_cache.get("strategies", [])
        keywords = self._scenario_cache.get("keywords", {})
        scenario = match_scenario(query, scenarios, keywords)
        if not scenario:
            return None

        target_skill = scenario.get("skill") or scenario.get("primary") or scenario.get("skill_id")
        if not target_skill:
            return LayerResult(
                layer=RoutingLayer.SCENARIO,
                matched=False,
                reason=f"Scenario '{scenario.get('scenario', 'unknown')}' matched but no target skill defined",
            )

        candidate = next((c for c in candidates if c["id"] == target_skill), None)
        if not candidate:
            return LayerResult(
                layer=RoutingLayer.SCENARIO,
                matched=False,
                reason=f"Scenario matched '{target_skill}' but skill not in candidates",
            )

        # Build alternatives from related skills in the same scenario
        alternatives: list[SkillRoute] = []
        related = scenario.get("related_skills", [])
        for rid in related:
            rel = next((c for c in candidates if c["id"] == rid), None)
            if rel:
                alternatives.append(
                    SkillRoute(
                        skill_id=rid,
                        confidence=0.75,
                        layer=RoutingLayer.SCENARIO,
                        source=self._get_skill_source(rid, rel.get("namespace", "builtin")),
                        description=str(rel.get("description", "")),
                        metadata={"scenario": scenario.get("scenario")},
                    )
                )

        scenario_name = scenario.get("scenario", "unknown")
        return LayerResult(
            match=SkillRoute(
                skill_id=target_skill,
                confidence=0.9,
                layer=RoutingLayer.SCENARIO,
                source=self._get_skill_source(
                    target_skill, candidate.get("namespace", "builtin")
                ),
                description=str(candidate.get("description", "")),
                metadata={"scenario": scenario_name},
            ),
            alternatives=alternatives,
            layer=RoutingLayer.SCENARIO,
            reason=f"Scenario matched: '{scenario_name}'",
            diagnostics={
                "scenario": scenario_name,
                "related_skills": related,
                "alternatives_count": len(alternatives),
            },
        )
