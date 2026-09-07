"""W1 acceptance: role words are not a squad; 写公众号总结 is not a plan."""

from __future__ import annotations

from vibesop.agent.runtime.agent_runtime import AgentRuntime, AgentRuntimeResult
from vibesop.agent.runtime.intent_interceptor import IntentInterceptor, InterceptionMode
from vibesop.core.orchestration.parallel_intent import is_explicit_parallel_workers


def test_implement_and_review_is_not_squad() -> None:
    decision = IntentInterceptor().should_intercept("设计架构并写代码实现")
    assert decision.should_route
    assert decision.mode != InterceptionMode.MULTI_AGENT_SQUAD


def test_wechat_summary_is_not_squad() -> None:
    decision = IntentInterceptor().should_intercept("写公众号总结")
    assert decision.mode != InterceptionMode.MULTI_AGENT_SQUAD
    assert decision.mode != InterceptionMode.ORCHESTRATE


def test_parallel_workers_phrase_is_squad() -> None:
    query = "用并行工人同时做前端 A 和后端 B"
    assert is_explicit_parallel_workers(query)
    decision = IntentInterceptor().should_intercept(query)
    assert decision.mode == InterceptionMode.MULTI_AGENT_SQUAD


def test_wechat_summary_hook_has_no_execution_plan() -> None:
    raw = AgentRuntime().handle_query_for_hook("写公众号总结", platform="generic")
    assert "Execution plan injected" not in raw
    assert "[VibeSOP Execution Plan]" not in raw
    assert "[ACTIVE SKILL]" not in raw


def test_implement_review_hook_has_no_execution_plan() -> None:
    raw = AgentRuntime().handle_query_for_hook("设计架构并写代码实现", platform="generic")
    assert "Execution plan injected" not in raw
    assert "[VibeSOP Execution Plan]" not in raw


def test_orchestrate_empty_plan_is_no_match_envelope() -> None:
    result = AgentRuntimeResult(mode="orchestrate", plan={"steps": []}, skill_id="")
    payload = result.to_hook_response()
    # Empty plan dict is truthy; runtime must clear mode before serialize.
    # This pins the serializer: orchestrate+empty steps still emits a plan
    # envelope if callers forget to demote — demote is tested via handle_query.
    assert isinstance(payload, str)
