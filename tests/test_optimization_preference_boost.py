import pytest
from vibesop.core.optimization.preference_boost import PreferenceBooster
from vibesop.core.matching import MatchResult, MatcherType


@pytest.fixture
def booster(tmp_path):
    return PreferenceBooster(storage_path=tmp_path / "preferences.json", weight=0.3, min_samples=1)


@pytest.fixture
def sample_matches():
    return [
        MatchResult(
            skill_id="systematic-debugging",
            confidence=0.7,
            matcher_type=MatcherType.KEYWORD,
            metadata={"namespace": "builtin"},
        ),
        MatchResult(
            skill_id="gstack/investigate",
            confidence=0.65,
            matcher_type=MatcherType.TFIDF,
            metadata={"namespace": "gstack"},
        ),
        MatchResult(
            skill_id="superpowers/debug",
            confidence=0.6,
            matcher_type=MatcherType.KEYWORD,
            metadata={"namespace": "superpowers"},
        ),
    ]


def test_no_preferences_returns_original(booster, sample_matches):
    boosted = booster.boost(sample_matches, "debug this")
    assert boosted[0].confidence == 0.7
    assert boosted[1].confidence == 0.65


def test_preference_boosts_matching_skill(booster, sample_matches):
    booster.record_selection("systematic-debugging", "debug this", helpful=True)
    booster.record_selection("systematic-debugging", "fix bug", helpful=True)
    boosted = booster.boost(sample_matches, "debug this")
    assert boosted[0].confidence > 0.7
    assert boosted[0].confidence > boosted[1].confidence


def test_unhelpful_feedback_reduces_boost(booster, sample_matches):
    booster.record_selection("systematic-debugging", "debug this", helpful=False)
    booster.record_selection("systematic-debugging", "fix bug", helpful=False)
    boosted = booster.boost(sample_matches, "debug this")
    assert boosted[0].confidence <= 0.72


def test_order_preserved_when_no_boost(booster):
    matches = [
        MatchResult(skill_id="a", confidence=0.8, matcher_type=MatcherType.KEYWORD),
        MatchResult(skill_id="b", confidence=0.6, matcher_type=MatcherType.KEYWORD),
    ]
    boosted = booster.boost(matches, "query")
    assert boosted[0].skill_id == "a"
    assert boosted[1].skill_id == "b"


def test_boost_respects_weight(booster, sample_matches):
    booster.record_selection("systematic-debugging", "debug", helpful=True)
    booster.record_selection("systematic-debugging", "debug", helpful=True)
    boosted = booster.boost(sample_matches, "debug")
    assert boosted[0].confidence <= 1.0
    assert boosted[0].confidence > 0.7


def test_disabled_booster(sample_matches):
    booster = PreferenceBooster(enabled=False)
    boosted = booster.boost(sample_matches, "query")
    for orig, b in zip(sample_matches, boosted):
        assert orig.confidence == b.confidence
