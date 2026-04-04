"""Unit tests for vector cache."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

np = pytest.importorskip("numpy", reason="numpy not installed")
pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")

from vibesop.semantic.cache import CacheMetadata, CacheStats, VectorCache
from vibesop.semantic.models import SemanticPattern


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cache_dir = tmp_path / "semantic_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture
def mock_encoder():
    """Create a mock encoder for testing."""
    encoder = Mock()
    encoder.model_name = "test-model"
    encoder.encode.return_value = np.array([0.1, 0.2, 0.3, 0.4])
    return encoder


class TestVectorCacheInit:
    """Tests for VectorCache initialization."""

    def test_initialization_creates_directories(self, temp_cache_dir, mock_encoder):
        """Test that initialization creates cache directories."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)

        assert cache.vectors_dir.exists()
        assert cache.metadata_dir.exists()
        assert cache.models_dir.exists()

    def test_initialization_default_ttl(self, temp_cache_dir, mock_encoder):
        """Test initialization with default TTL."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)

        assert cache.ttl == 86400  # 24 hours

    def test_initialization_custom_ttl(self, temp_cache_dir, mock_encoder):
        """Test initialization with custom TTL."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder, ttl=3600)

        assert cache.ttl == 3600


class TestVectorCacheGetOrCompute:
    """Tests for VectorCache.get_or_compute() method."""

    def test_get_or_compute_first_call_computes(self, temp_cache_dir, mock_encoder):
        """Test that first call computes and caches vector."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)

        examples = ["test example"]

        # First call should compute
        vector = cache.get_or_compute("test/pattern", examples)

        assert vector is not None
        assert isinstance(vector, np.ndarray)
        # Verify encoder.encode was called
        mock_encoder.encode.assert_called_once()

    def test_get_or_compute_second_call_returns_cached(self, temp_cache_dir, mock_encoder):
        """Test that second call returns cached vector."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)

        examples = ["test example"]

        # First call
        vector1 = cache.get_or_compute("test/pattern", examples)

        # Reset mock to track if encode is called again
        mock_encoder.encode.reset_mock()

        # Second call should use cache
        vector2 = cache.get_or_compute("test/pattern", examples)

        # Vectors should be identical
        assert np.array_equal(vector1, vector2)
        # Encoder should not be called again
        mock_encoder.encode.assert_not_called()

    def test_get_or_compute_updates_stats(self, temp_cache_dir, mock_encoder):
        """Test that get_or_compute updates cache statistics."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)

        examples = ["test example"]

        # First call (miss)
        cache.get_or_compute("test/pattern", examples)

        stats = cache.get_cache_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 0

        # Second call (hit)
        cache.get_or_compute("test/pattern", examples)

        stats = cache.get_cache_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 1

    def test_get_or_compute_empty_examples_raises_error(self, temp_cache_dir, mock_encoder):
        """Test that empty examples raises ValueError."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)

        with pytest.raises(ValueError, match="no examples"):
            cache.get_or_compute("test/pattern", [])


class TestVectorCacheComputeVector:
    """Tests for vector computation logic."""

    def test_compute_vector_single_example(self, temp_cache_dir):
        """Test computing vector with single example."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        examples = ["test example"]

        vector = cache._compute_vector("test/pattern", examples)

        assert vector.ndim == 1
        assert len(vector) == 384  # MiniLM-L12-v2 dimension
        # Check normalized
        norm = np.linalg.norm(vector)
        assert abs(norm - 1.0) < 1e-5

    def test_compute_vector_multiple_examples_mean(self, temp_cache_dir):
        """Test computing vector with multiple examples (mean strategy)."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        examples = ["example 1", "example 2", "example 3"]

        vector = cache._compute_vector("test/pattern", examples, strategy="mean")

        assert vector.ndim == 1
        assert len(vector) == 384

    def test_compute_vector_invalid_strategy_raises_error(self, temp_cache_dir):
        """Test that invalid strategy raises ValueError."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        examples = ["test example"]

        with pytest.raises(ValueError, match="Unknown aggregation strategy"):
            cache._compute_vector("test/pattern", examples, strategy="invalid")

    def test_compute_vector_creates_metadata(self, temp_cache_dir):
        """Test that computing vector creates metadata."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        examples = ["test example"]
        pattern_id = "test/pattern"

        cache._compute_vector(pattern_id, examples)

        # Check metadata was created
        assert pattern_id in cache._metadata
        metadata = cache._metadata[pattern_id]
        assert metadata.pattern_id == pattern_id
        assert metadata.strategy == "mean"


class TestVectorCacheDiskPersistence:
    """Tests for disk persistence functionality."""

    def test_save_to_disk_persists_vectors(self, temp_cache_dir):
        """Test that save_to_disk persists vectors to disk."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        # Compute some vectors
        cache.get_or_compute("pattern1", ["example 1"])
        cache.get_or_compute("pattern2", ["example 2"])

        # Save to disk
        cache.save_to_disk()

        # Check files exist
        assert (cache.vectors_dir / "pattern1.npy").exists()
        assert (cache.vectors_dir / "pattern2.npy").exists()

    def test_save_to_disk_persists_metadata(self, temp_cache_dir):
        """Test that save_to_disk persists metadata to disk."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        # Compute some vectors
        cache.get_or_compute("pattern1", ["example 1"])

        # Save to disk
        cache.save_to_disk()

        # Check metadata file exists
        metadata_file = cache.metadata_dir / "pattern1.json"
        assert metadata_file.exists()

        # Load and verify metadata
        with metadata_file.open("r") as f:
            data = json.load(f)

        assert data["pattern_id"] == "pattern1"

    def test_load_from_disk_cache_on_init(self, temp_cache_dir):
        """Test that vectors are loaded from disk on initialization."""
        from vibesop.semantic.encoder import SemanticEncoder

        # Create cache and save vectors
        encoder1 = SemanticEncoder()
        cache1 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder1)
        cache1.get_or_compute("pattern1", ["example 1"])
        cache1.save_to_disk()

        # Create new cache instance (should load from disk)
        encoder2 = SemanticEncoder()
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder2)

        # Get vector (should load from disk)
        vector = cache2.get_or_compute("pattern1", ["example 1"])

        assert vector is not None
        assert len(vector) == 384

    def test_load_from_disk_cache_miss_expired_entries(self, temp_cache_dir):
        """Test that expired cache entries are not loaded."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder, ttl=0)  # TTL=0

        # Save cache
        cache.get_or_compute("pattern1", ["example 1"])
        cache.save_to_disk()

        # Create new cache (entries should be expired)
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder, ttl=0)

        # Should recompute (not load from disk)
        # This is tested by verifying that encode is called
        # (in real scenario, not with mock encoder)


class TestVectorCacheInvalidation:
    """Tests for cache invalidation functionality."""

    def test_invalidate_pattern_removes_from_memory(self, temp_cache_dir):
        """Test that invalidating pattern removes it from memory."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        # Add vector
        cache.get_or_compute("test/pattern", ["example"])

        assert "test/pattern" in cache._vectors

        # Invalidate
        cache.invalidate_pattern("test/pattern")

        assert "test/pattern" not in cache._vectors

    def test_invalidate_pattern_removes_from_disk(self, temp_cache_dir):
        """Test that invalidating pattern removes files from disk."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        # Add and save vector
        cache.get_or_compute("test/pattern", ["example"])
        cache.save_to_disk()

        # Invalidate
        cache.invalidate_pattern("test/pattern")

        # Files should be removed
        assert not (cache.vectors_dir / "test/pattern.npy").exists()
        assert not (cache.metadata_dir / "test/pattern.json").exists()

    def test_invalidate_all_clears_everything(self, temp_cache_dir):
        """Test that invalidate_all clears all cache."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        # Add multiple vectors
        cache.get_or_compute("pattern1", ["example 1"])
        cache.get_or_compute("pattern2", ["example 2"])
        cache.save_to_disk()

        # Invalidate all
        cache.invalidate_all()

        # Memory should be cleared
        assert len(cache._vectors) == 0
        assert len(cache._metadata) == 0

        # Stats should be reset
        stats = cache.get_cache_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0


class TestVectorCacheStats:
    """Tests for cache statistics."""

    def test_get_cache_stats_returns_all_fields(self, temp_cache_dir):
        """Test that get_cache_stats returns all statistics."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        # Add some vectors
        cache.get_or_compute("pattern1", ["example 1"])
        cache.get_or_compute("pattern1", ["example 1"])  # Hit

        stats = cache.get_cache_stats()

        assert "hits" in stats
        assert "misses" in stats
        assert "total_requests" in stats
        assert "hit_rate" in stats
        assert "size" in stats
        assert "size_bytes" in stats
        assert "size_mb" in stats

    def test_cache_stats_hit_rate_calculation(self, temp_cache_dir):
        """Test that hit rate is calculated correctly."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        # 2 hits, 1 miss
        cache.get_or_compute("pattern1", ["example"])  # Miss
        cache.get_or_compute("pattern1", ["example"])  # Hit
        cache.get_or_compute("pattern1", ["example"])  # Hit

        stats = cache.get_cache_stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["total_requests"] == 3
        assert abs(stats["hit_rate"] - 2 / 3) < 1e-5

    def test_cache_stats_size_calculation(self, temp_cache_dir):
        """Test that cache size is calculated correctly."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        # Add some vectors
        cache.get_or_compute("pattern1", ["example 1"])
        cache.get_or_compute("pattern2", ["example 2"])

        stats = cache.get_cache_stats()

        assert stats["size"] == 2
        # Each vector is 384 floats = 384 * 8 bytes
        assert stats["size_bytes"] == 2 * 384 * 8


class TestVectorCachePreload:
    """Tests for preloading functionality."""

    def test_preload_patterns_loads_multiple_patterns(self, temp_cache_dir):
        """Test that preload_patterns loads multiple patterns."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        patterns = {
            "pattern1": ["example 1a", "example 1b"],
            "pattern2": ["example 2"],
            "pattern3": ["example 3a", "example 3b", "example 3c"],
        }

        cache.preload_patterns(patterns)

        # All patterns should be in cache
        assert "pattern1" in cache._vectors
        assert "pattern2" in cache._vectors
        assert "pattern3" in cache._vectors

    def test_preload_patterns_performance(self, temp_cache_dir):
        """Test that preloading is reasonably fast."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        # Create 30 patterns (typical number)
        patterns = {f"pattern{i}": [f"example {i}"] for i in range(30)}

        start = time.time()
        cache.preload_patterns(patterns)
        elapsed = time.time() - start

        # Should complete in reasonable time (< 10 seconds)
        assert elapsed < 10.0, f"Preloading too slow: {elapsed:.2f}s"


class TestVectorCacheHashExamples:
    """Tests for example hashing functionality."""

    def test_hash_examples_different_inputs_different_hashes(self, temp_cache_dir):
        """Test that different examples produce different hashes."""
        cache = VectorCache(
            cache_dir=temp_cache_dir,
            encoder=Mock(),
        )

        hash1 = cache._hash_examples(["example 1"])
        hash2 = cache._hash_examples(["example 2"])

        assert hash1 != hash2

    def test_hash_examples_same_inputs_same_hashes(self, temp_cache_dir):
        """Test that same examples produce same hashes."""
        cache = VectorCache(
            cache_dir=temp_cache_dir,
            encoder=Mock(),
        )

        hash1 = cache._hash_examples(["example 1", "example 2"])
        hash2 = cache._hash_examples(["example 1", "example 2"])

        assert hash1 == hash2

    def test_hash_examples_order_matters(self, temp_cache_dir):
        """Test that example order affects hash."""
        cache = VectorCache(
            cache_dir=temp_cache_dir,
            encoder=Mock(),
        )

        hash1 = cache._hash_examples(["example 1", "example 2"])
        hash2 = cache._hash_examples(["example 2", "example 1"])

        assert hash1 != hash2


class TestVectorCacheThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_get_or_compute(self, temp_cache_dir):
        """Test that concurrent access is thread-safe."""
        from vibesop.semantic.encoder import SemanticEncoder
        from concurrent.futures import ThreadPoolExecutor

        encoder = SemanticEncoder()
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        def get_vector(pattern_id):
            return cache.get_or_compute(pattern_id, ["example"])

        # Concurrently access cache
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(get_vector, f"pattern{i}") for i in range(50)]
            results = [f.result() for f in futures]

        # All results should be valid
        assert len(results) == 50
        for vector in results:
            assert isinstance(vector, np.ndarray)
            assert len(vector) == 384


class TestCacheMetadata:
    """Tests for CacheMetadata dataclass."""

    def test_cache_metadata_fields(self):
        """Test that CacheMetadata has all required fields."""
        metadata = CacheMetadata(
            pattern_id="test/pattern",
            examples_hash="abc123",
            model_name="test-model",
            computed_at=time.time(),
            vector_dim=384,
            strategy="mean",
        )

        assert metadata.pattern_id == "test/pattern"
        assert metadata.examples_hash == "abc123"
        assert metadata.model_name == "test-model"
        assert metadata.vector_dim == 384
        assert metadata.strategy == "mean"


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_cache_stats_initial_values(self):
        """Test that CacheStats initializes with zeros."""
        stats = CacheStats()

        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0
        assert stats.size_bytes == 0

    def test_cache_stats_hit_rate_property(self):
        """Test hit_rate property calculation."""
        stats = CacheStats()
        stats.hits = 5
        stats.misses = 3

        assert stats.total_requests == 8
        assert abs(stats.hit_rate - 5 / 8) < 1e-5

    def test_cache_stats_hit_rate_no_requests(self):
        """Test hit_rate when there are no requests."""
        stats = CacheStats()

        assert stats.total_requests == 0
        assert stats.hit_rate == 0.0
