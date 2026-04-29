"""Performance benchmarks for routing hot path."""

from __future__ import annotations

import time

import pytest

from vibesop.core.matching import RoutingContext
from vibesop.core.config.manager import RoutingConfig
from vibesop.core.routing import UnifiedRouter


class TestRoutingHotPath:
    """Benchmark routing performance for common scenarios."""

    @pytest.fixture(scope="class")
    def router(self, tmp_path_factory):
        tmp_path = tmp_path_factory.mktemp("bench")
        (tmp_path / ".vibe").mkdir(exist_ok=True)
        config = RoutingConfig(enable_ai_triage=False)
        return UnifiedRouter(project_root=tmp_path, config=config)

    def _measure(self, router, query: str, iterations: int = 20) -> dict:
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            router._route(query, context=RoutingContext())
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        times.sort()
        return {
            "p50": times[len(times) // 2],
            "p95": times[int(len(times) * 0.95)],
            "p99": times[int(len(times) * 0.99)],
            "min": times[0],
            "max": times[-1],
        }

    def test_simple_routing_p95_under_50ms(self, router):
        """Simple single-word queries should complete in <50ms P95."""
        stats = self._measure(router, "debug")
        assert stats["p50"] < 50, f"P50 {stats['p50']}ms exceeds 50ms"

    def test_medium_routing_p95_under_150ms(self, router):
        """Medium complexity queries should complete in <150ms P95."""
        stats = self._measure(router, "帮我调试数据库连接错误")
        assert stats["p95"] < 150, f"P95 {stats['p95']}ms exceeds 150ms"

    def test_complex_routing_tracks_latency(self, router):
        """Complex queries should complete and track latency."""
        stats = self._measure(router, "分析架构安全性然后优化代码性能")
        assert stats["max"] < 2000, f"Max {stats['max']}ms suspiciously high"

    def test_routing_is_consistent_across_runs(self, router):
        """Same query should produce consistent results."""
        result1 = router._route("debug error", context=RoutingContext())
        result2 = router._route("debug error", context=RoutingContext())
        if result1.primary and result2.primary:
            assert result1.primary.skill_id == result2.primary.skill_id
