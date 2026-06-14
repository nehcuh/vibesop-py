"""Tests for IntentInterceptor."""

from __future__ import annotations

from vibesop.agent.runtime.intent_interceptor import (
    IntentInterceptor,
    InterceptionContext,
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
            "debug this failing test and then deploy to staging",
            "第一步分析现有架构，第二步优化性能瓶颈",
        ]
        for query in queries:
            decision = interceptor.should_intercept(query)
            assert decision.should_route, f"Should route: {query}"
            assert decision.mode == InterceptionMode.ORCHESTRATE, f"Should orchestrate: {query}"

    def test_multi_intent_markers_with_multi_role_promotes_to_squad(self) -> None:
        """≥2 distinct professional roles + multi-intent markers → squad."""
        interceptor = IntentInterceptor()
        queries = [
            "first review the code then refactor the implementation",
            "请帮我设计微服务架构、然后用Python实现核心模块、最后做安全审查",
            "design the architecture and then implement the code and finally run a security audit",
        ]
        for query in queries:
            decision = interceptor.should_intercept(query)
            assert decision.should_route, f"Should route: {query}"
            assert decision.mode == InterceptionMode.MULTI_AGENT_SQUAD, (
                f"Should promote to squad (multi-role): {query}"
            )
            assert decision.analysis is not None
            assert len(decision.analysis.suggested_roles) >= 2

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

    def test_short_complex_role_query_promotes_to_single_agent(self) -> None:
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("帮我设计一个微服务架构")
        assert decision.should_route
        assert decision.mode == InterceptionMode.SINGLE_AGENT
        assert decision.analysis is not None
        assert "architect" in decision.analysis.suggested_roles

    def test_long_query_without_markers_can_select_multi_agent_squad(self) -> None:
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept(
            "design the system architecture, implement the core service layer, and conduct a security audit for vulnerabilities"
        )
        assert decision.should_route
        assert decision.mode == InterceptionMode.MULTI_AGENT_SQUAD
        assert decision.analysis is not None
        assert decision.analysis.squad_needed is True
        assert len(decision.analysis.suggested_roles) >= 2

    def test_long_single_role_query_selects_single_agent(self) -> None:
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept(
            "I need a thorough security audit to find all potential vulnerabilities and attack surfaces"
        )
        assert decision.should_route
        assert decision.mode == InterceptionMode.SINGLE_AGENT
        assert decision.analysis is not None
        assert "red_team" in decision.analysis.suggested_roles

    def test_multi_intent_markers_with_distinct_roles_promotes_to_squad_when_long(self) -> None:
        """Long query with multi-intent markers AND ≥2 distinct roles → squad.

        The fast role-keyword path overrides the legacy orchestrate decision
        when architect + implementer + red_team are all present.
        """
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept(
            "first design the system architecture and then implement the core service layer and finally run a security audit"
        )
        assert decision.should_route
        assert decision.mode == InterceptionMode.MULTI_AGENT_SQUAD
        assert decision.analysis is not None
        assert {"architect", "implementer", "red_team"}.issubset(
            set(decision.analysis.suggested_roles)
        )

    # ── Fast role-keyword detection matrix (P1 fix) ───────────────────────────

    def test_role_detection_matrix(self) -> None:
        """Verify the documented detection matrix from the P1 spec."""
        interceptor = IntentInterceptor()

        cases = [
            # (query, expected_roles, expected_mode)
            ("帮我调试一下这个错误", [], None),  # too short → no routing
            ("设计微服务架构", ["architect"], None),  # SINGLE_AGENT or ORCHESTRATE
            ("设计架构并写代码实现", ["architect", "implementer"],
             InterceptionMode.MULTI_AGENT_SQUAD),
            ("请帮我设计微服务架构、然后用Python实现核心模块、最后做安全审查",
             ["architect", "implementer", "red_team"],
             InterceptionMode.MULTI_AGENT_SQUAD),
            ("design architecture, implement code, security review",
             ["architect", "implementer", "red_team"],
             InterceptionMode.MULTI_AGENT_SQUAD),
            ("帮我对比微服务和单体架构", ["debater", "architect"], None),
        ]
        for query, expected_roles, expected_mode in cases:
            decision = interceptor.should_intercept(query)
            detected = interceptor._detect_roles(query)
            for role in expected_roles:
                assert role in detected, (
                    f"Expected role '{role}' in detected {detected} for: {query}"
                )
            if expected_mode is not None:
                assert decision.should_route, f"Should route: {query}"
                assert decision.mode == expected_mode, (
                    f"Query '{query}': expected {expected_mode}, got {decision.mode}"
                )

    def test_quick_squad_analysis_protocol_inference(self) -> None:
        """Protocol is inferred correctly from the role combination."""
        interceptor = IntentInterceptor()

        # red_team present → red_team protocol
        analysis = interceptor._build_quick_squad_analysis(
            "x", ["architect", "implementer", "red_team"]
        )
        assert analysis.collaboration_protocol == "red_team"
        assert analysis.suggested_roles == ["architect", "implementer", "red_team"]
        assert analysis.squad_needed is True
        assert analysis.complexity == "multi_agent"
        # per_agent_skills populated via skill_composer.infer_skills_for_role
        assert "system-design" in analysis.per_agent_skills["architect"]
        assert "security_audit" in analysis.per_agent_skills["red_team"]

        # implementer + reviewer → review_gate
        analysis = interceptor._build_quick_squad_analysis(
            "y", ["implementer", "reviewer"]
        )
        assert analysis.collaboration_protocol == "review_gate"

        # architect + implementer → sequential
        analysis = interceptor._build_quick_squad_analysis(
            "z", ["architect", "implementer"]
        )
        assert analysis.collaboration_protocol == "sequential"

    def test_single_role_does_not_trigger_squad(self) -> None:
        """A single role keyword should not promote to squad."""
        interceptor = IntentInterceptor()
        # Only architect keyword
        decision = interceptor.should_intercept(
            "请帮我设计一个高可用的微服务架构，包括服务拆分、API 网关和监控方案"
        )
        assert decision.should_route
        # Single architect role → should NOT be MULTI_AGENT_SQUAD
        assert decision.mode != InterceptionMode.MULTI_AGENT_SQUAD
