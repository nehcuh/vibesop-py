"""Tests for AI Triage Layer (Layer 2)."""

from unittest.mock import MagicMock

import pytest

from vibesop.core.routing.unified import RoutingLayer, RoutingResult, UnifiedRouter


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    llm = MagicMock()
    llm.configured.return_value = True
    llm.call.return_value = MagicMock(
        content="builtin/systematic-debugging",
        model="claude-3-5-haiku-20241022",
        tokens_used=50,
        input_tokens=40,
        output_tokens=10,
    )
    return llm


@pytest.fixture
def router_with_llm(tmp_path, mock_llm):
    """Router with mocked LLM client."""
    (tmp_path / ".vibe").mkdir()
    skill_dir = tmp_path / "core" / "skills" / "systematic-debugging"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: systematic-debugging\n---\n# Systematic Debugging\n",
        encoding="utf-8",
    )

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
    # AI triage should be in routing path after explicit/scenario attempts
    assert RoutingLayer.AI_TRIAGE in result.routing_path
    assert result.primary.skill_id == "builtin/systematic-debugging"
    # Confidence is dynamic: fallback parsing gets ~0.82, structured JSON gets ~0.88
    assert 0.8 <= result.primary.confidence <= 0.92
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
        input_tokens=80,
        output_tokens=20,
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
    # AI Triage was attempted but failed; it should appear in the full routing
    # path for observability, but the final match (if any) comes from later layers.
    assert RoutingLayer.AI_TRIAGE in result.routing_path
    assert result.routing_path[-1] != RoutingLayer.AI_TRIAGE


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
    # init_llm_client should return None when explicitly disabled
    assert router._triage_service.init_llm_client() is None


def test_parse_ai_triage_response():
    """Test parsing various LLM response formats."""
    import tempfile
    tmp_path = tempfile.mkdtemp()
    from vibesop.core.config.manager import ConfigManager

    manager = ConfigManager(project_root=tmp_path)
    router = UnifiedRouter(project_root=tmp_path, config=manager)

    # Structured JSON response (preferred)
    parsed = router._triage_service.parse_ai_triage_response('{"skill_id": "systematic-debugging"}')
    assert parsed["skill_id"] == "systematic-debugging"
    assert parsed["structured"] is True

    # JSON inside markdown code block
    parsed = router._triage_service.parse_ai_triage_response('```json\n{"skill_id": "gstack/qa"}\n```')
    assert parsed["skill_id"] == "gstack/qa"
    assert parsed["structured"] is True

    # Legacy code block format (regex fallback)
    parsed = router._triage_service.parse_ai_triage_response("```systematic-debugging```")
    assert parsed["skill_id"] == "systematic-debugging"
    assert parsed["structured"] is False

    # Plain text (regex fallback)
    parsed = router._triage_service.parse_ai_triage_response("gstack/qa")
    assert parsed["skill_id"] == "gstack/qa"
    assert parsed["structured"] is False

    # With namespace (regex fallback)
    parsed = router._triage_service.parse_ai_triage_response("omx/deep-interview")
    assert parsed["skill_id"] == "omx/deep-interview"
    assert parsed["structured"] is False

    # Empty response
    parsed = router._triage_service.parse_ai_triage_response("")
    assert parsed["skill_id"] is None

    # Random text
    parsed = router._triage_service.parse_ai_triage_response("I don't know")
    assert parsed["skill_id"] is None
