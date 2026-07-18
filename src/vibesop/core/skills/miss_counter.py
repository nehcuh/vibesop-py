"""Always-on, hash-only missed-query counter (P1: data foundation).

The single-route path historically wrote nothing when no skill matched, so the
product had no signal about *what users ask for that VibeSOP cannot route*.
``AnalyticsStore`` is opt-in (F-06) and stores redacted text; this counter is
the always-on complement: it persists only a **salted hash** of the query plus
a count and first/last timestamps — never the raw text — so it needs no
opt-in. The salt (``.vibe/miss_salt``, mode 0o600) makes the hashes
irreversible without local access, and the query still passes through
``redact_sensitive`` *before* hashing so a pasted secret cannot be recovered
by dictionary-attacking the hash.

Data file: ``<project_root>/.vibe/miss_counter.json`` — a JSON object mapping
hash -> entry (not JSONL, so counts can be updated in place)::

    {"<hash16>": {"n": 3, "first": "<iso>", "last": "<iso>"}}

Writes are atomic (``vibesop.utils.atomic_writer.write_text``) and every
operation is fault-tolerant: telemetry must never break routing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vibesop.utils.atomic_writer import write_text
from vibesop.utils.redaction import redact_sensitive

logger = logging.getLogger(__name__)

_HASH_LENGTH = 16


@dataclass
class MissedCluster:
    """A frequently-missed query cluster, identified by hash only (no raw text).

    Consumed by the P2 missed-query loop (clustering + suggestions).
    """

    hash: str
    count: int
    first: str  # ISO timestamp of first occurrence
    last: str  # ISO timestamp of most recent occurrence


class MissCounter:
    """Counts no-match/fallback routing misses, keyed by salted query hash."""

    def __init__(self, project_root: str | Path) -> None:
        self._vibe_dir = Path(project_root) / ".vibe"
        self._data_path = self._vibe_dir / "miss_counter.json"
        self._salt_path = self._vibe_dir / "miss_salt"
        self._salt: str | None = None

    def record(self, query: str) -> None:
        """Increment the counter for *query* (normalized → redacted → hashed).

        Normalization (strip, collapse whitespace, lowercase) makes
        cosmetically-different queries share one counter. Fault-tolerant: any
        failure is logged and swallowed so routing is never affected.

        Concurrency: not safe for concurrent writers (read-modify-write has no
        file lock — worst case is a lost increment, never corruption, since
        writes go through ``atomic_writer``). Acceptable for a single-user CLI;
        the loop tick lock already serializes loop-driven routes.
        """
        try:
            normalized = " ".join(query.split()).lower()
            if not normalized:
                return
            digest = self._hash(normalized)
            data = self._load()
            now = datetime.now(UTC).isoformat()
            entry = data.get(digest)
            if entry is None:
                data[digest] = {"n": 1, "first": now, "last": now}
            else:
                entry["n"] = int(entry.get("n", 0)) + 1
                entry["last"] = now
            write_text(self._data_path, json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:  # telemetry must never break routing
            logger.debug("Failed to record missed query: %s", e)

    def frequent(self, min_count: int = 3) -> list[MissedCluster]:
        """Return clusters whose count reached *min_count*, most frequent first."""
        clusters: list[MissedCluster] = []
        for digest, entry in self._load().items():
            try:
                count = int(entry.get("n", 0))
            except (TypeError, ValueError):
                continue
            if count < min_count:
                continue
            clusters.append(
                MissedCluster(
                    hash=digest,
                    count=count,
                    first=str(entry.get("first", "")),
                    last=str(entry.get("last", "")),
                )
            )
        clusters.sort(key=lambda c: c.count, reverse=True)
        return clusters

    def clear(self) -> None:
        """Delete the counter data file (the salt is kept). Used by data purge."""
        try:
            self._data_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Failed to clear miss counter: %s", e)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _hash(self, normalized_query: str) -> str:
        """sha256(salt + redacted_query)[:16] — irreversible without the salt."""
        redacted = redact_sensitive(normalized_query)
        payload = (self._get_salt() + redacted).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:_HASH_LENGTH]

    def _get_salt(self) -> str:
        """Read the per-install salt, generating it (mode 0o600) on first use."""
        if self._salt:
            return self._salt
        try:
            existing = self._salt_path.read_text(encoding="utf-8").strip()
        except OSError:
            existing = ""
        if existing:
            self._salt = existing
            return existing
        salt = secrets.token_hex(16)
        self._vibe_dir.mkdir(parents=True, exist_ok=True)
        # os.open with an explicit mode: no pathlib equivalent creates the file
        # with restrictive permissions atomically.
        fd = os.open(self._salt_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(salt)
        self._salt = salt
        return salt

    def _load(self) -> dict[str, dict[str, Any]]:
        """Load the counter file; tolerate absence or corruption as empty."""
        try:
            data: Any = json.loads(self._data_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}


__all__ = ["MissCounter", "MissedCluster"]
