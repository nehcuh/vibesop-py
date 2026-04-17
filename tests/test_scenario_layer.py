"""Tests for scenario pattern layer."""

import pytest

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
