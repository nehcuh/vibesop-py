"""Hardening tests for IntentInterceptor (v7.0.4 Phase 4).

Background: ``tests/agent/runtime/test_intent_interceptor.py`` covers the
happy path comprehensively (22 tests). These tests target specific gaps
flagged by the S23 Multi-Agent Squad deep analysis:

1. **Adversarial Chinese capture rejection (S21 regression test)**: The
   EXPLICIT_SKILL_PATTERNS include a Chinese ``"用 X"`` pattern. Before
   the S21 fix, the regex would happily capture Chinese text like
   ``"高可用"`` from ``"用 高可用 的方式实现"`` and treat it as a skill
   ID. The fix (``skill.isascii()`` check at ``_extract_explicit_skill``)
   must be preserved across refactors.

2. **Direct unit tests for ``_detect_roles``**: The existing test suite
   exercises role detection only indirectly through ``should_intercept``.
   These tests pin the contract directly so future refactors of the
   dispatcher cannot accidentally break the role-detection primitive.

3. **Protocol inference edge cases**: ``_build_quick_squad_analysis``
   picks a collaboration protocol from the role combination. Pin the
   priority order (red_team > review_gate > debate > parallel > sequential).
"""

from __future__ import annotations

import pytest

from vibesop.agent.runtime.intent_interceptor import IntentInterceptor, InterceptionMode


class TestExtractExplicitSkillChineseHardening:
    """S21 fix: _extract_explicit_skill must reject non-ASCII captures."""

    @pytest.fixture
    def interceptor(self) -> IntentInterceptor:
        return IntentInterceptor()

    def test_ascii_skill_id_accepted(self, interceptor: IntentInterceptor) -> None:
        """Legitimate ASCII skill IDs (slash, dash, underscore) pass."""
        assert interceptor._extract_explicit_skill("use gstack/review") == "gstack/review"
        assert (
            interceptor._extract_explicit_skill("调用 systematic-debugging")
            == "systematic-debugging"
        )
        assert interceptor._extract_explicit_skill("use my_skill_v2") == "my_skill_v2"

    def test_chinese_text_capture_rejected(self, interceptor: IntentInterceptor) -> None:
        """The S21 bug: '用 高可用' was hijacking '高可用' as a skill ID.

        Reproduction: the ``"用 X"`` pattern matches "用 高可用", capturing
        "高可用" as group 1. Pre-fix, this was returned as a skill ID
        and routed to a non-existent skill. Post-fix, the ``isascii()``
        check rejects the capture and falls through.
        """
        # This was the actual failing case from S21.
        result = interceptor._extract_explicit_skill("用 高可用 的方式实现微服务")
        assert result is None, (
            "Chinese text must not be captured as a skill ID — '高可用' "
            "is not a real skill. The isascii() guard must hold."
        )

    def test_chinese_skill_pretending_to_be_english_rejected(
        self, interceptor: IntentInterceptor
    ) -> None:
        """Mixed-script attacks where the captured group is non-ASCII."""
        # '使用 Ａrchitect' (fullwidth A) — the visual rendering is
        # indistinguishable from ASCII 'A' but isascii() must catch it.
        result = interceptor._extract_explicit_skill("使用 Ａrchitect 工具")
        assert result is None

    def test_skill_with_chinese_prefix_rejected(self, interceptor: IntentInterceptor) -> None:
        """When a Chinese word happens to match the ``"用 X"`` pattern
        boundary, the captured group must still be ASCII-clean."""
        # "用 数据库" — the "用" is a real Chinese word, "数据库" is
        # Chinese for "database". Neither belongs in a skill ID.
        result = interceptor._extract_explicit_skill("请用 数据库 连接池实现")
        assert result is None

    def test_mixed_ascii_chinese_capture_only_ascii_part_kept(
        self, interceptor: IntentInterceptor
    ) -> None:
        """If the captured group contains any non-ASCII char, reject."""
        # If somehow the regex matched across ASCII + Chinese, the whole
        # capture must be rejected (not partially-trimmed).
        result = interceptor._extract_explicit_skill("use skill-中文")
        # The capture is "skill-中文" which contains Chinese chars.
        assert result is None


class TestDetectRolesContract:
    """Direct unit tests for _detect_roles, pinning the contract that
    higher-level tests rely on indirectly."""

    @pytest.fixture
    def interceptor(self) -> IntentInterceptor:
        return IntentInterceptor()

    def test_no_roles_returns_empty(self, interceptor: IntentInterceptor) -> None:
        """A query with no professional-role keywords returns []."""
        assert interceptor._detect_roles("hello world") == []
        assert interceptor._detect_roles("随便写点什么") == []

    def test_single_role_detected(self, interceptor: IntentInterceptor) -> None:
        """One role keyword produces a single-item list."""
        roles = interceptor._detect_roles("请帮我设计架构")
        assert roles == ["architect"]

    def test_multiple_distinct_roles_deduplicated(self, interceptor: IntentInterceptor) -> None:
        """Multiple keywords from the same role count once; distinct
        roles produce distinct list items in dict-iteration order."""
        # Use real keywords from ROLE_KEYWORDS: 'architecture' (architect),
        # 'implement' (implementer), 'code review' (reviewer).
        roles = interceptor._detect_roles(
            "design the architecture, implement the code, do code review"
        )
        # Implementation iterates ROLE_KEYWORDS.items() in dict insertion
        # order (architect → implementer → reviewer → ...). All three
        # match this query.
        assert roles == ["architect", "implementer", "reviewer"]

    def test_same_role_multiple_keywords_deduplicated(self, interceptor: IntentInterceptor) -> None:
        """If 'architect' has multiple keywords (架构/设计/architecture),
        a query mentioning several of them still counts architect once."""
        # '架构' and 'architecture' both map to architect.
        roles = interceptor._detect_roles("design the 架构 architecture")
        # The architect role's keyword list has multiple entries; the
        # break-on-first-match means we don't double-count.
        assert roles.count("architect") == 1

    def test_case_insensitive_matching(self, interceptor: IntentInterceptor) -> None:
        """ROLE_KEYWORDS matching is case-insensitive (lowercased both sides)."""
        roles_lower = interceptor._detect_roles("design the ARCHITECTURE")
        roles_upper = interceptor._detect_roles("DESIGN THE ARCHITECTURE")
        roles_mixed = interceptor._detect_roles("Design The Architecture")
        assert roles_lower == roles_upper == roles_mixed == ["architect"]

    def test_first_seen_order_is_dict_iteration_order(self, interceptor: IntentInterceptor) -> None:
        """Roles are returned in dict-iteration order, NOT query-appearance
        order. This pins the current contract; if the contract changes to
        query-appearance order, this test will catch it."""
        # 'architecture' (architect) appears AFTER 'code review' (reviewer)
        # in the query, but architect comes first in ROLE_KEYWORDS dict.
        roles = interceptor._detect_roles("code review then architecture")
        assert roles == ["architect", "reviewer"], (
            "Role order should follow ROLE_KEYWORDS dict iteration, not "
            "query appearance order. If you intended to change this, "
            "update _detect_roles and this test together."
        )


class TestQuickSquadProtocolPriority:
    """_build_quick_squad_analysis protocol inference priority order."""

    @pytest.fixture
    def interceptor(self) -> IntentInterceptor:
        return IntentInterceptor()

    def test_red_team_wins_over_everything(self, interceptor: IntentInterceptor) -> None:
        """If red_team is in the role set, protocol is 'red_team'."""
        for roles in (
            ["architect", "implementer", "red_team"],
            ["red_team"],
            ["architect", "red_team", "reviewer", "implementer"],
        ):
            analysis = interceptor._build_quick_squad_analysis("x", roles)
            assert analysis.collaboration_protocol == "red_team", f"red_team must dominate: {roles}"

    def test_review_gate_when_reviewer_and_implementer_without_red_team(
        self, interceptor: IntentInterceptor
    ) -> None:
        """reviewer + implementer (no red_team) → review_gate."""
        analysis = interceptor._build_quick_squad_analysis("x", ["implementer", "reviewer"])
        assert analysis.collaboration_protocol == "review_gate"

    def test_debate_when_debater_present(self, interceptor: IntentInterceptor) -> None:
        """debater (without red_team / review_gate prereqs) → debate."""
        analysis = interceptor._build_quick_squad_analysis("x", ["architect", "debater"])
        assert analysis.collaboration_protocol == "debate"

    def test_parallel_when_three_plus_roles_no_special_markers(
        self, interceptor: IntentInterceptor
    ) -> None:
        """3+ roles without red_team / review_gate / debater → parallel."""
        analysis = interceptor._build_quick_squad_analysis(
            "x", ["architect", "implementer", "tester"]
        )
        assert analysis.collaboration_protocol == "parallel"

    def test_sequential_default_for_two_roles(self, interceptor: IntentInterceptor) -> None:
        """2 roles without special markers → sequential."""
        analysis = interceptor._build_quick_squad_analysis("x", ["architect", "implementer"])
        assert analysis.collaboration_protocol == "sequential"

    def test_per_agent_skills_populated(self, interceptor: IntentInterceptor) -> None:
        """Each role gets its skill set via skill_composer.infer_skills_for_role."""
        analysis = interceptor._build_quick_squad_analysis("x", ["architect", "red_team"])
        assert "architect" in analysis.per_agent_skills
        assert "red_team" in analysis.per_agent_skills
        # skill_composer provides these defaults; pin the contract:
        assert "system-design" in analysis.per_agent_skills["architect"]
        assert "security_audit" in analysis.per_agent_skills["red_team"]

    def test_handoff_points_match_role_count(self, interceptor: IntentInterceptor) -> None:
        """handoff_points is range(1, n_roles) — one less than role count."""
        for n in (2, 3, 4):
            roles = [f"role{i}" for i in range(n)]
            # Use roles that exist in ROLE_KEYWORDS to avoid empty skill sets;
            # we hand-craft the call to bypass role validation.
            real_roles = (
                ["architect", "implementer"][:n]
                if n <= 2
                else ["architect", "implementer", "reviewer", "tester"][:n]
            )
            analysis = interceptor._build_quick_squad_analysis("x", real_roles)
            assert len(analysis.handoff_points) == n - 1


class TestShouldInterceptEndToEndWithHardening:
    """End-to-end smoke tests confirming the hardened paths still flow."""

    def test_high_availability_phrase_does_not_hijack_to_skill(
        self,
    ) -> None:
        """The original S21 customer-reported case: a query about
        high-availability architecture must not get routed to a
        non-existent skill named '高可用'."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("用 高可用 的方式重新设计这个微服务架构")
        # Should NOT route to a single skill called "高可用".
        if decision.mode == InterceptionMode.SINGLE:
            assert "高可用" not in decision.reason, (
                "Chinese phrase '高可用' must never appear in the skill "
                "reason — the isascii() guard in _extract_explicit_skill "
                "must reject this capture."
            )

    def test_legitimate_chinese_prefixed_skill_still_works(self) -> None:
        """The hardening must not break real Chinese-prefixed skill calls."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("调用 systematic-debugging")
        assert decision.should_route
        assert decision.mode == InterceptionMode.SINGLE
        assert "systematic-debugging" in decision.reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
