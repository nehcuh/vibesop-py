"""Vector cache management for semantic pattern matching.

This module provides efficient caching of pre-computed semantic vectors
for patterns, with disk persistence and intelligent cache invalidation.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from vibesop.semantic.encoder import SemanticEncoder

logger = logging.getLogger(__name__)


@dataclass
class CacheMetadata:
    """Metadata for a cached vector."""

    pattern_id: str
    examples_hash: str  # Hash of examples used to compute vector
    model_name: str
    computed_at: float  # Unix timestamp
    vector_dim: int
    strategy: str = "mean"  # Aggregation strategy used


@dataclass
class CacheStats:
    """Statistics for the vector cache."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size_bytes: int = 0

    @property
    def total_requests(self) -> int:
        """Total number of cache requests."""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0-1)."""
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests


class VectorCache:
    """Vector cache manager for semantic pattern matching.

    This class manages pre-computed semantic vectors for patterns, providing
    efficient caching with disk persistence and intelligent invalidation.

    Features:
        - Pre-computation: Calculate pattern vectors at startup
        - Disk persistence: Save vectors to disk for fast loading
        - Incremental updates: Only recompute when patterns change
        - Version control: Automatic cache invalidation on model change
        - Thread-safe: Safe for concurrent access

    Cache Structure:
        .vibe/cache/semantic/
        ├── vectors/               # Vector files (.npy)
        │   ├── security_scan.npy
        │   ├── dev_test.npy
        │   └── ...
        ├── metadata/              # Cache metadata
        │   └── cache_index.json
        └── models/                # Model information
            └── model_info.json

    Example:
        >>> encoder = SemanticEncoder()
        >>> cache = VectorCache(cache_dir=Path(".vibe/cache/semantic"), encoder=encoder)
        >>> vector = cache.get_or_compute("test/scan", ["scan for vulnerabilities"])
        >>> cache.save_to_disk()  # Persist cache
    """

    def __init__(
        self,
        cache_dir: Path,
        encoder: SemanticEncoder,
        ttl: int = 86400,  # 24 hours
    ) -> None:
        """Initialize the vector cache.

        Args:
            cache_dir: Directory for storing cache data.
            encoder: Semantic encoder for computing vectors.
            ttl: Time-to-live for cache entries in seconds (default: 24 hours).
        """
        self.cache_dir = Path(cache_dir)
        self.encoder = encoder
        self.ttl = ttl

        # Create cache directories
        self.vectors_dir = self.cache_dir / "vectors"
        self.metadata_dir = self.cache_dir / "metadata"
        self.models_dir = self.cache_dir / "models"

        for dir_path in [self.vectors_dir, self.metadata_dir, self.models_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # In-memory cache
        self._vectors: dict[str, np.ndarray] = {}
        self._metadata: dict[str, CacheMetadata] = {}

        # Statistics
        self._stats = CacheStats()

        # Thread safety
        self._lock = threading.RLock()

        # Load existing cache from disk
        self._load_from_disk()

    def get_or_compute(
        self,
        pattern_id: str,
        examples: list[str],
    ) -> np.ndarray:
        """Get pattern vector from cache, or compute if not present.

        This method checks the in-memory cache first, then the disk cache,
        and finally computes the vector if not found anywhere.

        Args:
            pattern_id: Unique identifier for the pattern.
            examples: Example texts for the pattern (used to compute vector).

        Returns:
            Pattern vector as numpy array with shape (dim,).

        Example:
            >>> cache = VectorCache(...)
            >>> vector = cache.get_or_compute("security/scan", ["scan for vulnerabilities"])
            >>> vector.shape
            (384,)
        """
        with self._lock:
            # Check in-memory cache
            if pattern_id in self._vectors:
                self._stats.hits += 1
                return self._vectors[pattern_id]

            self._stats.misses += 1

            # Check disk cache
            disk_vector = self._load_from_disk_cache(pattern_id, examples)
            if disk_vector is not None:
                self._vectors[pattern_id] = disk_vector
                return disk_vector

            # Compute vector
            logger.debug(f"Computing vector for pattern: {pattern_id}")
            vector = self._compute_vector(pattern_id, examples)

            # Store in memory
            self._vectors[pattern_id] = vector

            return vector

    def _compute_vector(
        self,
        pattern_id: str,
        examples: list[str],
        strategy: str = "mean",
    ) -> np.ndarray:
        """Compute semantic vector for a pattern.

        Args:
            pattern_id: Pattern identifier.
            examples: Example texts for the pattern.
            strategy: Aggregation strategy for multiple examples.
                - "mean": Average of all example vectors (default)
                - "max": Maximum similarity (not recommended for encoding)

        Returns:
            Aggregated pattern vector.

        Raises:
            ValueError: If examples list is empty.
        """
        if not examples:
            raise ValueError(f"Cannot compute vector for pattern '{pattern_id}': no examples")

        # Encode all examples
        example_vectors = self.encoder.encode(examples, normalize=True)

        # Aggregate based on strategy
        if strategy == "mean":
            # Average vector
            vector = np.mean(example_vectors, axis=0)
        elif strategy == "max":
            # Take the first example (not recommended)
            vector = example_vectors[0]
        else:
            raise ValueError(f"Unknown aggregation strategy: {strategy}")

        # Normalize to unit length
        vector = vector / (np.linalg.norm(vector) + 1e-8)

        # Create metadata
        examples_hash = self._hash_examples(examples)
        metadata = CacheMetadata(
            pattern_id=pattern_id,
            examples_hash=examples_hash,
            model_name=self.encoder.model_name,
            computed_at=time.time(),
            vector_dim=len(vector),
            strategy=strategy,
        )

        # Store metadata
        self._metadata[pattern_id] = metadata

        return vector

    def _load_from_disk_cache(
        self,
        pattern_id: str,
        examples: list[str],
    ) -> np.ndarray | None:
        """Load vector from disk cache if available and valid.

        Args:
            pattern_id: Pattern identifier.
            examples: Current examples for the pattern (for validation).

        Returns:
            Cached vector if valid, None otherwise.
        """
        # Check if vector file exists
        vector_file = self.vectors_dir / f"{pattern_id}.npy"
        if not vector_file.exists():
            return None

        try:
            # Load vector
            vector = np.load(vector_file)

            # Load metadata
            metadata = self._load_metadata(pattern_id)
            if metadata is None:
                # No metadata, vector is stale
                return None

            # Check if cache entry is expired
            age = time.time() - metadata.computed_at
            if age > self.ttl:
                logger.debug(f"Cache entry expired for pattern: {pattern_id}")
                return None

            # Check if examples have changed
            current_hash = self._hash_examples(examples)
            if current_hash != metadata.examples_hash:
                logger.debug(f"Examples changed for pattern: {pattern_id}")
                return None

            # Check if model has changed
            if metadata.model_name != self.encoder.model_name:
                logger.debug(f"Model changed for pattern: {pattern_id}")
                return None

            # Vector is valid
            logger.debug(f"Loaded vector from disk cache: {pattern_id}")
            return vector

        except Exception as e:
            logger.warning(f"Failed to load vector from disk for {pattern_id}: {e}")
            return None

    def _load_metadata(self, pattern_id: str) -> CacheMetadata | None:
        """Load metadata for a pattern from disk cache.

        Args:
            pattern_id: Pattern identifier.

        Returns:
            CacheMetadata if found, None otherwise.
        """
        metadata_file = self.metadata_dir / f"{pattern_id}.json"
        if not metadata_file.exists():
            return None

        try:
            with metadata_file.open("r") as f:
                data = json.load(f)

            return CacheMetadata(**data)

        except Exception as e:
            logger.warning(f"Failed to load metadata for {pattern_id}: {e}")
            return None

    def _save_metadata(self, metadata: CacheMetadata) -> None:
        """Save metadata for a pattern to disk.

        Args:
            metadata: CacheMetadata to save.
        """
        metadata_file = self.metadata_dir / f"{metadata.pattern_id}.json"

        try:
            with metadata_file.open("w") as f:
                json.dump(metadata.__dict__, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save metadata for {metadata.pattern_id}: {e}")

    def save_to_disk(self) -> None:
        """Persist all in-memory cache to disk.

        This method saves all vectors and metadata to disk for faster
        subsequent loading.

        Example:
            >>> cache = VectorCache(...)
            >>> cache.get_or_compute("test/scan", ["scan for vulnerabilities"])
            >>> cache.save_to_disk()  # Persist to disk
        """
        with self._lock:
            logger.info("Saving cache to disk...")

            for pattern_id, vector in self._vectors.items():
                # Save vector
                vector_file = self.vectors_dir / f"{pattern_id}.npy"
                np.save(vector_file, vector)

                # Save metadata
                if pattern_id in self._metadata:
                    self._save_metadata(self._metadata[pattern_id])

            logger.info(f"Saved {len(self._vectors)} vectors to disk")

    def _load_from_disk(self) -> None:
        """Load cache from disk on initialization.

        This method loads the cache index and prepares the cache for use.
        """
        # Load model info
        model_info_file = self.models_dir / "model_info.json"
        if model_info_file.exists():
            try:
                with model_info_file.open("r") as f:
                    model_info = json.load(f)

                # Check if model has changed
                if model_info.get("model_name") != self.encoder.model_name:
                    logger.info("Model changed, clearing cache")
                    self.invalidate_all()
                    return

            except Exception as e:
                logger.warning(f"Failed to load model info: {e}")

        # Save current model info
        self._save_model_info()

    def _save_model_info(self) -> None:
        """Save current model information to disk."""
        model_info_file = self.models_dir / "model_info.json"

        try:
            model_info = {
                "model_name": self.encoder.model_name,
                "saved_at": time.time(),
            }

            with model_info_file.open("w") as f:
                json.dump(model_info, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save model info: {e}")

    def invalidate_pattern(self, pattern_id: str) -> None:
        """Invalidate cache entry for a specific pattern.

        Args:
            pattern_id: Pattern identifier to invalidate.

        Example:
            >>> cache.invalidate_pattern("security/scan")
        """
        with self._lock:
            # Remove from memory
            if pattern_id in self._vectors:
                del self._vectors[pattern_id]

            if pattern_id in self._metadata:
                del self._metadata[pattern_id]

            # Remove from disk
            vector_file = self.vectors_dir / f"{pattern_id}.npy"
            metadata_file = self.metadata_dir / f"{pattern_id}.json"

            vector_file.unlink(missing_ok=True)
            metadata_file.unlink(missing_ok=True)

            logger.debug(f"Invalidated cache for pattern: {pattern_id}")

    def invalidate_all(self) -> None:
        """Clear all cache entries.

        This removes all vectors and metadata from both memory and disk.

        Example:
            >>> cache.invalidate_all()
        """
        with self._lock:
            # Clear memory
            self._vectors.clear()
            self._metadata.clear()

            # Clear disk cache
            for vector_file in self.vectors_dir.glob("*.npy"):
                vector_file.unlink(missing_ok=True)

            for metadata_file in self.metadata_dir.glob("*.json"):
                metadata_file.unlink(missing_ok=True)

            # Reset statistics
            self._stats = CacheStats()

            logger.info("Cleared all cache")

    def get_cache_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics:
            - hits: Number of cache hits
            - misses: Number of cache misses
            - hit_rate: Cache hit rate (0-1)
            - size: Number of cached vectors
            - size_bytes: Estimated memory usage in bytes

        Example:
            >>> stats = cache.get_cache_stats()
            >>> stats["hit_rate"]
            0.85
        """
        with self._lock:
            # Estimate memory usage
            size_bytes = sum(v.nbytes for v in self._vectors.values())

            return {
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "total_requests": self._stats.total_requests,
                "hit_rate": self._stats.hit_rate,
                "size": len(self._vectors),
                "size_bytes": size_bytes,
                "size_mb": size_bytes / (1024 * 1024),
            }

    def _hash_examples(self, examples: list[str]) -> str:
        """Compute hash of examples for cache validation.

        Args:
            examples: List of example texts.

        Returns:
            SHA-256 hash string.
        """
        import hashlib

        # Join examples and hash
        text = "|||".join(examples)
        return hashlib.sha256(text.encode()).hexdigest()

    def preload_patterns(
        self,
        patterns: dict[str, list[str]],
    ) -> None:
        """Preload multiple patterns into cache.

        This is useful for warming up the cache at startup.

        Args:
            patterns: Dictionary mapping pattern_id to list of examples.

        Example:
            >>> patterns = {
            ...     "security/scan": ["scan for vulnerabilities"],
            ...     "dev/test": ["run tests", "execute tests"],
            ... }
            >>> cache.preload_patterns(patterns)
        """
        logger.info(f"Preloading {len(patterns)} patterns into cache...")

        start = time.time()

        for pattern_id, examples in patterns.items():
            self.get_or_compute(pattern_id, examples)

        elapsed = time.time() - start
        logger.info(f"Preloaded {len(patterns)} patterns in {elapsed:.2f}s")
