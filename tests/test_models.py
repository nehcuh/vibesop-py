"""Test core Pydantic models."""

import pytest
from pydantic import ValidationError

from vibesop.core.models import (
    AppSettings,
    RoutingLayer,
    RoutingRequest,
    RoutingResult,
    SkillRoute,
)


class TestSkillRoute:
    """Test SkillRoute model."""

    def test_create_valid_skill_route(self) -> None:
        """Test creating a valid skill route."""
        route = SkillRoute(
            skill_id="/review",
            confidence=0.95,
            layer=RoutingLayer.AI_TRIAGE,
            source="builtin",
        )
        assert route.skill_id == "/review"
        assert route.confidence == 0.95
        assert route.layer == RoutingLayer.AI_TRIAGE
        assert route.source == "builtin"

    def test_skill_id_valid_formats(self) -> None:
        """Test that skill_id accepts valid formats."""
        route1 = SkillRoute(
            skill_id="/review",
            confidence=0.95,
            layer=RoutingLayer.AI_TRIAGE,
            source="builtin",
        )
        assert route1.skill_id == "/review"

        route2 = SkillRoute(
            skill_id="gstack/review",
            confidence=0.95,
            layer=RoutingLayer.AI_TRIAGE,
            source="gstack",
        )
        assert route2.skill_id == "gstack/review"

        route3 = SkillRoute(
            skill_id="review",
            confidence=0.95,
            layer=RoutingLayer.AI_TRIAGE,
            source="builtin",
        )
        assert route3.skill_id == "review"

    def test_confidence_must_be_between_0_and_1(self) -> None:
        """Test confidence validation."""
        with pytest.raises(ValidationError):
            SkillRoute(
                skill_id="/review",
                confidence=1.5,
                layer=RoutingLayer.AI_TRIAGE,
                source="builtin",
            )

        with pytest.raises(ValidationError):
            SkillRoute(
                skill_id="/review",
                confidence=-0.1,
                layer=RoutingLayer.AI_TRIAGE,
                source="builtin",
            )

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        route = SkillRoute(
            skill_id="gstack/review",
            confidence=0.9,
            layer=RoutingLayer.SCENARIO,
            source="external",
            metadata={"key": "value"},
        )
        d = route.to_dict()
        assert d["skill_id"] == "gstack/review"
        assert d["layer"] == "scenario"
        assert d["metadata"] == {"key": "value"}

    def test_layer_number_property(self) -> None:
        """Test RoutingLayer.layer_number property."""
        assert RoutingLayer.AI_TRIAGE.layer_number == 0
        assert RoutingLayer.EXPLICIT.layer_number == 1
        assert RoutingLayer.SCENARIO.layer_number == 2
        assert RoutingLayer.KEYWORD.layer_number == 3
        assert RoutingLayer.LEVENSHTEIN.layer_number == 6


class TestRoutingRequest:
    """Test RoutingRequest model."""

    def test_create_routing_request(self) -> None:
        """Test creating a routing request."""
        request = RoutingRequest(
            query="帮我评审代码",
            context={"file_type": "python"},
        )
        assert request.query == "帮我评审代码"
        assert request.context["file_type"] == "python"

    def test_query_cannot_be_empty(self) -> None:
        """Test that query cannot be empty."""
        with pytest.raises(ValidationError):
            RoutingRequest(query="")

    def test_context_defaults_to_empty_dict(self) -> None:
        """Test default context."""
        request = RoutingRequest(query="test")
        assert request.context == {}


class TestRoutingResult:
    """Test RoutingResult model."""

    def test_create_routing_result(self) -> None:
        """Test creating a routing result."""
        primary = SkillRoute(
            skill_id="/review",
            confidence=0.95,
            layer=RoutingLayer.AI_TRIAGE,
            source="builtin",
        )
        result = RoutingResult(primary=primary)

        assert result.primary.skill_id == "/review"
        assert result.alternatives == []
        assert result.routing_path == []
        assert result.has_match is True

    def test_routing_result_with_alternatives(self) -> None:
        """Test routing result with alternatives."""
        primary = SkillRoute(
            skill_id="/review",
            confidence=0.95,
            layer=RoutingLayer.AI_TRIAGE,
            source="builtin",
        )
        alternatives = [
            SkillRoute(
                skill_id="/codex",
                confidence=0.80,
                layer=RoutingLayer.AI_TRIAGE,
                source="gstack",
            ),
        ]

        result = RoutingResult(
            primary=primary,
            alternatives=alternatives,
            routing_path=[RoutingLayer.AI_TRIAGE, RoutingLayer.KEYWORD],
        )

        assert len(result.alternatives) == 1
        assert len(result.routing_path) == 2

    def test_no_match_result(self) -> None:
        """Test result with no match."""
        result = RoutingResult()
        assert result.primary is None
        assert result.has_match is False

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        primary = SkillRoute(
            skill_id="gstack/review",
            confidence=0.9,
            layer=RoutingLayer.SCENARIO,
            source="external",
        )
        result = RoutingResult(primary=primary, query="test query", duration_ms=12.5)
        d = result.to_dict()
        assert d["primary"]["skill_id"] == "gstack/review"
        assert d["has_match"] is True
        assert d["duration_ms"] == 12.5


class TestAppSettings:
    """Test AppSettings model."""

    def test_default_settings(self) -> None:
        """Test default settings."""
        settings = AppSettings()
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert settings.llm_provider == "anthropic"

    def test_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading settings from environment."""
        monkeypatch.setenv("VIBE_DEBUG", "true")
        monkeypatch.setenv("VIBE_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("VIBE_LLM_PROVIDER", "openai")

        settings = AppSettings()
        assert settings.debug is True
        assert settings.log_level == "DEBUG"
        assert settings.llm_provider == "openai"
