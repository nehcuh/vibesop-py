"""Cache manager for AI routing results.

Provides multi-level caching:
1. In-memory cache (fastest) with true LRU eviction
2. File-based cache (persistent)

Cache keys are generated from normalized input and relevant context.
"""

import builtins
import collections
import contextlib
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibesop.constants import CacheSettings


@dataclass
class CacheEntry:
    """A cache entry with TTL."""

    data: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    ttl: int = CacheSettings.DEFAULT_TTL

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl


@dataclass
class CacheStats:
    """Cache statistics."""

    memory_hits: int = 0
    file_hits: int = 0
    misses: int = 0
    _total_requests: int = 0

    @property
    def hit_rate(self) -> float:
        if self._total_requests == 0:
            return 0.0
        hits = self.memory_hits + self.file_hits
        return hits / self._total_requests

    def record_hit(self, is_memory: bool = True) -> None:
        self._total_requests += 1
        if is_memory:
            self.memory_hits += 1
        else:
            self.file_hits += 1

    def record_miss(self) -> None:
        self._total_requests += 1
        self.misses += 1


class CacheManager:
    """Multi-level cache manager with true LRU eviction.

    Uses OrderedDict to implement proper LRU (Least Recently Used) eviction.
    On every cache hit, the entry is moved to the end (most recently used).
    When eviction is needed, the first entry (least recently used) is removed.

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
        if cache_dir is None:
            base_dir = Path.cwd()
            cache_dir = base_dir / ".vibe" / CacheSettings.DEFAULT_CACHE_DIR

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.memory_cache_max_size = min(memory_cache_max_size, CacheSettings.MAX_CACHE_SIZE)
        self._memory_cache: collections.OrderedDict[str, CacheEntry] = collections.OrderedDict()
        self._stats = CacheStats()

    def get(self, key: str) -> dict[str, Any] | None:
        """Get value from cache. Checks memory first, then file."""
        # Check memory cache
        if key in self._memory_cache:
            entry = self._memory_cache[key]
            if entry.is_expired():
                del self._memory_cache[key]
            else:
                self._memory_cache.move_to_end(key)
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
                    file_path.unlink()
                else:
                    self._set_memory_cache(key, entry)
                    self._stats.record_hit(is_memory=False)
                    return entry.data
            except (OSError, json.JSONDecodeError):
                pass

        self._stats.record_miss()
        return None

    def set(
        self,
        key: str,
        data: dict[str, Any],
        ttl: int = 86400,
        original_query: str | None = None,
    ) -> None:
        """Set value in both memory and file cache.

        Args:
            key: Cache key.
            data: Data to cache.
            ttl: Time-to-live in seconds.
            original_query: Optional original query text for semantic similarity matching.
        """
        if original_query is not None:
            data = dict(data)
            data["_cache_original_query"] = original_query
        entry = CacheEntry(data=data, ttl=ttl)
        self._set_memory_cache(key, entry)
        self._set_file_cache(key, entry)

    def clear(self) -> None:
        """Clear all cache."""
        self._memory_cache.clear()
        for cache_file in self.cache_dir.glob("cache_*.json"):
            with contextlib.suppress(OSError):
                cache_file.unlink()

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
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
        """Generate a cache key from input and context."""
        normalized = self._normalize_for_cache(input_text)
        relevant_context = self._extract_relevant_context(context or {})
        base = f"{normalized}:{json.dumps(relevant_context, sort_keys=True)}"
        return hashlib.sha256(base.encode()).hexdigest()[:16]

    def _set_memory_cache(self, key: str, entry: CacheEntry) -> None:
        """Set value in memory cache with true LRU eviction.

        Uses OrderedDict.move_to_end() for O(1) LRU maintenance.
        Evicts the least recently used entry when at capacity.
        """
        if len(self._memory_cache) >= self.memory_cache_max_size:
            self._memory_cache.popitem(last=False)

        self._memory_cache[key] = entry
        self._memory_cache.move_to_end(key)

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
            pass

    def _get_file_path(self, key: str) -> Path:
        return self.cache_dir / f"cache_{key}.json"

    def _normalize_for_cache(self, input_text: str) -> str:
        normalized = re.sub(r"\d+", "N", input_text)
        normalized = re.sub(r"['\"].*?['\"]", "X", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip().lower()

    def _extract_relevant_context(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "file_type": context.get("file_type"),
            "has_errors": bool(context.get("error_count", 0)),
        }

    def get_similar(
        self, query: str, similarity_threshold: float = 0.75
    ) -> dict[str, Any] | None:
        """Find a cached result for a semantically similar query.

        Uses character bigram Jaccard similarity for fast approximate
        matching without external dependencies. Falls back to exact match
        if no similar query is found.

        Args:
            query: The query to find a similar match for.
            similarity_threshold: Minimum similarity score (0.0-1.0).

        Returns:
            Cached data if a similar query is found, None otherwise.
        """
        if not self._memory_cache:
            return None

        query_bigrams = self._char_bigrams(query.lower())
        if not query_bigrams:
            return None

        best_match: tuple[str, float] | None = None
        for cached_key, entry in self._memory_cache.items():
            # Check if entry has stored original query text
            original_query = entry.data.get("_cache_original_query", "")
            if not original_query:
                continue

            cached_bigrams = self._char_bigrams(original_query.lower())
            if not cached_bigrams:
                continue

            similarity = self._jaccard_similarity(query_bigrams, cached_bigrams)
            if similarity >= similarity_threshold and (best_match is None or similarity > best_match[1]):
                best_match = (cached_key, similarity)

        if best_match:
            cached_key, _similarity = best_match
            entry = self._memory_cache[cached_key]
            if not entry.is_expired():
                self._memory_cache.move_to_end(cached_key)
                self._stats.record_hit(is_memory=True)
                return entry.data

        return None

    @staticmethod
    def _char_bigrams(text: str) -> builtins.set[str]:
        """Extract character bigrams from text."""
        return {text[i : i + 2] for i in range(len(text) - 1)}

    @staticmethod
    def _jaccard_similarity(set_a: builtins.set[str], set_b: builtins.set[str]) -> float:
        """Compute Jaccard similarity between two sets."""
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0
