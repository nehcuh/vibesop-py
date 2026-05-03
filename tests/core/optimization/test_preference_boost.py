"""Tests for preference boost logic."""

from unittest.mock import MagicMock

import pytest

from vibesop.core.matching.base import MatchResult, MatcherType
from vibesop.core.optimization.preference_boost import PreferenceBooster


class TestPreferenceBoosterInit:
    """Test PreferenceBooster initialization."""

    def test_defaults(self):
        booster = PreferenceBooster()
        assert booster.enabled is True
        assert booster.weight == pytest.approx(0.35)
        assert booster.min_samples == 2

    def test_disabled(self):
        booster = PreferenceBooster(enabled=False)
        assert booster.enabled is False

    def test_weight_clamping(self):
        booster = PreferenceBooster(weight=-0.5)
        assert booster.weight == pytest.approx(0.0)
        booster2 = PreferenceBooster(weight=1.5)
        assert booster2.weight == pytest.approx(1.0)


class TestPreferenceBoosterBoost:
    """Test boost application."""

    def _make_match(self, skill_id: str, confidence: float) -> MatchResult:
        return MatchResult(
            skill_id=skill_id,
            confidence=confidence,
            matcher_type=MatcherType.KEYWORD,
        )

    def test_boost_disabled_returns_copy(self):
        booster = PreferenceBooster(enabled=False)
        matches = [self._make_match("s1", 0.8)]
        result = booster.boost(matches)
        assert len(result) == 1
        assert result[0].skill_id == "s1"

    def test_boost_empty_list(self):
        booster = PreferenceBooster()
        assert booster.boost([]) == []

    def test_boost_no_preferences(self):
        booster = PreferenceBooster()
        matches = [self._make_match("s1", 0.8), self._make_match("s2", 0.6)]

        mock_learner = MagicMock()
        mock_learner.get_personalized_rankings.return_value = [("s1", 0.0), ("s2", 0.0)]
        booster._learner = mock_learner

        result = booster.boost(matches)
        assert len(result) == 2
        assert result[0].confidence == pytest.approx(0.8)
        assert result[1].confidence == pytest.approx(0.6)

    def test_boost_with_positive_preference(self):
        booster = PreferenceBooster(weight=0.5)
        matches = [self._make_match("s1", 0.8)]

        mock_learner = MagicMock()
        mock_learner.get_personalized_rankings.return_value = [("s1", 1.0)]
        booster._learner = mock_learner

        result = booster.boost(matches)
        # blended = 0.8 * 0.5 + 1.0 * 0.5 = 0.9
        assert result[0].confidence == pytest.approx(0.9)
        assert result[0].score_breakdown["preference_boost"] == pytest.approx(0.5)
        assert result[0].metadata["preference_applied"] is True

    def test_boost_with_negative_preference(self):
        booster = PreferenceBooster(weight=0.5)
        matches = [self._make_match("s1", 0.8)]

        mock_learner = MagicMock()
        mock_learner.get_personalized_rankings.return_value = [("s1", -0.2)]
        booster._learner = mock_learner

        result = booster.boost(matches)
        # max(0, 0.8 + (-0.2) * 0.5) = 0.7
        assert result[0].confidence == pytest.approx(0.7)

    def test_boost_reorders_results(self):
        booster = PreferenceBooster(weight=0.5)
        matches = [
            self._make_match("s1", 0.6),
            self._make_match("s2", 0.8),
        ]

        mock_learner = MagicMock()
        mock_learner.get_personalized_rankings.return_value = [("s1", 1.0), ("s2", 0.0)]
        booster._learner = mock_learner

        result = booster.boost(matches)
        # s1 boosted to 0.8, s2 stays at 0.8
        # After sort, order may change or be stable
        assert result[0].skill_id == "s1"

    def test_boost_learner_exception(self):
        booster = PreferenceBooster()
        matches = [self._make_match("s1", 0.8)]

        # Make get_learner itself raise, not the learner method
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(booster, "get_learner", lambda: (_ for _ in ()).throw(Exception("boom")))
            result = booster.boost(matches)
        assert len(result) == 1
        assert result[0].confidence == pytest.approx(0.8)


class TestBlendConfidence:
    """Test _blend_confidence method."""

    def test_zero_pref_score(self):
        booster = PreferenceBooster(weight=0.5)
        assert booster._blend_confidence(0.8, 0.0) == pytest.approx(0.8)

    def test_positive_pref_score(self):
        booster = PreferenceBooster(weight=0.5)
        # 0.8 * 0.5 + 1.0 * 0.5 = 0.9
        assert booster._blend_confidence(0.8, 1.0) == pytest.approx(0.9)

    def test_negative_pref_score(self):
        booster = PreferenceBooster(weight=0.5)
        # max(0, 0.8 + (-0.2) * 0.5) = 0.7
        assert booster._blend_confidence(0.8, -0.2) == pytest.approx(0.7)

    def test_clamps_to_1(self):
        booster = PreferenceBooster(weight=0.5)
        assert booster._blend_confidence(0.9, 2.0) == pytest.approx(1.0)

    def test_clamps_to_0(self):
        booster = PreferenceBooster(weight=0.5)
        assert booster._blend_confidence(0.1, -1.0) == pytest.approx(0.0)


class TestRecordSelection:
    """Test preference recording."""

    def test_record_selection_when_enabled(self):
        booster = PreferenceBooster(enabled=True)
        mock_learner = MagicMock()
        booster._learner = mock_learner

        booster.record_selection("s1", "query", helpful=True)
        mock_learner.record_selection.assert_called_once_with("s1", "query", was_helpful=True)

    def test_record_selection_when_disabled(self):
        booster = PreferenceBooster(enabled=False)
        mock_learner = MagicMock()
        booster._learner = mock_learner

        booster.record_selection("s1", "query")
        mock_learner.record_selection.assert_not_called()

    def test_record_selection_exception_ignored(self):
        booster = PreferenceBooster(enabled=True)
        mock_learner = MagicMock()
        mock_learner.record_selection.side_effect = Exception("boom")
        booster._learner = mock_learner

        # Should not raise
        booster.record_selection("s1", "query")
