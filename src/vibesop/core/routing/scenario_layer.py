"""Scenario pattern layer — predefined routing patterns.

Layer 2: Match queries against predefined scenario patterns from registry.yaml.
Each scenario maps a category of queries to a primary skill with alternatives.

Scenarios are defined in core/registry.yaml under conflict_resolution.strategies.
Scenario keywords are defined in core/registry.yaml under conflict_resolution.scenario_keywords.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


def load_scenario_config(registry_path: str | Path = "core/registry.yaml") -> dict[str, Any]:
    """Load scenario configuration from registry.yaml.

    Args:
        registry_path: Path to registry.yaml

    Returns:
        Dictionary with "strategies" and "keywords" keys.
    """
    registry_path = Path(registry_path)
    if not registry_path.exists():
        return {"strategies": [], "keywords": {}}

    try:
        with registry_path.open("r") as f:
            data = cast("Any", YAML().load(f))  # type: ignore[reportUnknownMemberType]

        if not data:
            return {"strategies": [], "keywords": {}}

        data = cast("dict[str, Any]", data)
        cr = data.get("conflict_resolution", {})
        if not cr.get("enabled", False):
            return {"strategies": [], "keywords": {}}

        return {
            "strategies": cr.get("strategies", []),
            "keywords": cr.get("scenario_keywords", {}),
        }
    except Exception as e:
        logger.debug(f"Failed to load scenario config from {registry_path}: {e}")
        return {"strategies": [], "keywords": {}}


def load_scenarios(registry_path: str | Path = "core/registry.yaml") -> list[dict[str, Any]]:
    """Load scenario patterns from registry.yaml.

    Backward-compatible wrapper that returns only the strategies list.

    Args:
        registry_path: Path to registry.yaml

    Returns:
        List of scenario dicts with scenario, primary, alternatives, etc.
    """
    return load_scenario_config(registry_path).get("strategies", [])


def match_scenario(
    query: str,
    scenarios: list[dict[str, Any]],
    keywords: dict[str, list[str]] | None = None,
) -> dict[str, Any] | None:
    """Match a query against scenario patterns.

    Uses keyword matching on scenario names. Keywords are looked up from the
    provided mapping, falling back to the scenario name itself.

    Args:
        query: User's query
        scenarios: List of scenario dicts from registry
        keywords: Optional mapping of scenario_name -> trigger keywords.
            If omitted, only the scenario name is used for matching.

    Returns:
        Matched scenario dict or None.
    """
    query_lower = query.lower()
    keywords = keywords or {}

    for scenario in scenarios:
        scenario_name = scenario.get("scenario", "")
        # Project-level scenario_patterns use "id" instead of "scenario"
        if not scenario_name:
            scenario_name = scenario.get("id", "")

        # Use keywords from the scenario dict first (supports project-level patterns),
        # then fall back to the global keywords mapping, then to the scenario name.
        scenario_keywords = scenario.get("keywords", [])
        if not scenario_keywords:
            scenario_keywords = keywords.get(scenario_name, [scenario_name])
        if not scenario_keywords or scenario_keywords == [""]:
            continue

        # Check if any keyword matches
        if any(kw and kw in query_lower for kw in scenario_keywords):
            return scenario

    return None
