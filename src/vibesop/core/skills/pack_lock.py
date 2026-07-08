"""Pack install locks — commit + content integrity for third-party skill packs.

Records the git commit SHA and a content sha256 of each installed pack at
``~/.config/skills/.pack-locks/<pack>.json``. On re-install, the new clone's
commit/content is verified against the lock — a force-push or tampered pack
(upstream change without the user's ``--upgrade`` consent) is rejected. Closes
the F-02 supply-chain gap where ``vibe install <pack>`` re-cloned HEAD with no
integrity check.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from vibesop.utils.atomic_writer import write_text
from vibesop.utils.pack_name import sanitize_pack_name

logger = logging.getLogger(__name__)


@dataclass
class PackLock:
    """Integrity lock for one installed pack."""

    pack_name: str
    source_url: str
    commit_sha: str  # `git rev-parse HEAD` at install time ("" if unavailable)
    content_sha256: str  # marker_files.calculate_checksum(target_path)
    installed_at: str  # ISO timestamp

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> PackLock:
        return cls(
            pack_name=data.get("pack_name", ""),
            source_url=data.get("source_url", ""),
            commit_sha=data.get("commit_sha", ""),
            content_sha256=data.get("content_sha256", ""),
            installed_at=data.get("installed_at", ""),
        )


class PackLockStore:
    """Per-pack lock files under ``~/.config/skills/.pack-locks/``.

    Sibling to ``TrustStore`` (``.trusted.json``). One file per pack → no
    cross-pack contention, so writes use plain atomic temp+rename (no flock).
    """

    LOCKS_DIR = Path.home() / ".config" / "skills" / ".pack-locks"

    def __init__(self, locks_dir: Path | None = None) -> None:
        self._dir = locks_dir or self.LOCKS_DIR

    def _path(self, pack_name: str) -> Path:
        sanitized = sanitize_pack_name(pack_name)
        return self._dir / f"{sanitized}.json"

    def get(self, pack_name: str) -> PackLock | None:
        """Return the lock for *pack_name*, or None if absent/corrupt."""
        path = self._path(pack_name)
        if not path.exists():
            return None
        try:
            return PackLock.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning("Corrupt pack lock %s, ignoring: %s", path, e)
            return None

    def write(self, lock: PackLock) -> None:
        """Atomically persist a pack lock."""
        self._dir.mkdir(parents=True, exist_ok=True)
        write_text(self._path(lock.pack_name), json.dumps(asdict(lock), indent=2))

    def clear(self, pack_name: str) -> None:
        """Remove a pack lock (uninstall path)."""
        path = self._path(pack_name)
        if path.exists():
            path.unlink()

    def clear_all(self) -> int:
        """Remove all pack locks. Returns the number of locks deleted."""
        if not self._dir.exists():
            return 0
        removed = 0
        for path in self._dir.glob("*.json"):
            path.unlink()
            removed += 1
        return removed
