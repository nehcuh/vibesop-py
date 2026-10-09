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

import pytest

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


# NOTE: sentence_transformers is stubbed to None suite-wide by the autouse
# ``_no_real_embedding_model`` fixture in tests/conftest.py (embedding paths
# fail open to lexical scoring), so these tests never download the 458MB
# paraphrase-multilingual-MiniLM-L12-v2 model into the per-test isolated HOME.
# The lexical scorer deterministically scores the identical query/pattern at
# 1.0, which is all the assertions below need.


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


class TestRewardSignalFix:
    """Phase 2 fix: record_outcome_for_query + record_feedback_outcome close the loop.

    These exercise the NEW wiring. They would fail on pre-fix code (the methods
    did not exist) and pass once the reward signal is connected.
    """

    def test_record_outcome_for_query_matures_instinct(self, tmp_path: Path) -> None:
        learner = _real_learner(tmp_path)
        learner.learn(pattern=QUERY, action=ACTION, source="auto_routing")
        iid = next(iter(learner.instincts))

        for _ in range(3):
            learner.record_outcome_for_query(QUERY, success=True)

        matured = learner.instincts[iid]
        assert matured.total_applications == 3
        assert matured.is_reliable is True

    def test_record_outcome_for_query_negative_suppresses(self, tmp_path: Path) -> None:
        """A 'no' is a real negative outcome (failure_count++), not neutral."""
        learner = _real_learner(tmp_path)
        learner.learn(pattern=QUERY, action=ACTION, source="auto_routing")
        iid = next(iter(learner.instincts))

        for _ in range(3):
            learner.record_outcome_for_query(QUERY, success=False)

        suppressed = learner.instincts[iid]
        assert suppressed.failure_count == 3
        assert suppressed.is_reliable is False  # suppressed, not neutral
        assert suppressed.confidence < 0.5

    def test_record_outcome_for_query_noop_when_no_instinct(self, tmp_path: Path) -> None:
        learner = _real_learner(tmp_path)
        # Query was never auto-recorded -> no-op, no crash.
        learner.record_outcome_for_query("never recorded query", success=True)
        assert learner.instincts == {}

    def test_record_feedback_outcome_closes_loop(self, tmp_path: Path) -> None:
        """Router.record_feedback_outcome wires explicit feedback -> maturation."""
        from vibesop.core.routing.context_mixin import RouterContextMixin

        class _StubHost(RouterContextMixin):
            """Minimal host exposing only what record_feedback_outcome touches."""

            def __init__(self, project_root: Path) -> None:
                self.project_root = project_root
                self._instinct_learner = None

        host = _StubHost(tmp_path)
        learner = host._get_instinct_learner()
        learner.learn(pattern=QUERY, action=ACTION, source="auto_routing")
        iid = next(iter(learner.instincts))

        # Three explicit "yes" feedbacks via the router-level entry point.
        for _ in range(3):
            host.record_feedback_outcome(QUERY, success=True)

        assert learner.instincts[iid].is_reliable is True


class TestActionChangeDropsInheritedEvidence:
    """D13 at the routing consumer: one success on a new action must not boost.

    ``apply_instinct_boost`` only sees instincts ``find_matching`` accepts
    (``is_reliable`` and confidence >= 0.6). The new action still names the
    same skill, so a row that kept the old three successes plus one new
    success would boost. Reset evidence must not.
    """

    def test_new_action_one_success_does_not_boost(self, tmp_path: Path) -> None:
        learner = _real_learner(tmp_path)
        learner.learn(pattern=QUERY, action=ACTION, source="auto_routing")
        iid = next(iter(learner.instincts))
        for _ in range(3):
            learner.record_outcome(iid, success=True)
        assert learner.instincts[iid].is_reliable is True

        svc = _make_service(learner)
        before = svc.apply_instinct_boost([_match(SKILL, 0.5)], QUERY, context=None)
        assert before[0].metadata.get("boosted") is True

        new_action = f"avoid {SKILL} skill"
        changed = learner.learn(pattern=QUERY, action=new_action, source="auto_routing")
        assert changed.id == iid
        assert changed.action == new_action
        assert changed.success_count == 0
        assert changed.failure_count == 0
        assert changed.confidence == pytest.approx(0.5)
        assert changed.is_reliable is False

        learner.record_outcome(iid, success=True)
        once = learner.instincts[iid]
        assert once.success_count == 1
        assert once.total_applications == 1
        assert once.is_reliable is False

        after = svc.apply_instinct_boost([_match(SKILL, 0.5)], QUERY, context=None)
        assert after[0].confidence == 0.5
        assert after[0].metadata.get("boosted") is not True
        assert after[0].metadata.get("boost_source") != "instinct"


_OTHER_SKILL = "builtin/code-review"
_OTHER_ACTION = f"suggest {_OTHER_SKILL} skill"


class TestOldActionFeedbackDoesNotCrossActions:
    """Feedback on a loaded action A must not become evidence for action B."""

    def test_old_accept_after_peer_switches_action_does_not_boost(self, tmp_path: Path) -> None:
        storage = tmp_path / "instincts.jsonl"
        seeder = InstinctLearner(storage_path=storage)
        seeder.learn(pattern=QUERY, action=ACTION, source="auto_routing")
        for _ in range(3):
            seeder.record_outcome_for_query(QUERY, success=True)

        holder = InstinctLearner(storage_path=storage)
        changer = InstinctLearner(storage_path=storage)
        changer.learn(pattern=QUERY, action=_OTHER_ACTION, source="auto_routing")
        assert holder.get_instinct_for_query(QUERY) is not None
        assert holder.get_instinct_for_query(QUERY).action == ACTION  # type: ignore[union-attr]

        holder.record_outcome_for_query(QUERY, success=True)

        reader = InstinctLearner(storage_path=storage)
        row = reader.get_instinct_for_query(QUERY)
        assert row is not None
        assert row.action == _OTHER_ACTION
        assert row.success_count == 0
        assert row.failure_count == 0
        assert row.is_reliable is False

        svc = _make_service(reader)
        boosted = svc.apply_instinct_boost(
            [_match(SKILL, 0.5), _match(_OTHER_SKILL, 0.5)], QUERY, None
        )
        assert boosted[0].metadata.get("boosted") is not True
        assert boosted[1].metadata.get("boosted") is not True
