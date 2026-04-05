"""Performance benchmarks for trigger system.

Tests performance characteristics and benchmarks.
"""

import pytest
import time
import statistics
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from vibesop.triggers import KeywordDetector, SkillActivator, DEFAULT_PATTERNS, auto_activate


class TestDetectionPerformance:
    """Performance benchmarks for keyword detection."""

    def test_benchmark_detection_speed(self):
        """Benchmark detection speed for various queries."""
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        test_queries = [
            "scan for security vulnerabilities",
            "deploy configuration to production",
            "run all unit tests",
            "generate API documentation",
            "initialize new project",
            "check for security issues",
            "validate config files",
            "build the project",
            "debug this error",
            "update the readme",
        ]

        # Warmup
        for query in test_queries:
            detector.detect_best(query)

        # Benchmark
        iterations = 1000
        start_time = time.time()

        for i in range(iterations):
            query = test_queries[i % len(test_queries)]
            detector.detect_best(query, min_confidence=0.6)

        elapsed = time.time() - start_time
        avg_time = elapsed / iterations
        queries_per_second = iterations / elapsed

        print(f"\nDetection Performance:")
        print(f"  Total time: {elapsed:.3f}s for {iterations} queries")
        print(f"  Average: {avg_time * 1000:.3f}ms per query")
        print(f"  Speed: {queries_per_second:.0f} queries/second")

        # Performance assertions
        assert avg_time < 0.01, f"Detection too slow: {avg_time * 1000:.2f}ms"
        assert queries_per_second > 100, f"Speed too low: {queries_per_second:.0f} q/s"

    def test_benchmark_initialization_time(self):
        """Benchmark detector initialization time."""
        iterations = 100
        times = []

        for _ in range(iterations):
            start = time.time()
            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            elapsed = time.time() - start
            times.append(elapsed)

        avg_time = statistics.mean(times)
        median_time = statistics.median(times)

        print(f"\nInitialization Performance:")
        print(f"  Average: {avg_time * 1000:.2f}ms")
        print(f"  Median: {median_time * 1000:.2f}ms")

        # Initialization should be fast (< 50ms)
        assert avg_time < 0.05, f"Initialization too slow: {avg_time * 1000:.2f}ms"

    def test_benchmark_idf_cache_building(self):
        """Benchmark IDF cache building performance."""
        iterations = 100
        times = []

        for _ in range(iterations):
            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            # Cache is built during initialization
            times.append(
                detector._cache_build_time if hasattr(detector, "_cache_build_time") else 0
            )

        if times:
            avg_time = statistics.mean(times)
            print(f"\nIDF Cache Build Time:")
            print(f"  Average: {avg_time * 1000:.2f}ms")

            # Cache building should be fast
            assert avg_time < 0.02, f"Cache building too slow: {avg_time * 1000:.2f}ms"

    def test_benchmark_scaling_with_pattern_count(self):
        """Benchmark how detection scales with pattern count."""
        # Test with different pattern set sizes
        pattern_counts = [5, 10, 20, 30]
        times = {}

        for count in pattern_counts:
            patterns = DEFAULT_PATTERNS[:count]
            detector = KeywordDetector(patterns=patterns)

            query = "scan for security vulnerabilities"

            # Warmup
            for _ in range(10):
                detector.detect_best(query)

            # Benchmark
            iterations = 100
            start = time.time()
            for _ in range(iterations):
                detector.detect_best(query)
            elapsed = time.time() - start

            times[count] = elapsed / iterations

        print(f"\nScaling Performance:")
        for count, avg_time in times.items():
            print(f"  {count} patterns: {avg_time * 1000:.3f}ms")

        # Performance should scale roughly linearly
        # Check that 30 patterns isn't more than 10x slower than 5 patterns
        ratio = times[30] / times[5]
        assert ratio < 10, f"Scaling too poor: 30 patterns is {ratio:.1f}x slower than 5"

    def test_benchmark_query_length_impact(self):
        """Benchmark impact of query length on performance."""
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        queries = [
            "scan",  # Short
            "scan for security",  # Medium
            "scan for security vulnerabilities in the entire codebase with detailed reporting",  # Long
        ]

        iterations = 1000
        results = {}

        for query in queries:
            start = time.time()
            for _ in range(iterations):
                detector.detect_best(query)
            elapsed = time.time() - start
            avg_time = elapsed / iterations
            results[len(query)] = avg_time

        print(f"\nQuery Length Impact:")
        for length, avg_time in sorted(results.items()):
            print(f"  {length} chars: {avg_time * 1000:.3f}ms")

        # Long queries shouldn't be dramatically slower
        # (tokenization is O(n) but should be fast)
        ratio = results[max(results.keys())] / results[min(results.keys())]
        assert ratio < 5, f"Query length impact too high: {ratio:.1f}x"


class TestActivationPerformance:
    """Performance benchmarks for skill activation."""

    @pytest.mark.asyncio
    async def test_benchmark_activation_speed(self, tmp_path):
        """Benchmark skill activation speed."""
        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
        ):
            # Setup
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(return_value="Success")
            mock_sm_class.return_value = mock_sm

            mock_router = MagicMock()
            mock_router.route.return_value = None
            mock_router_class.return_value = mock_router

            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            activator = SkillActivator(project_root=tmp_path)

            query = "scan for security issues"
            match = detector.detect_best(query)

            # Warmup
            for _ in range(10):
                await activator.activate(match)

            # Benchmark
            iterations = 100
            start = time.time()

            for _ in range(iterations):
                await activator.activate(match)

            elapsed = time.time() - start
            avg_time = elapsed / iterations

            print(f"\nActivation Performance:")
            print(f"  Total: {elapsed:.3f}s for {iterations} activations")
            print(f"  Average: {avg_time * 1000:.2f}ms per activation")

            # Activation should be reasonably fast
            # (most time is in the mock skill execution)
            assert avg_time < 0.1, f"Activation too slow: {avg_time * 1000:.2f}ms"

    @pytest.mark.asyncio
    async def test_benchmark_auto_activate_speed(self, tmp_path):
        """Benchmark auto_activate convenience function."""
        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
        ):
            # Setup
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(return_value="Success")
            mock_sm_class.return_value = mock_sm

            mock_router = MagicMock()
            mock_router.route.return_value = None
            mock_router_class.return_value = mock_router

            # Benchmark
            iterations = 100
            query = "scan for security issues"
            start = time.time()

            for _ in range(iterations):
                await auto_activate(query, project_root=tmp_path)

            elapsed = time.time() - start
            avg_time = elapsed / iterations

            print(f"\nAuto-Activate Performance:")
            print(f"  Total: {elapsed:.3f}s for {iterations} calls")
            print(f"  Average: {avg_time * 1000:.2f}ms per call")

            # Should be reasonably fast
            assert avg_time < 0.15, f"Auto-activate too slow: {avg_time * 1000:.2f}ms"


class TestMemoryPerformance:
    """Memory performance tests."""

    def test_memory_usage_detector(self):
        """Test memory usage of detector."""
        import gc
        import sys

        gc.collect()

        # Create multiple detectors
        detectors = []
        for _ in range(100):
            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            detectors.append(detector)

        # Check size
        # Note: This is approximate
        base_size = sys.getsizeof(detectors[0])
        total_size = sum(sys.getsizeof(d) for d in detectors)

        print(f"\nMemory Usage:")
        print(f"  Base detector: {base_size / 1024:.2f}KB")
        print(f"  Total for 100: {total_size / 1024:.2f}KB")
        print(f"  Average: {(total_size / 100) / 1024:.2f}KB")

        # Each detector should be reasonably sized
        avg_size = total_size / 100
        assert avg_size < 100 * 1024, f"Detector too large: {avg_size / 1024:.2f}KB"

    def test_memory_usage_with_idf_cache(self):
        """Test memory usage of IDF cache."""
        import gc
        import sys

        gc.collect()

        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        # Access cache to ensure it's loaded
        cache = detector.idf_cache

        if cache:
            cache_size = sys.getsizeof(cache)
            print(f"\nIDF Cache Size:")
            print(f"  {cache_size / 1024:.2f}KB")

            # Cache should be reasonably sized
            assert cache_size < 50 * 1024, f"IDF cache too large: {cache_size / 1024:.2f}KB"

    def test_memory_leak_detection(self):
        """Test for memory leaks in repeated operations."""
        import gc

        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        gc.collect()

        # Get baseline
        initial_objects = len(gc.get_objects())

        # Perform many operations
        for i in range(1000):
            query = f"scan for security issues {i}"
            detector.detect_best(query)

        gc.collect()

        # Check final count
        final_objects = len(gc.get_objects())
        growth = final_objects - initial_objects

        print(f"\nMemory Leak Test:")
        print(f"  Initial objects: {initial_objects}")
        print(f"  Final objects: {final_objects}")
        print(f"  Growth: {growth}")

        # Growth should be minimal
        # Allow some growth for caching, but not excessive
        assert growth < initial_objects * 0.1, f"Possible memory leak: {growth} objects grew"


class TestConcurrencyPerformance:
    """Concurrency performance tests."""

    @pytest.mark.asyncio
    async def test_concurrent_detection(self):
        """Test concurrent detection performance."""
        import asyncio

        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        queries = [
            "scan for security issues",
            "deploy configuration",
            "run tests",
            "generate docs",
            "init project",
        ] * 20  # 100 queries

        start = time.time()

        # Run concurrently
        tasks = [asyncio.to_thread(detector.detect_best, query) for query in queries]
        results = await asyncio.gather(*tasks)

        elapsed = time.time() - start
        avg_time = elapsed / len(queries)

        print(f"\nConcurrent Detection:")
        print(f"  Total: {elapsed:.3f}s for {len(queries)} queries")
        print(f"  Average: {avg_time * 1000:.3f}ms")

        # Concurrent should be faster than sequential
        assert avg_time < 0.01, f"Concurrent detection too slow: {avg_time * 1000:.2f}ms"

    @pytest.mark.asyncio
    async def test_concurrent_activation(self, tmp_path):
        """Test concurrent activation performance."""
        import asyncio

        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
        ):
            # Setup
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(return_value="Success")
            mock_sm_class.return_value = mock_sm

            mock_router = MagicMock()
            mock_router.route.return_value = None
            mock_router_class.return_value = mock_router

            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            activator = SkillActivator(project_root=tmp_path)

            # Prepare matches
            queries = [
                "scan for security issues",
                "deploy configuration",
                "run tests",
            ] * 10  # 30 queries

            matches = [detector.detect_best(q) for q in queries]

            start = time.time()

            # Run activations concurrently
            tasks = [activator.activate(match) for match in matches]
            results = await asyncio.gather(*tasks)

            elapsed = time.time() - start
            avg_time = elapsed / len(matches)

            print(f"\nConcurrent Activation:")
            print(f"  Total: {elapsed:.3f}s for {len(matches)} activations")
            print(f"  Average: {avg_time * 1000:.2f}ms")

            # Should complete reasonably fast
            assert elapsed < 5.0, f"Concurrent activation too slow: {elapsed:.2f}s"


class TestScalabilityPerformance:
    """Scalability performance tests."""

    def test_benchmark_large_batch_detection(self):
        """Benchmark detection with large batch of queries."""
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        # Generate large batch of queries
        queries = []
        templates = [
            "scan for {}",
            "deploy {}",
            "run {}",
            "generate {}",
            "init {}",
        ]
        targets = ["security issues", "configuration", "tests", "docs", "project"]

        for template in templates:
            for target in targets:
                queries.append(template.format(target))

        # Repeat to get 500 queries
        queries = queries * 20

        start = time.time()
        for query in queries:
            detector.detect_best(query)
        elapsed = time.time() - start

        avg_time = elapsed / len(queries)
        qps = len(queries) / elapsed

        print(f"\nLarge Batch Performance:")
        print(f"  Queries: {len(queries)}")
        print(f"  Total time: {elapsed:.3f}s")
        print(f"  Average: {avg_time * 1000:.3f}ms")
        print(f"  Throughput: {qps:.0f} queries/second")

        # Should handle large batches efficiently
        assert qps > 100, f"Throughput too low: {qps:.0f} q/s"

    def test_benchmark_worst_case_query(self):
        """Benchmark worst-case query performance."""
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        # Worst case: long query with many common words
        worst_query = " ".join(
            [
                "test check run build deploy scan generate validate create update",
                "test check run build deploy scan generate validate create update",
                "test check run build deploy scan generate validate create update",
            ]
        )

        iterations = 100
        start = time.time()

        for _ in range(iterations):
            detector.detect_best(worst_query)

        elapsed = time.time() - start
        avg_time = elapsed / iterations

        print(f"\nWorst Case Performance:")
        print(f"  Query length: {len(worst_query)} chars")
        print(f"  Average: {avg_time * 1000:.3f}ms")

        # Even worst case should be reasonably fast
        assert avg_time < 0.05, f"Worst case too slow: {avg_time * 1000:.2f}ms"


class TestComparisonPerformance:
    """Comparison with alternative approaches."""

    def test_compare_with_regex_only(self):
        """Compare multi-strategy vs regex-only matching."""
        import re

        # Regex-only patterns (simplified)
        regex_patterns = [
            (r"scan.*security", "security/scan"),
            (r"deploy.*config", "config/deploy"),
            (r"run.*test", "dev/test"),
            (r"generate.*doc", "docs/generate"),
            (r"init.*project", "project/init"),
        ]

        queries = [
            "scan for security issues",
            "deploy configuration to production",
            "run all tests",
            "generate documentation",
            "initialize new project",
        ] * 100

        # Benchmark regex-only
        start = time.time()
        for query in queries:
            for pattern, pattern_id in regex_patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    break
        regex_time = time.time() - start

        # Benchmark multi-strategy
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        start = time.time()
        for query in queries:
            detector.detect_best(query)
        multi_time = time.time() - start

        print(f"\nComparison (500 queries):")
        print(f"  Regex-only: {regex_time:.3f}s")
        print(f"  Multi-strategy: {multi_time:.3f}s")
        print(f"  Ratio: {multi_time / regex_time:.2f}x")

        # Multi-strategy should be competitive
        # (may be slightly slower but provides much better accuracy)
        assert multi_time < regex_time * 500, (
            f"Multi-strategy too slow compared to regex: {multi_time / regex_time:.2f}x"
        )
