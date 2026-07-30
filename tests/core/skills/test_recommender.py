"""Tests for skill recommender."""

from pathlib import Path
from unittest.mock import patch

import pytest

from vibesop.core.skills.recommender import SkillRecommendation, SkillRecommender


class TestSkillRecommendation:
    """Test SkillRecommendation dataclass."""

    def test_creation(self):
        rec = SkillRecommendation(skill_id="test/skill", reason="Good")
        assert rec.skill_id == "test/skill"
        assert rec.reason == "Good"
        assert rec.confidence == pytest.approx(0.5)
        assert rec.installed is False
        assert rec.score is None

    def test_to_dict(self):
        rec = SkillRecommendation(
            skill_id="s", reason="R", confidence=0.9, installed=True, score=4.5
        )
        d = rec.to_dict()
        assert d["skill_id"] == "s"
        assert d["confidence"] == pytest.approx(0.9)
        assert d["installed"] is True
        assert d["score"] == pytest.approx(4.5)


class TestSkillRecommenderSimpleDetect:
    """Test _simple_detect language detection."""

    def test_detects_python(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
        recommender = SkillRecommender(project_root=tmp_path)
        result = recommender._simple_detect()
        assert result["primary_language"] == "python"

    def test_detects_javascript(self, tmp_path: Path):
        (tmp_path / "app.js").write_text("console.log('hi')", encoding="utf-8")
        recommender = SkillRecommender(project_root=tmp_path)
        result = recommender._simple_detect()
        assert result["primary_language"] == "javascript"

    def test_detects_typescript(self, tmp_path: Path):
        (tmp_path / "app.ts").write_text("let x: number", encoding="utf-8")
        recommender = SkillRecommender(project_root=tmp_path)
        result = recommender._simple_detect()
        assert result["primary_language"] == "typescript"

    def test_default_when_empty(self, tmp_path: Path):
        recommender = SkillRecommender(project_root=tmp_path)
        result = recommender._simple_detect()
        assert result["primary_language"] == "default"

    def test_most_common_wins(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("a", encoding="utf-8")
        (tmp_path / "b.py").write_text("b", encoding="utf-8")
        (tmp_path / "c.js").write_text("c", encoding="utf-8")
        recommender = SkillRecommender(project_root=tmp_path)
        result = recommender._simple_detect()
        assert result["primary_language"] == "python"


class TestSkillRecommenderRecommendations:
    """Test recommendation methods."""

    def test_recommend_collaborative_gstack_only(self, tmp_path: Path):
        """gstack-only installs no longer trigger recommendations (not a default pack)."""
        recommender = SkillRecommender(project_root=tmp_path)
        with patch.object(recommender, "_get_installed_packs", return_value={"gstack"}):
            recs = recommender.recommend_collaborative()
        assert recs == []

    def test_recommend_collaborative_superpowers_only(self, tmp_path: Path):
        recommender = SkillRecommender(project_root=tmp_path)
        with patch.object(recommender, "_get_installed_packs", return_value={"superpowers"}):
            recs = recommender.recommend_collaborative()
        skill_ids = [r.skill_id for r in recs]
        assert "mattpocock/diagnosing-bugs" in skill_ids
        assert "mattpocock/tdd" in skill_ids

    def test_recommend_collaborative_both(self, tmp_path: Path):
        recommender = SkillRecommender(project_root=tmp_path)
        with patch.object(
            recommender, "_get_installed_packs", return_value={"superpowers", "mattpocock"}
        ):
            recs = recommender.recommend_collaborative()
        assert recs == []

    def test_detect_missing_skills(self, tmp_path: Path):
        recommender = SkillRecommender(project_root=tmp_path)
        with patch.object(recommender, "_get_installed_skill_ids", return_value=set()):
            recs = recommender.detect_missing_skills()
        skill_ids = [r.skill_id for r in recs]
        assert "superpowers/systematic-debugging" in skill_ids
        assert "mattpocock/diagnosing-bugs" in skill_ids
        assert "mattpocock/tdd" in skill_ids

    def test_detect_missing_skills_none_missing(self, tmp_path: Path):
        recommender = SkillRecommender(project_root=tmp_path)
        with patch.object(
            recommender,
            "_get_installed_skill_ids",
            return_value={
                "superpowers/systematic-debugging",
                "mattpocock/diagnosing-bugs",
                "mattpocock/tdd",
            },
        ):
            recs = recommender.detect_missing_skills()
        assert recs == []

    def test_recommend_for_project_python(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("pass", encoding="utf-8")
        recommender = SkillRecommender(project_root=tmp_path)
        with patch.object(recommender, "_get_installed_skill_ids", return_value=set()):
            with patch.object(recommender, "_get_analytics_recommendations", return_value=None):
                recs = recommender.recommend_for_project()

        assert len(recs) > 0
        skill_ids = [r.skill_id for r in recs]
        assert "superpowers/test-driven-development" in skill_ids

    def test_recommend_for_project_default(self, tmp_path: Path):
        recommender = SkillRecommender(project_root=tmp_path)
        with patch.object(recommender, "_get_installed_skill_ids", return_value=set()):
            with patch.object(recommender, "_get_analytics_recommendations", return_value=None):
                recs = recommender.recommend_for_project()

        skill_ids = [r.skill_id for r in recs]
        assert "mattpocock/diagnosing-bugs" in skill_ids

    def test_recommend_for_project_with_analytics(self, tmp_path: Path):
        recommender = SkillRecommender(project_root=tmp_path)
        mock_rec = SkillRecommendation(skill_id="analytics/skill", reason="Popular")
        with patch.object(recommender, "_get_analytics_recommendations", return_value=[mock_rec]):
            recs = recommender.recommend_for_project()

        assert len(recs) == 1
        assert recs[0].skill_id == "analytics/skill"
