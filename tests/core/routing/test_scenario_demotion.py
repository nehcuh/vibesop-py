"""Tests for scenario-layer demotion (no short-circuit) and junk-query filtering.

Scenario hits are pure keyword-regex matches at a fixed 0.9 confidence; they
no longer short-circuit the cascade. A scenario hit is demoted to a candidate
that AI triage arbitrates; only when triage produces nothing usable does the
scenario match become the result (flagged via metadata scenario_fallback).
SEMANTIC_INDEX early matches keep their short-circuit behavior.
"""

from __future__ import annotations

import copy
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.models import LayerDetail, RoutingLayer, SkillRoute
from vibesop.core.routing import UnifiedRouter
from vibesop.core.routing.triage_cache import TriageCache
from vibesop.core.routing.triage_service import LAST_GOOD_CONFIDENCE_DECAY

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

    # 4 chars <= keyword_match_max_chars default (15) → keyword branch
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

    # 4 chars <= keyword_match_max_chars default (15) → keyword branch
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


class TestLastGoodDecayScenarioBranch:
    """Real last-good decay against a configured 0.6 gate, then scenario fallback.

    The triage match is produced by the production cache writer
    (``SkillRoute.to_dict`` → ``TriageCache.store``) and a real LLM failure on
    a stale entry. Scenario and index are stubbed only so the cascade reaches
    the unchanged ``min_confidence`` comparison in unified.py. The decay
    constant and RoutingConfig's default gate are not modified; 0.6 is set on
    this router because that is the threshold the two sides are defined against.
    """

    QUERY = "提交代码"
    GATE = 0.6

    @staticmethod
    def _skill_candidate(tmp_path: Path, skill_id: str, description: str) -> dict[str, str]:
        """Real skill file. filter_routable drops candidates with no source_file."""
        path = tmp_path / "skills" / skill_id.replace("/", "-") / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nid: {skill_id}\n---\n{description}\n", encoding="utf-8")
        return {
            "id": skill_id,
            "description": description,
            "namespace": "builtin",
            "source_file": str(path),
        }

    def _routable_candidates(self, tmp_path: Path) -> list[dict[str, str]]:
        return [
            self._skill_candidate(tmp_path, "builtin/commit", "Commit code"),
            self._skill_candidate(tmp_path, "builtin/review", "Review code"),
        ]

    def _payload(self, tmp_path: Path, original_confidence: float) -> dict[str, Any]:
        config = RoutingConfig(enable_ai_triage=True, min_confidence=self.GATE)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        assert router._config.min_confidence == self.GATE
        assert RoutingConfig().min_confidence == 0.3
        llm = MagicMock()
        llm.configured.return_value = True
        llm.call.side_effect = RuntimeError("LLM down")
        router._llm = llm

        base = self._routable_candidates(tmp_path)
        stored = SkillRoute(
            skill_id="builtin/review",
            confidence=original_confidence,
            layer=RoutingLayer.AI_TRIAGE,
            source="builtin",
            description="Review code",
        ).to_dict()
        cache = router._triage_service._triage_cache
        assert cache is not None
        cache.store(self.QUERY, base, stored)
        # A different installed set makes the cache row stale. The stored
        # skill stays present, which is what last-good re-validates.
        extra = self._skill_candidate(tmp_path, "builtin/extra", "extra")
        routed = [*base, extra]

        with (
            patch(_SCEN_LAYER, return_value=_scenario_hit()),
            patch(_INDEX_LAYER, return_value=(None, _detail(RoutingLayer.SEMANTIC_INDEX, False))),
        ):
            result = router._single_skill_route(self.QUERY, candidates=routed)

        payload = result.to_dict()
        assert "primary" in payload
        assert "layer_details" in payload
        primary = payload["primary"]
        assert primary is not None
        # The producer decay is visible on the triage detail even when the
        # gate later drops the match. The rounded percent in the reason is
        # not the contract; the route metadata / scenario flag is.
        triage = next(
            detail
            for detail in payload["layer_details"]
            if detail["layer"] == RoutingLayer.AI_TRIAGE.value
        )
        assert triage["matched"] is True
        assert "builtin/review" in triage["reason"]
        decayed = original_confidence * LAST_GOOD_CONFIDENCE_DECAY
        if decayed >= self.GATE:
            assert primary["metadata"].get("last_good_original_confidence") == pytest.approx(
                original_confidence
            )
            assert primary["confidence"] >= self.GATE
        else:
            assert primary["metadata"].get("last_good") is not True
        return payload

    def test_decayed_0_63_accepted_without_scenario_fallback(self, tmp_path: Path) -> None:
        """0.9 * 0.7 = 0.63 >= 0.6 keeps the last-good route."""
        payload = self._payload(tmp_path, 0.9)
        primary = payload["primary"]
        meta = primary["metadata"]
        assert primary["skill_id"] == "builtin/review"
        assert primary["layer"] == RoutingLayer.AI_TRIAGE.value
        assert meta.get("last_good") is True
        assert meta.get("last_good_original_confidence") == pytest.approx(0.9)
        assert "scenario_fallback" not in meta
        assert meta.get("scenario_fallback") is not True

    def test_decayed_0_56_rejected_with_scenario_fallback(self, tmp_path: Path) -> None:
        """0.8 * 0.7 = 0.56 < 0.6 drops last-good and flags the scenario fallback."""
        payload = self._payload(tmp_path, 0.8)
        primary = payload["primary"]
        meta = primary["metadata"]
        assert primary["skill_id"] == "builtin/commit"
        assert primary["layer"] == RoutingLayer.SCENARIO.value
        assert meta.get("scenario_fallback") is True
        assert meta.get("last_good") is not True
        assert "last_good_original_confidence" not in meta


def _e2e_module() -> Any:
    """Load the live script. The oracle under test is not a production import."""
    path = Path(__file__).resolve().parents[3] / "scripts" / "e2e_llm_routing.py"
    spec = importlib.util.spec_from_file_location("e2e_llm_routing_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CONTROLLED_CASES = (
    "accept",
    "reject",
    "equality",
    "negative",
    "no-entry",
    "same-skill-two-query",
    "context-key",
)


class TestCapturedKeyLastGoodOracle:
    """Script oracle: one captured lookup key, never a skill/reason cache scan."""

    def test_live_precondition_missing_is_not_a_pass(self) -> None:
        mod = _e2e_module()
        missing = (
            None,
            {"skill_id": None, "confidence": 0.0},
            {"skill_id": "builtin/review"},
            {"skill_id": "builtin/review", "confidence": True},
            {"skill_id": "builtin/review", "confidence": "0.9"},
            {"skill_id": "", "confidence": 0.9},
        )
        for row in missing:
            assert mod.live_t4_precondition(row) == "PRECONDITION_MISSING"
        assert mod.live_t4_precondition({"skill_id": "builtin/review", "confidence": 0.9}) == (
            "POSITIVE"
        )
        assert "PASS" not in {
            mod.live_t4_precondition(row) for row in (*missing, {"skill_id": "x", "confidence": 1})
        }

    def test_row_lookup_uses_captured_key_only(self) -> None:
        mod = _e2e_module()
        cache = {
            "key-actual": {"skill_id": "builtin/review", "confidence": 0.8},
            "key-other": {"skill_id": "builtin/review", "confidence": 0.9},
        }
        row = mod.row_for_captured_key(cache, "key-actual")
        assert row["confidence"] == pytest.approx(0.8)
        assert mod.row_for_captured_key(cache, "missing") is None
        assert mod.row_for_captured_key(cache, None) is None
        assert not hasattr(mod, "_recorded_last_good_original")

    def test_observer_delegates_to_real_lookup(self, tmp_path: Path) -> None:
        mod = _e2e_module()
        cache = TriageCache(tmp_path)
        query = "提交代码"
        candidates = [{"id": "builtin/review", "description": "Review code"}]
        stored = SkillRoute(
            skill_id="builtin/review",
            confidence=0.9,
            layer=RoutingLayer.AI_TRIAGE,
            source="builtin",
            description="Review code",
        ).to_dict()
        cache.store(query, candidates, stored)
        observed = mod.install_lookup_observer(cache)
        fresh, stale = cache.lookup(query, candidates, 72)
        assert observed["reached"] is True
        assert observed["query"] == query
        assert observed["key"] == TriageCache.key_for(query)
        assert fresh is not None and stale is None
        assert fresh["confidence"] == pytest.approx(0.9)
        assert fresh["skill_id"] == "builtin/review"

    def test_same_skill_two_queries_oracle_returns_that_rows_original(self, tmp_path: Path) -> None:
        """Same skill at .8 and .9 must not make the .8 query's oracle return None."""
        outcome = _e2e_module().controlled_same_skill_two_query(tmp_path)
        assert outcome["marker"] == "controlled"
        assert outcome["confidence_source"] == "controlled_fixture"
        assert outcome["located_by"] == "captured_key"
        assert outcome["ok"] is True
        assert outcome["original"] == pytest.approx(0.8)
        assert outcome["other_original"] == pytest.approx(0.9)
        assert outcome["decayed"] == pytest.approx(outcome["original"] * LAST_GOOD_CONFIDENCE_DECAY)
        assert outcome["decayed"] < outcome["min_confidence"]
        assert outcome["min_confidence"] == pytest.approx(outcome["router_min_confidence"])
        assert outcome["scenario_fallback"] is True
        assert outcome["last_good"] is not True
        assert outcome["stored_candidates_hash"] != "deadbeefdeadbeef"

    def test_context_lookup_key_differs_from_raw_and_result_query(self, tmp_path: Path) -> None:
        """Augmented cache query, raw prompt, and RoutingResult.query are three strings."""
        outcome = _e2e_module().controlled_context_key(tmp_path)
        assert outcome["marker"] == "controlled"
        assert outcome["confidence_source"] == "controlled_fixture"
        assert outcome["located_by"] == "captured_key"
        assert outcome["ok"] is True
        assert outcome["captured_query"] != outcome["raw_query"]
        assert outcome["captured_query"] != outcome["result_query"]
        assert outcome["raw_query"] != outcome["result_query"]
        assert outcome["captured_key"] == TriageCache.key_for(outcome["captured_query"])
        assert outcome["captured_key"] != TriageCache.key_for(outcome["raw_query"])
        assert outcome["captured_key"] != TriageCache.key_for(outcome["result_query"])
        assert outcome["raw_key_in_cache"] is True
        assert outcome["result_query_key_in_cache"] is False
        assert outcome["original"] == pytest.approx(0.9)
        assert outcome["decoy_original"] == pytest.approx(0.8)
        assert outcome["row_key"] == outcome["captured_key"]

    def test_default_live_path_still_requires_api_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        script = Path(__file__).resolve().parents[3] / "scripts" / "e2e_llm_routing.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--project-root", str(tmp_path)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=60,
            check=False,
        )
        assert proc.returncode == 2
        assert "DEEPSEEK_API_KEY" in proc.stdout

    def test_controlled_cli_is_independent_of_live_and_api_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        script = Path(__file__).resolve().parents[3] / "scripts" / "e2e_llm_routing.py"
        repo_cache = Path(__file__).resolve().parents[3] / ".vibe" / "triage_cache.json"
        before = repo_cache.read_bytes() if repo_cache.exists() else None
        proc = subprocess.run(
            [sys.executable, str(script), "--controlled-lastgood"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=180,
            check=False,
        )
        after = repo_cache.read_bytes() if repo_cache.exists() else None
        assert before == after
        assert proc.returncode == 0, proc.stdout + proc.stderr
        for case in _CONTROLLED_CASES:
            assert f"controlled {case} " in proc.stdout
        assert "CONTROLLED SUMMARY: 7/7 passed marker=controlled" in proc.stdout
        assert "LIVE SUMMARY:" in proc.stdout
        assert "PRECONDITION_MISSING" not in proc.stdout
        assert "live_llm" not in proc.stdout
        assert "controlled_fixture" in proc.stdout
        assert "marker=controlled" in proc.stdout

    def test_accept_oracle_rejects_mutated_primary_confidence_and_skill(
        self, tmp_path: Path
    ) -> None:
        """Real to_dict copies: .63/.6 → .01, missing, bool, nonfinite, or wrong skill fail."""
        mod = _e2e_module()
        outcomes = {item["case"]: item for item in mod._controlled_outcomes(tmp_path)}
        for name in ("accept", "equality", "context-key"):
            outcome = outcomes[name]
            route = outcome["route"]
            row = outcome["row"]
            gate = outcome["min_confidence"]
            assert outcome["ok"] is True
            assert mod._decay_matches_row(route, row, gate)[0] is True
            assert route["primary"]["skill_id"] == row["skill_id"]
            assert route["primary"]["confidence"] == pytest.approx(outcome["decayed"])
            assert route["primary"]["confidence"] != pytest.approx(0.01)
            replacements: tuple[object, ...] = (
                0.01,
                True,
                float("nan"),
                float("inf"),
                float("-inf"),
            )
            for value in replacements:
                damaged = copy.deepcopy(route)
                damaged["primary"]["confidence"] = value
                assert mod._decay_matches_row(damaged, row, gate)[0] is False
            missing = copy.deepcopy(route)
            del missing["primary"]["confidence"]
            assert mod._decay_matches_row(missing, row, gate)[0] is False
            wrong_skill = copy.deepcopy(route)
            wrong_skill["primary"]["skill_id"] = "builtin/not-the-captured-row"
            assert wrong_skill["primary"]["skill_id"] != row["skill_id"]
            assert mod._decay_matches_row(wrong_skill, row, gate)[0] is False

    def test_reject_oracle_does_not_require_scenario_primary_confidence(
        self, tmp_path: Path
    ) -> None:
        """Scenario fallback confidence stays 0.9; it is not the decayed last-good number."""
        mod = _e2e_module()
        query = "提交代码"
        outcome = mod._controlled_case(
            tmp_path,
            "reject",
            query=query,
            stores=[(query, 0.8)],
        )
        route = outcome["route"]
        row = outcome["row"]
        assert outcome["ok"] is True
        assert route["primary"]["layer"] == RoutingLayer.SCENARIO.value
        assert route["primary"]["skill_id"] != row["skill_id"]
        assert route["primary"]["confidence"] == pytest.approx(0.9)
        assert outcome["decayed"] == pytest.approx(0.8 * LAST_GOOD_CONFIDENCE_DECAY)
        assert route["primary"]["confidence"] != pytest.approx(outcome["decayed"])
        damaged = copy.deepcopy(route)
        damaged["primary"]["confidence"] = 0.01
        assert mod._decay_matches_row(damaged, row, outcome["min_confidence"])[0] is True
