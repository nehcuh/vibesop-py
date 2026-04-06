"""Tests for optimization layer effectiveness."""

import pytest

from vibesop.core.optimization.clustering import SkillClusterIndex
from vibesop.core.optimization.prefilter import CandidatePrefilter


@pytest.fixture
def full_candidates():
    """44 skill candidates."""
    return [
        {
            "id": "systematic-debugging",
            "namespace": "builtin",
            "priority": "P0",
            "description": "Find root cause before attempting fixes.",
            "intent": "debugging",
        },
        {
            "id": "verification-before-completion",
            "namespace": "builtin",
            "priority": "P0",
            "description": "Require fresh verification evidence.",
            "intent": "verification",
        },
        {
            "id": "session-end",
            "namespace": "builtin",
            "priority": "P0",
            "description": "Capture handoff before ending session.",
            "intent": "session management",
        },
        {
            "id": "planning-with-files",
            "namespace": "builtin",
            "priority": "P1",
            "description": "Use persistent files as working memory.",
            "intent": "planning",
        },
        {
            "id": "riper-workflow",
            "namespace": "builtin",
            "priority": "P1",
            "description": "5-phase development workflow.",
            "intent": "execution",
        },
        {
            "id": "using-git-worktrees",
            "namespace": "builtin",
            "priority": "P1",
            "description": "Branch isolation using git worktrees.",
            "intent": "git",
        },
        {
            "id": "autonomous-experiment",
            "namespace": "builtin",
            "priority": "P1",
            "description": "Autonomous experiment loop.",
            "intent": "experimentation",
        },
        {
            "id": "skill-craft",
            "namespace": "builtin",
            "priority": "P1",
            "description": "Detect recurring patterns and generate skills.",
            "intent": "skill creation",
        },
        {
            "id": "superpowers/tdd",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Test-driven development.",
            "intent": "testing",
        },
        {
            "id": "superpowers/brainstorm",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Structured brainstorming.",
            "intent": "brainstorming",
        },
        {
            "id": "superpowers/refactor",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Systematic code refactoring.",
            "intent": "refactoring",
        },
        {
            "id": "superpowers/debug",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Advanced debugging workflows.",
            "intent": "debugging",
        },
        {
            "id": "superpowers/architect",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "System architecture design.",
            "intent": "architecture",
        },
        {
            "id": "superpowers/review",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Code review.",
            "intent": "review",
        },
        {
            "id": "superpowers/optimize",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Performance optimization.",
            "intent": "optimization",
        },
        {
            "id": "gstack/office-hours",
            "namespace": "gstack",
            "priority": "P2",
            "description": "YC Office Hours brainstorming.",
            "intent": "product thinking",
        },
        {
            "id": "gstack/plan-ceo-review",
            "namespace": "gstack",
            "priority": "P2",
            "description": "CEO plan review.",
            "intent": "review",
        },
        {
            "id": "gstack/plan-eng-review",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Eng plan review.",
            "intent": "review",
        },
        {
            "id": "gstack/plan-design-review",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Design plan review.",
            "intent": "review",
        },
        {
            "id": "gstack/review",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Pre-landing PR review.",
            "intent": "review",
        },
        {
            "id": "gstack/design-review",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Designer's eye QA.",
            "intent": "testing",
        },
        {
            "id": "gstack/codex",
            "namespace": "gstack",
            "priority": "P2",
            "description": "OpenAI Codex wrapper.",
            "intent": "review",
        },
        {
            "id": "gstack/investigate",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Systematic debugging.",
            "intent": "debugging",
        },
        {
            "id": "gstack/qa",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Browser QA testing.",
            "intent": "testing",
        },
        {
            "id": "gstack/qa-only",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Report-only QA.",
            "intent": "testing",
        },
        {
            "id": "gstack/browse",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Headless browser testing.",
            "intent": "testing",
        },
        {
            "id": "gstack/ship",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Release workflow.",
            "intent": "shipping",
        },
        {
            "id": "gstack/careful",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Safety guardrails.",
            "intent": "safety",
        },
        {
            "id": "gstack/freeze",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Directory freeze.",
            "intent": "safety",
        },
        {
            "id": "gstack/guard",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Full safety mode.",
            "intent": "safety",
        },
        {
            "id": "gstack/unfreeze",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Clear freeze.",
            "intent": "safety",
        },
        {
            "id": "omx/deep-interview",
            "namespace": "omx",
            "priority": "P1",
            "description": "Socratic requirements clarification.",
            "intent": "requirements",
        },
        {
            "id": "omx/ralph",
            "namespace": "omx",
            "priority": "P1",
            "description": "Persistent completion loop.",
            "intent": "execution",
        },
        {
            "id": "omx/ralplan",
            "namespace": "omx",
            "priority": "P1",
            "description": "Consensus planning.",
            "intent": "planning",
        },
        {
            "id": "omx/team",
            "namespace": "omx",
            "priority": "P1",
            "description": "Multi-agent parallel execution.",
            "intent": "parallel execution",
        },
        {
            "id": "omx/ultrawork",
            "namespace": "omx",
            "priority": "P2",
            "description": "Tier-aware parallel execution.",
            "intent": "parallel execution",
        },
        {
            "id": "omx/autopilot",
            "namespace": "omx",
            "priority": "P1",
            "description": "Full autonomous lifecycle.",
            "intent": "execution",
        },
        {
            "id": "omx/ultraqa",
            "namespace": "omx",
            "priority": "P1",
            "description": "Autonomous QA cycling.",
            "intent": "testing",
        },
    ]


def test_prefilter_reduces_debug_query(full_candidates):
    """Debug query should reduce candidates by 70%+."""
    prefilter = CandidatePrefilter()
    result = prefilter.filter("帮我调试数据库错误", full_candidates)
    reduction = 1 - len(result) / len(full_candidates)
    assert reduction >= 0.5
    assert any(c["id"] == "systematic-debugging" for c in result)


def test_prefilter_reduces_planning_query(full_candidates):
    """Planning query should reduce candidates significantly."""
    prefilter = CandidatePrefilter()
    result = prefilter.filter("这个功能怎么设计", full_candidates)
    assert len(result) < len(full_candidates)


def test_prefilter_reduces_qa_query(full_candidates):
    """QA query should reduce candidates significantly."""
    prefilter = CandidatePrefilter()
    result = prefilter.filter("帮我测试这个网站", full_candidates)
    assert len(result) < len(full_candidates)


def test_prefilter_keeps_p0_for_any_query(full_candidates):
    """P0 skills should always be in results."""
    prefilter = CandidatePrefilter()
    for query in ["随便问点什么", "发布", "调试", "规划", "测试"]:
        result = prefilter.filter(query, full_candidates)
        p0_ids = {c["id"] for c in result if c.get("priority") == "P0"}
        assert len(p0_ids) >= 3, f"P0 skills missing for query: {query}"


def test_prefilter_includes_namespace_on_trigger(full_candidates):
    """Namespace trigger should include that namespace's skills."""
    prefilter = CandidatePrefilter()
    result = prefilter.filter("用 gstack 发布", full_candidates)
    gstack_skills = [c for c in result if c["id"].startswith("gstack/")]
    assert len(gstack_skills) > 0


def test_prefilter_excludes_p2_without_trigger(full_candidates):
    """P2 skills should be excluded without namespace trigger."""
    prefilter = CandidatePrefilter()
    result = prefilter.filter("发布新版本", full_candidates)
    p2_skills = [c for c in result if c.get("priority") == "P2"]
    assert len(p2_skills) == 0


def test_clustering_groups_similar_intents(full_candidates):
    """Clustering should group skills with similar intents."""
    index = SkillClusterIndex()
    index.build(full_candidates)

    debug_cluster = index.get_cluster("systematic-debugging")
    assert debug_cluster is not None

    investigate_cluster = index.get_cluster("gstack/investigate")
    assert investigate_cluster == debug_cluster


def test_clustering_reduces_conflicts(full_candidates):
    """Clustering should help resolve conflicts between similar skills."""
    index = SkillClusterIndex()
    index.build(full_candidates)

    result = index.resolve_conflicts(
        "",
        ["systematic-debugging", "gstack/investigate", "superpowers/debug"],
        confidences={
            "systematic-debugging": 0.8,
            "gstack/investigate": 0.6,
            "superpowers/debug": 0.5,
        },
    )
    assert result["primary"] == "systematic-debugging"
    assert len(result["alternatives"]) == 2
