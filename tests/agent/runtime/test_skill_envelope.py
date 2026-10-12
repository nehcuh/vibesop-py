"""Real disk skill -> injector -> runtime -> both hook serialization channels."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from vibesop.agent.runtime.agent_runtime import AgentRuntime, AgentRuntimeResult
from vibesop.agent.runtime.intent_interceptor import InterceptionMode
from vibesop.agent.runtime.skill_injector import PlatformType, SkillInjector
from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute


@pytest.mark.parametrize("platform", list(PlatformType))
@pytest.mark.parametrize("large", [False, True])
def test_runtime_serializers_preserve_real_complete_handoff(tmp_path, platform, large):
    source = tmp_path / "discovered" / "example.skill" / "SKILL.md"
    source.parent.mkdir(parents=True)
    body = "# Example\n\n" + ("a safe workflow step\n" * (300 if large else 1))
    source.write_text(body, encoding="utf-8")
    runtime = AgentRuntime(project_root=tmp_path)
    route = SkillRoute(
        skill_id="project/example",
        confidence=0.9,
        layer=RoutingLayer.AI_TRIAGE,
        source="project",
        metadata={"source_file": str(source)},
    )
    runtime._router = MagicMock()
    runtime._router.route.return_value = RoutingResult(query="implement example", primary=route)
    runtime._interceptor = MagicMock()
    runtime._interceptor.should_intercept.return_value = SimpleNamespace(
        should_route=True,
        mode=InterceptionMode.SINGLE,
        analysis=None,
    )
    result = runtime.handle_query("implement example", platform=platform.value)
    assert result.skill_context_prepared
    assert result.skill_path == source.resolve().as_posix()
    assert result.has_match
    emitted = json.loads(result.to_hook_json())
    response = json.loads(
        result.to_hook_response(platform=platform.value, hook_event_name="UserPromptSubmit")
    )
    context = response["hookSpecificOutput"]["additionalContext"]
    assert context == emitted["skillContent"] == result.skill_content
    assert context.count("[ACTIVE SKILL: project/example]") == 1
    assert source.resolve().as_posix() in context
    assert len(context) <= 3000
    assert "scope" in context or "范围" in context
    assert "You MUST follow this skill's workflow" not in context
    assert "Source file" not in context  # Real discovered path, no resolver fallback.
    if platform == PlatformType.KIMI_CLI:
        assert body not in context
        assert "读取完整" in context
    else:
        assert "NEXT STEP (MANDATORY): read" in context
        assert ("[Content truncated]" in context) is large
        if not large:
            assert body in context
    assert "skillContent" not in response
    assert "hookSpecificOutput" not in emitted


def test_legacy_raw_body_gets_read_handoff_in_both_channels(tmp_path):
    source = tmp_path / "SKILL.md"
    source.write_text("# source", encoding="utf-8")
    result = AgentRuntimeResult(
        intercepted=True,
        mode="single",
        skill_id="example",
        router_matched=True,
        skill_path=str(source),
        skill_content="# raw\n" + "x" * 4000,
    )
    hook = json.loads(result.to_hook_response())
    assert (
        json.loads(result.to_hook_json())["skillContent"]
        == hook["hookSpecificOutput"]["additionalContext"]
    )
    assert "[Content truncated]" in hook["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("missing", [False, True])
def test_notice_paths_never_get_activation_or_read_directive(tmp_path, monkeypatch, missing):
    source = tmp_path / "SKILL.md"
    source.write_text("# harmless", encoding="utf-8")
    injector = SkillInjector(tmp_path)
    if not missing:
        monkeypatch.setattr(injector, "_is_content_safe", lambda _text: (False, "fixture"))
    injection = injector.inject_single_skill(
        "example",
        PlatformType.CLAUDE_CODE,
        source_file=source if not missing else None,
    )
    assert injection.notice_only and not injection.context_prepared
    result = AgentRuntimeResult(
        intercepted=True,
        mode="single",
        skill_id="example",
        notice_only=True,
        skill_content=str(injection.payload),
    )
    response = json.loads(result.to_hook_response())
    assert "[ACTIVE SKILL:" not in str(response)
    assert "NEXT STEP" not in str(response)
    for spelling in {str(source), source.resolve().as_posix()}:
        assert spelling not in response["hookSpecificOutput"]["additionalContext"]


def test_legacy_unknown_source_uses_resolver_instead_of_fabricated_read_path():
    result = AgentRuntimeResult(
        intercepted=True,
        mode="single",
        skill_id="nonexistent-example",
        skill_content="# raw instructions",
    )
    context = json.loads(result.to_hook_response())["hookSpecificOutput"]["additionalContext"]
    assert "run `vibe skills info nonexistent-example`" in context
    assert "NEXT STEP (MANDATORY): read nonexistent-example SKILL.md not found" not in context
