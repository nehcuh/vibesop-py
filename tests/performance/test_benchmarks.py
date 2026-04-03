"""Performance benchmark tests.

These tests establish performance baselines and detect regressions.
"""

import time
from pathlib import Path
from typing import Dict, List

import pytest

from vibesop.core.routing.engine import SkillRouter
from vibesop.core.models import RoutingRequest


class RoutingBenchmarks:
    """Benchmark tests for routing performance."""

    @pytest.mark.benchmark
    def test_baseline_routing_latency(self, benchmark) -> None:
        """Establish baseline for routing latency.

        Benchmark:
            - Median latency should be < 50ms
            - 99th percentile should be < 200ms
        """
        router = SkillRouter()

        def route_request() -> None:
            router.route(RoutingRequest(query="test query"))

        # Benchmark multiple iterations
        result = benchmark.pedantic(
            route_request,
            iterations=100,
            rounds=3,
            warmup_rounds=1
        )

        # Assert reasonable performance
        assert result.median < 0.05, f"Baseline median {result.median:.3f}s too high"
        assert result.min < 0.01, f"Baseline min {result.min:.3f}s too high"

    @pytest.mark.benchmark
    def test_baseline_cache_performance(self, benchmark) -> None:
        """Establish baseline for cache performance.

        Benchmark:
            - Cache hit should be < 1ms
            - Cache miss should be < 50ms
        """
        from vibesop.core.routing.cache import CacheManager

        cache = CacheManager()

        # Benchmark cache hit
        def cache_hit() -> None:
            cache.get("test_key")

        hit_result = benchmark(cache_hit, iterations=1000)
        assert hit_result.median < 0.001, "Cache hit too slow"

        # Benchmark cache miss
        def cache_miss() -> None:
            cache.set("test_key", {"data": "test"})

        miss_result = benchmark(cache_miss, iterations=100)
        assert miss_result.median < 0.05, "Cache miss too slow"


class PerformanceBaselines:
    """Establish and track performance baselines."""

    BASELINE_FILE = Path(__file__).parent / "benchmarks" / "baseline.json"

    @staticmethod
    def get_baseline_metrics() -> Dict[str, float]:
        """Get baseline performance metrics.

        Returns:
            Dictionary of baseline metrics
        """
        # These are example baseline values
        # In production, these would be loaded from file
        return {
            "routing_p50_latency_ms": 50.0,
            "routing_p99_latency_ms": 200.0,
            "cache_hit_latency_ms": 1.0,
            "cache_miss_latency_ms": 50.0,
            "config_render_ms": 100.0,
        }

    def test_current_performance_vs_baseline(self) -> None:
        """Compare current performance against baseline.

        Fails if performance regresses more than 20% from baseline.
        """
        baseline = self.get_baseline_metrics()
        router = SkillRouter()

        # Measure current performance
        requests = [
            RoutingRequest(query=f"test query {i}")
            for i in range(100)
        ]

        start = time.perf_counter()
        for req in requests:
            router.route(req)
        end = time.perf_counter()

        total_time = end - start
        avg_latency_ms = (total_time / len(requests)) * 1000

        # Compare with baseline (allow 20% regression)
        baseline_p50 = baseline["routing_p50_latency_ms"]
        max_acceptable = baseline_p50 * 1.2

        assert avg_latency_ms < max_acceptable, (
            f"Performance regression: {avg_latency_ms:.1f}ms "
            f"vs baseline {baseline_p50:.1f}ms"
        )


@pytest.mark.benchmark
class BenchmarkComparison:
    """Compare different implementations."""

    def test_layer_0_vs_layer_3_performance(self) -> None:
        """Compare AI triage vs semantic matching performance.

        This test helps decide which routing layer to prioritize.
        """
        router = SkillRouter()

        # Test Layer 3 (semantic matching) - no LLM call
        query = "test query for comparison"

        requests_layer_3 = [RoutingRequest(query=query) for _ in range(10)]

        start = time.perf_counter()
        for req in requests_layer_3:
            router._layer_3_semantic(router._normalize_input(query))
        end = time.perf_counter()

        layer_3_time = end - start

        # Layer 3 should be fast (< 10ms for 10 requests)
        assert layer_3_time < 0.01, f"Layer 3 too slow: {layer_3_time:.3f}s"

        # Note: Layer 0 (AI triage) would be tested separately
        # as it requires actual LLM calls
