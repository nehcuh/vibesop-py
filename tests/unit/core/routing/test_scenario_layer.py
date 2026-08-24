"""Tests for scenario pattern layer (Layer 1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from vibesop.core.routing._layers import try_scenario_layer
from vibesop.core.routing.scenario_layer import (
    _matches_keyword,
    load_scenario_config,
    load_scenarios,
    match_scenario,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


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
        registry.write_text("conflict_resolution:\n  enabled: false\n", encoding="utf-8")
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
            "    debug: [debug, bug, error]\n",
            encoding="utf-8",
        )
        result = load_scenario_config(registry)
        assert len(result["strategies"]) == 1
        assert result["strategies"][0]["scenario"] == "debug"
        assert result["keywords"]["debug"] == ["debug", "bug", "error"]

    def test_invalid_yaml_returns_empty(self, tmp_path: Path) -> None:
        """Invalid YAML returns empty config without raising."""
        registry = tmp_path / "registry.yaml"
        registry.write_text("not: valid: yaml: [", encoding="utf-8")
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
            "      primary: systematic-debugging\n",
            encoding="utf-8",
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


class TestScenarioPrimarySource:
    """try_scenario_layer must honor a scenario's declared primary_source.

    Regression guard for the code_review hijack: a bare ``primary: /review``
    used to resolve to the FIRST installed pack skill named ``review``
    (e.g. mattpocock/review) at a fixed 0.9 confidence, hijacking generic
    review/评审/pr/merge queries on machines without the intended pack.
    """

    def _router(self, strategies: list[dict], keywords: dict[str, list[str]]) -> MagicMock:
        router = MagicMock()
        router._scenario_cache = {"strategies": strategies, "keywords": keywords}
        router._get_skill_source = lambda sid, ns: ns
        return router

    def test_declared_source_missing_fails_closed(self) -> None:
        """Declared primary_source with no installed candidate → no match."""
        router = self._router(
            [{"scenario": "code_review", "primary": "/review", "primary_source": "gstack"}],
            {"code_review": ["review"]},
        )
        candidates = [
            {"id": "mattpocock/review", "description": "Review", "namespace": "mattpocock"},
        ]
        match, detail = try_scenario_layer(router, "please review this", candidates)
        assert match is None
        assert detail.matched is False
        assert "gstack" in detail.reason

    def test_declared_source_match_resolves(self) -> None:
        """Candidate in the declared namespace resolves normally."""
        router = self._router(
            [{"scenario": "code_review", "primary": "/review", "primary_source": "gstack"}],
            {"code_review": ["review"]},
        )
        candidates = [
            {"id": "mattpocock/review", "description": "Pack review", "namespace": "mattpocock"},
            {"id": "gstack/review", "description": "GStack review", "namespace": "gstack"},
        ]
        match, detail = try_scenario_layer(router, "please review this", candidates)
        assert match is not None
        assert match.skill_id == "gstack/review"
        assert detail.matched is True

    def test_undeclared_source_keeps_legacy_resolution(self) -> None:
        """Without primary_source, the first matching candidate still wins."""
        router = self._router(
            [{"scenario": "code_review", "primary": "/review"}],
            {"code_review": ["review"]},
        )
        candidates = [
            {"id": "mattpocock/review", "description": "Review", "namespace": "mattpocock"},
        ]
        match, _detail = try_scenario_layer(router, "please review this", candidates)
        assert match is not None
        assert match.skill_id == "mattpocock/review"

    def test_id_prefix_counts_as_source(self) -> None:
        """Namespace missing from candidate dict: id prefix is accepted."""
        router = self._router(
            [{"scenario": "code_review", "primary": "/review", "primary_source": "gstack"}],
            {"code_review": ["review"]},
        )
        candidates = [{"id": "gstack/review", "description": "Review"}]
        match, _detail = try_scenario_layer(router, "please review this", candidates)
        assert match is not None
        assert match.skill_id == "gstack/review"


class TestRegistryScenarioConfig:
    """Regression guards on the real core/registry.yaml scenario config."""

    def test_planning_scenario_removed(self) -> None:
        """The planning scenario coupled broad plan/design keywords to
        builtin/riper-workflow at a fixed 0.9, contradicting that skill's
        explicit-intent-only contract. It must stay removed."""
        config = load_scenario_config(REPO_ROOT / "core" / "registry.yaml")
        names = {s.get("scenario") or s.get("id") for s in config["strategies"]}
        assert "planning" not in names
        assert "planning" not in config["keywords"]

    def test_code_review_scenario_pinned_to_gstack(self) -> None:
        """code_review's primary must stay source-pinned so it fails closed
        on machines without the intended pack installed."""
        config = load_scenario_config(REPO_ROOT / "core" / "registry.yaml")
        code_review = next(s for s in config["strategies"] if s.get("scenario") == "code_review")
        assert code_review.get("primary_source") == "gstack"
