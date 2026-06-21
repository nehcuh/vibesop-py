"""Tests for AgentRuntime async dispatch (Phase 4)."""

from __future__ import annotations

import pytest

from vibesop.agent.runtime.agent_runtime import AgentRuntime
from vibesop.agent.runtime.intent_interceptor import InterceptionMode


class TestAgentRuntimeProcessQuery:
    """Async process_query dispatch by InterceptionMode."""

    @pytest.mark.asyncio
    async def test_process_query_not_intercepted(self) -> None:
        runtime = AgentRuntime()
        result = await runtime.process_query("hi")

        assert result["intercepted"] is False
        assert result["query"] == "hi"

    @pytest.mark.asyncio
    async def test_process_query_single(self) -> None:
        runtime = AgentRuntime()
        result = await runtime.process_query("review my code")

        assert result["intercepted"] is True
        assert result["mode"] == InterceptionMode.SINGLE.value
        assert "primary" in result

    @pytest.mark.asyncio
    async def test_process_query_single_agent(self) -> None:
        runtime = AgentRuntime()
        # Short query with architect role promotes to SINGLE_AGENT
        result = await runtime.process_query("Design the architecture for a new service")

        assert result["intercepted"] is True
        assert result["mode"] == InterceptionMode.SINGLE_AGENT.value
        assert "role" in result
        assert "skills" in result
        assert result["role"] == "architect"
        assert isinstance(result["skills"], list)

    @pytest.mark.asyncio
    async def test_process_query_multi_agent_squad(self) -> None:
        runtime = AgentRuntime()
        # Explicit multi-agent keyword with multiple facets
        result = await runtime.process_query(
            "multi-agent: design the payment architecture, implement the service, and perform a security audit"
        )

        assert result["intercepted"] is True
        assert result["mode"] == InterceptionMode.MULTI_AGENT_SQUAD.value
        assert "analysis" in result
        assert result["analysis"]["squad_needed"] is True
        assert len(result["analysis"]["suggested_roles"]) >= 2

    @pytest.mark.asyncio
    async def test_process_query_orchestrate(self) -> None:
        runtime = AgentRuntime()
        # Multi-intent marker should keep legacy ORCHESTRATE behavior
        result = await runtime.process_query("分析项目架构并优化整体性能")

        assert result["intercepted"] is True
        assert result["mode"] == InterceptionMode.ORCHESTRATE.value
        assert "is_multi_intent" in result

    @pytest.mark.asyncio
    async def test_orchestrate_path_backward_compatible(self) -> None:
        runtime = AgentRuntime()
        result = await runtime.process_query("分析项目架构并优化整体性能")

        # Should not raise and should contain expected keys
        assert isinstance(result, dict)
        assert "intercepted" in result
        assert "mode" in result


class TestAgentRuntimeBackwardCompat:
    """Existing handle_query API remains unchanged."""

    def test_handle_query_still_works(self) -> None:
        runtime = AgentRuntime()
        result = runtime.handle_query("review my code")

        from vibesop.agent.runtime.agent_runtime import AgentRuntimeResult

        assert isinstance(result, AgentRuntimeResult)
        assert isinstance(result.to_hook_json(), str)

    def test_handle_query_short_query_not_intercepted(self) -> None:
        runtime = AgentRuntime()
        result = runtime.handle_query("hi")

        assert result.intercepted is False
        assert result.mode == "none"

    def test_handle_query_slash_command(self) -> None:
        runtime = AgentRuntime()
        result = runtime.handle_query("/vibe-help")

        assert result.intercepted is True
        assert result.mode == "slash_command"
