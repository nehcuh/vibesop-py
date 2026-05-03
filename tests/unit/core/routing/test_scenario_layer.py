"""Tests for scenario pattern layer (Layer 1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from vibesop.core.routing.scenario_layer import (
    _matches_keyword,
    load_scenario_config,
    load_scenarios,
    match_scenario,
)


class TestMatchesKeyword:
    """Test keyword matching with word boundaries and CJK support."""

    def test_ascii_word_boundary_match(self) -> None:
        """ASCII keyword matches with word boundary."""
        assert _matches_keyword("debug", "help me debug this") is True

    def test_ascii_no_substring_match(self) -> None:
        """ASCII keyword does not match as substring of another word."""
        assert _matches_keyword("pr", "project") is False
        assert _matches_keyword("merge", "emerged") is False

    def test_cjk_substring_match(self) -> None:
        """CJK keyword matches via substring (no word boundary)."""
        assert _matches_keyword("调试", "帮我调试这个错误") is True

    def test_cjk_partial_no_match(self) -> None:
        """CJK keyword should not match partial characters."""
        assert _matches_keyword("调试器", "帮我调试") is False

    def test_empty_keyword(self) -> None:
        """Empty keyword never matches."""
        assert _matches_keyword("", "any query") is False

    def test_case_insensitive(self) -> None:
        """Matching is case-insensitive (query already lowercased)."""
        assert _matches_keyword("debug", "debug this") is True


class TestLoadScenarioConfig:
    """Test scenario config loading from registry.yaml."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent registry returns empty config."""
        result = load_scenario_config(tmp_path / "nonexistent.yaml")
        assert result == {"strategies": [], "keywords": {}}

    def test_disabled_conflict_resolution(self, tmp_path: Path) -> None:
        """Registry with disabled conflict_resolution returns empty."""
        registry = tmp_path / "registry.yaml"
        registry.write_text("conflict_resolution:\n  enabled: false\n")
        result = load_scenario_config(registry)
        assert result == {"strategies": [], "keywords": {}}

    def test_enabled_with_data(self, tmp_path: Path) -> None:
        """Registry with enabled conflict_resolution and data."""
        registry = tmp_path / "registry.yaml"
        registry.write_text(
            "conflict_resolution:\n"
            "  enabled: true\n"
            "  strategies:\n"
            "    - scenario: debug\n"
            "      primary: systematic-debugging\n"
            "  scenario_keywords:\n"
            "    debug: [debug, bug, error]\n"
        )
        result = load_scenario_config(registry)
        assert len(result["strategies"]) == 1
        assert result["strategies"][0]["scenario"] == "debug"
        assert result["keywords"]["debug"] == ["debug", "bug", "error"]

    def test_invalid_yaml_returns_empty(self, tmp_path: Path) -> None:
        """Invalid YAML returns empty config without raising."""
        registry = tmp_path / "registry.yaml"
        registry.write_text("not: valid: yaml: [")
        result = load_scenario_config(registry)
        assert result == {"strategies": [], "keywords": {}}


class TestLoadScenarios:
    """Test load_scenarios wrapper."""

    def test_returns_strategies_list(self, tmp_path: Path) -> None:
        """load_scenarios returns only the strategies list."""
        registry = tmp_path / "registry.yaml"
        registry.write_text(
            "conflict_resolution:\n"
            "  enabled: true\n"
            "  strategies:\n"
            "    - scenario: debug\n"
            "      primary: systematic-debugging\n"
        )
        scenarios = load_scenarios(registry)
        assert isinstance(scenarios, list)
        assert len(scenarios) == 1
        assert scenarios[0]["scenario"] == "debug"


class TestMatchScenario:
    """Test scenario matching against query."""

    def test_exact_match(self) -> None:
        """Query containing scenario keyword matches."""
        scenarios = [
            {"scenario": "debug", "primary": "systematic-debugging"},
        ]
        result = match_scenario("help me debug this", scenarios)
        assert result is not None
        assert result["scenario"] == "debug"

    def test_no_match(self) -> None:
        """Query without matching keywords returns None."""
        scenarios = [
            {"scenario": "debug", "primary": "systematic-debugging"},
        ]
        result = match_scenario("deploy to production", scenarios)
        assert result is None

    def test_custom_keywords(self) -> None:
        """Custom keywords mapping overrides scenario name."""
        scenarios = [
            {"scenario": "review", "primary": "gstack/review"},
        ]
        keywords = {"review": ["review", "pr", "code review"]}
        result = match_scenario("check my pr", scenarios, keywords)
        assert result is not None
        assert result["scenario"] == "review"

    def test_scenario_with_inline_keywords(self) -> None:
        """Scenario dict with 'keywords' field uses inline keywords."""
        scenarios = [
            {
                "scenario": "test",
                "primary": "superpowers/tdd",
                "keywords": ["test", "testing", "unittest"],
            },
        ]
        result = match_scenario("write unittest for this", scenarios)
        assert result is not None
        assert result["scenario"] == "test"

    def test_scenario_uses_id_when_scenario_missing(self) -> None:
        """Scenario dict with 'id' but no 'scenario' uses id."""
        scenarios = [
            {"id": "deploy", "primary": "gstack/ship"},
        ]
        result = match_scenario("deploy now", scenarios)
        assert result is not None
        assert result["id"] == "deploy"

    def test_empty_scenarios(self) -> None:
        """Empty scenarios list returns None."""
        result = match_scenario("anything", [])
        assert result is None

    def test_empty_keywords_skips(self) -> None:
        """Scenario with empty keywords list is skipped."""
        scenarios = [
            {"scenario": "empty", "primary": "none", "keywords": []},
        ]
        result = match_scenario("anything", scenarios)
        assert result is None

    def test_cjk_query_match(self) -> None:
        """CJK query matches CJK keywords."""
        scenarios = [
            {"scenario": "调试", "primary": "systematic-debugging"},
        ]
        result = match_scenario("帮我调试这个错误", scenarios)
        assert result is not None
        assert result["scenario"] == "调试"
