"""Test cache manager for AI routing results."""

import shutil
import tempfile
import time
from pathlib import Path

from vibesop.core.routing.cache import CacheEntry, CacheManager, CacheStats


class TestCacheEntry:
    """Test CacheEntry dataclass."""

    def test_create_entry(self) -> None:
        """Test creating a cache entry."""
        entry = CacheEntry(data={"skill": "/review"})

        assert entry.data == {"skill": "/review"}
        assert entry.ttl == 86400  # default

    def test_is_expired_false(self) -> None:
        """Test expiration check for fresh entry."""
        entry = CacheEntry(data={"skill": "/review"}, ttl=3600)

        assert not entry.is_expired()

    def test_is_expired_true(self) -> None:
        """Test expiration check for old entry."""
        # Create entry in the past
        entry = CacheEntry(data={"skill": "/review"}, ttl=0)

        # Small delay to ensure expiration
        time.sleep(0.01)

        assert entry.is_expired()


class TestCacheStats:
    """Test CacheStats class."""

    def test_initial_stats(self) -> None:
        """Test initial statistics."""
        stats = CacheStats()

        assert stats.memory_hits == 0
        assert stats.file_hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0

    def test_record_memory_hit(self) -> None:
        """Test recording memory cache hit."""
        stats = CacheStats()
        stats.record_hit(is_memory=True)

        assert stats.memory_hits == 1
        assert stats.file_hits == 0
        assert stats.hit_rate == 1.0

    def test_record_file_hit(self) -> None:
        """Test recording file cache hit."""
        stats = CacheStats()
        stats.record_hit(is_memory=False)

        assert stats.memory_hits == 0
        assert stats.file_hits == 1
        assert stats.hit_rate == 1.0

    def test_record_miss(self) -> None:
        """Test recording cache miss."""
        stats = CacheStats()
        stats.record_miss()

        assert stats.misses == 1
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self) -> None:
        """Test hit rate calculation."""
        stats = CacheStats()

        # 2 hits, 1 miss
        stats.record_hit(is_memory=True)
        stats.record_hit(is_memory=False)
        stats.record_miss()

        assert stats.hit_rate == 2 / 3

    def test_hit_rate_zero_requests(self) -> None:
        """Test hit rate with no requests."""
        stats = CacheStats()

        assert stats.hit_rate == 0.0


class TestCacheManager:
    """Test CacheManager class."""

    def _create_manager(self) -> CacheManager:
        """Helper to create a manager with temp cache dir."""
        tmpdir = Path(tempfile.mkdtemp())
        return CacheManager(cache_dir=tmpdir / "cache")

    def test_init_creates_cache_dir(self) -> None:
        """Test initialization creates cache directory."""
        tmpdir = Path(tempfile.mkdtemp())
        cache_dir = tmpdir / "cache"

        CacheManager(cache_dir=cache_dir)

        assert cache_dir.exists()

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_set_and_get_memory_cache(self) -> None:
        """Test setting and getting from memory cache."""
        manager = self._create_manager()

        manager.set("test_key", {"skill": "/review"})

        result = manager.get("test_key")

        assert result == {"skill": "/review"}
        assert manager.stats()["memory_hits"] == 1

    def test_get_nonexistent_key(self) -> None:
        """Test getting nonexistent key returns None."""
        manager = self._create_manager()

        result = manager.get("nonexistent")

        assert result is None
        assert manager.stats()["misses"] == 1

    def test_set_with_custom_ttl(self) -> None:
        """Test setting entry with custom TTL."""
        manager = self._create_manager()

        manager.set("test_key", {"skill": "/review"}, ttl=1)

        # Should be available immediately
        assert manager.get("test_key") is not None

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        assert manager.get("test_key") is None

    def test_expired_memory_entry_removed(self) -> None:
        """Test expired memory entries are removed."""
        manager = self._create_manager()

        manager.set("test_key", {"skill": "/review"}, ttl=0)
        time.sleep(0.01)

        # First access - should find entry expired and remove it
        assert manager.get("test_key") is None

        # Second access - should miss (entry was removed)
        assert manager.get("test_key") is None

        # Check memory cache is empty
        assert manager.stats()["memory_size"] == 0

    def test_file_cache_persistence(self) -> None:
        """Test file cache persists across manager instances."""
        tmpdir = Path(tempfile.mkdtemp())
        cache_dir = tmpdir / "cache"

        # Create first manager and set value
        manager1 = CacheManager(cache_dir=cache_dir)
        manager1.set("test_key", {"skill": "/review"})

        # Create second manager with same cache dir
        manager2 = CacheManager(cache_dir=cache_dir)
        result = manager2.get("test_key")

        assert result == {"skill": "/review"}
        assert manager2.stats()["file_hits"] == 1

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_file_cache_promotes_to_memory(self) -> None:
        """Test file cache hit promotes to memory cache."""
        manager = self._create_manager()

        # Set value (both memory and file)
        manager.set("test_key", {"skill": "/review"})

        # Clear memory cache
        manager._memory_cache.clear()

        # Get from file cache
        result = manager.get("test_key")

        assert result is not None
        assert manager.stats()["file_hits"] == 1

        # Should now be in memory cache
        assert "test_key" in manager._memory_cache

        # Second get should hit memory
        manager.get("test_key")
        assert manager.stats()["memory_hits"] == 1

    def test_expired_file_cache_removed(self) -> None:
        """Test expired file cache entries are removed."""
        manager = self._create_manager()

        manager.set("test_key", {"skill": "/review"}, ttl=0)
        time.sleep(0.01)

        # Clear memory to force file access
        manager._memory_cache.clear()

        # Should find file entry expired and remove it
        assert manager.get("test_key") is None

        # File should be removed
        file_path = manager._get_file_path("test_key")
        assert not file_path.exists()

    def test_clear_memory_cache(self) -> None:
        """Test clearing memory cache."""
        manager = self._create_manager()

        manager.set("key1", {"skill": "/review"})
        manager.set("key2", {"skill": "/debug"})

        assert manager.stats()["memory_size"] == 2

        manager.clear()

        assert manager.stats()["memory_size"] == 0
        assert manager.get("key1") is None
        assert manager.get("key2") is None

    def test_clear_file_cache(self) -> None:
        """Test clearing file cache."""
        manager = self._create_manager()

        manager.set("key1", {"skill": "/review"})
        manager.set("key2", {"skill": "/debug"})

        # Verify files exist
        assert manager._get_file_path("key1").exists()
        assert manager._get_file_path("key2").exists()

        manager.clear()

        # Files should be removed
        assert not manager._get_file_path("key1").exists()
        assert not manager._get_file_path("key2").exists()

    def test_stats(self) -> None:
        """Test cache statistics."""
        manager = self._create_manager()

        # Do some operations
        manager.set("key1", {"skill": "/review"})
        manager.get("key1")  # Hit
        manager.get("key2")  # Miss

        stats = manager.stats()

        assert stats["memory_hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["memory_size"] == 1

    def test_generate_key_basic(self) -> None:
        """Test basic key generation."""
        manager = self._create_manager()

        key = manager.generate_key("review my code")

        assert len(key) == 16
        assert isinstance(key, str)

    def test_generate_key_with_context(self) -> None:
        """Test key generation with context."""
        manager = self._create_manager()

        key1 = manager.generate_key("review code", {"file_type": "py"})
        key2 = manager.generate_key("review code", {"file_type": "js"})

        # Different context should produce different keys
        assert key1 != key2

    def test_generate_key_normalization(self) -> None:
        """Test key generation normalizes input."""
        manager = self._create_manager()

        # Numbers should be normalized
        key1 = manager.generate_key("fix error 123")
        key2 = manager.generate_key("fix error 456")

        assert key1 == key2

        # Case should be normalized
        key3 = manager.generate_key("REVIEW CODE")
        key4 = manager.generate_key("review code")

        assert key3 == key4

    def test_generate_key_ignores_irrelevant_context(self) -> None:
        """Test irrelevant context is ignored."""
        manager = self._create_manager()

        key1 = manager.generate_key("test", {"irrelevant": "value", "file_type": "py"})
        key2 = manager.generate_key("test", {"other": "value", "file_type": "py"})

        # Only file_type and has_errors are relevant
        assert key1 == key2

    def test_memory_cache_lru_eviction(self) -> None:
        """Test LRU eviction when memory cache is full."""
        # Create manager with small cache
        tmpdir = Path(tempfile.mkdtemp())
        manager = CacheManager(cache_dir=tmpdir / "cache", memory_cache_max_size=2)

        # Add 3 entries (max is 2)
        manager.set("key1", {"skill": "1"})
        manager.set("key2", {"skill": "2"})
        manager.set("key3", {"skill": "3"})

        # First entry evicted from memory but still in file cache
        assert manager.get("key1") is not None  # File cache hit
        assert manager.get("key2") is not None  # Memory cache hit
        assert manager.get("key3") is not None  # Memory cache hit

        # Verify memory cache size is at max
        assert len(manager._memory_cache) == 2

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_normalize_for_cache(self) -> None:
        """Test input normalization for cache."""
        manager = self._create_manager()

        # Numbers
        assert manager._normalize_for_cache("error 123") == "error n"
        assert manager._normalize_for_cache("fix 456 bug") == "fix n bug"

        # Quoted content
        assert manager._normalize_for_cache('say "hello world"') == "say x"
        assert manager._normalize_for_cache("say 'foo bar'") == "say x"

        # Whitespace
        assert manager._normalize_for_cache("too    much   space") == "too much space"

        # Case
        assert manager._normalize_for_cache("HELLO") == "hello"

    def test_extract_relevant_context(self) -> None:
        """Test extracting relevant context."""
        manager = self._create_manager()

        context = {
            "file_type": "py",
            "error_count": 5,
            "irrelevant": "stuff",
        }

        relevant = manager._extract_relevant_context(context)

        assert relevant == {"file_type": "py", "has_errors": True}

    def test_extract_relevant_context_no_errors(self) -> None:
        """Test context with no errors."""
        manager = self._create_manager()

        context = {"file_type": "js", "error_count": 0}

        relevant = manager._extract_relevant_context(context)

        assert relevant == {"file_type": "js", "has_errors": False}

    def test_corrupted_file_cache_skipped(self) -> None:
        """Test corrupted cache files are skipped."""
        manager = self._create_manager()

        # Write a corrupted file
        file_path = manager._get_file_path("corrupted")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("not valid json")

        # Should return None and not crash
        assert manager.get("corrupted") is None

    def test_empty_input_normalization(self) -> None:
        """Test normalizing empty input."""
        manager = self._create_manager()

        result = manager._normalize_for_cache("")

        assert result == ""

    def test_set_updates_existing_entry(self) -> None:
        """Test updating existing cache entry."""
        manager = self._create_manager()

        manager.set("key", {"skill": "/review"})
        manager.set("key", {"skill": "/debug"})

        result = manager.get("key")

        assert result == {"skill": "/debug"}
