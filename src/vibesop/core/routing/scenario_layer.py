"""Scenario pattern layer — predefined routing patterns.

Layer 2: Match queries against predefined scenario patterns from registry.yaml.
Each scenario maps a category of queries to a primary skill with alternatives.

Scenarios are defined in core/registry.yaml under conflict_resolution.strategies.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


def load_scenarios(registry_path: str | Path = "core/registry.yaml") -> list[dict[str, Any]]:
    """Load scenario patterns from registry.yaml.

    Args:
        registry_path: Path to registry.yaml

    Returns:
        List of scenario dicts with scenario, primary, alternatives, etc.
    """
    registry_path = Path(registry_path)
    if not registry_path.exists():
        return []

    try:
        with registry_path.open("r") as f:
            data = cast(Any, YAML().load(f))  # type: ignore[reportUnknownMemberType]

        if not data:
            return []

        data = cast(dict[str, Any], data)
        cr = data.get("conflict_resolution", {})
        if not cr.get("enabled", False):
            return []

        return cr.get("strategies", [])
    except Exception as e:
        logger.debug(f"Failed to load scenarios from {registry_path}: {e}")
        return []


def match_scenario(
    query: str,
    scenarios: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Match a query against scenario patterns.

    Uses keyword matching on scenario names and triggers.

    Args:
        query: User's query
        scenarios: List of scenario dicts from registry

    Returns:
        Matched scenario dict or None.
    """
    query_lower = query.lower()

    # Scenario keyword mapping
    scenario_keywords = {
        "debugging": ["debug", "bug", "error", "崩溃", "报错", "调试", "fix"],
        "code_review": ["review", "审查", "pr", "merge", "land"],
        "product_thinking": ["product", "产品", "brainstorm", "头脑风暴", "idea", "想法"],
        "planning": ["plan", "规划", "design", "设计", "architect", "架构"],
        "refactoring": ["refactor", "重构", "clean", "整理"],
        "architecture": ["architecture", "架构", "system design", "系统设计"],
        "requirements_clarification": [
            "clarify",
            "澄清",
            "requirements",
            "需求",
            "understand",
            "理解",
            "figure out",
            "搞清楚",
            "what to build",
            "做什么",
        ],
        "persistent_execution": [
            "implement",
            "实现",
            "build",
            "构建",
            "develop",
            "开发",
            "complete",
            "完成",
            "persistent",
            "持久",
        ],
        "structured_planning": [
            "plan",
            "规划",
            "structured",
            "结构化",
            "consensus",
            "共识",
            "adr",
            "decision",
            "决策",
        ],
        "parallel_execution": [
            "parallel",
            "并行",
            "team",
            "团队",
            "ultrawork",
            "multi-agent",
            "多代理",
            "distribute",
            "分发",
        ],
        "qa_cycling": [
            "qa",
            "test",
            "测试",
            "quality",
            "质量",
            "cycle",
            "循环",
            "browser test",
            "浏览器测试",
        ],
    }

    for scenario in scenarios:
        scenario_name = scenario.get("scenario", "")
        keywords = scenario_keywords.get(scenario_name, [])

        # Check if any keyword matches
        if any(kw in query_lower for kw in keywords):
            return scenario

    return None
