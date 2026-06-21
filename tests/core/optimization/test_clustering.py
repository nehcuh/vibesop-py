"""Tests for skill clustering."""

from vibesop.core.optimization.clustering import SkillClusterIndex


class TestSkillClusterIndex:
    """Test SkillClusterIndex clustering logic."""

    def test_init(self):
        index = SkillClusterIndex()
        assert index._clusters == {}
        assert index._built is False

    def test_build_empty(self):
        index = SkillClusterIndex()
        result = index.build([])
        assert result == {}
        assert index._built is True

    def test_build_single_skill(self):
        index = SkillClusterIndex()
        skills = [{"id": "s1", "intent": "debug"}]
        result = index.build(skills)
        assert "default" in result
        assert result["default"] == ["s1"]

    def test_build_few_skills_by_intent(self):
        index = SkillClusterIndex()
        skills = [
            {"id": "s1", "intent": "debug"},
            {"id": "s2", "intent": "debug"},
            {"id": "s3", "intent": "plan"},
        ]
        result = index.build(skills)
        assert "debugging" in result
        assert "planning" in result
        assert "s1" in result["debugging"]
        assert "s2" in result["debugging"]
        assert "s3" in result["planning"]

    def test_normalize_intent(self):
        index = SkillClusterIndex()
        assert index._normalize_intent("debug") == "debugging"
        assert index._normalize_intent("plan") == "planning"
        assert index._normalize_intent("test") == "testing"
        assert index._normalize_intent("ship") == "shipping"
        assert index._normalize_intent("unknown") == "other"

    def test_get_relevant_clusters_before_build(self):
        index = SkillClusterIndex()
        assert index.get_relevant_clusters("query") == []

    def test_get_relevant_clusters_after_build(self):
        index = SkillClusterIndex()
        skills = [
            {"id": "s1", "intent": "debug", "description": "fix bugs"},
            {"id": "s2", "intent": "plan", "description": "make plans"},
        ]
        index.build(skills)
        clusters = index.get_relevant_clusters("debugging")
        assert len(clusters) > 0

    def test_get_cluster_members(self):
        index = SkillClusterIndex()
        skills = [
            {"id": "s1", "intent": "debug"},
            {"id": "s2", "intent": "debug"},
        ]
        index.build(skills)
        members = index.get_cluster_members("debugging")
        assert "s1" in members
        assert "s2" in members

    def test_get_cluster_members_unknown(self):
        index = SkillClusterIndex()
        assert index.get_cluster_members("unknown") == []

    def test_skill_to_cluster_mapping(self):
        index = SkillClusterIndex()
        skills = [
            {"id": "s1", "intent": "debug"},
            {"id": "s2", "intent": "debug"},
        ]
        index.build(skills)
        assert index._skill_to_cluster["s1"] == "debugging"
