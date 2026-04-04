"""Test preference learning system."""

import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from vibesop.core.preference import (
    PreferenceLearner,
    PreferenceScore,
    SkillSelection,
)


class TestSkillSelection:
    """Test SkillSelection dataclass."""

    def test_create_selection(self) -> None:
        """Test creating a skill selection."""
        selection = SkillSelection(
            skill_id="/review",
            query="review my code",
            timestamp=datetime.now(),
            was_helpful=True,
        )

        assert selection.skill_id == "/review"
        assert selection.was_helpful is True


class TestPreferenceLearner:
    """Test PreferenceLearner class."""

    def _create_learner(self) -> PreferenceLearner:
        """Helper to create a learner with temp storage."""
        tmpdir = Path(tempfile.mkdtemp())
        return PreferenceLearner(storage_path=tmpdir / "prefs.json")

    def test_init(self) -> None:
        """Test initialization."""
        learner = self._create_learner()

        assert learner._storage.selections == []
        assert learner.min_samples == 3

    def test_record_selection(self) -> None:
        """Test recording a selection."""
        learner = self._create_learner()

        learner.record_selection("/review", "review code", was_helpful=True)

        assert len(learner._storage.selections) == 1
        assert learner._storage.selections[0]["skill_id"] == "/review"

    def test_multiple_selections(self) -> None:
        """Test recording multiple selections."""
        learner = self._create_learner()

        learner.record_selection("/review", "review code")
        learner.record_selection("/debug", "debug error")
        learner.record_selection("/review", "review again")

        assert len(learner._storage.selections) == 3

    def test_get_preference_score_insufficient_data(self) -> None:
        """Test getting score with insufficient data."""
        learner = self._create_learner()

        learner.record_selection("/review", "review code")
        learner.record_selection("/review", "review again")

        # Only 2 selections, below min_samples of 3
        score = learner.get_preference_score("/review")

        # Should return neutral score when insufficient data
        assert score == 0.5

    def test_get_preference_score_with_data(self) -> None:
        """Test getting score with sufficient data."""
        learner = self._create_learner()

        learner.record_selection("/review", "review code", was_helpful=True)
        learner.record_selection("/review", "review code", was_helpful=True)
        learner.record_selection("/review", "review code", was_helpful=True)

        score = learner.get_preference_score("/review")

        # With helpful selections, score should be high
        assert score > 0.5

    def test_get_preference_score_unknown_skill(self) -> None:
        """Test getting score for unknown skill."""
        learner = self._create_learner()

        score = learner.get_preference_score("/unknown")

        assert score == 0.0

    def test_get_personalized_rankings(self) -> None:
        """Test personalized rankings."""
        learner = self._create_learner()

        # Record some preferences
        for _ in range(3):
            learner.record_selection("/review", "review code")

        rankings = learner.get_personalized_rankings(
            ["/review", "/debug", "/test"],
            query="review code",
        )

        assert len(rankings) == 3
        # Rankings should be tuples
        assert isinstance(rankings[0], tuple)
        # Should be sorted by score descending
        scores = [r[1] for r in rankings]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]

    def test_get_top_skills(self) -> None:
        """Test getting top skills."""
        learner = self._create_learner()

        # Record selections for different skills
        for _ in range(5):
            learner.record_selection("/review", "review")

        for _ in range(3):
            learner.record_selection("/debug", "debug")

        top = learner.get_top_skills(limit=5, min_selections=2)

        assert len(top) > 0
        # Should return PreferenceScore objects
        assert isinstance(top[0], PreferenceScore)

    def test_get_selection_history(self) -> None:
        """Test getting selection history."""
        learner = self._create_learner()

        learner.record_selection("/review", "query1")
        learner.record_selection("/debug", "query2")

        history = learner.get_selection_history(limit=10)

        assert len(history) == 2
        # History is returned in insertion order (oldest first)
        assert history[0].skill_id == "/review"
        assert history[1].skill_id == "/debug"

    def test_get_stats(self) -> None:
        """Test getting statistics."""
        learner = self._create_learner()

        learner.record_selection("/review", "review code", was_helpful=True)
        learner.record_selection("/debug", "debug error", was_helpful=False)
        learner.record_selection("/review", "review again", was_helpful=True)

        stats = learner.get_stats()

        assert stats["total_selections"] == 3
        assert stats["helpful_count"] == 2
        assert 0 < stats["helpful_rate"] < 1
        assert stats["unique_skills"] == 2

    def test_clear_old_data(self) -> None:
        """Test clearing old data."""
        learner = self._create_learner()

        # Record a selection
        learner.record_selection("/review", "old query")

        # Manually age the data
        old_timestamp = (datetime.now() - timedelta(days=100)).isoformat()
        learner._storage.selections[0]["timestamp"] = old_timestamp

        # Clear data older than 90 days
        removed = learner.clear_old_data(days=90)

        assert removed == 1
        assert len(learner._storage.selections) == 0

    def test_persistence(self) -> None:
        """Test saving and loading preferences."""
        tmpdir = Path(tempfile.mkdtemp())
        storage_path = tmpdir / "prefs.json"

        # Create learner and record data
        learner1 = PreferenceLearner(storage_path=storage_path)
        learner1.record_selection("/review", "test")
        learner1.record_selection("/debug", "test")

        # Create new learner with same path
        learner2 = PreferenceLearner(storage_path=storage_path)

        # Should load saved data
        assert len(learner2.get_selection_history()) == 2

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_extract_words(self) -> None:
        """Test word extraction."""
        learner = self._create_learner()

        words = learner._extract_words("Review code quality and debug")

        # Should extract meaningful words
        assert "review" in words
        assert "code" in words
        assert "quality" in words
        assert "debug" in words
        # Note: "and" is not filtered as it's long enough
        # Stop words filtering only applies to very common words

    def test_record_feedback(self) -> None:
        """Test recording explicit feedback."""
        learner = self._create_learner()

        # Record positive feedback
        learner.record_feedback("/review", "review my code", helpful=True)
        assert len(learner.get_selection_history()) == 1

        # Record negative feedback
        learner.record_feedback("/review", "review my code", helpful=False)
        assert len(learner.get_selection_history()) == 2

        # Check stats
        stats = learner.get_stats()
        assert stats["total_selections"] == 2
        assert stats["helpful_count"] == 1
