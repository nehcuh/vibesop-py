"""Scenario routing configuration.

Scenario patterns are configurable rather than hardcoded,
allowing users to customize which skills handle which scenarios.
"""

from __future__ import annotations

from typing import Any

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
