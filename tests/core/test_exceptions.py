"""Tests for core exceptions."""

from pathlib import Path

import pytest

from vibesop.core.exceptions import (
    CacheError,
    ConfigurationError,
    CronParseError,
    InvalidConfigError,
    LLMError,
    LoopNameError,
    MatcherError,
    NoMatchingSkillError,
    PermissionError,
    RoutingError,
    SkillLoadError,
    SkillNotFoundError,
    SkillParseError,
    VibeSOPError,
)


class TestVibeSOPError:
    """Tests for base exception."""

    def test_basic_message(self) -> None:
        exc = VibeSOPError("Something went wrong")
        assert str(exc) == "Something went wrong"
        assert exc.message == "Something went wrong"
        assert exc.details == {}

    def test_with_details(self) -> None:
        exc = VibeSOPError("Something went wrong", details={"code": "E123", "field": "name"})
        assert "Something went wrong" in str(exc)
        assert "code=E123" in str(exc)
        assert "field=name" in str(exc)
        assert exc.details == {"code": "E123", "field": "name"}


class TestRoutingErrors:
    """Tests for routing exceptions."""

    def test_routing_error(self) -> None:
        exc = RoutingError("Route failed")
        assert str(exc) == "Route failed"

    def test_skill_not_found(self) -> None:
        exc = SkillNotFoundError("debug")
        assert "Skill not found: debug" in str(exc)
        assert exc.skill_id == "debug"
        assert exc.details["skill_id"] == "debug"

    def test_no_matching_skill(self) -> None:
        exc = NoMatchingSkillError("help me", 0.45)
        assert "No skill matched query" in str(exc)
        assert exc.query == "help me"
        assert exc.max_confidence == 0.45

    def test_matcher_error(self) -> None:
        exc = MatcherError("tfidf", "vectorizer not fitted")
        assert "Matcher error in tfidf" in str(exc)
        assert exc.matcher_type == "tfidf"


class TestConfigurationErrors:
    """Tests for configuration exceptions."""

    def test_configuration_error(self) -> None:
        exc = ConfigurationError("Bad config")
        assert str(exc) == "Bad config"

    def test_invalid_config(self) -> None:
        exc = InvalidConfigError("timeout", "abc", "must be a number")
        assert "Invalid configuration for timeout" in str(exc)
        assert exc.key == "timeout"
        assert exc.value == "abc"
        assert exc.reason == "must be a number"

    def test_invalid_config_none_value(self) -> None:
        exc = InvalidConfigError("timeout", None, "required")
        assert "Invalid configuration for timeout" in str(exc)


class TestSkillErrors:
    """Tests for skill exceptions."""

    def test_skill_load_error(self) -> None:
        path = Path("/tmp/skill.md")
        exc = SkillLoadError(path, "File not found")
        assert "Failed to load skill" in str(exc)
        assert exc.skill_path == path
        assert exc.reason == "File not found"

    def test_skill_parse_error(self) -> None:
        path = Path("/tmp/skill.md")
        exc = SkillParseError(path, "Invalid YAML")
        assert "Failed to load skill" in str(exc)


class TestLLMError:
    """Tests for LLM exception."""

    def test_llm_error(self) -> None:
        exc = LLMError("anthropic", "Rate limited")
        assert "LLM error (anthropic)" in str(exc)
        assert exc.provider == "anthropic"
        assert exc.details["provider"] == "anthropic"


class TestPermissionError:
    """Tests for permission exception."""

    def test_permission_error(self) -> None:
        exc = PermissionError("write", "/etc/config")
        assert "Permission denied for write on /etc/config" in str(exc)
        assert exc.operation == "write"
        assert exc.resource == "/etc/config"


class TestCacheError:
    """Tests for cache exception."""

    def test_cache_error(self) -> None:
        exc = CacheError("Cache miss")
        assert str(exc) == "Cache miss"


class TestCronParseError:
    """deep-diagnosis-2026-07-24 P0-2: new exception types in the loop /
    instinct / observability modules must be VibeSOPError subclasses AND
    multi-inherit ValueError so Pydantic validators still surface them as
    ValidationError. Otherwise the CLI can't tell user config errors
    (catch VibeSOPError → friendly message) apart from internal bugs."""

    def test_is_vibesop_error(self) -> None:
        exc = CronParseError("foo bar", "test reason")
        assert isinstance(exc, VibeSOPError)
        assert isinstance(exc, ConfigurationError)

    def test_is_value_error(self) -> None:
        """Pydantic only catches ValueError in validators — multi-inheritance
        keeps the new exception type compatible with existing validator usage."""
        exc = CronParseError("foo bar", "test reason")
        assert isinstance(exc, ValueError)

    def test_caught_by_value_error_except(self) -> None:
        """Existing CLI code with ``except ValueError`` must keep working."""
        with pytest.raises(ValueError, match="foo bar"):
            raise CronParseError("foo bar", "demo")

    def test_attributes_preserved(self) -> None:
        exc = CronParseError("*/foo * * * *", "must be 5 fields")
        assert exc.expr == "*/foo * * * *"
        assert exc.reason == "must be 5 fields"
        assert "*/foo * * * *" in str(exc)


class TestLoopNameError:
    """Same multi-inheritance rationale as CronParseError."""

    def test_is_vibesop_error(self) -> None:
        exc = LoopNameError("../etc", "pattern mismatch")
        assert isinstance(exc, VibeSOPError)
        assert isinstance(exc, ConfigurationError)

    def test_is_value_error(self) -> None:
        exc = LoopNameError("../etc", "pattern mismatch")
        assert isinstance(exc, ValueError)

    def test_message_format(self) -> None:
        """Existing test_store.py asserts regex 'unsafe loop name' — keep the
        lowercase prefix stable."""
        exc = LoopNameError("../etc", "must match pattern")
        assert "unsafe loop name" in str(exc)
        assert "../etc" in str(exc)
