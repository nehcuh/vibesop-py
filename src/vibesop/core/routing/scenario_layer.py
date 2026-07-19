"""Scenario pattern layer — predefined routing patterns.

Layer 1: Match queries against predefined scenario patterns from registry.yaml.
Each scenario maps a category of queries to a primary skill with alternatives.

Scenarios are defined in core/registry.yaml under conflict_resolution.strategies.
Scenario keywords are defined in core/registry.yaml under conflict_resolution.scenario_keywords.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


def _matches_keyword(keyword: str, query_lower: str) -> bool:
    """Check whether a scenario keyword matches the (already-lowercased) query.

    ASCII keywords use a regex word-boundary match to prevent false positives
    where a short keyword is a substring of an unrelated word — e.g. ``"pr"``
    would otherwise match ``"project"``, ``"merge"`` would match ``"emerged"``.

    Non-ASCII (CJK) keywords keep substring matching because Python's ``\\b``
    word-boundary anchor only fires between ``[A-Za-z0-9_]`` and other
    characters, which doesn't behave well for Chinese/Japanese/Korean text.
    """
    if not keyword:
        return False
    if any(ord(c) > 127 for c in keyword):
        return keyword in query_lower
    return re.search(r"\b" + re.escape(keyword) + r"\b", query_lower) is not None


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
        with registry_path.open("r", encoding="utf-8") as f:
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
        # Same anti-pattern as ConfigManager.load_registry: swallowing parse
        # errors at debug silently disables scenario routing. Log at ERROR so a
        # broken registry.yaml is visible. Return contract preserved (empty).
        logger.error(
            "Failed to parse scenario config from %s: %s — scenario routing will "
            "be disabled. Fix the YAML (see parse error above).",
            registry_path,
            e,
        )
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

        # Check if any keyword matches (word-bounded for ASCII, substring for CJK).
        if any(_matches_keyword(kw, query_lower) for kw in scenario_keywords):
            return scenario

    return None
