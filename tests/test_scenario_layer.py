"""Tests for scenario pattern layer."""

import pytest
from vibesop.core.routing.scenario_layer import load_scenarios, match_scenario


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


def test_match_debugging_scenario(scenarios):
    """Debug query should match debugging scenario."""
    result = match_scenario("帮我调试数据库错误", scenarios)
    assert result is not None
    assert result["primary"] == "systematic-debugging"


def test_match_debugging_scenario_english(scenarios):
    """English debug query should match."""
    result = match_scenario("debug this error please", scenarios)
    assert result is not None
    assert result["primary"] == "systematic-debugging"


def test_match_code_review_scenario(scenarios):
    """Review query should match code_review scenario."""
    result = match_scenario("review this PR before merge", scenarios)
    assert result is not None
    assert result["primary"] == "gstack/review"


def test_match_qa_scenario(scenarios):
    """QA query should match qa_cycling scenario."""
    result = match_scenario("帮我测试这个网站", scenarios)
    assert result is not None
    assert result["primary"] == "omx/ultraqa"


def test_no_match(scenarios):
    """Unrelated query should not match any scenario."""
    result = match_scenario("generate documentation", scenarios)
    assert result is None


def test_load_scenarios_from_registry():
    """Should load scenarios from registry.yaml."""
    scenarios = load_scenarios()
    assert isinstance(scenarios, list)
    assert len(scenarios) > 0
    # Should include our omx scenarios
    scenario_names = [s.get("scenario") for s in scenarios]
    assert "requirements_clarification" in scenario_names
    assert "parallel_execution" in scenario_names


def test_load_nonexistent_registry():
    """Should return empty list for nonexistent registry."""
    scenarios = load_scenarios("nonexistent/registry.yaml")
    assert scenarios == []
