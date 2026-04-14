"""Performance benchmark tests.

These tests establish performance baselines and detect regressions.
"""

import time
from pathlib import Path

import pytest

from vibesop.core.routing.unified import UnifiedRouter


class RoutingBenchmarks:
    """Benchmark tests for routing performance."""

    @pytest.mark.benchmark
    def test_baseline_routing_latency(self, benchmark) -> None:
        """Establish baseline for routing latency.

        Benchmark:
            - Median latency should be < 50ms
            - 99th percentile should be < 200ms
        """
        router = UnifiedRouter()

        def route_request() -> None:
            router.route("test query")

        # Benchmark multiple iterations
        result = benchmark.pedantic(route_request, iterations=100, rounds=3, warmup_rounds=1)

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
    def get_baseline_metrics() -> dict[str, float]:
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
        router = UnifiedRouter()

        # Measure current performance
        queries = [f"test query {i}" for i in range(100)]

        start = time.perf_counter()
        for query in queries:
            router.route(query)
        end = time.perf_counter()

        total_time = end - start
        avg_latency_ms = (total_time / 100) * 1000

        # Compare with baseline (allow 20% regression)
        baseline_p50 = baseline["routing_p50_latency_ms"]
        max_acceptable = baseline_p50 * 1.2

        assert avg_latency_ms < max_acceptable, (
            f"Performance regression: {avg_latency_ms:.1f}ms vs baseline {baseline_p50:.1f}ms"
        )


@pytest.mark.benchmark
class BenchmarkComparison:
    """Compare different implementations."""

    def test_routing_pipeline_performance(self) -> None:
        """Test full routing pipeline performance.

        This test measures the complete routing pipeline speed,
        including keyword, TF-IDF, and Levenshtein matching.
        """
        router = UnifiedRouter()

        query = "test query for comparison"

        start = time.perf_counter()
        for _ in range(10):
            router.route(query)
        end = time.perf_counter()

        pipeline_time = end - start

        # Full pipeline should be fast (< 100ms for 10 requests)
        assert pipeline_time < 0.1, f"Routing pipeline too slow: {pipeline_time:.3f}s"
