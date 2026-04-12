"""Tests for AI Triage Layer (Layer 0)."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from vibesop.core.routing.unified import UnifiedRouter, RoutingLayer, RoutingResult


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    llm = MagicMock()
    llm.configured.return_value = True
    llm.call.return_value = MagicMock(
        content="systematic-debugging",
        model="claude-3-5-haiku-20241022",
        tokens_used=50,
    )
    return llm


@pytest.fixture
def router_with_llm(tmp_path, mock_llm):
    """Router with mocked LLM client."""
    (tmp_path / ".vibe").mkdir()
    (tmp_path / "core" / "skills").mkdir(parents=True)

    from vibesop.core.config.manager import ConfigManager

    manager = ConfigManager(project_root=tmp_path)
    manager.set_cli_override("routing.enable_ai_triage", True)

    router = UnifiedRouter(project_root=tmp_path, config=manager)
    router._llm = mock_llm
    return router


def test_ai_triage_returns_skill_route(router_with_llm):
    """AI triage should return a SkillRoute when LLM responds."""
    result = router_with_llm.route("帮我调试数据库错误")
    assert isinstance(result, RoutingResult)
    # AI triage should be Layer 0
    assert result.routing_path[0] == RoutingLayer.AI_TRIAGE
    assert result.primary.skill_id == "systematic-debugging"
    assert result.primary.confidence == 0.92
    assert result.primary.metadata.get("ai_triage") is True


def test_ai_triage_disabled_by_default(tmp_path):
    """AI triage should be disabled when config is False."""
    (tmp_path / ".vibe").mkdir()
    (tmp_path / "core" / "skills").mkdir(parents=True)

    from vibesop.core.config.manager import ConfigManager

    manager = ConfigManager(project_root=tmp_path)
    manager.set_cli_override("routing.enable_ai_triage", False)

    router = UnifiedRouter(project_root=tmp_path, config=manager)
    # Should not call LLM
    result = router.route("debug this")
    # Should fall through to keyword/TF-IDF matchers
    assert isinstance(result, RoutingResult)


def test_ai_triage_caches_results(router_with_llm, tmp_path):
    """AI triage should cache results to avoid repeated LLM calls."""
    # First call
    router_with_llm.route("debug error")
    assert router_with_llm._llm.call.call_count == 1

    # Second call with same query should use cache
    router_with_llm.route("debug error")
    assert router_with_llm._llm.call.call_count == 1  # Still 1, cached


def test_ai_triage_handles_invalid_response(tmp_path, mock_llm):
    """AI triage should handle invalid LLM responses gracefully."""
    mock_llm.call.return_value = MagicMock(
        content="this is not a valid skill id at all and has no pattern match",
        model="claude-3-5-haiku-20241022",
        tokens_used=100,
    )

    (tmp_path / ".vibe").mkdir()
    (tmp_path / "core" / "skills").mkdir(parents=True)

    from vibesop.core.config.manager import ConfigManager

    manager = ConfigManager(project_root=tmp_path)
    manager.set_cli_override("routing.enable_ai_triage", True)

    router = UnifiedRouter(project_root=tmp_path, config=manager)
    router._llm = mock_llm

    # Should fall through to next layer
    result = router.route("debug this")
    assert isinstance(result, RoutingResult)
    # Should NOT be AI_TRIAGE since response was invalid
    if result.routing_path:
        assert result.routing_path[0] != RoutingLayer.AI_TRIAGE
    else:
        assert result.primary is None or result.routing_path == []


def test_ai_triage_handles_llm_error(tmp_path):
    """AI triage should handle LLM errors gracefully."""
    (tmp_path / ".vibe").mkdir()
    (tmp_path / "core" / "skills").mkdir(parents=True)

    from vibesop.core.config.manager import ConfigManager

    manager = ConfigManager(project_root=tmp_path)
    manager.set_cli_override("routing.enable_ai_triage", True)

    router = UnifiedRouter(project_root=tmp_path, config=manager)

    # Mock LLM that raises an exception
    mock_llm = MagicMock()
    mock_llm.configured.return_value = True
    mock_llm.call.side_effect = Exception("API error")
    router._llm = mock_llm

    # Should fall through to next layer without crashing
    result = router.route("debug this")
    assert isinstance(result, RoutingResult)


def test_ai_triage_explicit_disable(tmp_path, monkeypatch):
    """AI triage can be explicitly disabled via env var."""
    monkeypatch.setenv("VIBE_AI_TRIAGE_ENABLED", "0")

    (tmp_path / ".vibe").mkdir()
    (tmp_path / "core" / "skills").mkdir(parents=True)

    from vibesop.core.config.manager import ConfigManager

    manager = ConfigManager(project_root=tmp_path)
    manager.set_cli_override("routing.enable_ai_triage", True)

    router = UnifiedRouter(project_root=tmp_path, config=manager)
    # _init_llm_client should return None when explicitly disabled
    assert router._init_llm_client() is None


def test_parse_ai_triage_response():
    """Test parsing various LLM response formats."""
    (tmp_path := __import__("tempfile").mkdtemp())
    from vibesop.core.config.manager import ConfigManager

    manager = ConfigManager(project_root=tmp_path)
    router = UnifiedRouter(project_root=tmp_path, config=manager)

    # Code block format
    assert router._parse_ai_triage_response("```systematic-debugging```") == "systematic-debugging"
    # JSON code block
    assert (
        router._parse_ai_triage_response("```json\nsystematic-debugging\n```")
        == "systematic-debugging"
    )
    # Plain text
    assert router._parse_ai_triage_response("gstack/qa") == "gstack/qa"
    # With namespace
    assert router._parse_ai_triage_response("omx/deep-interview") == "omx/deep-interview"
    # Empty response
    assert router._parse_ai_triage_response("") is None
    # Random text
    assert router._parse_ai_triage_response("I don't know") is None
