"""Passive update detection for installed skill packs and the featured registry.

Installed packs record ``commit_sha`` + ``source_url`` in their pack lock
(``~/.config/skills/.pack-locks/<pack>.json``), but nothing ever compared
them against upstream — recommended packs silently went stale. This module
adds an offline-safe checker:

- ``check_pack_updates()`` compares each lock's commit SHA against
  ``git ls-remote <url> HEAD`` and caches verdicts for 24 h
  (``.update-cache.json`` — a dotfile, explicitly skipped by
  ``PackLockStore.list_all()``; ``clear_all()`` does sweep it, which is
  correct for its data-purge callers).
- ``cached_pack_updates()`` returns only what the cache already knows and
  never touches the network (safe for ``vibe status``).
- ``registry_age_days()`` reports the age of the local featured-skills
  registry so callers can hint ``vibe sync-registry``.

Network failures never raise: the affected pack is reported as
``state="unknown"`` and stale cached entries are simply not reused.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from vibesop.core.skills.pack_lock import PackLockStore
from vibesop.installer.analyzer import parse_github_url
from vibesop.utils.atomic_writer import write_text

logger = logging.getLogger(__name__)

__all__ = [
    "CACHE_FILENAME",
    "CACHE_TTL_SECONDS",
    "PackUpdateStatus",
    "cached_pack_updates",
    "check_pack_updates",
    "registry_age_days",
    "remote_head_sha",
]

CACHE_TTL_SECONDS = 86400  # 24 h — mirrors CacheSettings.DEFAULT_TTL
LS_REMOTE_TIMEOUT = 8  # seconds; bounds `vibe skills outdated` on dead networks
CACHE_FILENAME = ".update-cache.json"


@dataclass
class PackUpdateStatus:
    """Upstream comparison verdict for one installed pack."""

    pack_name: str
    source_url: str
    installed_sha: str
    remote_sha: str
    state: str  # "up_to_date" | "update_available" | "unknown"
    checked_at: str  # ISO timestamp ("" when unknown)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> PackUpdateStatus:
        return cls(
            pack_name=data.get("pack_name", ""),
            source_url=data.get("source_url", ""),
            installed_sha=data.get("installed_sha", ""),
            remote_sha=data.get("remote_sha", ""),
            state=data.get("state", "unknown"),
            checked_at=data.get("checked_at", ""),
        )


def remote_head_sha(source_url: str, timeout: int = LS_REMOTE_TIMEOUT) -> str:
    """Return upstream HEAD via ``git ls-remote`` ("" on any failure).

    The URL is passed as an argv element (never through a shell), and it was
    already validated by the install-time trust/lock chain.
    """
    clone_url, _ = parse_github_url(source_url)
    try:
        # Fixed argv, no shell — the URL never reaches a shell parser.
        result = subprocess.run(
            ["git", "ls-remote", clone_url, "HEAD"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""
    lines = result.stdout.strip().splitlines()
    if lines and lines[0].split():
        return lines[0].split()[0]
    return ""


def _read_cache(store: PackLockStore) -> tuple[datetime | None, dict[str, PackUpdateStatus]]:
    """Load the update cache; corrupt/missing files degrade to (None, {})."""
    cache_file = store.directory / CACHE_FILENAME
    if not cache_file.exists():
        return None, {}
    try:
        raw = json.loads(cache_file.read_text(encoding="utf-8"))
        checked_at = datetime.fromisoformat(raw.get("checked_at", ""))
        packs = {k: PackUpdateStatus.from_dict(v) for k, v in raw.get("packs", {}).items()}
        return checked_at, packs
    except (json.JSONDecodeError, TypeError, ValueError, OSError) as e:
        logger.debug("Ignoring corrupt update cache %s: %s", cache_file, e)
        return None, {}


def check_pack_updates(
    *,
    refresh: bool = False,
    store: PackLockStore | None = None,
    ttl_seconds: int = CACHE_TTL_SECONDS,
) -> list[PackUpdateStatus]:
    """Compare installed packs against upstream HEAD.

    Uses a 24 h cache; ``refresh=True`` forces fresh ``git ls-remote`` calls.
    Packs whose lock lacks a commit SHA, and lookups that fail (offline),
    come back as ``state="unknown"`` instead of raising.
    """
    store = store or PackLockStore()
    locks = store.list_all()
    now = datetime.now(UTC)

    cache_time, cached = _read_cache(store)
    fresh = cache_time is not None and (now - cache_time).total_seconds() < ttl_seconds

    if fresh and not refresh:
        results: list[PackUpdateStatus] = []
        for lock in locks:
            hit = cached.get(lock.pack_name)
            if hit is not None and hit.installed_sha == lock.commit_sha:
                results.append(hit)
            else:
                # Pack (re)installed after the cache snapshot — verdict unknown
                # until the next refresh; do not hit the network here.
                results.append(
                    PackUpdateStatus(
                        pack_name=lock.pack_name,
                        source_url=lock.source_url,
                        installed_sha=lock.commit_sha,
                        remote_sha="",
                        state="unknown",
                        checked_at="",
                    )
                )
        return results

    results = []
    for lock in locks:
        remote = remote_head_sha(lock.source_url) if lock.source_url else ""
        if not lock.commit_sha or not remote:
            state = "unknown"
        elif remote == lock.commit_sha:
            state = "up_to_date"
        else:
            state = "update_available"
        results.append(
            PackUpdateStatus(
                pack_name=lock.pack_name,
                source_url=lock.source_url,
                installed_sha=lock.commit_sha,
                remote_sha=remote,
                state=state,
                checked_at=now.isoformat(),
            )
        )

    try:
        payload = json.dumps(
            {
                "checked_at": now.isoformat(),
                "packs": {r.pack_name: r.to_dict() for r in results},
            },
            indent=2,
        )
        write_text(store.directory / CACHE_FILENAME, payload)
    except OSError as e:
        logger.debug("Could not write pack update cache: %s", e)

    return results


def cached_pack_updates(store: PackLockStore | None = None) -> list[PackUpdateStatus]:
    """Return only what the cache already knows — never touches the network."""
    _, cached = _read_cache(store or PackLockStore())
    return list(cached.values())


def registry_age_days(project_root: Path) -> float | None:
    """Age of the local featured-skills registry in days (None if unknown).

    ``None`` means "cannot tell": no local registry file (built-in defaults in
    use) or a pre-fix file whose ``updated_at`` was written as "".
    """
    local_file = project_root / ".vibe" / "featured-skills.json"
    if not local_file.exists():
        return None
    try:
        raw = json.loads(local_file.read_text(encoding="utf-8"))
        updated_at = str(raw.get("updated_at", ""))
        if not updated_at:
            return None
        ts = datetime.fromisoformat(updated_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return (datetime.now(UTC) - ts).total_seconds() / 86400
    except (json.JSONDecodeError, TypeError, ValueError, OSError):
        return None
