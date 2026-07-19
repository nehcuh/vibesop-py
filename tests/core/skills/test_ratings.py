"""Tests for skill ratings and review system."""

from pathlib import Path

import pytest

from vibesop.core.skills.ratings import SkillRating, SkillRatingStore


class TestSkillRating:
    """Test SkillRating dataclass."""

    def test_creation(self):
        rating = SkillRating(skill_id="test/skill", score=4, review="Good")
        assert rating.skill_id == "test/skill"
        assert rating.score == 4
        assert rating.review == "Good"
        assert rating.user_id == "local"
        assert rating.created_at

    def test_to_dict(self):
        rating = SkillRating(skill_id="s", score=5, review="Excellent", user_id="u1")
        d = rating.to_dict()
        assert d["skill_id"] == "s"
        assert d["score"] == 5
        assert d["review"] == "Excellent"
        assert d["user_id"] == "u1"
        assert "created_at" in d

    def test_from_dict(self):
        d = {
            "skill_id": "s",
            "score": 3,
            "review": "OK",
            "user_id": "u1",
            "created_at": "2024-01-01",
        }
        rating = SkillRating.from_dict(d)
        assert rating.skill_id == "s"
        assert rating.score == 3
        assert rating.review == "OK"

    def test_from_dict_defaults(self):
        d = {"skill_id": "s"}
        rating = SkillRating.from_dict(d)
        assert rating.score == 3
        assert rating.review == ""
        assert rating.user_id == "local"


class TestSkillRatingStore:
    """Test SkillRatingStore persistence and queries."""

    def test_init_creates_directory(self, tmp_path: Path):
        store_path = tmp_path / ".vibe" / "ratings.jsonl"
        SkillRatingStore(store_path=store_path)
        assert store_path.parent.exists()

    def test_rate_and_get(self, tmp_path: Path):
        store_path = tmp_path / "ratings.jsonl"
        store = SkillRatingStore(store_path=store_path)

        rating = store.rate("test/skill", 5, "Great skill")
        assert rating.score == 5
        assert rating.review == "Great skill"

        ratings = store.get_ratings("test/skill")
        assert len(ratings) == 1
        assert ratings[0].score == 5

    def test_invalid_score_raises(self, tmp_path: Path):
        store_path = tmp_path / "ratings.jsonl"
        store = SkillRatingStore(store_path=store_path)

        with pytest.raises(ValueError, match="Score must be 1-5"):
            store.rate("s", 0)
        with pytest.raises(ValueError, match="Score must be 1-5"):
            store.rate("s", 6)

    def test_get_ratings_missing_skill(self, tmp_path: Path):
        store_path = tmp_path / "ratings.jsonl"
        store = SkillRatingStore(store_path=store_path)
        assert store.get_ratings("missing") == []

    def test_get_avg_score(self, tmp_path: Path):
        store_path = tmp_path / "ratings.jsonl"
        store = SkillRatingStore(store_path=store_path)

        store.rate("s", 4)
        store.rate("s", 5)
        assert store.get_avg_score("s") == pytest.approx(4.5)

    def test_get_avg_score_no_ratings(self, tmp_path: Path):
        store_path = tmp_path / "ratings.jsonl"
        store = SkillRatingStore(store_path=store_path)
        assert store.get_avg_score("missing") is None

    def test_get_count(self, tmp_path: Path):
        store_path = tmp_path / "ratings.jsonl"
        store = SkillRatingStore(store_path=store_path)

        store.rate("s", 3)
        store.rate("s", 4)
        assert store.get_count("s") == 2
        assert store.get_count("missing") == 0

    def test_get_top_rated(self, tmp_path: Path):
        store_path = tmp_path / "ratings.jsonl"
        store = SkillRatingStore(store_path=store_path)

        store.rate("skill-a", 5)
        store.rate("skill-b", 3)
        store.rate("skill-c", 4)

        top = store.get_top_rated(limit=2)
        assert len(top) == 2
        assert top[0][0] == "skill-a"
        assert top[0][1] == pytest.approx(5.0)

    def test_get_top_rated_min_reviews(self, tmp_path: Path):
        store_path = tmp_path / "ratings.jsonl"
        store = SkillRatingStore(store_path=store_path)

        store.rate("skill-a", 5)
        store.rate("skill-a", 4)
        store.rate("skill-b", 5)

        top = store.get_top_rated(min_reviews=2)
        assert len(top) == 1
        assert top[0][0] == "skill-a"

    def test_persistence(self, tmp_path: Path):
        store_path = tmp_path / "ratings.jsonl"

        store1 = SkillRatingStore(store_path=store_path)
        store1.rate("s", 4, "Good")

        store2 = SkillRatingStore(store_path=store_path)
        ratings = store2.get_ratings("s")
        assert len(ratings) == 1
        assert ratings[0].score == 4
        assert ratings[0].review == "Good"

    def test_persistence_skips_corrupted_lines(self, tmp_path: Path):
        store_path = tmp_path / "ratings.jsonl"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text('not json\n{"skill_id": "s", "score": 5}\n', encoding="utf-8")

        store = SkillRatingStore(store_path=store_path)
        ratings = store.get_ratings("s")
        assert len(ratings) == 1
        assert ratings[0].score == 5
