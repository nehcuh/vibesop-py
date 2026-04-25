"""Performance benchmarks for routing engine."""

from __future__ import annotations

import time

import pytest

from vibesop.core.routing.unified import UnifiedRouter


class TestRoutingPerformance:
    """Benchmarks for routing latency."""

    @pytest.mark.benchmark
    def test_routing_latency_simple(self) -> None:
        """Test routing latency for simple queries.

        Note: Warm-up cache first to measure typical latency (not cold-start).
        In real CLI usage, the first call loads cache, subsequent calls are fast.
        """
        router = UnifiedRouter()
        queries = ["review", "debug", "test", "build", "deploy"]

        # Warm up: Load candidate cache on first call
        router.route("warmup")

        latencies: list[float] = []
        for query in queries:
            start = time.perf_counter()
            router.route(query)
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

        avg_latency = sum(latencies) / len(latencies)
        # v4.4.0 target: P95 < 100ms. Current: ~200ms avg, 354ms P95.
        # Use conservative guardrail to prevent regression beyond current baseline.
        assert avg_latency < 400, f"Average latency {avg_latency:.1f}ms > 400ms guardrail"

    @pytest.mark.benchmark
    def test_routing_throughput(self) -> None:
        """Test routing throughput (queries per second)."""
        router = UnifiedRouter()
        query = "review my code"
        count = 50

        # Warm up: Load candidate cache first
        router.route("warmup")

        start = time.perf_counter()
        for _ in range(count):
            router.route(query)
        elapsed = time.perf_counter() - start

        qps = count / elapsed
        # v4.4.0 target: P95 < 100ms (~20+ QPS). Current: ~4 QPS (200ms avg).
        # Use conservative guardrail to prevent regression beyond current baseline.
        assert qps > 3, f"Throughput {qps:.0f} qps < 3 qps guardrail"
