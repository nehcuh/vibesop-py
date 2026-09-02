"""Conformance tests: AgentRuntime entry point.

Verifies the unified AgentRuntime correctly handles interception, routing,
injection, slash commands, hook response formatting, and multi-intent
orchestration.
"""

from __future__ import annotations

import json

from vibesop.agent.runtime import (
    AgentRuntime,
    AgentRuntimeResult,
)


class TestAgentRuntimeResult:
    """AgentRuntimeResult dataclass conformance."""

    def test_default_values(self):
        result = AgentRuntimeResult()
        assert result.intercepted is False
        assert result.mode == "none"
        assert result.skill_id == ""
        assert result.confidence == 0.0
        assert result.alternatives == []
        assert result.errors == []

    def test_has_match_false_when_not_intercepted(self):
        result = AgentRuntimeResult(intercepted=False, mode="single", skill_id="test/skill")
        assert not result.has_match

    def test_has_match_true_when_intercepted_single(self):
        result = AgentRuntimeResult(intercepted=True, mode="single", skill_id="test/skill")
        assert result.has_match

    def test_has_match_true_when_intercepted_orchestrate(self):
        result = AgentRuntimeResult(intercepted=True, mode="orchestrate", skill_id="test/skill")
        assert result.has_match

    def test_success_true_when_no_errors(self):
        result = AgentRuntimeResult()
        assert result.success

    def test_success_false_when_errors(self):
        result = AgentRuntimeResult(errors=["Bad thing happened"])
        assert not result.success

    def test_to_hook_json_produces_valid_json(self):
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="test/skill",
            confidence=0.85,
        )
        data = json.loads(result.to_hook_json())
        assert data["intercepted"] is True
        assert data["mode"] == "single"
        assert data["skillId"] == "test/skill"
        assert data["confidence"] == 0.85

    def test_to_hook_json_truncates_skill_content(self):
        long_content = "x" * 5000
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="test/skill",
            skill_content=long_content,
        )
        data = json.loads(result.to_hook_json())
        assert len(data["skillContent"]) <= 3000


class TestAgentRuntimeHookResponse:
    """to_hook_response() produces platform-specific hook JSON."""

    def test_not_intercepted_returns_empty_json(self):
        result = AgentRuntimeResult(intercepted=False)
        assert result.to_hook_response() == "{}"

    def test_slash_command_response(self):
        result = AgentRuntimeResult(
            intercepted=True,
            mode="slash_command",
            slash_result={"success": True, "message": "VibeSOP Slash Commands..."},
        )
        data = json.loads(result.to_hook_response())
        assert "systemMessage" in data
        assert "VibeSOP" in data["systemMessage"]

    def test_single_match_response_format(self):
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="gstack/review",
            confidence=0.85,
            skill_content="# Code Review Skill\n\nReview flow.",
            alternatives=[
                {"skill_id": "gstack/analyze", "confidence": 0.45},
            ],
        )
        resp = result.to_hook_response(
            platform="claude-code",
            hook_event_name="UserPromptSubmit",
            include_additional_context=True,
        )
        data = json.loads(resp)
        assert "systemMessage" in data
        assert "gstack/review" in data["systemMessage"]
        assert "85%" in data["systemMessage"]
        assert "hookSpecificOutput" in data
        assert "additionalContext" in data["hookSpecificOutput"]
        assert data["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
        assert "ACTIVE SKILL" in data["hookSpecificOutput"]["additionalContext"]

    def test_no_hook_event_name_omitted(self):
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="test/skill",
            confidence=0.9,
            skill_content="some content",
        )
        resp = result.to_hook_response(
            platform="opencode",
            hook_event_name="",
        )
        data = json.loads(resp)
        assert "hookEventName" not in data.get("hookSpecificOutput", {})

    def test_no_additional_context_when_disabled(self):
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="test/skill",
            confidence=0.9,
            skill_content="some content",
        )
        resp = result.to_hook_response(
            platform="opencode",
            include_additional_context=False,
        )
        data = json.loads(resp)
        assert "hookSpecificOutput" not in data

    def test_no_match_with_message(self):
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="fallback-llm",
        )
        resp = result.to_hook_response(no_match_message=True)
        data = json.loads(resp)
        assert "No matching skill found" in data["systemMessage"]

    def test_no_match_without_message(self):
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="fallback-llm",
        )
        resp = result.to_hook_response(no_match_message=False)
        assert resp == "{}"

    def test_orchestration_response(self):
        result = AgentRuntimeResult(
            intercepted=True,
            mode="orchestrate",
            plan={"plan_id": "plan-1", "steps": [{"step_number": 1, "skill_id": "test/a"}]},
        )
        resp = result.to_hook_response(
            platform="claude-code",
            hook_event_name="UserPromptSubmit",
        )
        data = json.loads(resp)
        assert "systemMessage" in data
        assert "multiple intents" in data["systemMessage"].lower()
        assert "hookSpecificOutput" in data
        assert "Execution Plan" in data["hookSpecificOutput"]["additionalContext"]

    def test_alternatives_in_system_message(self):
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="gstack/review",
            confidence=0.85,
            alternatives=[
                {"skill_id": "gstack/analyze", "confidence": 0.50},
                {"skill_id": "gstack/refactor", "confidence": 0.35},
            ],
        )
        resp = result.to_hook_response()
        assert "ALTERNATIVE SKILLS" in resp
        assert "gstack/analyze" in resp
        assert "gstack/refactor" in resp

    def test_hook_hint_uses_injected_skill_path(self):
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="kimi-gated-fix",
            confidence=0.8,
            skill_content="# gated body",
            skill_path=("C:/proj/.vibe/skills/cross-cutting/kimi-gated-fix.skill/SKILL.md"),
        )
        data = json.loads(result.to_hook_response())
        assert "kimi-gated-fix.skill/SKILL.md" in data["systemMessage"]
        assert "skills/kimi-gated-fix/SKILL.md" not in data["systemMessage"]

    def test_notice_only_skips_active_skill_wrap(self):
        from vibesop.security.runtime_scan import unsafe_replacement_notice

        notice = unsafe_replacement_notice("evil-skill")
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="evil-skill",
            confidence=0.9,
            skill_content=notice,
            notice_only=True,
        )
        data = json.loads(result.to_hook_response(hook_event_name="UserPromptSubmit"))
        assert "VibeSOP routed" not in data["systemMessage"]
        assert "NEXT STEP" not in data["systemMessage"]
        assert "ACTIVE SKILL" not in data["systemMessage"]
        ctx = data["hookSpecificOutput"]["additionalContext"]
        assert "ACTIVE SKILL" not in ctx
        assert "MUST follow" not in ctx
        assert "SECURITY" in ctx

    def test_notice_only_empty_content_does_not_route(self):
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="evil-skill",
            confidence=0.9,
            skill_content="",
            notice_only=True,
        )
        data = json.loads(result.to_hook_response())
        assert "VibeSOP routed" not in data["systemMessage"]
        assert "NEXT STEP" not in data["systemMessage"]
        assert "ACTIVE SKILL" not in data["systemMessage"]
        assert "not injected" in data["systemMessage"]

    def test_vibe_sop_notice_without_flag_still_skips_wrap(self):
        from vibesop.security.runtime_scan import empty_content_notice

        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="ghost",
            confidence=0.8,
            skill_content=empty_content_notice("ghost"),
        )
        data = json.loads(result.to_hook_response())
        ctx = data["hookSpecificOutput"]["additionalContext"]
        assert "ACTIVE SKILL" not in ctx
        assert "MUST follow" not in ctx


class TestAgentRuntimeHandleQuery:
    """AgentRuntime.handle_query() pipeline conformance."""

    def test_handle_query_returns_result(self):
        runtime = AgentRuntime()
        result = runtime.handle_query("review my code")
        assert isinstance(result, AgentRuntimeResult)
        assert not result.errors

    def test_slash_command_is_intercepted(self):
        runtime = AgentRuntime()
        result = runtime.handle_query("/vibe-help")
        assert result.intercepted
        assert result.mode == "slash_command"
        assert result.slash_result is not None
        assert result.slash_result["success"]

    def test_short_query_not_intercepted(self):
        runtime = AgentRuntime()
        result = runtime.handle_query("hi")
        assert not result.intercepted
        assert result.mode == "none"

    def test_handle_query_for_hook_returns_json(self):
        runtime = AgentRuntime()
        resp = runtime.handle_query_for_hook(
            "/vibe-help",
            platform="claude-code",
            hook_event_name="UserPromptSubmit",
        )
        data = json.loads(resp)
        assert "systemMessage" in data

    def test_empty_query_for_hook_returns_empty(self):
        runtime = AgentRuntime()
        result = runtime.handle_query("")
        assert not result.intercepted

    def test_handle_query_returns_structured_data(self):
        runtime = AgentRuntime()
        result = runtime.handle_query("review my code")
        # The result should be well-structured regardless of routing outcome
        assert isinstance(result.to_hook_json(), str)
        json.loads(result.to_hook_json())  # must be valid JSON

    def test_handle_query_accepts_conversation_id(self):
        runtime = AgentRuntime()
        result = runtime.handle_query("review my code", conversation_id="test-conv-123")
        assert isinstance(result, AgentRuntimeResult)

    def test_handle_query_accepts_platform(self):
        runtime = AgentRuntime()
        result = runtime.handle_query("review my code", platform="claude-code")
        assert isinstance(result, AgentRuntimeResult)


class TestAgentRuntimeLazyInit:
    """AgentRuntime components are lazily initialized on first access."""

    def test_all_components_lazy(self):
        runtime = AgentRuntime()
        assert runtime._interceptor is None
        assert runtime._router is None
        assert runtime._injector is None
        assert runtime._presenter is None
        assert runtime._slash_executor is None
        assert runtime._plan_executor is None
        assert runtime._context_injector is None

    def test_interceptor_initialized_on_access(self):
        runtime = AgentRuntime()
        interceptor = runtime.interceptor
        assert interceptor is not None
        assert runtime._interceptor is interceptor  # cached

    def test_slash_executor_initialized_on_access(self):
        runtime = AgentRuntime()
        executor = runtime.slash_executor
        assert executor is not None

    def test_injector_initialized_on_access(self):
        runtime = AgentRuntime()
        injector = runtime.injector
        assert injector is not None

    def test_presenter_initialized_on_access(self):
        runtime = AgentRuntime()
        presenter = runtime.presenter
        assert presenter is not None
