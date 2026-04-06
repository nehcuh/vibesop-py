"""Performance benchmarks for routing with optimization."""

import time

import pytest

from vibesop.core.optimization.clustering import SkillClusterIndex
from vibesop.core.optimization.prefilter import CandidatePrefilter


@pytest.fixture
def large_candidate_set():
    """100 skill candidates for performance testing."""
    candidates = []
    for i in range(100):
        ns = ["builtin", "superpowers", "gstack", "omx"][i % 4]
        priority = ["P0", "P1", "P2"][i % 3]
        candidates.append(
            {
                "id": f"{ns}/skill-{i}",
                "namespace": ns,
                "priority": priority,
                "description": f"Skill {i} for testing performance.",
                "intent": ["debugging", "planning", "testing", "execution"][i % 4],
            }
        )
    return candidates


def test_prefilter_performance(large_candidate_set):
    """Prefilter should complete in < 5ms for 100 candidates."""
    prefilter = CandidatePrefilter()

    times = []
    for _ in range(100):
        start = time.perf_counter()
        prefilter.filter("帮我调试数据库错误", large_candidate_set)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

    p95 = sorted(times)[95]

    assert p95 < 5.0, f"P95 prefilter time {p95:.2f}ms exceeds 5ms limit"


def test_clustering_build_performance(large_candidate_set):
    """Clustering build should complete in < 50ms for 100 skills."""
    index = SkillClusterIndex()

    start = time.perf_counter()
    index.build(large_candidate_set)
    elapsed = (time.perf_counter() - start) * 1000

    assert elapsed < 50.0, f"Clustering build time {elapsed:.2f}ms exceeds 50ms limit"


def test_clustering_query_performance(large_candidate_set):
    """Clustering query should complete in < 2ms."""
    index = SkillClusterIndex()
    index.build(large_candidate_set)

    times = []
    for _ in range(100):
        start = time.perf_counter()
        index.get_cluster("builtin/skill-0")
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

    p95 = sorted(times)[95]
    assert p95 < 2.0, f"P95 cluster query time {p95:.2f}ms exceeds 2ms limit"


def test_conflict_resolution_performance(large_candidate_set):
    """Conflict resolution should complete in < 2ms."""
    index = SkillClusterIndex()
    index.build(large_candidate_set)

    matched = [f"builtin/skill-{i}" for i in range(10)]
    confidences = {f"builtin/skill-{i}": 0.9 - i * 0.05 for i in range(10)}

    times = []
    for _ in range(100):
        start = time.perf_counter()
        index.resolve_conflicts("query", matched, confidences)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

    p95 = sorted(times)[95]
    assert p95 < 2.0, f"P95 conflict resolution time {p95:.2f}ms exceeds 2ms limit"
