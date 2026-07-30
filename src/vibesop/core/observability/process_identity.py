"""Process-level session + project identity (W5.0.A.1).

Each CLI invocation is a distinct session; spans emitted within one CLI
process share a session_id so downstream recall / clustering can group
"this run" vs "this query across runs".

The CLI entry point (``cli/main.py`` route path) mints one UUID per
process via ``set_process_session_id``. Subprocesses (hooks shelling out)
get their own UUID — that's correct: a hook firing is a separate session
from the CLI that triggered it.

``project_id`` is lazy-computed from ``Path.cwd()`` on first access and
cached. Cached because cwd doesn't change mid-process in practice; if a
caller does ``os.chdir`` they should ``set_process_project_id`` explicitly.

Defaults:
- ``session_id``: ``None`` until ``set_process_session_id`` is called.
  ``tracer.trace()`` leaves Span.session_id as None when no value is set,
  matching pre-W5.0 behavior for code paths that don't go through the CLI
  (e.g. unit tests, library use).
- ``project_id``: falls back to ``"default"`` if cwd is unavailable.
  This matches Span.project_id's default and keeps the data contract
  stable for spans emitted in non-CLI contexts.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "get_process_project_id",
    "get_process_session_id",
    "set_process_project_id",
    "set_process_session_id",
]

_process_session_id: str | None = None
_process_project_id: str | None = None


def set_process_session_id(session_id: str) -> None:
    """Set the process-level session_id (one UUID per CLI invocation).

    Idempotent within a process — last write wins. CLI calls this once
    near entry; library callers may set it explicitly to correlate spans
    across library boundaries (e.g. in-process agent API).
    """
    global _process_session_id
    _process_session_id = session_id


def get_process_session_id() -> str | None:
    """Return the session_id set by ``set_process_session_id``, or None."""
    return _process_session_id


def set_process_project_id(project_id: str) -> None:
    """Set the process-level project_id explicitly.

    Use when cwd is not the right project indicator (e.g. orchestrator
    invoked from a different cwd than the target project). Clears the
    lazy cache — subsequent ``get_process_project_id()`` returns this value.
    """
    global _process_project_id
    _process_project_id = project_id


def get_process_project_id() -> str | None:
    """Return the project_id, lazy-computing from cwd on first call.

    Returns None if cwd can't be resolved (extremely rare; caller —
    ``tracer.trace()`` — falls back to Span.project_id's "default" in
    that case). Cached after first successful resolution.

    W5.1: resolves symlinks so the canonical form agrees with
    ``SpanWriter._path`` (which calls ``Path.resolve()`` at construction).
    Without this, macOS tmpdir-backed paths (``/tmp/...`` →
    ``/private/tmp/...``) would disagree with SpanWriter, breaking
    Phase 3 ``vibe pool`` membership matching.
    """
    global _process_project_id
    if _process_project_id is None:
        try:
            cwd = Path.cwd().resolve()
            _process_project_id = str(cwd)
        except (OSError, RuntimeError):
            # cwd unavailable (deleted, permission, etc.). Leave None;
            # caller falls back to "default".
            return None
    return _process_project_id
