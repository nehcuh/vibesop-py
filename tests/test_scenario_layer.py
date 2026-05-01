"""Tests for scenario pattern layer."""

from unittest.mock import MagicMock

import pytest

from vibesop.core.models import RoutingLayer
from vibesop.core.routing._layers import try_scenario_layer
from vibesop.core.routing.scenario_layer import (
    load_scenario_config,
    load_scenarios,
    match_scenario,
)


@pytest.fixture
def scenarios():
    return [
        {
            "scenario": "debugging",
            "primary": "systematic-debugging",
            "primary_source": "builtin",
            "alternatives": [
                {"skill": "gstack/investigate", "source": "gstack"},
            ],
        },
        {
            "scenario": "code_review",
            "primary": "gstack/review",
            "primary_source": "gstack",
            "alternatives": [
                {"skill": "superpowers/review", "source": "superpowers"},
            ],
        },
        {
            "scenario": "qa_cycling",
            "primary": "omx/ultraqa",
            "primary_source": "omx",
            "alternatives": [
                {"skill": "gstack/qa", "source": "gstack"},
            ],
        },
    ]


@pytest.fixture
def scenario_keywords():
    return {
        "debugging": ["debug", "bug", "error", "崩溃", "报错", "调试", "fix"],
        "code_review": ["review", "审查", "pr", "merge", "land"],
        "qa_cycling": ["qa", "test", "测试", "quality", "质量", "cycle", "循环", "browser test", "浏览器测试"],
    }


def test_match_debugging_scenario(scenarios, scenario_keywords):
    """Debug query should match debugging scenario."""
    result = match_scenario("帮我调试数据库错误", scenarios, scenario_keywords)
    assert result is not None
    assert result["primary"] == "systematic-debugging"


def test_match_debugging_scenario_english(scenarios, scenario_keywords):
    """English debug query should match."""
    result = match_scenario("debug this error please", scenarios, scenario_keywords)
    assert result is not None
    assert result["primary"] == "systematic-debugging"


def test_match_code_review_scenario(scenarios, scenario_keywords):
    """Review query should match code_review scenario."""
    result = match_scenario("review this PR before merge", scenarios, scenario_keywords)
    assert result is not None
    assert result["primary"] == "gstack/review"


def test_match_qa_scenario(scenarios, scenario_keywords):
    """QA query should match qa_cycling scenario."""
    result = match_scenario("帮我测试这个网站", scenarios, scenario_keywords)
    assert result is not None
    assert result["primary"] == "omx/ultraqa"


def test_no_match(scenarios, scenario_keywords):
    """Unrelated query should not match any scenario."""
    result = match_scenario("generate documentation", scenarios, scenario_keywords)
    assert result is None


def test_match_without_keywords_fallback(scenarios):
    """When no keywords provided, falls back to scenario name matching."""
    result = match_scenario("I need debugging help", scenarios)
    assert result is not None
    assert result["scenario"] == "debugging"


def test_load_scenarios_from_registry():
    """Should load scenarios from registry.yaml."""
    scenarios = load_scenarios()
    assert isinstance(scenarios, list)
    assert len(scenarios) > 0
    # Should include our omx scenarios
    scenario_names = [s.get("scenario") for s in scenarios]
    assert "requirements_clarification" in scenario_names
    assert "parallel_execution" in scenario_names


def test_load_scenario_config_from_registry():
    """Should load full scenario config from registry.yaml."""
    config = load_scenario_config()
    assert "strategies" in config
    assert "keywords" in config
    assert isinstance(config["strategies"], list)
    assert isinstance(config["keywords"], dict)
    assert "debugging" in config["keywords"]


def test_load_nonexistent_registry():
    """Should return empty list for nonexistent registry."""
    scenarios = load_scenarios("nonexistent/registry.yaml")
    assert scenarios == []


def test_load_nonexistent_registry_config():
    """Should return empty config for nonexistent registry."""
    config = load_scenario_config("nonexistent/registry.yaml")
    assert config["strategies"] == []
    assert config["keywords"] == {}


# -- Regression tests for try_scenario_layer --


def test_scenario_layer_returns_full_skill_id():
    """When scenario matches a short skill name but candidate has namespaced ID,
    the returned match must use the candidate's actual ID, not the short name.

    Regression: previously returned 'review' when candidate was 'gstack/review',
    causing the consumer to look up a nonexistent skill file.
    """
    router = MagicMock()
    router._scenario_cache = {
        "strategies": [
            {
                "scenario": "code_review",
                "primary": "review",
                "keywords": ["review", "审查"],
            }
        ],
        "keywords": {
            "code_review": ["review", "审查"],
        },
    }
    router._get_skill_source.return_value = "external"
    router._record_layer = MagicMock()

    # Candidate has namespaced ID — this is the real format from SkillLoader
    candidates = [
        {
            "id": "gstack/review",
            "name": "review",
            "namespace": "gstack",
            "description": "Code review skill",
        }
    ]

    match, detail = try_scenario_layer(router, "帮我 review 这段代码", candidates)

    assert match is not None, f"Expected match, got None with detail: {detail.reason}"
    assert match.skill_id == "gstack/review", (
        f"Expected 'gstack/review', got '{match.skill_id}'. "
        "Scenario layer must return the candidate's actual ID, not the short name."
    )
    assert match.layer == RoutingLayer.SCENARIO
    assert detail.matched is True


def test_scenario_layer_returns_exact_match_id():
    """When candidate ID exactly matches scenario target_skill, use it as-is."""
    router = MagicMock()
    router._scenario_cache = {
        "strategies": [
            {
                "scenario": "debugging",
                "primary": "systematic-debugging",
                "keywords": ["debug", "bug"],
            }
        ],
        "keywords": {
            "debugging": ["debug", "bug"],
        },
    }
    router._get_skill_source.return_value = "builtin"
    router._record_layer = MagicMock()

    candidates = [
        {
            "id": "systematic-debugging",
            "namespace": "builtin",
            "description": "Debug skill",
        }
    ]

    match, detail = try_scenario_layer(router, "debug this error", candidates)

    assert match is not None
    assert match.skill_id == "systematic-debugging"
    assert detail.matched is True


def test_scenario_layer_short_name_with_dash_prefix():
    """Scenario with /-prefixed short name should resolve via endswith checks."""
    router = MagicMock()
    router._scenario_cache = {
        "strategies": [
            {
                "scenario": "benchmarking",
                "primary": "/benchmark",
                "keywords": ["benchmark", "性能测试"],
            }
        ],
        "keywords": {
            "benchmarking": ["benchmark", "性能测试"],
        },
    }
    router._get_skill_source.return_value = "external"
    router._record_layer = MagicMock()

    candidates = [
        {
            "id": "superpowers/benchmark",
            "namespace": "superpowers",
            "description": "Benchmark skill",
        }
    ]

    match, detail = try_scenario_layer(router, "benchmark this code", candidates)

    assert match is not None, f"Expected match, got None: {detail.reason}"
    assert match.skill_id == "superpowers/benchmark", (
        f"Expected 'superpowers/benchmark', got '{match.skill_id}'"
    )


def test_scenario_layer_no_match_when_skill_missing():
    """When scenario matches but no candidate exists, should return no match."""
    router = MagicMock()
    router._scenario_cache = {
        "strategies": [
            {
                "scenario": "code_review",
                "primary": "nonexistent-skill",
                "keywords": ["review"],
            }
        ],
        "keywords": {
            "code_review": ["review"],
        },
    }
    router._get_skill_source.return_value = "builtin"
    router._record_layer = MagicMock()

    candidates = [
        {
            "id": "gstack/review",
            "namespace": "gstack",
            "description": "Code review skill",
        }
    ]

    match, detail = try_scenario_layer(router, "review my code", candidates)

    assert match is None
    assert detail.matched is False
    assert "skill not in candidates" in detail.reason
