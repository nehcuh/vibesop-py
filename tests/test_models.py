"""Test core Pydantic models."""

import pytest
from pydantic import ValidationError

from vibesop.core.models import (
    AppSettings,
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
            layer=0,
            source="builtin",
        )
        assert route.skill_id == "/review"
        assert route.confidence == 0.95
        assert route.layer == 0
        assert route.source == "builtin"

    def test_skill_id_valid_formats(self) -> None:
        """Test that skill_id accepts valid formats."""
        # Shorthand with leading slash
        route1 = SkillRoute(
            skill_id="/review",
            confidence=0.95,
            layer=0,
            source="builtin",
        )
        assert route1.skill_id == "/review"

        # Namespaced format
        route2 = SkillRoute(
            skill_id="gstack/review",
            confidence=0.95,
            layer=0,
            source="gstack",
        )
        assert route2.skill_id == "gstack/review"

        # Shorthand without leading slash gets normalized
        route3 = SkillRoute(
            skill_id="review",
            confidence=0.95,
            layer=0,
            source="builtin",
        )
        assert route3.skill_id == "/review"

    def test_confidence_must_be_between_0_and_1(self) -> None:
        """Test confidence validation."""
        with pytest.raises(ValidationError):
            SkillRoute(
                skill_id="/review",
                confidence=1.5,  # Too high
                layer=0,
                source="builtin",
            )

        with pytest.raises(ValidationError):
            SkillRoute(
                skill_id="/review",
                confidence=-0.1,  # Too low
                layer=0,
                source="builtin",
            )


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
            layer=0,
            source="builtin",
        )
        result = RoutingResult(primary=primary)

        assert result.primary.skill_id == "/review"
        assert result.alternatives == []
        assert result.routing_path == []

    def test_routing_result_with_alternatives(self) -> None:
        """Test routing result with alternatives."""
        primary = SkillRoute(
            skill_id="/review",
            confidence=0.95,
            layer=0,
            source="builtin",
        )
        alternatives = [
            SkillRoute(
                skill_id="/codex",
                confidence=0.80,
                layer=0,
                source="gstack",
            ),
        ]

        result = RoutingResult(
            primary=primary,
            alternatives=alternatives,
            routing_path=[0, 3],
        )

        assert len(result.alternatives) == 1
        assert result.routing_path == [0, 3]


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
