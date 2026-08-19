"""Tier2 gating for ``UnifiedRouter._record_routing_decision`` (auto_extract fix).

Pins down the junk-instinct / positive-feedback fixes:

  - weak last-resort layers (levenshtein/custom/fallback_llm) never mint
    instincts, even at inflated confidence (0.9) — that confidence is not
    trustworthy (see routing_pending._WEAK_MATCH_LAYERS);
  - ai_triage never auto-mints — LLM triage outcomes are human-reviewed via
    the routing pending queue (accept/dismiss write-back) instead;
  - trusted layers (explicit/scenario/semantic_index/keyword/tfidf/embedding)
    DO mint at confidence >= 0.7;
  - low-information queries and megaprompt-length patterns never mint
    (shared ``is_auto_extract_worthy`` gate);
  - routing alone never writes to the preference learner — helpfulness
    requires explicit user feedback, not merely being routed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.models import RoutingLayer, SkillRoute
from vibesop.core.optimization.preference_boost import PreferenceBooster
from vibesop.core.routing.unified import UnifiedRouter

GOOD_QUERY = "debug this routing error now"
# 11 chars (> 5) but zero meaningful tokens ("ok" < 3 latin chars) — low-info.
LOW_INFO_QUERY = "ok ok ok ok"
# Plenty of meaningful tokens, but far beyond AUTO_EXTRACT_MAX_PATTERN_CHARS.
MEGAPROMPT_QUERY = " ".join(["fix the flaky routing test"] * 30)
SKILL = "builtin/systematic-debugging"


class _StubRouter:
    """Minimal host exposing only what _record_routing_decision touches."""

    def __init__(self, tmp_path: Path) -> None:
        self._learner = InstinctLearner(storage_path=tmp_path / "instincts.jsonl")
        self._preference_booster = PreferenceBooster(
            storage_path=str(tmp_path / "preferences.json")
        )

    def _get_instinct_learner(self) -> InstinctLearner:
        return self._learner


def _record(router: _StubRouter, query: str, layer: RoutingLayer, confidence: float) -> None:
    route = SkillRoute(skill_id=SKILL, confidence=confidence, layer=layer)
    UnifiedRouter._record_routing_decision(router, query, route, None)


@pytest.fixture
def router(tmp_path: Path) -> _StubRouter:
    return _StubRouter(tmp_path)


class TestWeakLayersNeverMint:
    @pytest.mark.parametrize(
        "layer",
        [RoutingLayer.LEVENSHTEIN, RoutingLayer.CUSTOM, RoutingLayer.FALLBACK_LLM],
    )
    def test_weak_last_resort_layer_at_high_confidence_mints_nothing(
        self, router: _StubRouter, layer: RoutingLayer
    ) -> None:
        _record(router, GOOD_QUERY, layer, 0.9)
        assert router._learner.instincts == {}

    def test_ai_triage_never_auto_mints(self, router: _StubRouter) -> None:
        """LLM triage outcomes are reviewed via the pending queue, not auto-minted."""
        _record(router, GOOD_QUERY, RoutingLayer.AI_TRIAGE, 0.9)
        assert router._learner.instincts == {}


class TestTrustedLayersMint:
    @pytest.mark.parametrize(
        "layer",
        [
            RoutingLayer.EXPLICIT,
            RoutingLayer.SCENARIO,
            RoutingLayer.SEMANTIC_INDEX,
            RoutingLayer.KEYWORD,
            RoutingLayer.TFIDF,
            RoutingLayer.EMBEDDING,
        ],
    )
    def test_trusted_layer_at_high_confidence_mints(
        self, router: _StubRouter, layer: RoutingLayer
    ) -> None:
        _record(router, GOOD_QUERY, layer, 0.9)
        instinct = next(iter(router._learner.instincts.values()))
        assert instinct.pattern == GOOD_QUERY
        assert instinct.action == f"suggest {SKILL} skill"
        assert instinct.context == layer.value
        assert instinct.source == "auto_routing"
        assert "auto_extracted" in instinct.tags

    def test_confidence_floor_still_applies(self, router: _StubRouter) -> None:
        """Trusted layer below 0.7 confidence still mints nothing."""
        _record(router, GOOD_QUERY, RoutingLayer.KEYWORD, 0.6)
        assert router._learner.instincts == {}


class TestQualityGate:
    def test_low_information_query_never_mints(self, router: _StubRouter) -> None:
        _record(router, LOW_INFO_QUERY, RoutingLayer.KEYWORD, 0.9)
        assert router._learner.instincts == {}

    def test_megaprompt_never_mints(self, router: _StubRouter) -> None:
        """700+ char megaprompts are one-off prompts, not reusable patterns."""
        assert len(MEGAPROMPT_QUERY) > 300
        _record(router, MEGAPROMPT_QUERY, RoutingLayer.KEYWORD, 0.9)
        assert router._learner.instincts == {}


class TestPreferenceNotInflatedByRouting:
    def test_routing_alone_writes_no_preference(self, router: _StubRouter, tmp_path: Path) -> None:
        """Being routed is not evidence of helpfulness — nothing is recorded."""
        _record(router, GOOD_QUERY, RoutingLayer.KEYWORD, 0.9)
        # The instinct minted (proves the recording path ran) ...
        assert len(router._learner.instincts) == 1
        # ... but the preference learner was never even touched.
        assert not (tmp_path / "preferences.json").exists()
