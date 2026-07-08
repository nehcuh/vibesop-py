"""Trust store for user-approved skill pack sources.

Stores user-approved pack names and source URLs at
~/.config/skills/.trusted.json. Each pack entry also records the sha256
content hash of the pack tree at approval time (F-10). On subsequent
audits, a mismatching hash revokes the implicit trust downgrade.
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

    def _load(self) -> dict[str, Any]:
        if not self.PATH.exists():
            return {"packs": {}, "sources": {}}
        try:
            return json.loads(self.PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {"packs": {}, "sources": {}}

    def _save(self) -> None:
        self.PATH.parent.mkdir(parents=True, exist_ok=True)
        write_text(self.PATH, json.dumps(self._data, indent=2, default=str))

    def is_trusted_pack(self, pack_name: str, content_sha256: str = "") -> bool:
        """Return True if *pack_name* is trusted and its hash matches (if known).

        A recorded hash that does not match the current *content_sha256* means
        the pack tree has changed since the user approved it, so trust is not
        honored (F-10). Legacy entries without a recorded hash are still honored
        for backward compatibility.
        """
        entry = self._data.get("packs", {}).get(pack_name)
        if entry is None:
            return False
        recorded = entry.get("content_sha256", "")
        if not recorded or not content_sha256:
            return True
        return recorded == content_sha256

    def is_trusted_source(self, source_url: str) -> bool:
        return source_url in self._data.get("sources", {})

    def trust_pack(self, pack_name: str, source_url: str = "", content_sha256: str = "") -> None:
        self._data.setdefault("packs", {})[pack_name] = {
            "trusted_at": datetime.now(UTC).isoformat(),
            "source": source_url,
        }
        if content_sha256:
            self._data["packs"][pack_name]["content_sha256"] = content_sha256
        else:
            logger.warning(
                "Trust recorded for %s without a content hash; the downgrade will "
                "apply to any future install of that pack name.",
                pack_name,
            )
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
