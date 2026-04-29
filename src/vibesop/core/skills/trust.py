"""Trust store for user-approved skill pack sources.

Stores user-approved pack names and source URLs at
~/.config/skills/.trusted.json.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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
        self.PATH.write_text(json.dumps(self._data, indent=2, default=str))

    def is_trusted_pack(self, pack_name: str) -> bool:
        return pack_name in self._data.get("packs", {})

    def is_trusted_source(self, source_url: str) -> bool:
        return source_url in self._data.get("sources", {})

    def trust_pack(self, pack_name: str, source_url: str = "") -> None:
        self._data.setdefault("packs", {})[pack_name] = {
            "trusted_at": datetime.now(UTC).isoformat(),
            "source": source_url,
        }
        self._save()

    def trust_source(self, source_url: str, reason: str = "") -> None:
        self._data.setdefault("sources", {})[source_url] = {
            "trusted_at": datetime.now(UTC).isoformat(),
            "reason": reason,
        }
        self._save()

    def revoke(self, key: str) -> bool:
        removed = (
            self._data.get("packs", {}).pop(key, None)
            or self._data.get("sources", {}).pop(key, None)
        )
        if removed:
            self._save()
        return removed is not None

    def get_trusted_packs(self) -> dict[str, Any]:
        return dict(self._data.get("packs", {}))

    def get_trusted_sources(self) -> dict[str, Any]:
        return dict(self._data.get("sources", {}))
