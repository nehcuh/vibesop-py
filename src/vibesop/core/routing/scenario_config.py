"""Scenario routing configuration.

Scenario patterns are loaded from core/policies/task-routing.yaml,
allowing users to customize which skills handle which scenarios.

Project-level overrides can be specified in .vibe/skill-routing.yaml
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True

logger = logging.getLogger(__name__)

# Fallback scenarios if YAML file is not found
DEFAULT_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "debug",
        "keywords": ["bug", "error", "错误", "调试", "debug", "fix", "修复"],
        "skill_id": "systematic-debugging",
        "confidence": 0.85,
    },
    {
        "name": "review",
        "keywords": ["review", "审查", "评审", "检查"],
        "skill_id": "gstack/review",
        "fallback_id": "/review",
        "confidence": 0.85,
    },
    {
        "name": "test",
        "keywords": ["test", "测试", "tdd"],
        "skill_id": "superpowers/tdd",
        "fallback_id": "/test",
        "confidence": 0.85,
    },
    {
        "name": "refactor",
        "keywords": ["refactor", "重构"],
        "skill_id": "superpowers/refactor",
        "confidence": 0.85,
    },
]


def load_scenarios(project_root: str | Path = ".") -> list[dict[str, Any]]:
    """Load scenario patterns from YAML configuration.

    Args:
        project_root: Path to project root directory

    Returns:
        List of scenario dictionaries
    """
    config_path = Path(project_root) / "core" / "policies" / "task-routing.yaml"

    if not config_path.exists():
        return DEFAULT_SCENARIOS

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = cast("Any", yaml.load(f))  # type: ignore[reportUnknownMemberType]

        if not isinstance(data, dict):
            return DEFAULT_SCENARIOS

        data = cast("dict[str, Any]", data)
        patterns = data.get("scenario_patterns", [])
        scenarios: list[dict[str, Any]] = []

        for pattern in patterns:
            if not isinstance(pattern, dict):
                continue

            pattern = cast("dict[str, Any]", pattern)
            scenario = {
                "id": pattern.get("id", "unknown"),
                "name": pattern.get("name", pattern.get("id", "unknown")),
                "keywords": pattern.get("keywords", []),
                "skill_id": pattern.get("skill_id", ""),
                "confidence": pattern.get("confidence", 0.85),
                "trigger_mode": pattern.get("trigger_mode", "suggest"),
                "priority": pattern.get("priority", "P1"),
                "message": pattern.get("message", ""),
            }

            # Add fallback_id if specified
            if "fallback_id" in pattern:
                scenario["fallback_id"] = pattern["fallback_id"]

            scenarios.append(scenario)

        return scenarios if scenarios else DEFAULT_SCENARIOS

    except (OSError, Exception) as e:
        logger.debug(f"Failed to load scenario config from {config_path}: {e}")
        return DEFAULT_SCENARIOS


def get_routing_hints(project_root: str | Path = ".") -> list[dict[str, Any]]:
    """Load routing hints from YAML configuration.

    Args:
        project_root: Path to project root directory

    Returns:
        List of routing hint dictionaries
    """
    config_path = Path(project_root) / "core" / "policies" / "task-routing.yaml"

    if not config_path.exists():
        return []

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = cast("Any", yaml.load(f))  # type: ignore[reportUnknownMemberType]

        if not isinstance(data, dict):
            return []

        data = cast("dict[str, Any]", data)
        return list(data.get("routing_hints", []))

    except (OSError, Exception) as e:
        logger.debug(f"Failed to load routing hints from {config_path}: {e}")
        return []
