"""Tests for scenario-layer demotion (no short-circuit) and junk-query filtering.

Scenario hits are pure keyword-regex matches at a fixed 0.9 confidence; they
no longer short-circuit the cascade. A scenario hit is demoted to a candidate
that AI triage arbitrates; only when triage produces nothing usable does the
scenario match become the result (flagged via metadata scenario_fallback).
SEMANTIC_INDEX early matches keep their short-circuit behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.models import LayerDetail, RoutingLayer, SkillRoute
from vibesop.core.routing import UnifiedRouter

if TYPE_CHECKING:
    from pathlib import Path

_SCEN_LAYER = "vibesop.core.routing._layers.try_scenario_layer"
_INDEX_LAYER = "vibesop.core.routing._layers.try_index_layer"
_TRIAGE_LAYER = "vibesop.core.routing._layers.try_ai_triage_layer"


def _route(
    skill_id: str,
    confidence: float,
    layer: RoutingLayer,
    metadata: dict | None = None,
) -> SkillRoute:
    return SkillRoute(
        skill_id=skill_id,
        confidence=confidence,
        layer=layer,
        source="builtin",
        metadata=metadata or {},
    )


def _detail(layer: RoutingLayer, matched: bool, reason: str = "") -> LayerDetail:
    return LayerDetail(layer=layer, matched=matched, reason=reason)


def _scenario_hit() -> tuple[SkillRoute, LayerDetail]:
    return (
        _route("builtin/commit", 0.9, RoutingLayer.SCENARIO, {"scenario": "commit"}),
        _detail(RoutingLayer.SCENARIO, True, "Scenario matched: 'commit'"),
    )


def _candidates() -> list[dict]:
    return [
        {"id": "builtin/commit", "description": "Commit code", "namespace": "builtin"},
        {"id": "builtin/review", "description": "Review code", "namespace": "builtin"},
    ]


class TestScenarioDemotionKeywordBranch:
    """use_keyword=True branch (short queries, or long queries without LLM)."""

    # 4 chars <= keyword_match_max_chars default (5) → keyword branch
    QUERY = "提交代码"

    def _make_router(self, tmp_path: Path) -> UnifiedRouter:
        config = RoutingConfig(enable_ai_triage=True)
        return UnifiedRouter(project_root=tmp_path, config=config)

    def test_triage_wins_over_scenario_hit(self, tmp_path: Path) -> None:
        """Scenario hit + usable triage match → triage result, no fallback flag."""
        router = self._make_router(tmp_path)
        triage_match = _route("builtin/review", 0.85, RoutingLayer.AI_TRIAGE)

        with (
            patch(_SCEN_LAYER, return_value=_scenario_hit()),
            patch(_INDEX_LAYER, return_value=(None, _detail(RoutingLayer.SEMANTIC_INDEX, False))),
            patch(
                _TRIAGE_LAYER,
                return_value=(triage_match, _detail(RoutingLayer.AI_TRIAGE, True)),
            ),
        ):
            result = router._single_skill_route(self.QUERY, candidates=_candidates())

        assert result.primary is not None
        assert result.primary.skill_id == "builtin/review"
        assert result.primary.layer == RoutingLayer.AI_TRIAGE
        assert "scenario_fallback" not in result.primary.metadata
        assert RoutingLayer.SCENARIO in result.routing_path
        assert RoutingLayer.AI_TRIAGE in result.routing_path

    def test_scenario_fallback_when_triage_returns_nothing(self, tmp_path: Path) -> None:
        """Scenario hit + triage no-result → scenario match with fallback flag."""
        router = self._make_router(tmp_path)

        with (
            patch(_SCEN_LAYER, return_value=_scenario_hit()),
            patch(_INDEX_LAYER, return_value=(None, _detail(RoutingLayer.SEMANTIC_INDEX, False))),
            patch(
                _TRIAGE_LAYER,
                return_value=(None, _detail(RoutingLayer.AI_TRIAGE, False, "LLM not initialized")),
            ),
        ):
            result = router._single_skill_route(self.QUERY, candidates=_candidates())

        assert result.primary is not None
        assert result.primary.skill_id == "builtin/commit"
        assert result.primary.layer == RoutingLayer.SCENARIO
        assert result.primary.metadata["scenario_fallback"] is True

    def test_scenario_fallback_when_triage_below_min_confidence(self, tmp_path: Path) -> None:
        """Triage match under min_confidence counts as no usable result."""
        router = self._make_router(tmp_path)
        weak_triage = _route("builtin/review", 0.1, RoutingLayer.AI_TRIAGE)

        with (
            patch(_SCEN_LAYER, return_value=_scenario_hit()),
            patch(_INDEX_LAYER, return_value=(None, _detail(RoutingLayer.SEMANTIC_INDEX, False))),
            patch(
                _TRIAGE_LAYER,
                return_value=(weak_triage, _detail(RoutingLayer.AI_TRIAGE, True)),
            ),
        ):
            result = router._single_skill_route(self.QUERY, candidates=_candidates())

        assert result.primary is not None
        assert result.primary.skill_id == "builtin/commit"
        assert result.primary.layer == RoutingLayer.SCENARIO
        assert result.primary.metadata["scenario_fallback"] is True

    def test_index_short_circuit_unchanged(self, tmp_path: Path) -> None:
        """Index winning the best-of still short-circuits; triage never runs."""
        router = self._make_router(tmp_path)
        index_match = _route("builtin/review", 0.95, RoutingLayer.SEMANTIC_INDEX)
        triage_mock = MagicMock(return_value=(None, _detail(RoutingLayer.AI_TRIAGE, False)))

        with (
            patch(_SCEN_LAYER, return_value=_scenario_hit()),
            patch(
                _INDEX_LAYER,
                return_value=(index_match, _detail(RoutingLayer.SEMANTIC_INDEX, True)),
            ),
            patch(_TRIAGE_LAYER, triage_mock),
        ):
            result = router._single_skill_route(self.QUERY, candidates=_candidates())

        assert result.primary is not None
        assert result.primary.skill_id == "builtin/review"
        assert result.primary.layer == RoutingLayer.SEMANTIC_INDEX
        triage_mock.assert_not_called()
        assert RoutingLayer.AI_TRIAGE not in result.routing_path

    def test_scenario_hit_forces_triage_on_short_query(self, tmp_path: Path) -> None:
        """Short query + scenario hit → triage called with force=True.

        The short-query bypass must not apply when a scenario candidate is
        pending: scenario-matching queries are the ambiguity hot spots the
        forced triage arbitration exists for.
        """
        router = self._make_router(tmp_path)
        triage_match = _route("builtin/review", 0.85, RoutingLayer.AI_TRIAGE)
        triage_mock = MagicMock(return_value=(triage_match, _detail(RoutingLayer.AI_TRIAGE, True)))

        with (
            patch(_SCEN_LAYER, return_value=_scenario_hit()),
            patch(_INDEX_LAYER, return_value=(None, _detail(RoutingLayer.SEMANTIC_INDEX, False))),
            patch(_TRIAGE_LAYER, triage_mock),
        ):
            result = router._single_skill_route(self.QUERY, candidates=_candidates())

        assert triage_mock.call_args.kwargs["force"] is True
        assert result.primary is not None
        assert result.primary.skill_id == "builtin/review"
        assert result.primary.layer == RoutingLayer.AI_TRIAGE
        assert "scenario_fallback" not in result.primary.metadata

    def test_forced_triage_no_result_still_falls_back_to_scenario(self, tmp_path: Path) -> None:
        """Forced triage producing nothing → scenario fallback path unchanged."""
        router = self._make_router(tmp_path)
        triage_mock = MagicMock(
            return_value=(None, _detail(RoutingLayer.AI_TRIAGE, False, "LLM not initialized"))
        )

        with (
            patch(_SCEN_LAYER, return_value=_scenario_hit()),
            patch(_INDEX_LAYER, return_value=(None, _detail(RoutingLayer.SEMANTIC_INDEX, False))),
            patch(_TRIAGE_LAYER, triage_mock),
        ):
            result = router._single_skill_route(self.QUERY, candidates=_candidates())

        assert triage_mock.call_args.kwargs["force"] is True
        assert result.primary is not None
        assert result.primary.skill_id == "builtin/commit"
        assert result.primary.layer == RoutingLayer.SCENARIO
        assert result.primary.metadata["scenario_fallback"] is True

    def test_short_query_without_scenario_hit_keeps_bypass(self, tmp_path: Path) -> None:
        """No scenario candidate → triage stays unforced (bypass still applies)."""
        router = self._make_router(tmp_path)
        triage_mock = MagicMock(
            return_value=(None, _detail(RoutingLayer.AI_TRIAGE, False, "Short-query bypass"))
        )

        with (
            patch(_SCEN_LAYER, return_value=(None, _detail(RoutingLayer.SCENARIO, False))),
            patch(_INDEX_LAYER, return_value=(None, _detail(RoutingLayer.SEMANTIC_INDEX, False))),
            patch(_TRIAGE_LAYER, triage_mock),
        ):
            router._single_skill_route(self.QUERY, candidates=_candidates())

        assert triage_mock.call_args.kwargs["force"] is False


class TestScenarioDemotionLLMBranch:
    """use_keyword=False branch (long query with LLM available).

    The LLM branch never tries the scenario layer (index standalone), so the
    demotion does not apply there; triage is forced as before.
    """

    # 21 chars > keyword_match_max_chars default (15) → LLM branch
    QUERY = "请全面审查这个仓库的代码质量并给出改进建议"

    def _make_router(self, tmp_path: Path) -> UnifiedRouter:
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        router._llm = MagicMock()
        return router

    def test_scenario_layer_not_tried_and_triage_wins(self, tmp_path: Path) -> None:
        router = self._make_router(tmp_path)
        triage_match = _route("builtin/review", 0.85, RoutingLayer.AI_TRIAGE)
        scenario_mock = MagicMock(return_value=_scenario_hit())

        with (
            patch(_SCEN_LAYER, scenario_mock),
            patch(_INDEX_LAYER, return_value=(None, _detail(RoutingLayer.SEMANTIC_INDEX, False))),
            patch(
                _TRIAGE_LAYER,
                return_value=(triage_match, _detail(RoutingLayer.AI_TRIAGE, True)),
            ),
        ):
            result = router._single_skill_route(self.QUERY, candidates=_candidates())

        scenario_mock.assert_not_called()
        assert result.primary is not None
        assert result.primary.skill_id == "builtin/review"
        assert result.primary.layer == RoutingLayer.AI_TRIAGE

    def test_index_short_circuit_unchanged_in_llm_branch(self, tmp_path: Path) -> None:
        router = self._make_router(tmp_path)
        index_match = _route("builtin/review", 0.95, RoutingLayer.SEMANTIC_INDEX)
        triage_mock = MagicMock(return_value=(None, _detail(RoutingLayer.AI_TRIAGE, False)))

        with (
            patch(
                _INDEX_LAYER,
                return_value=(index_match, _detail(RoutingLayer.SEMANTIC_INDEX, True)),
            ),
            patch(_TRIAGE_LAYER, triage_mock),
        ):
            result = router._single_skill_route(self.QUERY, candidates=_candidates())

        assert result.primary is not None
        assert result.primary.layer == RoutingLayer.SEMANTIC_INDEX
        triage_mock.assert_not_called()


class TestScenarioParticipationCounting:
    """Layer stats must count scenario participation under triage arbitration.

    A scenario hit forces triage arbitration; when triage wins, the scenario
    layer still participated in the routing decision and must be counted
    exactly once — otherwise layer stats under-report scenario involvement.
    """

    # 4 chars <= keyword_match_max_chars default (5) → keyword branch
    QUERY = "提交代码"

    def _make_router(self, tmp_path: Path) -> UnifiedRouter:
        config = RoutingConfig(enable_ai_triage=True)
        return UnifiedRouter(project_root=tmp_path, config=config)

    def test_triage_win_counts_scenario_participation(self, tmp_path: Path) -> None:
        router = self._make_router(tmp_path)
        triage_match = _route("builtin/review", 0.85, RoutingLayer.AI_TRIAGE)

        with (
            patch(_SCEN_LAYER, return_value=_scenario_hit()),
            patch(_INDEX_LAYER, return_value=(None, _detail(RoutingLayer.SEMANTIC_INDEX, False))),
            patch(
                _TRIAGE_LAYER,
                return_value=(triage_match, _detail(RoutingLayer.AI_TRIAGE, True)),
            ),
        ):
            router._single_skill_route(self.QUERY, candidates=_candidates())

        dist = router.get_stats()["layer_distribution"]
        assert dist[RoutingLayer.AI_TRIAGE.value] == 1
        assert dist[RoutingLayer.SCENARIO.value] == 1

    def test_scenario_fallback_counts_scenario_once(self, tmp_path: Path) -> None:
        """The fallback branch has its own count — no double counting."""
        router = self._make_router(tmp_path)

        with (
            patch(_SCEN_LAYER, return_value=_scenario_hit()),
            patch(_INDEX_LAYER, return_value=(None, _detail(RoutingLayer.SEMANTIC_INDEX, False))),
            patch(
                _TRIAGE_LAYER,
                return_value=(None, _detail(RoutingLayer.AI_TRIAGE, False, "LLM not initialized")),
            ),
        ):
            router._single_skill_route(self.QUERY, candidates=_candidates())

        dist = router.get_stats()["layer_distribution"]
        assert dist[RoutingLayer.SCENARIO.value] == 1
        assert RoutingLayer.AI_TRIAGE.value not in dist

    def test_triage_win_without_scenario_hit_no_scenario_count(self, tmp_path: Path) -> None:
        router = self._make_router(tmp_path)
        triage_match = _route("builtin/review", 0.85, RoutingLayer.AI_TRIAGE)

        with (
            patch(_SCEN_LAYER, return_value=(None, _detail(RoutingLayer.SCENARIO, False))),
            patch(_INDEX_LAYER, return_value=(None, _detail(RoutingLayer.SEMANTIC_INDEX, False))),
            patch(
                _TRIAGE_LAYER,
                return_value=(triage_match, _detail(RoutingLayer.AI_TRIAGE, True)),
            ),
        ):
            router._single_skill_route(self.QUERY, candidates=_candidates())

        dist = router.get_stats()["layer_distribution"]
        assert dist[RoutingLayer.AI_TRIAGE.value] == 1
        assert RoutingLayer.SCENARIO.value not in dist


class TestSystemReminderFilter:
    """Queries that ARE harness markup (the query starts with a known
    injection marker: <system-reminder>, <system_reminder>, or
    <environment_details>) are rejected at the routing entry point: no
    matching layer runs, no analytics/miss telemetry. Queries that merely
    mention a marker mid-text are legitimate and must flow through the
    cascade."""

    JUNK_QUERY = "<system-reminder>Auto permission mode is active.</system-reminder> 帮我审查代码"

    def test_junk_query_returns_no_match_without_layers(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.route(self.JUNK_QUERY, candidates=_candidates())

        assert result.primary is None
        assert not result.has_match
        # No matching layer was entered
        assert result.routing_path == []
        assert len(result.layer_details) == 1
        assert result.layer_details[0].layer == RoutingLayer.NO_MATCH
        assert result.layer_details[0].matched is False

    def test_junk_query_skips_telemetry(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        router._record_single_route_execution = MagicMock()
        router._record_route_miss = MagicMock()
        router._maybe_enqueue_routing_pending = MagicMock()

        router.route(self.JUNK_QUERY, candidates=_candidates())

        router._record_single_route_execution.assert_not_called()
        router._record_route_miss.assert_not_called()
        router._maybe_enqueue_routing_pending.assert_not_called()

    def test_junk_query_does_not_start_trace(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        router._tracer.enabled = True
        start_trace = MagicMock()
        router._tracer.start_trace = start_trace

        router.route(self.JUNK_QUERY, candidates=_candidates())

        start_trace.assert_not_called()

    def test_normal_query_unaffected(self, tmp_path: Path) -> None:
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.route("review my pull request", candidates=_candidates())

        # Normal queries still flow through the layer cascade
        assert result.routing_path != []

    def test_single_skill_route_guarded_for_direct_callers(self, tmp_path: Path) -> None:
        """The guard is sunk into _single_skill_route: orchestrator / session
        callers bypass route() but must still never reach the layer cascade."""
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        try_layers = MagicMock()

        with patch.object(router, "_try_layers", try_layers):
            result = router._single_skill_route(self.JUNK_QUERY, candidates=_candidates())

        try_layers.assert_not_called()
        assert result.primary is None
        assert result.routing_path == []
        assert len(result.layer_details) == 1
        assert result.layer_details[0].layer == RoutingLayer.NO_MATCH

    def test_orchestrate_path_junk_query_skips_matching_layers(self, tmp_path: Path) -> None:
        """orchestrate() calls _single_skill_route directly — junk queries
        must not enter the matching layers on that path either."""
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        try_layers = MagicMock()

        with patch.object(router, "_try_layers", try_layers):
            result = router.orchestrate(self.JUNK_QUERY, candidates=_candidates())

        try_layers.assert_not_called()
        assert result.primary is None

    def test_whitespace_prefixed_injection_still_rejected(self, tmp_path: Path) -> None:
        """Real injection with leading whitespace/newlines before the marker
        is still junk (the predicate ignores leading whitespace)."""
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        result = router.route("\n  " + self.JUNK_QUERY, candidates=_candidates())

        assert result.primary is None
        assert result.routing_path == []
        assert len(result.layer_details) == 1
        assert result.layer_details[0].layer == RoutingLayer.NO_MATCH

    def test_all_marker_forms_rejected(self, tmp_path: Path) -> None:
        """All known injection shapes are junk when they prefix the query:
        Kimi Code <system-reminder>, Claude Code <system_reminder>, and
        <environment_details>."""
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        for marker in ("<system-reminder", "<system_reminder", "<environment_details"):
            result = router.route(
                f"{marker}>harness injected context</x> 帮我审查代码",
                candidates=_candidates(),
            )

            assert result.primary is None, marker
            assert result.routing_path == [], marker
            assert len(result.layer_details) == 1, marker
            assert result.layer_details[0].layer == RoutingLayer.NO_MATCH, marker

    def test_literal_marker_mention_not_rejected(self, tmp_path: Path) -> None:
        """A normal query that literally discusses a marker mid-text (e.g.
        developing this repo's own junk filter) must NOT be rejected — only
        queries starting with a marker are junk."""
        config = RoutingConfig(enable_ai_triage=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)

        for query in (
            "为什么 route() 要拦截 <system-reminder> 标记?帮我审查这段逻辑",
            "为什么 route() 要拦截 <system_reminder> 标记?帮我审查这段逻辑",
            "为什么 route() 要拦截 <environment_details> 标记?帮我审查这段逻辑",
        ):
            result = router.route(query, candidates=_candidates())

            # Flowed through the layer cascade instead of the junk no-match shape
            assert result.routing_path != [], query

    def test_orchestrate_path_long_junk_query_never_decomposes(self, tmp_path: Path) -> None:
        """Regression: _single_skill_route returns no-match for junk, but the
        detector's primary=None branch treated any long no-match query as a
        possible multi-part request and decomposed the garbage text. Junk must
        short-circuit in the orchestrator before multi-intent detection."""
        config = RoutingConfig(enable_ai_triage=True)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        # Long enough that the primary=None heuristic branch would decompose
        long_junk = self.JUNK_QUERY + " " + ("harness injected padding text " * 10)
        decomposer = MagicMock()

        with patch.object(router, "_get_task_decomposer", return_value=decomposer):
            result = router.orchestrate(long_junk, candidates=_candidates())

        decomposer.decompose.assert_not_called()
        assert result.primary is None
