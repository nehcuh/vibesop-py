"""Trust store for user-approved skill pack sources.

Stores user-approved pack names and source URLs at
~/.config/skills/.trusted.json. Every pack entry records the sha256
content hash of the pack tree at approval time (F-10) — entries without
a hash are never honored. On subsequent audits, a mismatching hash
revokes the implicit trust downgrade.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vibesop.utils.atomic_writer import write_text

logger = logging.getLogger(__name__)


class TrustStore:
    """Persistent store for user-approved skill pack sources."""

    PATH: Path = Path.home() / ".config" / "skills" / ".trusted.json"

    def __init__(self) -> None:
        self._data = self._load()
        self._migrate_legacy_entries()

    def _load(self) -> dict[str, Any]:
        if not self.PATH.exists():
            return {"packs": {}, "sources": {}}
        try:
            return json.loads(self.PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {"packs": {}, "sources": {}}

    def _save(self) -> None:
        self.PATH.parent.mkdir(parents=True, exist_ok=True)
        write_text(self.PATH, json.dumps(self._data, indent=2, default=str))

    def _migrate_legacy_entries(self) -> None:
        """One-time migration for pre-F-10 pack entries that lack a content hash.

        For each trusted pack without ``content_sha256``: if the installed
        pack directory still exists next to the trust store
        (``~/.config/skills/<pack>``), backfill the hash from the current
        tree; otherwise drop the stale entry. New entries always carry a hash
        (``trust_pack`` enforces it), so once every entry is hashed this
        short-circuits to a no-op on subsequent loads.
        """
        packs = self._data.get("packs", {})
        legacy = [name for name, info in packs.items() if not info.get("content_sha256")]
        if not legacy:
            return

        from vibesop.utils.marker_files import MarkerFileManager

        changed = False
        for name in legacy:
            pack_dir = self.PATH.parent / name
            if pack_dir.is_dir():
                try:
                    packs[name]["content_sha256"] = MarkerFileManager().calculate_checksum(pack_dir)
                except OSError as e:
                    logger.warning("Could not hash legacy trusted pack %s: %s", name, e)
                    continue
                logger.warning(
                    "legacy trust entry %r migrated: content hash computed from "
                    "current on-disk pack; re-run 'vibe trust <pack>' if you did "
                    "not expect this",
                    name,
                )
                changed = True
            else:
                del packs[name]
                logger.info(
                    "Dropped legacy trusted pack %s (pack directory %s not found)",
                    name,
                    pack_dir,
                )
                changed = True
        if changed:
            self._save()

    def is_trusted_pack(self, pack_name: str, content_sha256: str = "") -> bool:
        """Return True only if *pack_name* is trusted with a matching recorded hash.

        A recorded hash that does not match the current *content_sha256* means
        the pack tree has changed since the user approved it, so trust is not
        honored (F-10). Entries without a recorded hash are never trusted;
        legacy entries are migrated (hash backfill) or dropped at load time.
        """
        entry = self._data.get("packs", {}).get(pack_name)
        if entry is None:
            return False
        recorded = entry.get("content_sha256", "")
        return bool(recorded) and recorded == content_sha256

    def is_trusted_source(self, source_url: str) -> bool:
        return source_url in self._data.get("sources", {})

    def trust_pack(self, pack_name: str, source_url: str = "", content_sha256: str = "") -> None:
        """Record user trust for *pack_name*, bound to its content hash (F-10).

        Raises:
            ValueError: If *content_sha256* is empty. Trust without a content
                hash would silently downgrade future audits of any pack with
                this name, so it is a hard error. Install the pack first so
                its content can be hashed.
        """
        if not content_sha256:
            raise ValueError(
                f"content_sha256 is required to trust pack {pack_name!r}; "
                "install the pack first so its content can be hashed"
            )
        self._data.setdefault("packs", {})[pack_name] = {
            "trusted_at": datetime.now(UTC).isoformat(),
            "source": source_url,
            "content_sha256": content_sha256,
        }
        self._save()

    def trust_source(self, source_url: str, reason: str = "") -> None:
        self._data.setdefault("sources", {})[source_url] = {
            "trusted_at": datetime.now(UTC).isoformat(),
            "reason": reason,
        }
        self._save()

    def revoke(self, key: str) -> bool:
        removed = self._data.get("packs", {}).pop(key, None) or self._data.get("sources", {}).pop(
            key, None
        )
        if removed:
            self._save()
        return removed is not None

    def get_trusted_packs(self) -> dict[str, Any]:
        return dict(self._data.get("packs", {}))

    def get_trusted_sources(self) -> dict[str, Any]:
        return dict(self._data.get("sources", {}))
