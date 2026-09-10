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
    result = AgentRuntimeResult(
        intercepted=True,
        mode="orchestrate",
        plan={"steps": []},
        skill_id="",
    )
    payload = result.to_hook_response()
    assert "Execution plan injected" not in payload
    assert "[VibeSOP Execution Plan]" not in payload
    assert "No matching skill found" in payload


def test_disabled_skill_ids_unwraps_agent_router() -> None:
    ids = AgentRuntime()._disabled_skill_ids()
    assert "builtin/verify-result" in ids


def test_strip_keeps_verification_step_drops_named_cards() -> None:
    runtime = AgentRuntime()
    runtime._disabled_skill_ids = lambda: {"grill-me", "builtin/verify-result"}  # type: ignore[method-assign]
    stripped = runtime._strip_disabled_skill_ids_from_plan(
        {
            "steps": [
                {"skill_id": "code-review"},
                {"skill_id": "grill-me"},
                {"skill_id": "builtin/verify-result", "is_verification_step": True},
            ]
        }
    )
    assert [s["skill_id"] for s in stripped["steps"]] == [
        "code-review",
        "builtin/verify-result",
    ]


def test_strip_drops_verification_step_when_all_deps_stripped() -> None:
    """8.3.1 (B-5): an all-disabled adversarial plan must not degrade into a
    verify-only shell with dangling dependencies — the verification step is
    dropped with the implementation steps, leaving the empty-plan no-match
    demote to fire."""
    runtime = AgentRuntime()
    runtime._disabled_skill_ids = lambda: {"grill-me"}  # type: ignore[method-assign]
    stripped = runtime._strip_disabled_skill_ids_from_plan(
        {
            "steps": [
                {"skill_id": "grill-me", "step_id": "s1"},
                {
                    "skill_id": "builtin/verify-result",
                    "step_id": "v1",
                    "is_verification_step": True,
                    "dependencies": ["s1"],
                },
            ]
        }
    )
    assert stripped["steps"] == []


def test_strip_chained_verification_steps_converges_to_fixpoint() -> None:
    """8.3.1 (B-5 fixpoint): dropping verifier v1 must also drop verifier v2
    that depended on v1 — a single-pass filter leaves v2 with a dangling
    dependency that can never be satisfied."""
    runtime = AgentRuntime()
    runtime._disabled_skill_ids = lambda: {"grill-me"}  # type: ignore[method-assign]
    stripped = runtime._strip_disabled_skill_ids_from_plan(
        {
            "steps": [
                {"skill_id": "grill-me", "step_id": "s1"},
                {
                    "skill_id": "builtin/verify-result",
                    "step_id": "v1",
                    "is_verification_step": True,
                    "dependencies": ["s1"],
                },
                {
                    "skill_id": "builtin/verify-result",
                    "step_id": "v2",
                    "is_verification_step": True,
                    "dependencies": ["v1"],
                },
            ]
        }
    )
    assert stripped["steps"] == []


def test_strip_chained_verification_keeps_step_with_surviving_dep() -> None:
    """Fixpoint must not over-drop: v2 depends on v1, v1 depends on a LIVE
    step — both survive, v2's dependency stays intact."""
    runtime = AgentRuntime()
    runtime._disabled_skill_ids = lambda: {"grill-me"}  # type: ignore[method-assign]
    stripped = runtime._strip_disabled_skill_ids_from_plan(
        {
            "steps": [
                {"skill_id": "code-review", "step_id": "s1"},
                {"skill_id": "grill-me", "step_id": "s2"},
                {
                    "skill_id": "builtin/verify-result",
                    "step_id": "v1",
                    "is_verification_step": True,
                    "dependencies": ["s1", "s2"],
                },
                {
                    "skill_id": "builtin/verify-result",
                    "step_id": "v2",
                    "is_verification_step": True,
                    "dependencies": ["v1"],
                },
            ]
        }
    )
    assert [s["step_id"] for s in stripped["steps"]] == ["s1", "v1", "v2"]
    assert stripped["steps"][1]["dependencies"] == ["s1"]
    assert stripped["steps"][2]["dependencies"] == ["v1"]
