"""Cache manager for AI routing results.

Provides multi-level caching:
1. In-memory cache (fastest)
2. File-based cache (persistent)

Cache keys are generated from normalized input and relevant context.
"""

import contextlib
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibesop.constants import CacheSettings


@dataclass
class CacheEntry:
    """A cache entry with TTL.

    Attributes:
        data: Cached data
        created_at: Timestamp when entry was created
        ttl: Time-to-live in seconds
    """

    data: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    ttl: int = CacheSettings.DEFAULT_TTL

    def is_expired(self) -> bool:
        """Check if entry is expired."""
        return time.time() - self.created_at > self.ttl


@dataclass
class CacheStats:
    """Cache statistics.

    Attributes:
        memory_hits: Number of memory cache hits
        file_hits: Number of file cache hits
        misses: Number of cache misses
        hit_rate: Cache hit rate (0.0 to 1.0)
    """

    memory_hits: int = 0
    file_hits: int = 0
    misses: int = 0
    _total_requests: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        if self._total_requests == 0:
            return 0.0
        hits = self.memory_hits + self.file_hits
        return hits / self._total_requests

    def record_hit(self, is_memory: bool = True) -> None:
        """Record a cache hit."""
        self._total_requests += 1
        if is_memory:
            self.memory_hits += 1
        else:
            self.file_hits += 1

    def record_miss(self) -> None:
        """Record a cache miss."""
        self._total_requests += 1
        self.misses += 1


class CacheManager:
    """Multi-level cache manager for AI routing results.

    Usage:
        cache = CacheManager(cache_dir=".vibe/cache")
        cache.set("key", {"skill": "/review"})
        result = cache.get("key")
        print(cache.stats())
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        memory_cache_max_size: int = 500,
    ) -> None:
        """Initialize the cache manager.

        Args:
            cache_dir: Directory for file-based cache (default: from constants)
            memory_cache_max_size: Max entries in memory cache
        """
        if cache_dir is None:
            base_dir = Path(os.getcwd())
            cache_dir = base_dir / ".vibe" / CacheSettings.DEFAULT_CACHE_DIR

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.memory_cache_max_size = min(memory_cache_max_size, CacheSettings.MAX_CACHE_SIZE)
        self._memory_cache: dict[str, CacheEntry] = {}
        self._stats = CacheStats()

    def get(self, key: str) -> dict[str, Any] | None:
        """Get value from cache.

        Checks memory cache first, then file cache.

        Args:
            key: Cache key

        Returns:
            Cached data or None if not found/expired
        """
        # Check memory cache first
        if key in self._memory_cache:
            entry = self._memory_cache[key]
            if entry.is_expired():
                del self._memory_cache[key]
            else:
                self._stats.record_hit(is_memory=True)
                return entry.data

        # Check file cache
        file_path = self._get_file_path(key)
        if file_path.exists():
            try:
                with file_path.open("r") as f:
                    entry_data = json.load(f)
                entry = CacheEntry(**entry_data)

                if entry.is_expired():
                    file_path.unlink()  # Remove expired file
                else:
                    # Promote to memory cache
                    self._set_memory_cache(key, entry)
                    self._stats.record_hit(is_memory=False)
                    return entry.data
            except (OSError, json.JSONDecodeError):
                # File corrupted or unreadable, skip
                pass

        self._stats.record_miss()
        return None

    def set(
        self,
        key: str,
        data: dict[str, Any],
        ttl: int = 86400,
    ) -> None:
        """Set value in cache.

        Stores in both memory and file cache.

        Args:
            key: Cache key
            data: Data to cache
            ttl: Time-to-live in seconds
        """
        entry = CacheEntry(data=data, ttl=ttl)

        # Set in memory cache
        self._set_memory_cache(key, entry)

        # Set in file cache
        self._set_file_cache(key, entry)

    def clear(self) -> None:
        """Clear all cache."""
        self._memory_cache.clear()

        # Clear file cache
        for cache_file in self.cache_dir.glob("cache_*.json"):
            with contextlib.suppress(OSError):
                cache_file.unlink()

    def stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return {
            "memory_hits": self._stats.memory_hits,
            "file_hits": self._stats.file_hits,
            "misses": self._stats.misses,
            "hit_rate": round(self._stats.hit_rate, 2),
            "memory_size": len(self._memory_cache),
        }

    def generate_key(
        self,
        input_text: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Generate a cache key from input and context.

        Args:
            input_text: Normalized input text
            context: Optional context dict

        Returns:
            Cache key (SHA256 hash)
        """
        normalized = self._normalize_for_cache(input_text)
        relevant_context = self._extract_relevant_context(context or {})

        # Create hash from normalized input + context
        base = f"{normalized}:{json.dumps(relevant_context, sort_keys=True)}"
        return hashlib.sha256(base.encode()).hexdigest()[:16]

    def _set_memory_cache(self, key: str, entry: CacheEntry) -> None:
        """Set value in memory cache with LRU eviction."""
        # Evict oldest if at capacity
        if len(self._memory_cache) >= self.memory_cache_max_size:
            # Simple FIFO eviction (could use LRU for better performance)
            oldest_key = next(iter(self._memory_cache))
            del self._memory_cache[oldest_key]

        self._memory_cache[key] = entry

    def _set_file_cache(self, key: str, entry: CacheEntry) -> None:
        """Set value in file cache."""
        file_path = self._get_file_path(key)

        try:
            with file_path.open("w") as f:
                json.dump(
                    {
                        "data": entry.data,
                        "created_at": entry.created_at,
                        "ttl": entry.ttl,
                    },
                    f,
                )
        except OSError:
            # Fail silently if file write fails
            pass

    def _get_file_path(self, key: str) -> Path:
        """Get file path for cache key."""
        return self.cache_dir / f"cache_{key}.json"

    def _normalize_for_cache(self, input_text: str) -> str:
        """Normalize input text for cache key."""
        # Normalize numbers
        normalized = re.sub(r"\d+", "N", input_text)
        # Normalize quoted content
        normalized = re.sub(r"['\"].*?['\"]", "X", normalized)
        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip().lower()

    def _extract_relevant_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Extract only relevant context for caching."""
        return {
            "file_type": context.get("file_type"),
            "has_errors": bool(context.get("error_count", 0)),
        }
