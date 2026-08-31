"""Persistent cross-process cache for AI triage results.

``vibe route`` is a CLI — every invocation is a new process, so the in-process
``CacheManager`` never survives long enough to help. This module persists
triage results in ``.vibe/triage_cache.json`` so repeat queries skip the LLM
call entirely, and stale entries serve as a last-good fallback when the LLM
fails.

Follows the ``LastRouteTracker`` pattern (``.vibe/last_route.json``): hashed
query keys (redact + whitespace-collapse + lowercase, no raw query text),
non-blocking advisory cross-process lock, atomic temp+rename writes, and
fail-open semantics — corruption, lock contention, or any IO error silently
degrades to "no cache" and never breaks the routing main flow.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from vibesop.utils.redaction import redact_sensitive

logger = logging.getLogger(__name__)

MAX_ENTRIES = 1000
_HASH_LENGTH = 16


class TriageCache:
    """File-backed cache of triage results keyed by normalized query hash."""

    # Entries missing this version (or carrying a different one) were written
    # under older semantics — notably pre-2026-08-29 entries may encode the
    # unstructured forced-match false positives — and must not surface as
    # fresh hits or last-good fallbacks.
    SCHEMA_VERSION = 2

    # No-match entries (skill_id None) amortize repeat LLM calls for the
    # chat/QA traffic that dominates hook queries, but stale negatives are
    # cheap to re-derive — cap them well below the positive TTL.
    NEGATIVE_TTL_HOURS = 6.0

    def __init__(self, storage_dir: str | Path = ".vibe") -> None:
        self.cache_path = Path(storage_dir) / "triage_cache.json"
        self.lock_path = Path(storage_dir) / "triage_cache.lock"

    @staticmethod
    def key_for(query: str) -> str:
        """Hash the normalized query (same normalization as LastRouteTracker)."""
        normalized = " ".join(redact_sensitive(query).split()).lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def candidates_hash(candidates: list[dict[str, Any]]) -> str:
        """Hash the candidate skill id set; invalidates entries on skill changes.

        Callers pass the FULL candidate list (not the prefiltered top-N
        window) so the hash is a fingerprint of the installed skill set and
        the lookup can run before the (expensive) recall prefilter. Entries
        stored under the old convention (hash over the prefiltered window)
        simply mismatch once — they degrade to last-good and are overwritten
        on the next store, i.e. the cache self-heals.
        """
        ids = sorted(str(c.get("id", "")) for c in candidates)
        return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()[:_HASH_LENGTH]

    def lookup(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        ttl_hours: float,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Look up ``query``; returns ``(fresh_entry, stale_entry)``.

        A fresh entry (within TTL and matching ``candidates_hash``) is returned
        in the first slot. An expired or candidate-mismatched entry is returned
        in the second slot as a last-good fallback. Any failure (contention,
        corruption, IO) yields ``(None, None)``.
        """
        try:
            from vibesop.utils.file_lock import cross_process_lock

            with cross_process_lock(self.lock_path, blocking=False):
                data = self._read()
            if not data:
                return None, None
            entry = data.get(self.key_for(query))
            if not isinstance(entry, dict):
                return None, None
            if entry.get("v") != self.SCHEMA_VERSION:
                # Self-heal: evict the incompatible entry instead of letting
                # it squat in the file forever (it can never hit again).
                # Re-read under the lock so pop+write is atomic against a
                # concurrent store (the read above already released it);
                # contention just skips the eviction.
                with cross_process_lock(self.lock_path, blocking=False):
                    data = self._read()
                    if data and data.get(self.key_for(query), {}).get("v") != self.SCHEMA_VERSION:
                        # Re-check under the lock: a concurrent store may
                        # have upgraded the entry to the current schema
                        # version since the unlocked read above — only pop
                        # when it is still incompatible.
                        data.pop(self.key_for(query), None)
                        self._write(data)
                return None, None
            age_seconds = time.time() - float(entry.get("ts", 0))
            if not entry.get("skill_id"):
                ttl_hours = min(ttl_hours, self.NEGATIVE_TTL_HOURS)
            fresh = (
                entry.get("candidates_hash") == self.candidates_hash(candidates)
                and age_seconds <= ttl_hours * 3600
            )
            return (entry, None) if fresh else (None, entry)
        except Exception as e:  # cache must never break routing
            logger.debug("Triage cache lookup unavailable: %s", e)
            return None, None

    def store(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        route: dict[str, Any],
    ) -> None:
        """Persist a triage result; evicts oldest entries past MAX_ENTRIES."""
        try:
            from vibesop.utils.file_lock import cross_process_lock

            with cross_process_lock(self.lock_path, blocking=False):
                data = self._read() or {}
                data[self.key_for(query)] = {
                    "v": self.SCHEMA_VERSION,
                    "skill_id": route["skill_id"],
                    "confidence": route["confidence"],
                    "source": route.get("source", ""),
                    "description": route.get("description", ""),
                    "candidates_hash": self.candidates_hash(candidates),
                    "ts": time.time(),
                }
                if len(data) > MAX_ENTRIES:
                    oldest = sorted(
                        data.items(),
                        key=lambda kv: float(kv[1].get("ts", 0)),
                    )[: len(data) - MAX_ENTRIES]
                    for key, _ in oldest:
                        data.pop(key, None)
                self._write(data)
        except Exception as e:  # cache must never break routing
            logger.debug("Triage cache store unavailable: %s", e)

    def _read(self) -> dict[str, Any] | None:
        """Read cache state; corrupt/missing state returns None (self-heals
        on the next ``_write``)."""
        self._cleanup_stale_tmp()
        if not self.cache_path.exists():
            return None
        try:
            with self.cache_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _cleanup_stale_tmp(self) -> None:
        """Remove ``triage_cache.<pid>.tmp`` leftovers from crashed writers.

        ``_write`` renames its per-process tmp file atomically, so a tmp file
        surviving to a later read means that writer died mid-write (every
        ``_read`` caller holds the cross-process lock, so a live writer's tmp
        is never seen here). Best-effort: any OSError is ignored.
        """
        for tmp in self.cache_path.parent.glob(f"{self.cache_path.stem}.*.tmp"):
            with contextlib.suppress(OSError):
                tmp.unlink()

    def _write(self, data: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        # Per-process tmp name: two processes writing concurrently must not
        # interleave on a shared tmp file.
        tmp_path = self.cache_path.with_suffix(f".{os.getpid()}.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp_path.replace(self.cache_path)
