"""Span writer — persists spans to JSONL file storage.

Writes spans to ``.vibe/observability/spans.jsonl`` using file-locked
appends (pattern matching ``AnalyticsStore``). Redacts sensitive data
before persistence via ``redact_sensitive()``.

Atomicity note: PIPE_BUF (4096 bytes on POSIX) only guarantees atomic
append for lines that fit. Span lines routinely exceed this once metadata
+ input_data + output_data are populated. We use an ``fcntl`` exclusive
lock to serialise writers across processes (multiple ``vibe`` hooks
running concurrently) so lines do not interleave.
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
# Kept generous so we don't routinely truncate useful debugging context.
# Cross-process serialisation is handled by fcntl lock in write_span.
_MAX_PAYLOAD_CHARS = 16384


class SpanWriter:
    """Persists spans to a JSONL file with redaction, truncation, and locking.

    Thread-safe within a process (in-process threading.Lock) and across
    processes (fcntl.LOCK_EX on the file). Required because span lines
    routinely exceed PIPE_BUF (4096 bytes), so kernel-level atomic append
    cannot be relied on.
    """

    def __init__(self, storage_path: Path | str | None = None) -> None:
        self._path = Path(storage_path) if storage_path else Path(".vibe/observability/spans.jsonl")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write_span(self, span: Span) -> None:
        """Write a single span to the JSONL file.

        The span's input_data/output_data are JSON-serialised and redacted.
        Payloads exceeding ``_MAX_PAYLOAD_CHARS`` are truncated.
        Thread-safe + cross-process-safe via fcntl lock.
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
            self._locked_append(line)

    def _locked_append(self, line: str) -> None:
        """Append with cross-process lock.

        Inline fcntl on POSIX (perf-critical: the ``test_enabled_tracer_under_100us_p95``
        benchmark gates this on <100µs p95; going through ``cross_process_lock``
        added two ``import fcntl`` lookups + a function-call layer per write
        and pushed p95 to ~200µs). On Windows, where this path is rare and
        not benchmarked, fall back to ``cross_process_lock`` which dispatches
        to ``msvcrt.locking``.

        Pre-P0-3 Windows was a silent no-op (``fcntl`` ImportError → plain
        append → concurrent writers could interleave JSONL lines). The POSIX
        path here is unchanged from before P0-3.
        """
        try:
            import fcntl
        except ImportError:
            # Windows: use the helper so msvcrt.locking actually takes the lock.
            from vibesop.utils.file_lock import cross_process_lock

            with cross_process_lock(self._path):
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(line)
            return

        with self._path.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(line)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

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
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            return records[-limit:]
