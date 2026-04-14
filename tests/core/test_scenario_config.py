"""Tests for scenario routing configuration."""

from pathlib import Path

from vibesop.core.routing.scenario_config import (
    DEFAULT_SCENARIOS,
    get_routing_hints,
    load_scenarios,
)


class TestLoadScenarios:
    """Test suite for load_scenarios."""

    def test_fallback_when_file_missing(self, tmp_path) -> None:
        """Should return DEFAULT_SCENARIOS when config file is absent."""
        scenarios = load_scenarios(tmp_path)
        assert scenarios == DEFAULT_SCENARIOS

    def test_load_valid_yaml(self, tmp_path) -> None:
        """Should parse valid YAML config."""
        config_path = tmp_path / "core" / "policies" / "task-routing.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            """
scenario_patterns:
  - id: test-scenario
    name: Test Scenario
    keywords: [test, example]
    skill_id: test/skill
    confidence: 0.95
    trigger_mode: auto
    priority: P0
    message: "Hello"
  - id: fallback-scenario
    name: Fallback
    keywords: [fallback]
    skill_id: fallback/skill
    fallback_id: /fallback
routing_hints:
  - hint: use_builtin
""",
            encoding="utf-8",
        )
        scenarios = load_scenarios(tmp_path)
        assert len(scenarios) == 2
        assert scenarios[0]["id"] == "test-scenario"
        assert scenarios[0]["trigger_mode"] == "auto"
        assert scenarios[0]["priority"] == "P0"
        assert scenarios[0]["message"] == "Hello"
        assert "fallback_id" not in scenarios[0]
        assert scenarios[1].get("fallback_id") == "/fallback"

    def test_load_invalid_yaml_non_dict(self, tmp_path) -> None:
        """Should fallback when YAML content is not a dict."""
        config_path = tmp_path / "core" / "policies" / "task-routing.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        scenarios = load_scenarios(tmp_path)
        assert scenarios == DEFAULT_SCENARIOS

    def test_load_empty_scenario_patterns(self, tmp_path) -> None:
        """Should fallback when scenario_patterns is empty."""
        config_path = tmp_path / "core" / "policies" / "task-routing.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("scenario_patterns: []\n", encoding="utf-8")
        scenarios = load_scenarios(tmp_path)
        assert scenarios == DEFAULT_SCENARIOS

    def test_skip_non_dict_patterns(self, tmp_path) -> None:
        """Should skip pattern entries that are not dicts."""
        config_path = tmp_path / "core" / "policies" / "task-routing.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            """
scenario_patterns:
  - id: valid
    name: Valid
    keywords: [ok]
    skill_id: valid/skill
  - not a dict
""",
            encoding="utf-8",
        )
        scenarios = load_scenarios(tmp_path)
        assert len(scenarios) == 1
        assert scenarios[0]["id"] == "valid"

    def test_load_oserror(self, tmp_path, monkeypatch) -> None:
        """Should fallback on OSError during read."""
        config_path = tmp_path / "core" / "policies" / "task-routing.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("scenario_patterns: []\n", encoding="utf-8")

        def raise_oserror(*args, **kwargs):
            raise OSError("read error")

        monkeypatch.setattr(Path, "open", raise_oserror)
        scenarios = load_scenarios(tmp_path)
        assert scenarios == DEFAULT_SCENARIOS

    def test_load_yaml_parsing_exception(self, tmp_path) -> None:
        """Should fallback on YAML parsing exception."""
        config_path = tmp_path / "core" / "policies" / "task-routing.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("not: valid: : yaml: [", encoding="utf-8")
        scenarios = load_scenarios(tmp_path)
        assert scenarios == DEFAULT_SCENARIOS


class TestGetRoutingHints:
    """Test suite for get_routing_hints."""

    def test_empty_when_file_missing(self, tmp_path) -> None:
        """Should return empty list when config file is absent."""
        hints = get_routing_hints(tmp_path)
        assert hints == []

    def test_load_valid_hints(self, tmp_path) -> None:
        """Should parse routing hints from YAML."""
        config_path = tmp_path / "core" / "policies" / "task-routing.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            """
routing_hints:
  - type: prefer_builtin
    skill_id: debug
  - type: fallback
    skill_id: default
""",
            encoding="utf-8",
        )
        hints = get_routing_hints(tmp_path)
        assert len(hints) == 2
        assert hints[0]["type"] == "prefer_builtin"

    def test_load_hints_non_dict_yaml(self, tmp_path) -> None:
        """Should return empty list when YAML is not a dict."""
        config_path = tmp_path / "core" / "policies" / "task-routing.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("- list\n- items\n", encoding="utf-8")
        hints = get_routing_hints(tmp_path)
        assert hints == []

    def test_load_hints_oserror(self, tmp_path, monkeypatch) -> None:
        """Should return empty list on OSError."""
        config_path = tmp_path / "core" / "policies" / "task-routing.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("routing_hints: []\n", encoding="utf-8")

        def raise_oserror(*args, **kwargs):
            raise OSError("read error")

        monkeypatch.setattr(Path, "open", raise_oserror)
        hints = get_routing_hints(tmp_path)
        assert hints == []
