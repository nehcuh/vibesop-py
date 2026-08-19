"""Embedding-based candidate recall for the AI triage prefilter.

The AI triage prefilter historically ranked candidates with the
KeywordMatcher: a literal-token gate in front of the LLM, so a correct
skill with no lexical overlap never reached the LLM window (and CJK
queries tokenize to single characters, making recall near-random). This
module replaces that gate with semantic recall: candidates are embedded
once (paraphrase-multilingual-MiniLM-L12-v2, same model as the index
embedding fallback in ``_layers.py``), cached on disk, and the query is
ranked against them by cosine similarity.

Persistence follows the ``TriageCache`` pattern
(``.vibe/skill_embeddings.json``): the read-modify-write cycle runs in a
single non-blocking advisory cross-process lock critical section (a
split read/write would lose entries written concurrently), writes are
atomic temp+rename, corruption self-heals on the next write, and
semantics are fail-open — any failure (missing optional dependency,
model load error, lock contention, IO) returns ``None`` so the caller
falls back to the KeywordMatcher path. Entries whose skill is no longer
a candidate (e.g. uninstalled) are pruned on write so the cache cannot
grow without bound. Each cache entry also carries the embedding model
name; entries written by a different model are treated as stale and
re-encoded, so switching ``MODEL_NAME`` never silently reuses
incompatible vectors.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_HASH_LENGTH = 16

# Minimum cosine similarity for a recall candidate to enter the triage window.
# paraphrase-multilingual-MiniLM-L12-v2 assigns roughly 0.1-0.3 cosine to
# unrelated text pairs, so 0.25 sits just above the noise floor: without a
# floor, a junk query still gets its top-N "best" garbage forwarded to the
# LLM. Recall is a top-N prefilter (not a hard match — the SEMANTIC_INDEX
# embedding fallback uses 0.45 for that), so the floor stays permissive.
# The floor is only consulted when recall actually runs — i.e. when eligible
# candidates exceed the triage window; smaller sets are forwarded whole (see
# TriageService.prefilter_ai_triage_candidates).
# Configurable via RoutingConfig.ai_triage_recall_min_similarity.
DEFAULT_MIN_SIMILARITY = 0.25


class EmbeddingRecall:
    """Semantic top-N candidate recall with a persistent embedding cache.

    ``min_similarity`` is a public attribute: TriageService re-reads the
    configured floor into it per prefilter call so a config swap after
    construction takes effect.
    """

    def __init__(
        self,
        storage_dir: str | Path = ".vibe",
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> None:
        self.cache_path = Path(storage_dir) / "skill_embeddings.json"
        self.lock_path = Path(storage_dir) / "skill_embeddings.lock"
        self.min_similarity = min_similarity
        self._model: Any | None = None
        self._model_failed = False

    def recall(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int,
    ) -> list[str] | None:
        """Return up to ``top_n`` candidate ids ranked by embedding similarity.

        ``None`` on any failure — the caller must fall back to keyword
        prefiltering. Candidates scoring below ``min_similarity`` are dropped;
        when nothing clears the floor the result is an empty list, which the
        caller treats as "recall ran, nothing is semantically relevant"
        (distinct from ``None`` = recall unavailable). Note the caller only
        invokes recall when the eligible candidate count exceeds ``top_n``;
        smaller sets bypass this floor entirely.
        """
        try:
            model = self._get_model()
            if model is None:
                return None
            embeddings = self._candidate_embeddings(model, candidates)
            if not embeddings:
                return None
            query_emb = self._encode(model, [query])[0]
            scored = sorted(
                (
                    (str(c["id"]), _cosine_similarity(query_emb, embeddings[str(c["id"])]))
                    for c in candidates
                    if str(c.get("id", "")) in embeddings
                ),
                key=lambda kv: kv[1],
                reverse=True,
            )
            # Drop everything below the similarity floor; may be empty.
            return [skill_id for skill_id, s in scored[:top_n] if s >= self.min_similarity]
        except Exception as e:  # recall must never break routing
            logger.debug("Embedding recall unavailable: %s", e)
            return None

    def _get_model(self) -> Any | None:
        """Lazy-load the model once per instance; failures are sticky."""
        if self._model is not None:
            return self._model
        if self._model_failed:
            return None
        try:
            from sentence_transformers import (
                SentenceTransformer,  # pyright: ignore[reportMissingImports]
            )

            self._model = SentenceTransformer(MODEL_NAME)
        except Exception as e:
            logger.debug("sentence-transformers unavailable for triage recall: %s", e)
            self._model_failed = True
            return None
        return self._model

    def _candidate_embeddings(
        self,
        model: Any,
        candidates: list[dict[str, Any]],
    ) -> dict[str, list[float]]:
        """Return embeddings for all candidates; re-encode only content changes."""
        texts = {str(c["id"]): self._candidate_text(c) for c in candidates if c.get("id")}
        cached = self._refresh_cache(model, texts)
        if cached is None:
            # Lock contention or unreadable cache: degrade to a fresh
            # in-memory encode; nothing is persisted (the next route
            # re-encodes and retries).
            cached = self._encode_entries(model, texts, list(texts))
        return {
            sid: entry["embedding"]
            for sid, entry in cached.items()
            if sid in texts and isinstance(entry, dict) and isinstance(entry.get("embedding"), list)
        }

    def _refresh_cache(
        self,
        model: Any,
        texts: dict[str, str],
    ) -> dict[str, Any] | None:
        """Read-modify-write the cache in a single lock critical section.

        Re-encodes stale entries and prunes entries whose skill is no
        longer a candidate, then persists atomically. Returns the merged
        cache, or ``None`` on any lock/IO failure — the caller degrades
        to an in-memory encode.
        """
        try:
            from vibesop.utils.file_lock import cross_process_lock

            with cross_process_lock(self.lock_path, blocking=False):
                cached = self._read_cache()
                stale = [
                    sid
                    for sid, text in texts.items()
                    if not isinstance(cached.get(sid), dict)
                    or cached[sid].get("content_hash") != _content_hash(text)
                    # Vectors are model-specific: an entry written by a different
                    # embedding model (or by a pre-model-versioning build, which
                    # lacks the field) must be re-encoded, never silently reused.
                    or cached[sid].get("model") != MODEL_NAME
                ]
                if stale:
                    cached.update(self._encode_entries(model, texts, stale))
                pruned = {sid: entry for sid, entry in cached.items() if sid in texts}
                if stale or len(pruned) != len(cached):
                    self._write_cache(pruned)
                return pruned
        except Exception as e:  # cache refresh must never break recall
            logger.debug("Embedding cache refresh skipped: %s", e)
            return None

    def _encode_entries(
        self,
        model: Any,
        texts: dict[str, str],
        sids: list[str],
    ) -> dict[str, Any]:
        """Encode the given candidate ids into cache entries."""
        vectors = self._encode(model, [texts[sid] for sid in sids])
        now = time.time()
        return {
            sid: {
                "content_hash": _content_hash(texts[sid]),
                "model": MODEL_NAME,
                "embedding": vector,
                "ts": now,
            }
            for sid, vector in zip(sids, vectors, strict=True)
        }

    @staticmethod
    def _candidate_text(candidate: dict[str, Any]) -> str:
        parts = [
            str(candidate.get("id", "")),
            str(candidate.get("description", "")),
            str(candidate.get("intent", "")),
        ]
        for key in ("triggers", "keywords", "scenarios"):
            values = candidate.get(key) or []
            if isinstance(values, (list, tuple)):
                parts.extend(str(v) for v in values)
        return " ".join(p for p in parts if p)

    @staticmethod
    def _encode(model: Any, texts: list[str]) -> list[list[float]]:
        raw = model.encode(texts, show_progress_bar=False)
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in raw]

    def _read_cache(self) -> dict[str, Any]:
        """Read cache state; corruption returns an empty dict (self-heals
        on the next ``_write_cache``). Caller must hold the lock."""
        if not self.cache_path.exists():
            return {}
        try:
            with self.cache_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_cache(self, data: dict[str, Any]) -> None:
        """Persist cache state via atomic temp+rename. Caller must hold
        the lock; failures propagate to ``_refresh_cache``, which skips
        silently (the next route re-encodes and retries)."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.cache_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp_path.replace(self.cache_path)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_HASH_LENGTH]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b + 1e-10)
