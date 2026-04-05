import pytest
from vibesop.core.optimization.clustering import SkillClusterIndex


@pytest.fixture
def sample_skills():
    return [
        {
            "id": "systematic-debugging",
            "description": "Find root cause before attempting fixes.",
            "intent": "debugging",
        },
        {
            "id": "gstack/investigate",
            "description": "Systematic root-cause debugging.",
            "intent": "debugging",
        },
        {
            "id": "superpowers/debug",
            "description": "Advanced debugging workflows.",
            "intent": "debugging",
        },
        {
            "id": "planning-with-files",
            "description": "Use persistent files for planning.",
            "intent": "planning",
        },
        {
            "id": "omx/ralplan",
            "description": "Consensus planning with deliberation.",
            "intent": "planning",
        },
        {
            "id": "riper-workflow",
            "description": "5-phase development workflow.",
            "intent": "execution",
        },
        {"id": "omx/ralph", "description": "Persistent completion loop.", "intent": "execution"},
        {"id": "gstack/qa", "description": "Browser QA testing.", "intent": "testing"},
        {"id": "omx/ultraqa", "description": "Autonomous QA cycling.", "intent": "testing"},
        {"id": "gstack/ship", "description": "Release workflow.", "intent": "shipping"},
    ]


def test_build_clusters(sample_skills):
    index = SkillClusterIndex()
    clusters = index.build(sample_skills)
    assert len(clusters) > 0
    all_skills = set()
    for skill_ids in clusters.values():
        all_skills.update(skill_ids)
    assert len(all_skills) == len(sample_skills)


def test_get_cluster(sample_skills):
    index = SkillClusterIndex()
    index.build(sample_skills)
    cluster_debug = index.get_cluster("systematic-debugging")
    cluster_investigate = index.get_cluster("gstack/investigate")
    assert cluster_debug == cluster_investigate


def test_get_cluster_members(sample_skills):
    index = SkillClusterIndex()
    index.build(sample_skills)
    cluster_id = index.get_cluster("systematic-debugging")
    members = index.get_cluster_members(cluster_id)
    assert "systematic-debugging" in members


def test_resolve_conflicts_no_conflict(sample_skills):
    index = SkillClusterIndex()
    index.build(sample_skills)
    result = index.resolve_conflicts(query="debug this", matched_skills=["systematic-debugging"])
    assert result["primary"] == "systematic-debugging"
    assert result["alternatives"] == []


def test_resolve_conflicts_same_cluster(sample_skills):
    index = SkillClusterIndex()
    index.build(sample_skills)
    result = index.resolve_conflicts(
        query="debug this",
        matched_skills=["systematic-debugging", "gstack/investigate"],
        confidences={"systematic-debugging": 0.8, "gstack/investigate": 0.6},
    )
    assert result["primary"] == "systematic-debugging"
    assert "gstack/investigate" in result["alternatives"]


def test_resolve_conflicts_close_confidence(sample_skills):
    index = SkillClusterIndex()
    index.build(sample_skills)
    result = index.resolve_conflicts(
        query="debug this",
        matched_skills=["systematic-debugging", "gstack/investigate"],
        confidences={"systematic-debugging": 0.75, "gstack/investigate": 0.72},
        confidence_gap_threshold=0.1,
    )
    assert result["primary"] == "systematic-debugging"
    assert result.get("needs_review") is True


def test_empty_skills():
    index = SkillClusterIndex()
    clusters = index.build([])
    assert clusters == {}


def test_single_skill():
    index = SkillClusterIndex()
    clusters = index.build([{"id": "only-one", "description": "test", "intent": "test"}])
    assert len(clusters) >= 1
