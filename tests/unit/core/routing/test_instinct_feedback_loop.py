"""Reproduction: the instinct -> routing feedback loop is dead (Phase 0 finding).

Phase 0 diagnosed that auto-recorded instincts never mature, so the learning
loop is wired-but-dead:

  1. ``UnifiedRouter._record_routing_decision`` (unified.py) calls
     ``InstinctLearner.learn(...)`` for every high-confidence route
     (``source="auto_routing"``). ``learn()`` creates an instinct with
     ``success_count=0, failure_count=0, confidence=0.5`` ->
     ``total_applications=0`` -> ``is_reliable=False``.
  2. The ONLY thing that increments ``total_applications`` is
     ``InstinctLearner.record_outcome`` (learner.py) — and its sole caller is
     ``extract_from_experiment``, which itself has zero callers in src/.
     The routing path NEVER calls ``record_outcome``.
  3. ``find_matching`` skips every instinct where ``not is_reliable``
     (learner.py) — so auto-recorded instincts never surface.
  4. ``OptimizationService.apply_instinct_boost`` calls ``find_matching``
     (min_confidence=0.6), gets ``[]``, and applies 0 boosts.

Result: 1203 auto-recorded instincts on disk, all stuck at confidence=0.5 /
success_count=0, contributing nothing to routing. The contrast test below shows
the loop WOULD close if outcomes were recorded.

These tests nail down the current (broken) behavior. Phase 2 wires
``record_outcome`` into the routing acceptance path; once wired, a separate
routing-level test will confirm maturation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.matching.base import MatchResult, MatcherType
from vibesop.core.routing.optimization_service import OptimizationService

QUERY = "debug this routing error now"
SKILL = "builtin/systematic-debugging"
# Mirrors the action string UnifiedRouter._record_routing_decision writes:
# f"suggest {match.skill_id} skill"
ACTION = f"suggest {SKILL} skill"


def _real_learner(tmp_path: Path) -> InstinctLearner:
    """InstinctLearner backed by tmp storage (isolated from .vibe/instincts.jsonl)."""
    return InstinctLearner(storage_path=tmp_path / "instincts.jsonl")


def _make_service(learner: InstinctLearner) -> OptimizationService:
    """OptimizationService with real instinct learner; other deps mocked.

    ``apply_instinct_boost`` only touches ``self._get_instinct_learner`` (not
    config), so the mocked config/boosters are never exercised here.
    """
    return OptimizationService(
        config=MagicMock(),
        optimization_config=MagicMock(),
        preference_booster=MagicMock(),
        cluster_index=MagicMock(),
        conflict_resolver=MagicMock(),
        get_instinct_learner=lambda: learner,
    )


def _match(skill_id: str, confidence: float) -> MatchResult:
    return MatchResult(
        skill_id=skill_id,
        confidence=confidence,
        matcher_type=MatcherType.KEYWORD,
        matched_keywords=[],
        metadata={},
        score_breakdown={},
    )


class TestInstinctFeedbackLoopDead:
    """Nail down: auto-recorded instincts yield 0 boosts (the dead loop)."""

    def test_auto_recorded_instinct_is_immature(self, tmp_path: Path) -> None:
        """The unified.py auto-record path produces an instinct that can never be reliable."""
        learner = _real_learner(tmp_path)
        # Mirrors UnifiedRouter._record_routing_decision auto-record call.
        learner.learn(
            pattern=QUERY,
            action=ACTION,
            context="ai_triage",
            tags=["routing", "auto_extracted"],
            source="auto_routing",
        )
        instinct = next(iter(learner.instincts.values()))

        assert instinct.total_applications == 0
        assert instinct.success_count == 0
        assert instinct.confidence == 0.5
        # Root cause: total_applications < 3 -> never reliable, no matter the confidence.
        assert instinct.is_reliable is False

    def test_find_matching_skips_immature_instinct(self, tmp_path: Path) -> None:
        """find_matching filters out the immature auto-recorded instinct -> empty list."""
        learner = _real_learner(tmp_path)
        learner.learn(pattern=QUERY, action=ACTION, source="auto_routing")

        # min_confidence=0.6 mirrors apply_instinct_boost's call.
        matches = learner.find_matching(QUERY, min_confidence=0.6)

        # THE BUG: an auto-recorded instinct for the exact query never surfaces.
        assert matches == []

    def test_apply_instinct_boost_returns_zero_boosts_for_auto_recorded(
        self, tmp_path: Path
    ) -> None:
        """The production consumer applies NO boost for auto-recorded instincts."""
        learner = _real_learner(tmp_path)
        learner.learn(pattern=QUERY, action=ACTION, source="auto_routing")
        svc = _make_service(learner)

        result = svc.apply_instinct_boost([_match(SKILL, 0.5)], QUERY, context=None)

        # Unchanged confidence + no boost metadata = 0 instinct boost applied.
        assert result[0].confidence == 0.5
        assert result[0].metadata.get("boosted") is not True
        assert result[0].metadata.get("boost_source") != "instinct"


class TestContrastLoopClosesWithOutcomes:
    """CONTRAST: if record_outcome WERE wired, the instinct would mature and boost.

    Phase 2 wires record_outcome into routing acceptance; these show the loop
    closes mechanically once outcomes land. No routing change is needed for
    these to pass — they exercise the learner/service directly.
    """

    def test_record_outcome_matures_instinct(self, tmp_path: Path) -> None:
        """3 accepted outcomes cross the is_reliable threshold."""
        learner = _real_learner(tmp_path)
        learner.learn(pattern=QUERY, action=ACTION, source="auto_routing")
        instinct = next(iter(learner.instincts.values()))

        # Simulate 3 accepted outcomes (what routing acceptance should do).
        for _ in range(3):
            learner.record_outcome(instinct.id, success=True)

        assert instinct.total_applications == 3
        assert instinct.is_reliable is True
        # Wilson-scored confidence rises above the 0.6 find_matching gate.
        assert instinct.confidence >= 0.6

    def test_matured_instinct_boosts_match(self, tmp_path: Path) -> None:
        """Once matured, apply_instinct_boost applies a real boost -> loop closed."""
        learner = _real_learner(tmp_path)
        learner.learn(pattern=QUERY, action=ACTION, source="auto_routing")
        instinct = next(iter(learner.instincts.values()))
        for _ in range(3):
            learner.record_outcome(instinct.id, success=True)

        svc = _make_service(learner)
        result = svc.apply_instinct_boost([_match(SKILL, 0.5)], QUERY, context=None)

        assert result[0].confidence > 0.5  # boosted
        assert result[0].metadata.get("boosted") is True
        assert result[0].metadata.get("boost_source") == "instinct"
