"""Tests for dynamic renderer condition evaluation."""

from unittest.mock import MagicMock

from vibesop.builder.dynamic_renderer import ConfigDrivenRenderer


class TestEvaluateCondition:
    """Tests for safe condition evaluation."""

    def test_empty_condition(self) -> None:
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        assert renderer._evaluate_condition("", manifest) is True
        assert renderer._evaluate_condition("   ", manifest) is True

    def test_valid_equality(self) -> None:
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"
        manifest.metadata.version = "2.1.0"

        assert renderer._evaluate_condition("platform == 'claude-code'", manifest) is True
        assert renderer._evaluate_condition("platform == 'opencode'", manifest) is False
        assert renderer._evaluate_condition("version == '2.1.0'", manifest) is True
        assert renderer._evaluate_condition('version == "2.1.0"', manifest) is True

    def test_invalid_condition_returns_false(self) -> None:
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"
        manifest.metadata.version = "2.1.0"

        assert renderer._evaluate_condition("import os", manifest) is False
        assert renderer._evaluate_condition("__import__('os').system('ls')", manifest) is False
        assert renderer._evaluate_condition("platform = 'claude-code'", manifest) is False
        assert renderer._evaluate_condition("unknown == 'value'", manifest) is False
        assert renderer._evaluate_condition("platform == claude-code", manifest) is False

    def test_parse_simple_equality(self) -> None:
        renderer = ConfigDrivenRenderer()
        context = {"platform": "claude-code", "version": "2.1.0"}

        assert renderer._parse_simple_equality("platform == 'claude-code'", context) is True
        assert renderer._parse_simple_equality("platform == 'opencode'", context) is False
