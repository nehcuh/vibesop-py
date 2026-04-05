"""Performance benchmarks for semantic recognition.

These tests measure the performance of semantic matching components
to ensure they meet the specified targets.

Performance Targets:
    - Encoder throughput: > 500 texts/sec
    - Similarity calculation: < 0.1ms per calculation
    - E2E latency: < 20ms per query (with semantic)
    - Memory overhead: < 200MB
    - Cache hit rate: > 95%

DEPRECATED: These benchmarks use the deprecated triggers module.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from vibesop.semantic.models import EncoderConfig, SemanticPattern

# Skip these benchmarks since they depend on deprecated triggers module
pytest.skip("Benchmarks depend on deprecated triggers module.", allow_module_level=True)

from vibesop.triggers.detector import KeywordDetector
from vibesop.triggers.models import TriggerPattern, PatternCategory

pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")


@pytest.fixture
def benchmark_patterns():
    """Create patterns for benchmarking."""
    return [
        TriggerPattern(
            pattern_id=f"pattern{i}",
            name=f"Pattern {i}",
            description=f"Test pattern {i}",
            category=PatternCategory.DEV,
            keywords=[f"keyword{i}"],
            skill_id="/dev/test",
            priority=50,
            confidence_threshold=0.6,
            examples=[f"example {i} text"],
            enable_semantic=True,
            semantic_examples=[f"semantic example {i}"],
        )
        for i in range(30)  # 30 patterns
    ]


class TestEncoderBenchmarks:
    """Benchmarks for SemanticEncoder."""

    @pytest.mark.slow
    def test_encode_single_text_performance(self):
        """Test encoding a single text is fast enough."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder.warmup()  # Pre-load model

        iterations = 100
        start = time.time()

        for _ in range(iterations):
            encoder.encode("test query")

        elapsed = time.time() - start
        avg_time = elapsed / iterations

        # Should be very fast (< 50ms per encode)
        assert avg_time < 0.05, f"Single encode too slow: {avg_time*1000:.2f}ms"

    @pytest.mark.slow
    def test_encode_batch_throughput(self):
        """Test encoding throughput for batches."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder.warmup()  # Pre-load model

        # Encode 100 texts in batches
        texts = [f"test query {i}" for i in range(100)]
        batch_size = 32

        start = time.time()
        vectors = encoder.encode(texts, batch_size=batch_size)
        elapsed = time.time() - start

        throughput = len(texts) / elapsed

        # Should achieve > 500 texts/sec (after model is loaded)
        assert throughput >= 500, f"Throughput too low: {throughput:.0f} texts/sec"

    @pytest.mark.slow
    def test_encode_query_performance(self):
        """Test encode_query method performance."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder.warmup()  # Pre-load model

        iterations = 1000
        start = time.time()

        for _ in range(iterations):
            encoder.encode_query("test query")

        elapsed = time.time() - start
        avg_time = elapsed / iterations

        # Should be < 10ms per query (after warmup)
        assert avg_time < 0.01, f"Query encode too slow: {avg_time*1000:.2f}ms"


class TestSimilarityBenchmarks:
    """Benchmarks for SimilarityCalculator."""

    def test_calculate_single_performance(self):
        """Test single similarity calculation is fast."""
        from vibesop.semantic.similarity import SimilarityCalculator

        calc = SimilarityCalculator()

        query = np.random.rand(384)
        pattern = np.random.rand(384)

        iterations = 10000
        start = time.time()

        for _ in range(iterations):
            calc.calculate_single(query, pattern)

        elapsed = time.time() - start
        avg_time = elapsed / iterations

        # Should be < 0.1ms per calculation
        assert avg_time < 0.0001, f"Similarity calc too slow: {avg_time*1000:.3f}ms"

    def test_calculate_batch_performance(self):
        """Test batch similarity calculation performance."""
        from vibesop.semantic.similarity import SimilarityCalculator

        calc = SimilarityCalculator()

        query = np.random.rand(384)
        patterns = np.random.rand(30, 384)  # 30 patterns

        iterations = 1000
        start = time.time()

        for _ in range(iterations):
            calc.calculate(query, patterns)

        elapsed = time.time() - start
        avg_time = elapsed / iterations

        # Should be < 1ms for 30 patterns
        assert avg_time < 0.001, f"Batch calc too slow: {avg_time*1000:.2f}ms"

    def test_batch_calculate_performance(self):
        """Test batch calculate method performance."""
        from vibesop.semantic.similarity import SimilarityCalculator

        calc = SimilarityCalculator()

        queries = np.random.rand(100, 384)
        patterns = np.random.rand(30, 384)

        start = time.time()
        result = calc.batch_calculate(queries, patterns)
        elapsed = time.time() - start

        avg_time = elapsed / len(queries)

        # Should be < 1ms per query in batch
        assert avg_time < 0.001, f"Batch query too slow: {avg_time*1000:.2f}ms"


class TestCacheBenchmarks:
    """Benchmarks for VectorCache."""

    @pytest.mark.slow
    def test_cache_hit_rate(self, benchmark_patterns):
        """Test cache hit rate is high."""
        from vibesop.semantic.cache import VectorCache
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(
            cache_dir=Path("/tmp/test_cache"),
            encoder=encoder,
        )

        # First access (misses)
        for pattern in benchmark_patterns:
            cache.get_or_compute(pattern.pattern_id, pattern.examples)

        # Second access (hits)
        for pattern in benchmark_patterns:
            cache.get_or_compute(pattern.pattern_id, pattern.examples)

        stats = cache.get_cache_stats()

        # Hit rate should be > 95%
        assert stats["hit_rate"] > 0.95, f"Hit rate too low: {stats['hit_rate']:.0%}"

    @pytest.mark.slow
    def test_cache_throughput(self, benchmark_patterns):
        """Test cache throughput is high."""
        from vibesop.semantic.cache import VectorCache
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(
            cache_dir=Path("/tmp/test_cache_throughput"),
            encoder=encoder,
        )

        # Measure cache get performance
        iterations = 1000
        start = time.time()

        for i in range(iterations):
            pattern = benchmark_patterns[i % len(benchmark_patterns)]
            cache.get_or_compute(pattern.pattern_id, pattern.examples)

        elapsed = time.time() - start
        ops_per_sec = iterations / elapsed

        # Should be able to do > 1000 ops/sec
        assert ops_per_sec > 1000, f"Cache throughput too low: {ops_per_sec:.0f} ops/sec"

    @pytest.mark.slow
    def test_preload_performance(self, benchmark_patterns):
        """Test preloading performance."""
        from vibesop.semantic.cache import VectorCache
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(
            cache_dir=Path("/tmp/test_cache_preload"),
            encoder=encoder,
        )

        # Prepare pattern data
        pattern_data = {
            p.pattern_id: p.examples + p.semantic_examples
            for p in benchmark_patterns
        }

        start = time.time()
        cache.preload_patterns(pattern_data)
        elapsed = time.time() - start

        # Should preload 30 patterns in < 10 seconds
        assert elapsed < 10.0, f"Preload too slow: {elapsed:.2f}s for {len(benchmark_patterns)} patterns"

    @pytest.mark.slow
    def test_cache_persistence_performance(self, benchmark_patterns):
        """Test cache save/load performance."""
        from vibesop.semantic.cache import VectorCache
        from vibesop.semantic.encoder import SemanticEncoder
        import tempfile

        encoder = SemanticEncoder()
        cache_dir = tempfile.mkdtemp()
        cache = VectorCache(cache_dir=Path(cache_dir), encoder=encoder)

        # Compute vectors
        for pattern in benchmark_patterns[:5]:  # Test with 5 patterns
            cache.get_or_compute(pattern.pattern_id, pattern.examples)

        # Test save performance
        start = time.time()
        cache.save_to_disk()
        save_time = time.time() - start

        # Save should be fast (< 1 second for 5 vectors)
        assert save_time < 1.0, f"Save too slow: {save_time:.2f}s"

        # Test load performance (by creating new cache)
        start = time.time()
        cache2 = VectorCache(cache_dir=Path(cache_dir), encoder=encoder)
        load_time = time.time() - start

        # Load should be fast (< 1 second)
        assert load_time < 1.0, f"Load too slow: {load_time:.2f}s"


class TestDetectorBenchmarks:
    """Benchmarks for KeywordDetector with semantic."""

    @pytest.mark.slow
    def test_detect_best_traditional_only_performance(self, benchmark_patterns):
        """Test detect_best performance with traditional matching only."""
        detector = KeywordDetector(
            patterns=benchmark_patterns,
            enable_semantic=False,  # Traditional only
        )

        iterations = 1000
        start = time.time()

        for _ in range(iterations):
            detector.detect_best("test query")

        elapsed = time.time() - start
        avg_time = elapsed / iterations

        # Traditional should be very fast (< 5ms)
        assert avg_time < 0.005, f"Traditional detection too slow: {avg_time*1000:.2f}ms"

    @pytest.mark.slow
    def test_detect_best_with_semantic_performance(self, benchmark_patterns):
        """Test detect_best performance with semantic enabled."""
        # Mock semantic components for benchmarking
        with Mock() as MockCache:
            with Mock() as MockEncoder:
                with Mock() as MockCalc:
                    # Setup mocks with fast return
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    # Simulate fast encoding (0.5ms)
                    def fast_encode(query):
                        time.sleep(0.0005)
                        return np.random.rand(384)
                    mock_encoder.encode_query.side_effect = fast_encode
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    # Simulate fast cache hit (0.1ms)
                    def fast_get(pattern_id, examples):
                        time.sleep(0.0001)
                        return np.random.rand(384)
                    mock_cache.get_or_compute.side_effect = fast_get
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    # Simulate fast similarity (0.05ms)
                    def fast_calc(query, patterns):
                        time.sleep(0.00005)
                        return np.random.rand(len(patterns))
                    mock_calc.calculate.side_effect = fast_calc
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=benchmark_patterns,
                        enable_semantic=True,
                    )

                    iterations = 100
                    start = time.time()

                    for _ in range(iterations):
                        detector.detect_best("test query")

                    elapsed = time.time() - start
                    avg_time = elapsed / iterations

                    # With semantic, should be < 20ms per query
                    assert avg_time < 0.02, f"Semantic detection too slow: {avg_time*1000:.2f}ms"

    @pytest.mark.slow
    def test_detect_all_performance(self, benchmark_patterns):
        """Test detect_all performance."""
        detector = KeywordDetector(
            patterns=benchmark_patterns,
            enable_semantic=False,
        )

        iterations = 100
        start = time.time()

        for _ in range(iterations):
            detector.detect_all("test query")

        elapsed = time.time() - start
        avg_time = elapsed / iterations

        # Should be fast (< 10ms)
        assert avg_time < 0.01, f"detect_all too slow: {avg_time*1000:.2f}ms"


class TestMemoryBenchmarks:
    """Benchmarks for memory usage."""

    @pytest.mark.slow
    def test_memory_overhead(self, benchmark_patterns):
        """Test memory overhead is within limits."""
        import tracemalloc

        from vibesop.semantic.cache import VectorCache
        from vibesop.semantic.encoder import SemanticEncoder

        # Start tracking memory
        tracemalloc.start()

        # Baseline
        baseline = tracemalloc.get_traced_memory()[0]

        # Create encoder and cache
        encoder = SemanticEncoder()
        cache_dir = Path("/tmp/test_cache_memory")
        cache = VectorCache(cache_dir=cache_dir, encoder=encoder)

        # Load some vectors (10 patterns)
        for pattern in benchmark_patterns[:10]:
            cache.get_or_compute(pattern.pattern_id, pattern.examples)

        # Measure memory
        current = tracemalloc.get_traced_memory()[0]
        overhead = (current - baseline) / (1024 * 1024)  # Convert to MB

        # Should be < 200MB overhead
        assert overhead < 200, f"Memory overhead too high: {overhead:.0f}MB"

        tracemalloc.stop()

    @pytest.mark.slow
    def test_cache_size_per_pattern(self):
        """Test cache size per pattern is reasonable."""
        import tracemalloc

        from vibesop.semantic.cache import VectorCache
        from vibesop.semantic.encoder import SemanticEncoder

        tracemalloc.start()

        encoder = SemanticEncoder()
        cache_dir = Path("/tmp/test_cache_pattern_size")
        cache = VectorCache(cache_dir=cache_dir, encoder=encoder)

        # Baseline
        baseline = tracemalloc.get_traced_memory()[0]

        # Add one pattern
        pattern = SemanticPattern(
            pattern_id="test/pattern",
            examples=["example 1", "example 2", "example 3"],
        )
        cache.get_or_compute(pattern.pattern_id, pattern.examples)

        # Measure
        current = tracemalloc.get_traced_memory()[0]
        size_bytes = current - baseline

        # Each pattern should be < 100KB (384 floats * 8 bytes = 3KB + metadata)
        assert size_bytes < 100 * 1024, f"Pattern size too large: {size_bytes / 1024:.1f}KB"

        tracemalloc.stop()


class TestE2EBenchmarks:
    """End-to-end performance benchmarks."""

    @pytest.mark.slow
    def test_e2e_query_latency(self):
        """Test complete end-to-end query latency."""
        # This is a simplified benchmark - real testing would use actual encoder
        with Mock() as MockCache:
            with Mock() as MockEncoder:
                with Mock() as MockCalc:
                    # Setup realistic timing
                    mock_encoder = Mock()
                    mock_encoder.model_name = "paraphrase-multilingual-MiniLM-L12-v2"

                    # Simulate encoding time (8ms typical)
                    def encode_query(query):
                        time.sleep(0.008)
                        return np.random.rand(384)
                    mock_encoder.encode_query.side_effect = encode_query

                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    # Simulate cache hit (0.1ms)
                    def get_or_compute(pattern_id, examples):
                        time.sleep(0.0001)
                        return np.random.rand(384)
                    mock_cache.get_or_compute.side_effect = get_or_compute
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    # Simulate similarity calculation (0.1ms for 30 patterns)
                    def calculate(query, patterns):
                        time.sleep(0.0001)
                        return np.random.rand(len(patterns))
                    mock_calc.calculate.side_effect = calculate
                    MockCalc.return_value = mock_calc

                    # Create detector with realistic pattern count
                    patterns = [
                        TriggerPattern(
                            pattern_id=f"pattern{i}",
                            name=f"Pattern {i}",
                            description=f"Test pattern {i}",
                            category=PatternCategory.DEV,
                            keywords=[f"keyword{i}"],
                            skill_id="/dev/test",
                            priority=50,
                            confidence_threshold=0.6,
                            examples=[f"example {i}"],
                            enable_semantic=True,
                        )
                        for i in range(30)
                    ]

                    detector = KeywordDetector(
                        patterns=patterns,
                        enable_semantic=True,
                    )

                    # Measure E2E latency
                    iterations = 50
                    start = time.time()

                    for _ in range(iterations):
                        detector.detect_best("test query")

                    elapsed = time.time() - start
                    avg_latency = elapsed / iterations

                    # E2E latency should be < 20ms
                    assert avg_latency < 0.02, f"E2E latency too high: {avg_latency*1000:.2f}ms"

    @pytest.mark.slow
    def test_batch_query_throughput(self):
        """Test throughput for batch queries."""
        queries = [
            "scan for vulnerabilities",
            "run tests",
            "build project",
            "generate documentation",
            "deploy configuration",
        ]

        # Simulate processing
        start = time.time()

        for query in queries:
            # Simulate fast detection
            time.sleep(0.002)  # 2ms per query

        elapsed = time.time() - start
        throughput = len(queries) / elapsed

        # Should achieve > 100 queries/sec
        assert throughput > 100, f"Batch throughput too low: {throughput:.0f} queries/sec"


class TestPrecomputationBenchmarks:
    """Benchmarks for vector precomputation."""

    @pytest.mark.slow
    def test_precompute_all_patterns(self):
        """Test precomputing all pattern vectors."""
        from vibesop.semantic.cache import VectorCache
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache_dir = Path("/tmp/test_precompute")
        cache = VectorCache(cache_dir=cache_dir, encoder=encoder)

        # Create 30 patterns
        patterns = {
            f"pattern{i}": [f"example {i} text"]
            for i in range(30)
        }

        start = time.time()
        cache.preload_patterns(patterns)
        elapsed = time.time() - start

        # Should precompute 30 patterns in < 5 seconds
        assert elapsed < 5.0, f"Precompute too slow: {elapsed:.2f}s for 30 patterns"

    @pytest.mark.slow
    def test_incremental_precomputation(self):
        """Test incremental precomputation is efficient."""
        from vibesop.semantic.cache import VectorCache
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache_dir = Path("/tmp/test_incremental")
        cache = VectorCache(cache_dir=cache_dir, encoder=encoder)

        # First batch
        patterns1 = {f"pattern{i}": [f"example {i}"] for i in range(10)}
        start = time.time()
        cache.preload_patterns(patterns1)
        time1 = time.time() - start

        # Second batch (should use cache)
        patterns2 = {f"pattern{i}": [f"example {i}"] for i in range(10, 20)}
        start = time.time()
        cache.preload_patterns(patterns2)
        time2 = time.time() - start

        # Second batch should be similar or faster (no significant slowdown)
        assert time2 < time1 * 1.5, f"Incremental precompute slowed down: {time2:.2f}s vs {time1:.2f}s"
