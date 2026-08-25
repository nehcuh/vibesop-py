"""Unit tests for ``process_identity`` module (W5.0.A.1).

Verifies:
- ``set_process_session_id`` / ``get_process_session_id`` round-trip
- ``get_process_project_id`` lazy-computes from cwd
- Second ``get_process_project_id`` returns cached value (no recompute)
- Both default to None when unset (caller falls back to Span defaults)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.core.observability import process_identity
from vibesop.core.observability.process_identity import (
    get_process_project_id,
    get_process_session_id,
    set_process_project_id,
    set_process_session_id,
)


@pytest.fixture(autouse=True)
def reset_process_identity():
    """Clear module globals between tests so they don't pollute each other.

    The module-level ``_process_session_id`` / ``_process_project_id``
    persist across the process; tests must reset to a clean slate.
    """
    saved_session = process_identity._process_session_id
    saved_project = process_identity._process_project_id
    process_identity._process_session_id = None
    process_identity._process_project_id = None
    yield
    process_identity._process_session_id = saved_session
    process_identity._process_project_id = saved_project


def test_session_id_set_and_get_round_trip():
    """``set`` followed by ``get`` returns the value passed."""
    set_process_session_id("abc-123")
    assert get_process_session_id() == "abc-123"


def test_session_id_defaults_none_when_unset():
    """Before any ``set``, ``get`` returns None (pre-W5.0 behavior)."""
    assert get_process_session_id() is None


def test_project_id_lazy_computed_from_cwd(monkeypatch):
    """First ``get_process_project_id()`` call resolves str(Path.cwd()).

    W5.1: resolves symlinks so it agrees with SpanWriter._path's resolved form.
    """

    # Force lazy re-resolution by clearing cache.
    process_identity._process_project_id = None

    fake_cwd = Path("/tmp/some-project")
    monkeypatch.setattr(Path, "cwd", lambda: fake_cwd)

    result = get_process_project_id()
    assert result == str(fake_cwd.resolve())


def test_project_id_cached_after_first_resolution(monkeypatch):
    """Second ``get`` returns cached value even if cwd changes.

    Guards against accidentally calling Path.cwd() on every span write.
    """
    fake1 = Path("/first-cwd")
    monkeypatch.setattr(Path, "cwd", lambda: fake1)
    first = get_process_project_id()
    assert first == str(fake1.resolve())  # resolve(): Windows adds the drive

    # Simulate cwd changing after first resolution.
    monkeypatch.setattr(Path, "cwd", lambda: Path("/second-cwd"))
    second = get_process_project_id()
    assert second == str(fake1.resolve())  # cached, not recomputed


def test_project_id_explicit_set_overrides_lazy(monkeypatch):
    """``set_process_project_id`` overrides lazy cwd resolution."""
    set_process_project_id("/explicit-project")

    # Even if cwd is something else, explicit set wins.
    monkeypatch.setattr(Path, "cwd", lambda: Path("/somewhere-else"))
    assert get_process_project_id() == "/explicit-project"


def test_project_id_defaults_none_when_unset_and_cwd_fails(monkeypatch):
    """When unset and ``Path.cwd()`` raises, returns None (not crash).

    Caller (``tracer.trace``) falls back to Span.project_id's "default"
    in this case — that's by design (see module docstring).
    """

    def _raise():
        raise OSError("cwd unavailable")

    monkeypatch.setattr(Path, "cwd", _raise)
    process_identity._process_project_id = None  # force lazy re-resolve
    assert get_process_project_id() is None
