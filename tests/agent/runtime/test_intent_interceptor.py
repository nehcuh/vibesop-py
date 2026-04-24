"""Tests for IntentInterceptor."""

from __future__ import annotations

import pytest

from vibesop.agent.runtime.intent_interceptor import (
    IntentInterceptor,
    InterceptionContext,
    InterceptionDecision,
    InterceptionMode,
)


class TestIntentInterceptor:
    """Test intent interception logic."""

    def test_short_query_skipped(self) -> None:
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("hi")
        assert not decision.should_route
        assert "too short" in decision.reason.lower()

    def test_empty_query_skipped(self) -> None:
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("")
        assert not decision.should_route

    def test_meta_query_skipped(self) -> None:
        interceptor = IntentInterceptor()
        meta_queries = [
            "vibe route 怎么使用请告诉我",
            "为什么技能没有匹配成功呢",
            "what is vibesop and how does it work",
            "explain the routing system in detail",
        ]
        for query in meta_queries:
            decision = interceptor.should_intercept(query)
            assert not decision.should_route, f"Should skip meta query: {query}"
            assert "meta" in decision.reason.lower()

    def test_explicit_skill_override(self) -> None:
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("use gstack/review")
        assert decision.should_route
        assert decision.mode == InterceptionMode.SINGLE
        assert "gstack/review" in decision.reason

    def test_slash_command_override(self) -> None:
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("/review my code")
        assert decision.should_route
        assert decision.mode == InterceptionMode.SINGLE

    def test_chinese_explicit_skill(self) -> None:
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("调用 systematic-debugging")
        assert decision.should_route
        assert decision.mode == InterceptionMode.SINGLE

    def test_short_focused_query_single_mode(self) -> None:
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("review my code please")
        assert decision.should_route
        assert decision.mode == InterceptionMode.SINGLE

    def test_long_query_defaults_to_orchestrate(self) -> None:
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept(
            "请帮我仔细分析当前项目的架构设计，然后给出性能优化的具体建议"
        )
        assert decision.should_route
        assert decision.mode == InterceptionMode.ORCHESTRATE

    def test_multi_intent_markers_trigger_orchestrate(self) -> None:
        interceptor = IntentInterceptor()
        queries = [
            "请仔细分析当前项目的架构设计，并针对发现的问题进行性能优化",
            "first review the code then refactor the implementation",
            "debug this failing test and then deploy to staging",
            "第一步分析现有架构，第二步优化性能瓶颈",
        ]
        for query in queries:
            decision = interceptor.should_intercept(query)
            assert decision.should_route, f"Should route: {query}"
            assert decision.mode == InterceptionMode.ORCHESTRATE, f"Should orchestrate: {query}"

    def test_normal_query_with_context(self) -> None:
        interceptor = IntentInterceptor()
        context = InterceptionContext(
            session_id="test-session",
            current_skill="systematic-debugging",
        )
        decision = interceptor.should_intercept("help me debug this error", context)
        assert decision.should_route
        assert decision.query == "help me debug this error"

    def test_boundary_length(self) -> None:
        interceptor = IntentInterceptor()
        # Exactly at minimum length
        decision = interceptor.should_intercept("a" * 10)
        assert decision.should_route

        # Just below minimum
        decision = interceptor.should_intercept("a" * 9)
        assert not decision.should_route

    def test_query_preserved_in_decision(self) -> None:
        interceptor = IntentInterceptor()
        query = "review my pull request"
        decision = interceptor.should_intercept(query)
        assert decision.query == query
