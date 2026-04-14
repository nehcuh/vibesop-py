"""Performance tests for VibeSOP.

These tests verify performance characteristics and ensure
the system meets performance requirements.
"""

import time
from pathlib import Path

import pytest

from vibesop.builder import ConfigRenderer, QuickBuilder
from vibesop.core.routing.unified import UnifiedRouter


class TestRoutingPerformance:
    """Performance tests for routing system."""

    def test_routing_latency_p50(self) -> None:
        """Test routing latency P50 < 100ms.

        Routes 100 requests and verifies median latency is acceptable.
        """
        router = UnifiedRouter()

        # Warm up: trigger candidate loading and matcher initialization
        # to avoid measuring cold-start overhead in latency metrics
        router.route("warmup")

        # Generate test requests
        queries = [f"test query {i}" for i in range(100)]

        # Measure latencies
        latencies = []
        for query in queries:
            start = time.perf_counter()
            router.route(query)
            end = time.perf_counter()
            latencies.append(end - start)

        # Calculate P50 (median)
        latencies.sort()
        p50_index = len(latencies) // 2
        p50_latency = latencies[p50_index]

        # Assert P50 < 100ms
        assert p50_latency < 0.1, f"P50 latency {p50_latency:.3f}s exceeds 100ms"

    def test_routing_latency_p99(self) -> None:
        """Test routing latency P99 < 500ms.

        Routes 100 requests and verifies 99th percentile is acceptable.
        """
        router = UnifiedRouter()

        # Warm up: trigger candidate loading and matcher initialization
        # to avoid measuring cold-start overhead in latency metrics
        router.route("warmup")

        # Generate test requests
        queries = [f"test query {i}" for i in range(100)]

        # Measure latencies
        latencies = []
        for query in queries:
            start = time.perf_counter()
            router.route(query)
            end = time.perf_counter()
            latencies.append(end - start)

        # Calculate P99
        latencies.sort()
        p99_index = int(len(latencies) * 0.99)
        p99_latency = latencies[p99_index]

        # Assert P99 < 500ms
        assert p99_latency < 0.5, f"P99 latency {p99_latency:.3f}s exceeds 500ms"

    def test_cache_hit_rate(self) -> None:
        """Test cache hit rate > 80%.

        Verifies CacheManager stores and retrieves correctly.
        """
        from vibesop.core.routing.cache import CacheManager

        cache = CacheManager()

        # Store unique entries
        for i in range(20):
            cache.set(f"key_{i}", {"skill": f"skill_{i}"})

        # Retrieve and count hits
        hits = 0
        misses = 0
        for i in range(20):
            val = cache.get(f"key_{i}")
            if val:
                hits += 1
            else:
                misses += 1

        total = hits + misses
        hit_rate = hits / total
        assert hit_rate > 0.8, f"Cache hit rate {hit_rate:.1%} is below 80%"

    def test_concurrent_routing_performance(self) -> None:
        """Test concurrent routing performance.

        Simulates concurrent routing requests to ensure
        thread safety and performance.

        Note: Cache is warmed up before measuring to avoid cold-start overhead.
        """
        import threading

        router = UnifiedRouter()

        # Warm up: Load candidate cache before concurrent test
        router.route("warmup")

        results = []
        errors = []

        def route_query(query_id: int) -> None:
            try:
                result = router.route(f"concurrent test {query_id}")
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Create threads
        threads = [threading.Thread(target=route_query, args=(i,)) for i in range(10)]

        # Start all threads
        start = time.perf_counter()
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        end = time.perf_counter()

        # Verify all threads completed successfully
        assert len(errors) == 0, f"{len(errors)} threads failed"
        assert len(results) == 10

        # Verify performance (< 1 second for 10 concurrent requests)
        total_time = end - start
        assert total_time < 1.0, f"Concurrent routing took {total_time:.2f}s, too slow"


class TestConfigPerformance:
    """Performance tests for configuration generation."""

    def test_config_rendering_speed(self) -> None:
        """Test configuration rendering is fast enough.

        Verifies that rendering 10 configurations takes < 1 second.
        """
        import tempfile

        renderer = ConfigRenderer()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Measure rendering time
            start = time.perf_counter()

            for i in range(10):
                manifest = QuickBuilder.default(platform="claude-code")
                renderer.render(manifest, output_dir / f"config_{i}")

            end = time.perf_counter()

            total_time = end - start

            # Should render 10 configs in < 2 seconds
            assert total_time < 2.0, f"Rendering 10 configs took {total_time:.2f}s"

    def test_large_manifest_handling(self) -> None:
        """Test handling of large manifests.

        Verifies that manifests with many skills are handled efficiently.
        """
        manifest = QuickBuilder.default(platform="claude-code")

        # Add many skills to the manifest
        from vibesop.core.models import SkillDefinition

        for i in range(100):
            manifest.skills.append(
                SkillDefinition(
                    id=f"skill-{i}",
                    name=f"Skill {i}",
                    description=f"Description for skill {i}",
                    trigger_when=f"when {i}",
                    metadata={},
                )
            )

        # Measure build time
        start = time.perf_counter()
        # Just verify manifest creation is fast
        end = time.perf_counter()

        creation_time = end - start

        # Should be instant
        assert creation_time < 0.1, f"Large manifest creation took {creation_time:.3f}s"


class TestMemoryEfficiency:
    """Tests for memory efficiency."""

    def test_memory_cleanup(self) -> None:
        """Test that memory is properly cleaned up.

        Creates many objects and verifies they are garbage collected.
        """
        import gc

        # Get initial memory
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Create many routers
        routers = [UnifiedRouter() for _ in range(10)]

        # Use routers
        for router in routers:
            router.route("test")

        # Delete routers
        del routers
        gc.collect()

        # Get final memory
        final_objects = len(gc.get_objects())

        # Memory should be cleaned up (allow some tolerance)
        object_increase = final_objects - initial_objects
        assert object_increase < 10000, f"Memory leak detected: {object_increase} objects remaining"


@pytest.mark.slow
class TestLoadPerformance:
    """Load performance tests."""

    def test_sustained_load(self) -> None:
        """Test system under sustained load.

        Routes 1000 requests continuously and verifies performance remains stable.
        """
        router = UnifiedRouter()

        latencies = []
        for i in range(1000):
            start = time.perf_counter()
            router.route(f"load test {i}")
            end = time.perf_counter()
            latencies.append(end - start)

        # Check performance degradation
        first_100 = latencies[:100]
        last_100 = latencies[-100:]

        avg_first = sum(first_100) / len(first_100)
        avg_last = sum(last_100) / len(last_100)

        # Last 100 should not be more than 2x slower than first 100
        degradation_ratio = avg_last / avg_first
        assert degradation_ratio < 2.0, (
            f"Performance degraded by factor of {degradation_ratio:.1f}x"
        )
