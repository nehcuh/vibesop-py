"""Reflection dataclass — human-style annotation against routing / skill / task spans.

A Reflection captures a learning note the user (or the system) wants to
attach to a specific observability target:

- ``route_span``     — a routing decision (skill match / fallback)
- ``skill_span``     — a skill execution
- ``task``           — an entire task
- ``subagent``       — a sub-agent execution
- ``decision_node``  — a workflow graph fork (e.g. classifier pattern choice)

7 reflection kinds cover the dashboard v3 taxonomy:

- ``routing_miss``      — should have routed elsewhere
- ``skill_misuse``      — wrong skill invocation pattern
- ``trigger_vague``     — query was too vague to route cleanly
- ``cost_blow``         — spent too many tokens / tool calls
- ``agent_choice``      — wrong sub-agent assigned
- ``positive_pattern``  — something worked well (promote to instinct)
- ``context_note``      — generic annotation

Status lifecycle: ``open`` → ``addressed`` | ``dismissed`` (Task 8/9 store
handles transitions; here we only define the literals + JSON round-trip).

Round-trip contract: ``Reflection.from_dict(r.to_dict()) == r`` for any
Reflection, including ``created_at`` (ISO 8601 with tz) and ``linked_action``
(arbitrary dict or None).
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, get_args

logger = logging.getLogger(__name__)

__all__ = [
    "Reflection",
    "ReflectionKind",
    "ReflectionStatus",
    "ReflectionStore",
    "TargetType",
]


ReflectionKind = Literal[
    "routing_miss",
    "skill_misuse",
    "trigger_vague",
    "cost_blow",
    "agent_choice",
    "positive_pattern",
    "context_note",
]

ReflectionStatus = Literal["open", "addressed", "dismissed"]

TargetType = Literal["route_span", "skill_span", "task", "subagent", "decision_node"]

_VALID_KINDS: frozenset[str] = frozenset(get_args(ReflectionKind))
_VALID_STATUS: frozenset[str] = frozenset(get_args(ReflectionStatus))
_VALID_TARGET_TYPES: frozenset[str] = frozenset(get_args(TargetType))
_VALID_SEVERITY: frozenset[str] = frozenset({"info", "warn", "critical"})


def _validate_choice(value: str, valid: frozenset[str], field_name: str) -> str:
    """Runtime-validate a Literal field — keeps the dataclass a normal
    dataclass (no Pydantic dependency) while still rejecting bad values
    at construction time."""
    if value not in valid:
        msg = f"{field_name}={value!r} is not one of {sorted(valid)}"
        raise ValueError(msg)
    return value


@dataclass
class Reflection:
    """A single reflection annotation.

    Identity: ``id`` (uuid4 hex). Equality includes every field, so two
    Reflections with the same id but different content are NOT equal —
    round-trip identity requires every field to match.
    """

    target_type: TargetType
    target_id: str
    task_id: str
    kind: ReflectionKind
    content: str
    severity: Literal["info", "warn", "critical"] = "info"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: ReflectionStatus = "open"
    linked_action: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        # Runtime-validate the Literal fields. dataclass + Literal alone
        # does not enforce at runtime — without this, Reflection(target_type="x",
        # ..., kind="invalid_kind", ...) would silently construct an invalid
        # object that only fails when serialized.
        _validate_choice(self.target_type, _VALID_TARGET_TYPES, "target_type")
        _validate_choice(self.kind, _VALID_KINDS, "kind")
        _validate_choice(self.severity, _VALID_SEVERITY, "severity")
        _validate_choice(self.status, _VALID_STATUS, "status")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict.

        ``created_at`` becomes ISO 8601 with tz offset; ``linked_action``
        passes through unchanged (caller is responsible for JSON-safety of
        nested values — same contract as ``Span.metadata``).
        """
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "task_id": self.task_id,
            "kind": self.kind,
            "content": self.content,
            "severity": self.severity,
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "linked_action": self.linked_action,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Reflection:
        """Deserialize from ``to_dict`` output.

        Re-parses ``created_at`` (ISO 8601 → aware datetime). Other
        Literal fields are validated again on construction (defensive —
        a hand-edited JSON file could carry an invalid kind).
        """
        payload = dict(d)
        raw_created = payload.get("created_at")
        if isinstance(raw_created, str):
            payload["created_at"] = datetime.fromisoformat(raw_created)
        return cls(**payload)


class ReflectionStore:
    """Append-only JSONL store for Reflections.

    File layout: ``<storage_dir>/reflections.jsonl`` — one Reflection per
    line, serialised via ``Reflection.to_dict``. Production callers pass
    ``storage_dir=.vibe/observability`` (matching the SpanWriter convention
    where ``storage_dir`` IS the leaf directory).

    Concurrency: in-process ``threading.Lock`` + cross-process ``fcntl``
    on POSIX (or ``cross_process_lock`` on Windows). Same pattern as
    ``SpanWriter._locked_append``: PIPE_BUF (4096 bytes on POSIX) does not
    guarantee atomic append for reflection payloads that exceed it once
    ``content`` + ``linked_action`` are populated, so we MUST take the lock.

    Failure mode: ``list_all`` skips malformed JSON lines instead of
    raising — a partially-written file (e.g. disk-full mid-append in a
    pre-lock era, or a hand-edited corruption) must not crash the
    dashboard that reads this file.
    """

    FILENAME = "reflections.jsonl"

    def __init__(self, storage_dir: Path | str) -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / self.FILENAME
        self._lock = threading.Lock()

    def append(self, reflection: Reflection) -> None:
        """Append one reflection to the JSONL log.

        Atomicity: cross-process serialised via fcntl.LOCK_EX (POSIX) or
        ``cross_process_lock`` (Windows). In-process serialised via
        ``threading.Lock``. The two-layer locking matches SpanWriter.
        """
        line = json.dumps(reflection.to_dict(), ensure_ascii=False) + "\n"
        with self._lock:
            self._locked_append(line)

    def _locked_append(self, line: str) -> None:
        """Append with cross-process lock (pattern from SpanWriter._locked_append).

        Inline fcntl on POSIX — the import is cheap and flock is the right
        primitive. Windows falls back to ``cross_process_lock`` (which
        dispatches to ``msvcrt.locking``).
        """
        try:
            import fcntl
        except ImportError:
            from vibesop.utils.file_lock import cross_process_lock

            with cross_process_lock(self._path), self._path.open("a", encoding="utf-8") as f:
                f.write(line)
            return

        with self._path.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(line)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def list_all(self) -> list[Reflection]:
        """Read all reflections from the log.

        Returns reflections in file order (insertion order; newest last).
        Malformed JSON lines are skipped with a debug log — the dashboard
        must not crash because of one corrupt line.
        """
        if not self._path.exists():
            return []
        out: list[Reflection] = []
        with self._path.open("r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(
                        "skipping malformed reflection line %d in %s",
                        lineno,
                        self._path,
                    )
                    continue
                try:
                    out.append(Reflection.from_dict(d))
                except (ValueError, TypeError):
                    # Schema-violating line (bad kind / status / etc.) — skip
                    # rather than crash. Hand-edited files are a real failure
                    # mode and the dashboard should still render the rest.
                    logger.debug(
                        "skipping schema-invalid reflection line %d in %s",
                        lineno,
                        self._path,
                    )
                    continue
        return out

    def list_by_task(self, task_id: str) -> list[Reflection]:
        """Return only reflections whose ``task_id`` matches.

        Used by the dashboard's task-detail view to render reflections
        scoped to one task. Order matches ``list_all`` (insertion order).
        """
        return [r for r in self.list_all() if r.task_id == task_id]

    def list_open(self) -> list[Reflection]:
        """Return only reflections whose ``status == "open"``.

        The dashboard's reflection inbox shows only open items — addressed
        / dismissed are archived. Order matches ``list_all``.
        """
        return [r for r in self.list_all() if r.status == "open"]

    def update_status(self, reflection_id: str, new_status: ReflectionStatus) -> None:
        """Flip one reflection's status (open → addressed / dismissed).

        Atomicity: this is a read-modify-write cycle on the whole file —
        the entire ``reflections.jsonl`` is rewritten via ``AtomicWriter``
        (tmp file + rename) under the same cross-process lock as ``append``.
        Without the lock, two concurrent updates would each read the
        pre-update file and the loser's mutation would be silently dropped
        (lost-update race).

        Raises:
            KeyError: ``reflection_id`` not present in the log. Failing
                loud is intentional — a silent no-op would hide dashboard
                bugs where a stale id (post-rebuild) is sent to the store.
            ValueError / TypeError: ``new_status`` not in
                ``ReflectionStatus`` Literal.
        """
        # Validate the new status literal BEFORE acquiring the lock — fail
        # fast on caller bugs without blocking other writers.
        _validate_choice(new_status, _VALID_STATUS, "new_status")

        with self._lock:
            self._locked_update_status(reflection_id, new_status)

    def _locked_update_status(
        self, reflection_id: str, new_status: ReflectionStatus
    ) -> None:
        """Read → mutate one row → atomic rewrite. MUST be called under
        ``self._lock`` AND the cross-process lock to be safe."""
        from vibesop.utils.atomic_writer import AtomicWriter

        # Read pre-state
        current = self.list_all()
        if not current:
            raise KeyError(reflection_id)
        target_idx = next(
            (i for i, r in enumerate(current) if r.id == reflection_id), None
        )
        if target_idx is None:
            raise KeyError(reflection_id)

        # Mutate (dataclass replace via direct field set — Reflection is
        # mutable by default; ``frozen=True`` would block this)
        current[target_idx].status = new_status

        # Atomic rewrite under cross-process lock so concurrent appenders
        # cannot interleave with this rewrite.
        try:
            import fcntl
        except ImportError:
            from vibesop.utils.file_lock import cross_process_lock

            with cross_process_lock(self._path):
                self._atomic_write_all(current, AtomicWriter())
            return

        with self._path.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                self._atomic_write_all(current, AtomicWriter())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _atomic_write_all(
        self, reflections: list[Reflection], writer: Any
    ) -> None:
        """Rewrite the entire JSONL file atomically.

        ``AtomicWriter`` writes to ``<path>.tmp`` and renames into place —
        a crash mid-write leaves the old file intact rather than a
        truncated mix of old + new lines.
        """
        with writer.atomic_open(self._path, "w") as f:
            for r in reflections:
                f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")

