"""Embedding cache for task-memory loop (W1 Task A).

Stores query embeddings computed via FastEmbed (MiniLM-L12-v2). Cache
survives across CLI invocations so ``vibe recall`` doesn't re-run the
ONNX model on every query.

Cache key: ``sha1(model_id + normalize(query))[:16]`` — reuses task_id's
``normalize_query`` so cache hits align with task_id equivalence
(queries that normalize identically share one cache entry, one task_id).

Model upgrade: bump ``model_id``. Stored metadata records the model_id
used to compute each batch; on load, mismatched model_id invalidates
the whole cache (entries treated as misses → re-computed lazily).

Storage format (``.vibe/cache/embeddings.npz``):

- ``metadata`` : 0-d numpy ``<U`` array wrapping JSON ``{"model_id": ...}``
- ``keys``     : 1-d numpy ``<U16`` array of cache keys
- ``vectors``  : 2-d ``float32`` array, shape ``(N, dim)``

Cross-process safety: ``fcntl.flock`` during the read-modify-write,
mirroring ``SpanWriter``. Race tolerance: lost updates are acceptable
because embeddings are deterministic (re-computation yields the same
vector). The recent ReflectionStore race ([[project-dashboard-v3-phase-b-shipped]])
taught us RMW under a shared lock is the correct pattern; we apply it
here even though contention is low.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path

import numpy as np

from vibesop.core.observability.task_id import normalize_query

logger = logging.getLogger(__name__)

__all__ = ["EmbeddingCache", "get_embedding_cache"]

_DEFAULT_CACHE_PATH = Path(".vibe/cache/embeddings.npz")
# fastembed ≥0.8 requires the namespaced id; the bare name raises
# ValueError("not supported") at TextEmbedding() — which was swallowed into
# a per-query warning and silently disabled ALL embeddings (soft-merge
# never fired) until gate16 caught it on real data.
_DEFAULT_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_DEFAULT_MODEL_ID = "minilm-l12-v2"
_DEFAULT_DIM = 384

_embedding_cache: EmbeddingCache | None = None


class EmbeddingCache:
    """Persistent cache of query embeddings keyed by ``model_id + normalize(query)``."""

    def __init__(
        self,
        cache_path: Path | str | None = None,
        model_name: str = _DEFAULT_MODEL_NAME,
        model_id: str = _DEFAULT_MODEL_ID,
        dim: int = _DEFAULT_DIM,
    ) -> None:
        self._cache_path = Path(cache_path) if cache_path else _DEFAULT_CACHE_PATH
        self._model_name = model_name
        self._model_id = model_id
        self._dim = dim
        self._model: object | None = None
        self._lock = threading.Lock()
        self._cache: dict[str, np.ndarray] = {}
        self._load()

    def embed(self, query: str) -> np.ndarray | None:
        """Return cached embedding or compute+store. ``None`` if library missing."""
        key = self._make_key(query)
        if key is None:
            return None
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
        vec = self._compute(query)
        if vec is None:
            return None
        with self._lock:
            if self._cache.get(key) is None:
                self._cache[key] = vec
                self._flush_locked()
        return self._cache[key]

    def embed_batch(self, queries: list[str]) -> list[np.ndarray | None]:
        """Embed multiple queries. ``None`` per-slot where library missing."""
        results: list[np.ndarray | None] = [None] * len(queries)
        misses: list[tuple[int, str, str]] = []
        with self._lock:
            for i, q in enumerate(queries):
                key = self._make_key(q)
                if key is None:
                    continue
                cached = self._cache.get(key)
                if cached is not None:
                    results[i] = cached
                else:
                    misses.append((i, q, key))
        if not misses:
            return results
        computed = self._compute_batch([q for _, q, _ in misses])
        with self._lock:
            new_entries = 0
            for (idx, _, key), vec in zip(misses, computed, strict=False):
                if vec is None:
                    continue
                if self._cache.get(key) is None:
                    self._cache[key] = vec
                    new_entries += 1
                results[idx] = self._cache[key]
            if new_entries > 0:
                self._flush_locked()
        return results

    def _make_key(self, query: str) -> str | None:
        normalized = normalize_query(query)
        if not normalized:
            return None
        h = hashlib.sha1((self._model_id + "\x1f" + normalized).encode("utf-8"))
        return h.hexdigest()[:16]

    def _compute(self, query: str) -> np.ndarray | None:
        """Compute embedding via FastEmbed. Returns ``None`` if library missing."""
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError:
                logger.debug(
                    "fastembed not installed; embedding cache disabled for %r",
                    self._model_name,
                )
                return None
            try:
                self._model = TextEmbedding(model_name=self._model_name)
            except Exception as exc:
                logger.warning("fastembed model %r failed to load: %s", self._model_name, exc)
                return None
        try:
            vecs = list(self._model.embed([query]))  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("embedding computation failed for query: %s", exc)
            return None
        if not vecs:
            return None
        return np.asarray(vecs[0], dtype=np.float32)

    def _compute_batch(self, queries: list[str]) -> list[np.ndarray | None]:
        """Compute embeddings for a batch. Default: per-query fallback.

        Subclasses can override to use FastEmbed's batched embed, which is
        meaningfully faster for >8 queries. For MVP correctness, per-query
        fallback is fine.
        """
        return [self._compute(q) for q in queries]

    def _load(self) -> None:
        """Load cache from disk if it exists and model_id matches."""
        if not self._cache_path.exists():
            return
        try:
            npz = np.load(self._cache_path, allow_pickle=False)
            meta_arr = npz["metadata"]
            meta_str = meta_arr.item() if meta_arr.ndim == 0 else str(meta_arr[0])
            meta = json.loads(meta_str)
            if meta.get("model_id") != self._model_id:
                logger.info(
                    "embedding cache model_id mismatch (stored=%s, current=%s); "
                    "treating as cold cache",
                    meta.get("model_id"),
                    self._model_id,
                )
                return
            keys = [str(k) for k in npz["keys"].tolist()]
            vectors = npz["vectors"]
            if len(keys) != vectors.shape[0]:
                logger.warning(
                    "embedding cache shape mismatch: %d keys vs %d vectors; ignoring",
                    len(keys),
                    vectors.shape[0],
                )
                return
            for k, v in zip(keys, vectors, strict=False):
                self._cache[k] = np.asarray(v, dtype=np.float32)
        except (KeyError, ValueError, OSError) as exc:
            logger.warning("embedding cache load failed (%s); starting cold", exc)

    def _flush_locked(self) -> None:
        """Persist cache. Caller must hold ``self._lock``.

        Uses ``cross_process_lock`` on a sidecar ``.lock`` file for
        cross-process safety — same helper SpanWriter uses. Re-reads
        the cache under the lock to pick up entries added by other
        processes since our last ``_load()`` (RMW pattern).

        OSError policy: if the lock cannot be acquired (e.g. read-only
        filesystem), log a warning and skip the flush. The new entry
        stays in-memory for this process; the next ``embed()`` that
        triggers a flush will retry. Lost updates are tolerable because
        embeddings are deterministic.
        """
        if not self._cache:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._cache_path.with_suffix(".npz.lock")
        try:
            from vibesop.utils.file_lock import cross_process_lock

            with cross_process_lock(lock_path):
                self._merge_external_locked()
                if not self._cache:
                    return
                self._write_file()
        except OSError as exc:
            logger.warning(
                "embedding cache flush skipped (lock failed: %s); "
                "entry remains in-memory",
                exc,
            )

    def _write_file(self) -> None:
        """Atomically write current ``_cache`` to ``_cache_path``."""
        tmp_path = self._cache_path.with_suffix(".npz.tmp")
        keys = list(self._cache.keys())
        if not keys:
            return
        vectors = np.stack([self._cache[k] for k in keys]).astype(np.float32)
        metadata = np.array(
            json.dumps({"model_id": self._model_id, "version": 1, "count": len(keys)})
        )
        keys_arr = np.array(keys, dtype="<U16")
        # Open the file handle ourselves so numpy doesn't append .npz to tmp_path.
        with tmp_path.open("wb") as fh:
            np.savez(fh, metadata=metadata, keys=keys_arr, vectors=vectors)
        tmp_path.replace(self._cache_path)

    def _merge_external_locked(self) -> None:
        """Re-read cache file and merge any new keys. Caller holds the flock.

        Only adds keys we don't already have — never overwrites our own
        freshly-computed entries (they are authoritative for our process).
        """
        if not self._cache_path.exists():
            return
        try:
            npz = np.load(self._cache_path, allow_pickle=False)
            meta_arr = npz["metadata"]
            meta_str = meta_arr.item() if meta_arr.ndim == 0 else str(meta_arr[0])
            meta = json.loads(meta_str)
            if meta.get("model_id") != self._model_id:
                return
            keys = [str(k) for k in npz["keys"].tolist()]
            vectors = npz["vectors"]
            for k, v in zip(keys, vectors, strict=False):
                if k not in self._cache:
                    self._cache[k] = np.asarray(v, dtype=np.float32)
        except (KeyError, ValueError, OSError):
            return


def get_embedding_cache() -> EmbeddingCache:
    """Return the module-level singleton. Created lazily on first call."""
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = EmbeddingCache()
    return _embedding_cache
