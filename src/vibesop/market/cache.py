"""On-disk cache for market search results (per-entry TTL, corruption-tolerant)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Cache file location, relative to the project root.
CACHE_FILE = Path(".vibe/cache/market_search.json")

#: Time-to-live for cache entries, in seconds (24 hours).
CACHE_TTL_SECONDS = 24 * 60 * 60

#: Short TTL for partial results (e.g. some GitHub topics failed) so the
#: failed sources are retried within minutes instead of being masked for 24h.
PARTIAL_CACHE_TTL_SECONDS = 5 * 60


def normalize_query(query: str) -> str:
    """Normalize a query string for use as a cache key."""
    return " ".join(query.lower().split())


def get_cached(key: str, cache_file: Path | None = None) -> list[dict[str, Any]] | None:
    """Return the cached payload for key if present and fresh, else None.

    Missing, corrupt, or malformed cache files are treated as a cache miss.
    """
    path = cache_file or CACHE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    entry = data.get(key)
    if not isinstance(entry, dict):
        return None
    timestamp = entry.get("timestamp", 0)
    if not isinstance(timestamp, (int, float)):
        return None
    ttl = entry.get("ttl", CACHE_TTL_SECONDS)
    if not isinstance(ttl, (int, float)):
        ttl = CACHE_TTL_SECONDS
    if time.time() - timestamp > ttl:
        return None
    payload = entry.get("payload")
    if not isinstance(payload, list):
        return None
    return payload


def set_cached(
    key: str,
    payload: list[dict[str, Any]],
    cache_file: Path | None = None,
    ttl: int = CACHE_TTL_SECONDS,
) -> None:
    """Store payload under key, preserving other entries.

    The TTL is recorded with the entry so ``get_cached`` can honor it —
    partial results pass a short TTL to be retried sooner. Write failures
    are logged and ignored — caching must never break search.
    """
    path = cache_file or CACHE_FILE
    try:
        data: dict[str, Any] = {}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        data[key] = {"timestamp": time.time(), "ttl": ttl, "payload": payload}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except (OSError, ValueError) as e:
        logger.warning("Failed to write market search cache: %s", e)
