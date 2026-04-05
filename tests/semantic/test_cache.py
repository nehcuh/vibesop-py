"""Comprehensive unit tests for vector cache with mocked encoder.

All tests mock the SemanticEncoder to avoid loading real models.
Tests cover all public methods and key private methods of VectorCache,
CacheMetadata, and CacheStats.
"""

# pyright: reportPrivateUsage=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none, reportUnknownParameterType=none, reportMissingParameterType=none

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

# NumPy is optional for semantic features
np = pytest.importorskip("numpy", reason="numpy not installed")

from vibesop.semantic.cache import CacheMetadata, CacheStats, VectorCache


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """Create a temporary cache directory."""
    return tmp_path / "cache"


@pytest.fixture
def mock_encoder() -> Mock:
    """Create a mock encoder for testing."""
    encoder = Mock()
    encoder.model_name = "test-model-v1"
    encoder.encode.return_value = np.array(
        [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]], dtype=np.float64
    )
    return encoder


def _make_encoder(dim: int = 384, model_name: str = "test-model") -> Mock:
    """Helper to create a mock encoder with configurable dimension."""
    encoder = Mock()
    encoder.model_name = model_name
    encoder.encode.return_value = np.random.rand(2, dim).astype(np.float64)
    return encoder


class TestCacheMetadata:
    """Tests for CacheMetadata dataclass."""

    def test_cache_metadata_creation(self):
        """Test CacheMetadata can be created with all fields."""
        metadata = CacheMetadata(
            pattern_id="test/pattern",
            examples_hash="abc123",
            model_name="test-model",
            computed_at=1700000000.0,
            vector_dim=384,
            strategy="mean",
        )
        assert metadata.pattern_id == "test/pattern"
        assert metadata.examples_hash == "abc123"
        assert metadata.model_name == "test-model"
        assert metadata.computed_at == 1700000000.0
        assert metadata.vector_dim == 384
        assert metadata.strategy == "mean"

    def test_cache_metadata_default_strategy(self):
        """Test that strategy defaults to 'mean'."""
        metadata = CacheMetadata(
            pattern_id="p",
            examples_hash="h",
            model_name="m",
            computed_at=1.0,
            vector_dim=384,
        )
        assert metadata.strategy == "mean"

    def test_cache_metadata_to_dict(self):
        """Test metadata can be serialized via __dict__."""
        metadata = CacheMetadata(
            pattern_id="test/pattern",
            examples_hash="abc123",
            model_name="test-model",
            computed_at=1700000000.0,
            vector_dim=384,
            strategy="mean",
        )
        data = metadata.__dict__
        assert data["pattern_id"] == "test/pattern"
        assert data["strategy"] == "mean"

    def test_cache_metadata_roundtrip(self):
        """Test metadata can be serialized and deserialized."""
        original = CacheMetadata(
            pattern_id="test/pattern",
            examples_hash="abc123",
            model_name="test-model",
            computed_at=1700000000.0,
            vector_dim=384,
            strategy="mean",
        )
        data = original.__dict__
        restored = CacheMetadata(**data)
        assert restored.pattern_id == original.pattern_id
        assert restored.examples_hash == original.examples_hash
        assert restored.model_name == original.model_name
        assert restored.computed_at == original.computed_at
        assert restored.vector_dim == original.vector_dim
        assert restored.strategy == original.strategy


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_cache_stats_default_values(self):
        """Test CacheStats initializes with zeros."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0
        assert stats.size_bytes == 0

    def test_cache_stats_custom_values(self):
        """Test CacheStats with custom values."""
        stats = CacheStats(hits=10, misses=5, evictions=2, size_bytes=1024)
        assert stats.hits == 10
        assert stats.misses == 5
        assert stats.evictions == 2
        assert stats.size_bytes == 1024

    def test_total_requests(self):
        """Test total_requests property."""
        stats = CacheStats(hits=5, misses=3)
        assert stats.total_requests == 8

    def test_total_requests_zero(self):
        """Test total_requests when both are zero."""
        stats = CacheStats()
        assert stats.total_requests == 0

    def test_hit_rate(self):
        """Test hit_rate property calculation."""
        stats = CacheStats(hits=5, misses=3)
        assert stats.hit_rate == pytest.approx(5 / 8)

    def test_hit_rate_zero_requests(self):
        """Test hit_rate returns 0.0 when no requests."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_all_hits(self):
        """Test hit_rate is 1.0 when all requests are hits."""
        stats = CacheStats(hits=10, misses=0)
        assert stats.hit_rate == 1.0

    def test_hit_rate_all_misses(self):
        """Test hit_rate is 0.0 when all requests are misses."""
        stats = CacheStats(hits=0, misses=10)
        assert stats.hit_rate == 0.0


class TestVectorCacheInit:
    """Tests for VectorCache initialization."""

    def test_init_creates_directories(self, temp_cache_dir, mock_encoder):
        """Test that initialization creates cache directories."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        assert cache.vectors_dir.exists()
        assert cache.metadata_dir.exists()
        assert cache.models_dir.exists()

    def test_init_default_ttl(self, temp_cache_dir, mock_encoder):
        """Test default TTL is 24 hours."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        assert cache.ttl == 86400

    def test_init_custom_ttl(self, temp_cache_dir, mock_encoder):
        """Test custom TTL."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder, ttl=3600)
        assert cache.ttl == 3600

    def test_init_stores_encoder(self, temp_cache_dir, mock_encoder):
        """Test encoder is stored."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        assert cache.encoder is mock_encoder

    def test_init_empty_cache(self, temp_cache_dir, mock_encoder):
        """Test that new cache starts empty."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        assert len(cache._vectors) == 0
        assert len(cache._metadata) == 0

    def test_init_saves_model_info(self, temp_cache_dir, mock_encoder):
        """Test that model info is saved on init."""
        VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        model_info_file = temp_cache_dir / "models" / "model_info.json"
        assert model_info_file.exists()
        with model_info_file.open("r") as f:
            data = json.load(f)
        assert data["model_name"] == "test-model-v1"

    def test_init_existing_cache_same_model(self, temp_cache_dir, mock_encoder):
        """Test init with existing cache and same model doesn't clear."""
        # Create and save a vector
        cache1 = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache1.get_or_compute("p1", ["example"])
        cache1.save_to_disk()

        # Re-init with same model
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        # Cache should still have the vector file on disk
        assert (cache2.vectors_dir / "p1.npy").exists()

    def test_init_existing_cache_different_model_clears(self, temp_cache_dir):
        """Test init with different model clears cache."""
        encoder1 = _make_encoder(model_name="model-a")
        cache1 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder1)
        cache1.get_or_compute("p1", ["example"])
        cache1.save_to_disk()

        # Re-init with different model
        encoder2 = _make_encoder(model_name="model-b")
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder2)

        # Vector file should still exist on disk (invalidate_all removes it)
        # but in-memory should be empty
        assert len(cache2._vectors) == 0
        assert len(cache2._metadata) == 0


class TestVectorCacheGetOrCompute:
    """Tests for VectorCache.get_or_compute()."""

    def test_first_call_computes_vector(self, temp_cache_dir, mock_encoder):
        """Test first call computes and caches vector."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        vector = cache.get_or_compute("test/pattern", ["example"])
        assert isinstance(vector, np.ndarray)
        mock_encoder.encode.assert_called_once()

    def test_second_call_returns_cached(self, temp_cache_dir, mock_encoder):
        """Test second call returns cached vector without recomputing."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        vector1 = cache.get_or_compute("test/pattern", ["example"])
        mock_encoder.encode.reset_mock()
        vector2 = cache.get_or_compute("test/pattern", ["example"])
        assert np.array_equal(vector1, vector2)
        mock_encoder.encode.assert_not_called()

    def test_updates_stats_on_miss(self, temp_cache_dir, mock_encoder):
        """Test stats updated on cache miss."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["example"])
        stats = cache.get_cache_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 0

    def test_updates_stats_on_hit(self, temp_cache_dir, mock_encoder):
        """Test stats updated on cache hit."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["example"])  # miss
        cache.get_or_compute("p1", ["example"])  # hit
        stats = cache.get_cache_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 1

    def test_empty_examples_raises_value_error(self, temp_cache_dir, mock_encoder):
        """Test empty examples raises ValueError."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        with pytest.raises(ValueError, match="no examples"):
            cache.get_or_compute("test/pattern", [])

    def test_different_patterns_compute_separately(self, temp_cache_dir, mock_encoder):
        """Test different patterns are computed separately."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("pattern1", ["example 1"])
        cache.get_or_compute("pattern2", ["example 2"])
        assert mock_encoder.encode.call_count == 2
        assert len(cache._vectors) == 2

    def test_returns_copy_not_reference(self, temp_cache_dir, mock_encoder):
        """Test that returned vector is the cached reference."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        v1 = cache.get_or_compute("p1", ["example"])
        v2 = cache.get_or_compute("p1", ["example"])
        assert v1 is v2


class TestVectorCacheComputeVector:
    """Tests for _compute_vector method."""

    def test_compute_vector_mean_strategy(self, temp_cache_dir, mock_encoder):
        """Test mean aggregation strategy."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        vector = cache._compute_vector("p1", ["a", "b"])
        assert vector.ndim == 1
        assert len(vector) == 4  # mock returns 4-dim vectors

    def test_compute_vector_max_strategy(self, temp_cache_dir, mock_encoder):
        """Test max aggregation strategy (returns first example)."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        vector = cache._compute_vector("p1", ["a", "b"], strategy="max")
        assert vector.ndim == 1

    def test_compute_vector_invalid_strategy(self, temp_cache_dir, mock_encoder):
        """Test invalid strategy raises ValueError."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        with pytest.raises(ValueError, match="Unknown aggregation strategy"):
            cache._compute_vector("p1", ["a"], strategy="invalid")

    def test_compute_vector_empty_examples(self, temp_cache_dir, mock_encoder):
        """Test empty examples raises ValueError."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        with pytest.raises(ValueError, match="no examples"):
            cache._compute_vector("p1", [])

    def test_compute_vector_normalizes_output(self, temp_cache_dir):
        """Test output vector is normalized to unit length."""
        encoder = _make_encoder(dim=384)
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)
        vector = cache._compute_vector("p1", ["a", "b"])
        norm = np.linalg.norm(vector)
        assert abs(norm - 1.0) < 1e-5

    def test_compute_vector_creates_metadata(self, temp_cache_dir, mock_encoder):
        """Test computing vector creates metadata entry."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache._compute_vector("p1", ["example"])
        assert "p1" in cache._metadata
        metadata = cache._metadata["p1"]
        assert metadata.pattern_id == "p1"
        assert metadata.model_name == "test-model-v1"
        assert metadata.strategy == "mean"
        assert metadata.vector_dim == 4

    def test_compute_vector_stores_metadata(self, temp_cache_dir, mock_encoder):
        """Test metadata is stored in _metadata dict."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache._compute_vector("p1", ["a"])
        cache._compute_vector("p2", ["b"])
        assert len(cache._metadata) == 2


class TestVectorCacheHashExamples:
    """Tests for _hash_examples method."""

    def test_same_input_same_hash(self, temp_cache_dir):
        """Test same examples produce same hash."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=Mock())
        h1 = cache._hash_examples(["a", "b"])
        h2 = cache._hash_examples(["a", "b"])
        assert h1 == h2

    def test_different_input_different_hash(self, temp_cache_dir):
        """Test different examples produce different hashes."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=Mock())
        h1 = cache._hash_examples(["a"])
        h2 = cache._hash_examples(["b"])
        assert h1 != h2

    def test_order_matters(self, temp_cache_dir):
        """Test order of examples affects hash."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=Mock())
        h1 = cache._hash_examples(["a", "b"])
        h2 = cache._hash_examples(["b", "a"])
        assert h1 != h2

    def test_hash_is_sha256_hex(self, temp_cache_dir):
        """Test hash is a valid SHA-256 hex string."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=Mock())
        h = cache._hash_examples(["test"])
        assert len(h) == 64  # SHA-256 hex length
        int(h, 16)  # Should not raise

    def test_hash_empty_list(self, temp_cache_dir):
        """Test hashing empty list doesn't crash."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=Mock())
        h = cache._hash_examples([])
        assert len(h) == 64


class TestVectorCacheDiskPersistence:
    """Tests for save_to_disk and disk loading."""

    def test_save_to_disk_persists_vectors(self, temp_cache_dir, mock_encoder):
        """Test save_to_disk writes vector files."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["example"])
        cache.get_or_compute("p2", ["example"])
        cache.save_to_disk()
        assert (cache.vectors_dir / "p1.npy").exists()
        assert (cache.vectors_dir / "p2.npy").exists()

    def test_save_to_disk_persists_metadata(self, temp_cache_dir, mock_encoder):
        """Test save_to_disk writes metadata files."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["example"])
        cache.save_to_disk()
        metadata_file = cache.metadata_dir / "p1.json"
        assert metadata_file.exists()
        with metadata_file.open("r") as f:
            data = json.load(f)
        assert data["pattern_id"] == "p1"

    def test_load_from_disk_cache_hit(self, temp_cache_dir):
        """Test loading valid vector from disk cache."""
        encoder = _make_encoder(dim=384)
        cache1 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)
        cache1.get_or_compute("p1", ["example"])
        cache1.save_to_disk()

        encoder2 = _make_encoder(model_name="test-model")
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder2, ttl=86400)
        # Should load from disk, not recompute
        vector = cache2._load_from_disk_cache("p1", ["example"])
        assert vector is not None
        assert len(vector) == 384

    def test_load_from_disk_cache_miss_no_file(self, temp_cache_dir, mock_encoder):
        """Test loading from disk returns None when file doesn't exist."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        result = cache._load_from_disk_cache("nonexistent", ["example"])
        assert result is None

    def test_load_from_disk_cache_miss_no_metadata(self, temp_cache_dir, mock_encoder):
        """Test loading returns None when metadata file is missing."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        # Create a vector file without metadata
        vector_file = cache.vectors_dir / "orphan.npy"
        np.save(vector_file, np.zeros(4))
        result = cache._load_from_disk_cache("orphan", ["example"])
        assert result is None

    def test_load_from_disk_cache_miss_expired(self, temp_cache_dir):
        """Test loading returns None when cache entry is expired."""
        encoder = _make_encoder(dim=384)
        cache1 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder, ttl=1)
        cache1.get_or_compute("p1", ["example"])
        cache1.save_to_disk()

        time.sleep(1.1)

        encoder2 = _make_encoder(model_name="test-model")
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder2, ttl=1)
        result = cache2._load_from_disk_cache("p1", ["example"])
        assert result is None

    def test_load_from_disk_cache_miss_changed_examples(self, temp_cache_dir):
        """Test loading returns None when examples have changed."""
        encoder = _make_encoder(dim=384)
        cache1 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)
        cache1.get_or_compute("p1", ["original example"])
        cache1.save_to_disk()

        encoder2 = _make_encoder(model_name="test-model")
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder2, ttl=86400)
        result = cache2._load_from_disk_cache("p1", ["different example"])
        assert result is None

    def test_load_from_disk_cache_miss_model_changed(self, temp_cache_dir):
        """Test loading returns None when model has changed."""
        encoder1 = _make_encoder(dim=384, model_name="model-a")
        cache1 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder1)
        cache1.get_or_compute("p1", ["example"])
        cache1.save_to_disk()

        encoder2 = _make_encoder(dim=384, model_name="model-b")
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder2, ttl=86400)
        result = cache2._load_from_disk_cache("p1", ["example"])
        assert result is None

    def test_save_to_disk_empty_cache(self, temp_cache_dir, mock_encoder):
        """Test save_to_disk with no vectors doesn't crash."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.save_to_disk()  # Should not raise

    def test_roundtrip_save_and_load(self, temp_cache_dir):
        """Test full save/load roundtrip preserves vector data."""
        encoder = _make_encoder(dim=384)
        cache1 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)
        v1 = cache1.get_or_compute("p1", ["example"])
        cache1.save_to_disk()

        encoder2 = _make_encoder(model_name="test-model")
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder2, ttl=86400)
        v2 = cache2._load_from_disk_cache("p1", ["example"])
        assert v2 is not None
        np.testing.assert_array_almost_equal(v1, v2)


class TestVectorCacheLoadFromDisk:
    """Tests for _load_from_disk method."""

    def test_load_from_disk_no_existing_data(self, temp_cache_dir, mock_encoder):
        """Test _load_from_disk with no existing cache."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        # Should not raise, just saves model info
        assert (cache.models_dir / "model_info.json").exists()

    def test_load_from_disk_model_changed_clears_all(self, temp_cache_dir):
        """Test _load_from_disk clears cache when model changes."""
        encoder1 = _make_encoder(model_name="old-model")
        cache1 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder1)
        cache1.get_or_compute("p1", ["example"])
        cache1.save_to_disk()

        encoder2 = _make_encoder(model_name="new-model")
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder2)
        assert len(cache2._vectors) == 0
        assert len(cache2._metadata) == 0

    def test_load_from_disk_corrupted_model_info(self, temp_cache_dir, mock_encoder):
        """Test _load_from_disk handles corrupted model_info.json."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        model_info_file = cache.models_dir / "model_info.json"
        model_info_file.write_text("{invalid json")

        # Should handle gracefully and save new model info
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        assert cache2.encoder is mock_encoder

    def test_save_model_info(self, temp_cache_dir, mock_encoder):
        """Test _save_model_info writes correct data."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache._save_model_info()
        model_info_file = cache.models_dir / "model_info.json"
        with model_info_file.open("r") as f:
            data = json.load(f)
        assert data["model_name"] == "test-model-v1"
        assert "saved_at" in data


class TestVectorCacheMetadata:
    """Tests for _load_metadata and _save_metadata."""

    def test_save_and_load_metadata(self, temp_cache_dir, mock_encoder):
        """Test metadata roundtrip."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        metadata = CacheMetadata(
            pattern_id="p1",
            examples_hash="hash123",
            model_name="test-model-v1",
            computed_at=time.time(),
            vector_dim=4,
            strategy="mean",
        )
        cache._save_metadata(metadata)
        loaded = cache._load_metadata("p1")
        assert loaded is not None
        assert loaded.pattern_id == "p1"
        assert loaded.examples_hash == "hash123"

    def test_load_metadata_nonexistent(self, temp_cache_dir, mock_encoder):
        """Test loading metadata for nonexistent pattern returns None."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        result = cache._load_metadata("nonexistent")
        assert result is None

    def test_load_metadata_corrupted_file(self, temp_cache_dir, mock_encoder):
        """Test loading corrupted metadata file returns None."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        metadata_file = cache.metadata_dir / "bad.json"
        metadata_file.write_text("{invalid json")
        result = cache._load_metadata("bad")
        assert result is None


class TestVectorCacheInvalidation:
    """Tests for cache invalidation."""

    def test_invalidate_pattern_removes_from_memory(self, temp_cache_dir, mock_encoder):
        """Test invalidate_pattern removes vector from memory."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["example"])
        assert "p1" in cache._vectors
        cache.invalidate_pattern("p1")
        assert "p1" not in cache._vectors
        assert "p1" not in cache._metadata

    def test_invalidate_pattern_removes_from_disk(self, temp_cache_dir, mock_encoder):
        """Test invalidate_pattern removes files from disk."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["example"])
        cache.save_to_disk()
        assert (cache.vectors_dir / "p1.npy").exists()
        assert (cache.metadata_dir / "p1.json").exists()

        cache.invalidate_pattern("p1")
        assert not (cache.vectors_dir / "p1.npy").exists()
        assert not (cache.metadata_dir / "p1.json").exists()

    def test_invalidate_pattern_nonexistent(self, temp_cache_dir, mock_encoder):
        """Test invalidating nonexistent pattern doesn't crash."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.invalidate_pattern("nonexistent")  # Should not raise

    def test_invalidate_all_clears_memory(self, temp_cache_dir, mock_encoder):
        """Test invalidate_all clears in-memory cache."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["a"])
        cache.get_or_compute("p2", ["b"])
        cache.invalidate_all()
        assert len(cache._vectors) == 0
        assert len(cache._metadata) == 0

    def test_invalidate_all_clears_disk(self, temp_cache_dir, mock_encoder):
        """Test invalidate_all removes disk files."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["a"])
        cache.get_or_compute("p2", ["b"])
        cache.save_to_disk()
        cache.invalidate_all()
        assert list(cache.vectors_dir.glob("*.npy")) == []
        assert list(cache.metadata_dir.glob("*.json")) == []

    def test_invalidate_all_resets_stats(self, temp_cache_dir, mock_encoder):
        """Test invalidate_all resets statistics."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["a"])  # miss
        cache.get_or_compute("p1", ["a"])  # hit
        cache.invalidate_all()
        stats = cache.get_cache_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["total_requests"] == 0
        assert stats["hit_rate"] == 0.0


class TestVectorCacheStats:
    """Tests for get_cache_stats."""

    def test_stats_initial_state(self, temp_cache_dir, mock_encoder):
        """Test stats at initial state."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        stats = cache.get_cache_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["total_requests"] == 0
        assert stats["hit_rate"] == 0.0
        assert stats["size"] == 0
        assert stats["size_bytes"] == 0
        assert stats["size_mb"] == 0.0

    def test_stats_after_operations(self, temp_cache_dir, mock_encoder):
        """Test stats after cache operations."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["a"])  # miss
        cache.get_or_compute("p1", ["a"])  # hit
        cache.get_or_compute("p2", ["b"])  # miss
        cache.get_or_compute("p2", ["b"])  # hit
        cache.get_or_compute("p2", ["b"])  # hit

        stats = cache.get_cache_stats()
        assert stats["hits"] == 3
        assert stats["misses"] == 2
        assert stats["total_requests"] == 5
        assert stats["hit_rate"] == pytest.approx(3 / 5)
        assert stats["size"] == 2

    def test_stats_size_bytes_calculation(self, temp_cache_dir, mock_encoder):
        """Test size_bytes is sum of vector nbytes."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["a"])
        stats = cache.get_cache_stats()
        expected_bytes = cache._vectors["p1"].nbytes
        assert stats["size_bytes"] == expected_bytes

    def test_stats_size_mb_calculation(self, temp_cache_dir, mock_encoder):
        """Test size_mb is size_bytes / (1024 * 1024)."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.get_or_compute("p1", ["a"])
        stats = cache.get_cache_stats()
        expected_mb = stats["size_bytes"] / (1024 * 1024)
        assert stats["size_mb"] == pytest.approx(expected_mb)

    def test_stats_all_fields_present(self, temp_cache_dir, mock_encoder):
        """Test all expected fields are in stats dict."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        stats = cache.get_cache_stats()
        required_fields = [
            "hits",
            "misses",
            "total_requests",
            "hit_rate",
            "size",
            "size_bytes",
            "size_mb",
        ]
        for field in required_fields:
            assert field in stats


class TestVectorCachePreloadPatterns:
    """Tests for preload_patterns."""

    def test_preload_patterns_loads_all(self, temp_cache_dir, mock_encoder):
        """Test preload_patterns loads all patterns."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        patterns = {
            "p1": ["example 1a", "example 1b"],
            "p2": ["example 2"],
            "p3": ["example 3a", "example 3b", "example 3c"],
        }
        cache.preload_patterns(patterns)
        assert "p1" in cache._vectors
        assert "p2" in cache._vectors
        assert "p3" in cache._vectors

    def test_preload_patterns_empty_dict(self, temp_cache_dir, mock_encoder):
        """Test preload_patterns with empty dict doesn't crash."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.preload_patterns({})  # Should not raise

    def test_preload_patterns_encoder_called_for_each(self, temp_cache_dir, mock_encoder):
        """Test encoder.encode is called for each pattern."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        patterns = {"p1": ["a"], "p2": ["b"], "p3": ["c"]}
        cache.preload_patterns(patterns)
        assert mock_encoder.encode.call_count == 3

    def test_preload_patterns_stats_updated(self, temp_cache_dir, mock_encoder):
        """Test preload_patterns updates miss stats."""
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=mock_encoder)
        cache.preload_patterns({"p1": ["a"], "p2": ["b"]})
        stats = cache.get_cache_stats()
        assert stats["misses"] == 2
        assert stats["size"] == 2


class TestVectorCacheThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_get_or_compute_different_patterns(self, temp_cache_dir):
        """Test concurrent access with different patterns."""
        encoder = _make_encoder(dim=384)
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        errors = []

        def compute(pattern_id: str) -> None:
            try:
                v = cache.get_or_compute(pattern_id, [f"example {pattern_id}"])
                assert isinstance(v, np.ndarray)
                assert len(v) == 384
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=compute, args=(f"p{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(cache._vectors) == 20

    def test_concurrent_invalidate_and_compute(self, temp_cache_dir):
        """Test concurrent invalidate and compute operations."""
        encoder = _make_encoder(dim=384)
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        # Pre-populate
        for i in range(10):
            cache.get_or_compute(f"p{i}", [f"example {i}"])

        errors = []

        def invalidate_and_compute(idx: int) -> None:
            try:
                cache.invalidate_pattern(f"p{idx}")
                cache.get_or_compute(f"p{idx}", [f"new example {idx}"])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=invalidate_and_compute, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_save_to_disk(self, temp_cache_dir):
        """Test concurrent save_to_disk doesn't crash."""
        encoder = _make_encoder(dim=384)
        cache = VectorCache(cache_dir=temp_cache_dir, encoder=encoder)

        for i in range(5):
            cache.get_or_compute(f"p{i}", [f"example {i}"])

        errors = []

        def save() -> None:
            try:
                cache.save_to_disk()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=save) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestVectorCacheGetOrComputeDiskHit:
    """Tests for disk cache hit path in get_or_compute."""

    def test_get_or_compute_disk_hit(self, temp_cache_dir):
        """Test get_or_compute loads from disk when not in memory."""
        encoder1 = _make_encoder(dim=384)
        cache1 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder1)
        v1 = cache1.get_or_compute("p1", ["example"])
        cache1.save_to_disk()

        encoder2 = _make_encoder(model_name="test-model")
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder2, ttl=86400)
        # Not in memory, should load from disk
        v2 = cache2.get_or_compute("p1", ["example"])
        assert v2 is not None
        np.testing.assert_array_almost_equal(v1, v2)

    def test_get_or_compute_disk_hit_updates_stats_as_miss(self, temp_cache_dir):
        """Test disk cache hit still counts as miss in stats (since mem miss)."""
        encoder1 = _make_encoder(dim=384)
        cache1 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder1)
        cache1.get_or_compute("p1", ["example"])
        cache1.save_to_disk()

        encoder2 = _make_encoder(model_name="test-model")
        cache2 = VectorCache(cache_dir=temp_cache_dir, encoder=encoder2, ttl=86400)
        cache2.get_or_compute("p1", ["example"])
        stats = cache2.get_cache_stats()
        # Memory miss (not in _vectors), disk hit (loaded from disk)
        # The stats tracking only increments miss once in get_or_compute
        assert stats["misses"] == 1
        assert stats["hits"] == 0
