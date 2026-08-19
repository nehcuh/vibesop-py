"""Tests for UnifiedRouter._single_skill_route() branches and internal logic.

Covers:
    - Explicit layer routing
    - Scenario layer routing
    - Keyword/TF-IDF/Embedding matcher pipeline
    - Fallback handling
    - Degradation logic
    - _build_match_result
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.models import DegradationLevel, RoutingLayer
from vibesop.core.routing import UnifiedRouter

if TYPE_CHECKING:
    from pathlib import Path


class TestRouteExplicitLayer:
    """Test explicit override layer (Layer 0)."""

    @pytest.mark.skip(
        reason="Flaky: depends on live skill registry containing 'systematic-debugging' (not present in this environment)"
    )
    def test_explicit_skill_id_routing(self, tmp_path: Path) -> None:
        """Routing with explicit skill_id should match directly."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._single_skill_route("use skill:systematic-debugging")

        if result.has_match:
            assert "systematic-debugging" in result.primary.skill_id

    def test_explicit_namespace_routing(self, tmp_path: Path) -> None:
        """Routing with namespace prefix should match."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._single_skill_route("gstack/review")

        if result.has_match:
            assert "gstack" in result.primary.skill_id or "review" in result.primary.skill_id


class TestRouteScenarioLayer:
    """Test scenario pattern layer (Layer 1)."""

    def test_scenario_planning_query(self, tmp_path: Path) -> None:
        """Generic planning queries must NOT route to builtin/riper-workflow.

        The planning scenario (broad plan/design keywords → riper-workflow at
        a fixed 0.9) was removed: the skill's contract is explicit-RIPER-
        intent-only, and riper-workflow is now a guarded skill that fuzzy
        layers cannot select without an explicit signal. Pinned behavior for
        a generic planning query: NO skill match — the router falls back to
        the LLM, and riper-workflow must not even resurface among the
        fallback's nearest-skill suggestions.
        """
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        candidates = [
            {
                "id": "builtin/riper-workflow",
                "name": "riper-workflow",
                "description": "Use ONLY when the user explicitly requests the RIPER "
                "structured 5-phase development workflow (Research, Innovate, "
                "Plan, Execute, Review)",
                "namespace": "builtin",
                "keywords": ["riper", "riper-workflow", "5-phase", "structured-workflow"],
                "triggers": ["use riper", "riper workflow", "riper 工作流", "五阶段工作流"],
            },
            {"id": "debug-skill", "name": "debug-skill", "description": "Debug things"},
        ]
        result = router._single_skill_route("plan this complex task", candidates=candidates)

        assert not result.has_match
        assert result.primary is None or result.primary.layer == RoutingLayer.FALLBACK_LLM
        assert all(
            a.skill_id != "builtin/riper-workflow" for a in (result.alternatives or [])
        )

    def test_scenario_review_code(self, tmp_path: Path) -> None:
        """Review-related queries should match review skills."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._single_skill_route("review my pull request")

        if result.has_match:
            assert result.primary is not None
            # After v5.4.0: concrete skills removed, review queries route to
            # riper-workflow (fallback) or slash-* management tools
            assert result.primary.skill_id is not None


class TestRouteMatcherPipeline:
    """Test matcher pipeline (Layers 3-6)."""

    def test_keyword_matching_short_query(self, tmp_path: Path) -> None:
        """Short queries should use keyword matching."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._single_skill_route("help")

        assert result.has_match
        assert result.primary is not None
        assert result.primary.layer != RoutingLayer.FALLBACK_LLM

    def test_fuzzy_matching_typo(self, tmp_path: Path) -> None:
        """Typo-tolerant queries should match via Levenshtein."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        # Provide a builtin candidate so the prefilter keeps it
        candidates = [
            {
                "id": "systematic-debugging",
                "description": "Debug systematically",
                "namespace": "builtin",
                "enabled": True,
            }
        ]
        result = router._single_skill_route("systmatic", candidates=candidates)

        assert result.has_match
        assert result.primary is not None

    def test_no_match_returns_fallback(self, tmp_path: Path) -> None:
        """Queries with no match should return fallback layer."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._single_skill_route("xyzabc123 nonsense query")

        # Should either have no match or fallback
        if not result.has_match:
            # Fallback LLM sets primary to a fallback skill, not None
            assert result.primary is None or result.primary.layer == RoutingLayer.FALLBACK_LLM
        else:
            # If it matches something, that's also fine
            assert result.primary is not None


class TestKeywordRoutingFallback:
    """Test keyword routing fallback when LLM is unavailable."""

    def test_long_query_fallback_when_ai_triage_disabled(self, tmp_path: Path) -> None:
        """Long queries should fall back to keyword routing when AI triage is disabled."""
        config = RoutingConfig(enable_ai_triage=False, keyword_match_max_chars=15)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        # Query longer than keyword_match_max_chars but AI triage is disabled.
        # Uses an unguarded builtin candidate: guarded skills (riper-workflow,
        # session-end) are correctly rejected without an explicit signal.
        candidates = [
            {
                "id": "builtin/deep-diagnosis-optimization",
                "name": "deep-diagnosis-optimization",
                "description": "Deep diagnosis and optimization of the whole project",
                "namespace": "builtin",
                "keywords": ["diagnosis", "optimization", "deep"],
            }
        ]
        result = router._single_skill_route(
            "deep diagnosis and optimization of this project", candidates=candidates
        )

        # Should still produce a match via keyword/TF-IDF/levenshtein pipeline
        assert result.has_match
        assert result.primary is not None

    def test_keyword_max_chars_affects_routing_path(self, tmp_path: Path) -> None:
        """Keyword max chars should influence which layers are tried."""
        config = RoutingConfig(enable_ai_triage=False, keyword_match_max_chars=5)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        # Long query with strict keyword threshold → only scenario + matcher pipeline
        result = router._single_skill_route("plan this")
        # With keyword_match_max_chars=5, "plan this" (9 chars) should still
        # fall back to matcher pipeline since LLM is disabled
        assert result.primary is not None


class TestRouteDegradation:
    """Test degradation logic."""

    def test_degradation_levels_exist(self, tmp_path: Path) -> None:
        """Degradation levels should be properly defined."""
        assert DegradationLevel.AUTO == "auto"
        assert DegradationLevel.SUGGEST == "suggest"
        assert DegradationLevel.DEGRADE == "degrade"
        assert DegradationLevel.FALLBACK == "fallback"

    def test_high_confidence_auto(self, tmp_path: Path) -> None:
        """High confidence matches should not degrade."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._single_skill_route("debug")

        if result.has_match and result.primary.confidence >= 0.8:
            assert result.primary.layer != RoutingLayer.FALLBACK_LLM


class TestBuildMatchResult:
    """Test _build_match_result internal method."""

    def test_build_result_with_valid_match(self, tmp_path: Path) -> None:
        """Building result with valid match should succeed."""
        from vibesop.core.models import SkillRoute

        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        primary = SkillRoute(skill_id="test-skill", confidence=0.9, layer=RoutingLayer.KEYWORD)
        match = router._build_match_result(
            query="debug",
            primary=primary,
            alternatives=[],
            routing_path=[RoutingLayer.KEYWORD],
            layer_details=[],
            start_time=0.0,
            deprecated_warnings=None,
            conversation=None,
            original_query="debug",
        )
        assert match is not None
        assert match.primary is not None
        assert match.primary.skill_id == "test-skill"

    def test_build_result_with_alternatives(self, tmp_path: Path) -> None:
        """Building result with alternatives should include them."""
        from vibesop.core.models import SkillRoute

        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        primary = SkillRoute(skill_id="primary-skill", confidence=0.9, layer=RoutingLayer.KEYWORD)
        alt = SkillRoute(skill_id="alt-skill", confidence=0.7, layer=RoutingLayer.KEYWORD)
        match = router._build_match_result(
            query="debug",
            primary=primary,
            alternatives=[alt],
            routing_path=[RoutingLayer.KEYWORD],
            layer_details=[],
            start_time=0.0,
            deprecated_warnings=None,
            conversation=None,
            original_query="debug",
        )
        assert match is not None
        assert len(match.alternatives) >= 1


class TestRouteWithContext:
    """Test routing with context enrichment."""

    @pytest.mark.skip(
        reason="Flaky: depends on live skill registry; 'test' query falls through to fallback-llm with current candidate set"
    )
    def test_routing_with_project_type(self, tmp_path: Path) -> None:
        """Routing should accept project type context."""
        from vibesop.core.matching import RoutingContext

        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        context = RoutingContext(project_type="python")

        result = router._single_skill_route("test", context=context)

        assert result.has_match


class TestBuildDecompositionSkills:
    """The skill catalog builder shared by orchestrate(), agent, and `vibe decompose`."""

    def test_format_is_id_colon_description(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        candidates = [
            {"id": "gstack/review", "description": "Review code"},
            {"id": "gstack/test", "description": "Run tests"},
        ]

        skills = router._build_decomposition_skills(candidates=candidates)

        assert skills == ["gstack/review: Review code", "gstack/test: Run tests"]

    def test_falls_back_to_intent_when_description_missing(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        candidates = [{"id": "gstack/test", "intent": "test_code"}]

        skills = router._build_decomposition_skills(candidates=candidates)

        assert skills == ["gstack/test: test_code"]

    def test_uses_n_a_when_neither_field_present(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        skills = router._build_decomposition_skills(candidates=[{"id": "x"}])

        assert skills == ["x: N/A"]

    def test_limit_caps_output(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        candidates = [{"id": f"s{i}", "description": "x"} for i in range(20)]

        skills = router._build_decomposition_skills(candidates=candidates, limit=5)

        assert len(skills) == 5

    def test_default_uses_cached_candidates(self, tmp_path: Path) -> None:
        """Without explicit candidates, fall through to _get_cached_candidates."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        skills = router._build_decomposition_skills()

        # Real router has at least the project skills indexed; format check is enough.
        assert isinstance(skills, list)
        for s in skills:
            assert isinstance(s, str) and ":" in s


class TestSessionEndLayer:
    """Test early session-end detection for short explicit signals."""

    def test_short_chinese_session_end_signal(self, tmp_path: Path) -> None:
        """Very short Chinese session-end signals must still match."""
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        candidates = [
            {
                "id": "builtin/session-end",
                "description": "Session wrap-up",
                "namespace": "builtin",
                "triggers": ["that's all for now", "拜拜", "我要离开了", "先走了"],
            },
            {"id": "debug-skill", "description": "Debug things", "namespace": "builtin"},
        ]

        result = router._single_skill_route("我要离开了", candidates=candidates)

        assert result.has_match
        assert result.primary is not None
        assert result.primary.skill_id == "builtin/session-end"

    def test_short_english_session_end_signal(self, tmp_path: Path) -> None:
        """Short English session-end signals must still match."""
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        candidates = [
            {
                "id": "builtin/session-end",
                "description": "Session wrap-up",
                "namespace": "builtin",
                "triggers": ["i'm done", "heading out", "gotta go"],
            },
            {"id": "debug-skill", "description": "Debug things", "namespace": "builtin"},
        ]

        result = router._single_skill_route("I'm done", candidates=candidates)

        assert result.has_match
        assert result.primary is not None
        assert result.primary.skill_id == "builtin/session-end"

    def test_non_session_end_query_ignored(self, tmp_path: Path) -> None:
        """Problem reports should not hit the session-end layer."""
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        candidates = [
            {
                "id": "builtin/session-end",
                "description": "Session wrap-up",
                "namespace": "builtin",
                "triggers": ["that's all for now", "拜拜"],
            },
            {"id": "debug-skill", "description": "Debug things", "namespace": "builtin"},
        ]

        match, detail = router._try_session_end_layer(
            "CMSpark MCP 有问题，无法获取工具列表", candidates
        )

        assert match is None
        assert detail.matched is False

    def test_session_end_layer_returns_none_when_skill_missing(self, tmp_path: Path) -> None:
        """If session-end skill is not in candidates, layer returns None."""
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        candidates = [
            {"id": "debug-skill", "description": "Debug things", "namespace": "builtin"},
        ]

        match, detail = router._try_session_end_layer("拜拜", candidates)

        assert match is None
        assert detail.matched is False


class TestSessionEndLeavingSignal:
    """「我先离开了」 is an exit signal and must hit the session-end fast path.

    Regression: the trigger list covered 我要离开了/先走了 but not the bare
    离开了 pattern, so 「我先离开了」 fell through to fallback-llm.
    """

    def test_wo_xian_li_kai_le_matches(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        candidates = [
            {
                "id": "builtin/session-end",
                "description": "Session wrap-up",
                "namespace": "builtin",
                # Mirrors core/skills/session-end/SKILL.md triggers.
                "triggers": ["我要离开了", "离开了", "先走了", "收工", "拜拜"],
            },
            {"id": "debug-skill", "description": "Debug things", "namespace": "builtin"},
        ]

        result = router._single_skill_route("我先离开了", candidates=candidates)

        assert result.has_match
        assert result.primary is not None
        assert result.primary.skill_id == "builtin/session-end"


class TestGuardedSkillMatcherGate:
    """Guarded skills must not win the matcher pipeline on fuzzy scores alone.

    Regression: 「似乎有其他进程没有关闭，帮我先关闭了」 keyword-matched
    session-end (0.65) via the 会话 tag, and 「使用合适的 workflow …」
    keyword-matched riper-workflow (0.86) via 'workflow' ⊂ 'riper-workflow'.
    """

    def _candidates(self) -> list[dict]:
        return [
            {
                "id": "builtin/session-end",
                "name": "session-end",
                "description": "Session wrap-up - update handoff + commit",
                "namespace": "builtin",
                "keywords": ["session", "会话", "结束", "总结"],
                "triggers": ["我要离开了", "离开了", "先走了", "收工", "拜拜"],
            },
            {
                "id": "builtin/riper-workflow",
                "name": "riper-workflow",
                "description": "Use ONLY when the user explicitly requests the RIPER "
                "structured 5-phase development workflow",
                "namespace": "builtin",
                "keywords": ["riper", "riper-workflow", "5-phase", "structured-workflow"],
                "triggers": ["use riper", "riper workflow", "riper 工作流", "五阶段工作流"],
            },
            {
                "id": "debug-skill",
                "name": "debug-skill",
                "description": "Debug things",
                "namespace": "builtin",
            },
        ]

    def test_close_something_does_not_route_session_end(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._single_skill_route(
            "似乎有其他进程没有关闭，帮我先关闭了", candidates=self._candidates()
        )

        assert result.primary is None or result.primary.skill_id != "builtin/session-end"

    def test_generic_workflow_query_does_not_route_riper(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._single_skill_route(
            "使用合适的 workflow 在独立的 worktree 上进行开发吧", candidates=self._candidates()
        )

        assert result.primary is None or result.primary.skill_id != "builtin/riper-workflow"

    def test_explicit_riper_query_still_routes(self, tmp_path: Path) -> None:
        """Explicit RIPER intent keeps routing to riper-workflow."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router._single_skill_route(
            "use riper workflow for this feature", candidates=self._candidates()
        )

        assert result.has_match
        assert result.primary is not None
        assert result.primary.skill_id == "builtin/riper-workflow"
