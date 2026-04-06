import pytest

from vibesop.core.optimization.prefilter import CandidatePrefilter


@pytest.fixture
def candidates():
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
            "id": "gstack/office-hours",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Product brainstorming with forcing questions.",
            "intent": "product thinking",
        },
        {
            "id": "gstack/qa",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Browser QA testing.",
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
            "id": "omx/deep-interview",
            "namespace": "omx",
            "priority": "P1",
            "description": "Socratic requirements clarification with ambiguity scoring.",
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
            "description": "Consensus planning with structured deliberation.",
            "intent": "planning",
        },
        {
            "id": "omx/team",
            "namespace": "omx",
            "priority": "P1",
            "description": "Multi-agent parallel execution.",
            "intent": "parallel execution",
        },
    ]


@pytest.fixture
def prefilter(candidates):
    class MockClusterIndex:
        def get_relevant_clusters(self, query):
            return ["debugging"] if "debug" in query.lower() else []

        def get_cluster_members(self, cluster_id):
            return ["systematic-debugging"] if cluster_id == "debugging" else []

    return CandidatePrefilter(cluster_index=MockClusterIndex())


def test_p0_always_included(prefilter, candidates):
    result = prefilter.filter("随便问点什么", candidates)
    ids = [c["id"] for c in result]
    assert "systematic-debugging" in ids
    assert "verification-before-completion" in ids
    assert "session-end" in ids


def test_debug_query_filters_to_debug_skills(prefilter, candidates):
    result = prefilter.filter("帮我调试数据库错误", candidates)
    ids = [c["id"] for c in result]
    assert "systematic-debugging" in ids


def test_p2_excluded_without_namespace_trigger(prefilter, candidates):
    result = prefilter.filter("发布新版本", candidates)
    p2_skills = [c for c in result if c.get("priority") == "P2"]
    assert len(p2_skills) == 0


def test_p2_included_with_namespace_keyword(prefilter, candidates):
    result = prefilter.filter("用 gstack 发布", candidates)
    gstack_skills = [c for c in result if c["id"].startswith("gstack/")]
    assert len(gstack_skills) > 0


def test_candidate_reduction(prefilter, candidates):
    result = prefilter.filter("帮我调试数据库错误", candidates)
    assert len(result) < len(candidates)
    assert len(result) <= 10


def test_empty_candidates(prefilter):
    result = prefilter.filter("test", [])
    assert result == []
