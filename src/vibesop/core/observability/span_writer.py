"""Span writer — persists spans to JSONL file storage.

Writes spans to ``.vibe/observability/spans.jsonl`` using atomic writes
(pattern matching ``AnalyticsStore``). Redacts sensitive data before
persistence via ``redact_sensitive()``.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from vibesop.utils.redaction import redact_sensitive

if TYPE_CHECKING:
    from vibesop.core.observability.models import Span

logger = logging.getLogger(__name__)

# Default max payload chars for input_data / output_data serialisation.
_MAX_PAYLOAD_CHARS = 16384


class SpanWriter:
    """Persists spans to a JSONL file with redaction and truncation.

    Thread-safe: appends are serialised through a per-instance lock.
    JSONL append writes are inherently atomic for lines ≤ PIPE_BUF
    on POSIX systems (typically 4096 bytes).
    """

    def __init__(self, storage_path: Path | str | None = None) -> None:
        self._path = Path(storage_path) if storage_path else Path(".vibe/observability/spans.jsonl")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write_span(self, span: Span) -> None:
        """Write a single span to the JSONL file.

        The span's input_data/output_data are JSON-serialised and redacted.
        Payloads exceeding ``_MAX_PAYLOAD_CHARS`` are truncated.
        Thread-safe via internal lock.
        """
        record = span.to_dict()

        # Serialise and redact input_data / output_data
        for key in ("input_data", "output_data"):
            val = record.get(key)
            if val is not None:
                try:
                    serialised = json.dumps(val, ensure_ascii=False)
                except (TypeError, ValueError):
                    serialised = str(val)
                safe = self._truncate(redact_sensitive(serialised))
                record[key] = safe

        # Redact metadata fields (stored as string after serialisation)
        if record.get("metadata"):
            try:
                meta_str = json.dumps(record["metadata"], ensure_ascii=False)
                safe = self._truncate(redact_sensitive(meta_str))
                record["metadata"] = safe
            except (TypeError, ValueError):
                record["metadata"] = str(record["metadata"])

        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)

    @staticmethod
    def _truncate(s: str, max_chars: int = _MAX_PAYLOAD_CHARS) -> str:
        if len(s) <= max_chars:
            return s
        return s[: max_chars - 12] + "[TRUNCATED]"

    def query_recent(self, limit: int = 100) -> list[dict]:
        """Read the most recent spans (newest last, limited to *limit*)."""
        if not self._path.exists():
            return []
        records: list[dict] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            return records[-limit:]
