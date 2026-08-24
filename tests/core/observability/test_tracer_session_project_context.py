"""Tests for tracer session_id + project_id inheritance (W5.0.A.2 + A.3).

Verifies:
- ``trace()`` pulls session_id / project_id from ``process_identity`` when
  caller doesn't pass explicit values
- Explicit kwargs override process defaults
- Child spans (via ``span()`` and ``start_span()``) inherit both fields
  from the active ``TraceContext``
- Reset between tests so process_identity doesn't leak across the suite
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibesop.core.observability import process_identity
from vibesop.core.observability.tracer import ObservabilityTracer


@pytest.fixture
def fresh_tracer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ObservabilityTracer:
    """Reset the module-level tracer singleton to write into tmp_path."""
    import vibesop.core.observability.tracer as tracer_mod

    span_file = tmp_path / "spans.jsonl"
    fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return fresh


@pytest.fixture(autouse=True)
def reset_process_identity():
    """Clear process_identity globals between tests."""
    saved_session = process_identity._process_session_id
    saved_project = process_identity._process_project_id
    process_identity._process_session_id = None
    process_identity._process_project_id = None
    yield
    process_identity._process_session_id = saved_session
    process_identity._process_project_id = saved_project


def _read_spans(path: Path) -> list[dict]:
    if not path.exists():
        return []
    spans: list[dict] = []
    with path.open() as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if stripped:
                spans.append(json.loads(stripped))
    return spans


class TestTracePullsProcessDefaults:
    """A.3: trace() with no explicit kwargs pulls from process_identity."""

    def test_trace_pulls_session_id_from_process(self, fresh_tracer, tmp_path):
        """When session_id kwarg is None, trace() falls back to
        ``get_process_session_id()``."""
        process_identity.set_process_session_id("session-from-cli")
        with fresh_tracer.trace("root"):
            pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        assert spans[0]["session_id"] == "session-from-cli"

    def test_trace_pulls_project_id_from_process(self, fresh_tracer, tmp_path, monkeypatch):
        """When project_id kwarg is None, trace() falls back to
        ``get_process_project_id()`` (lazy cwd resolution)."""
        monkeypatch.setattr(Path, "cwd", lambda: Path("/tmp/mycms"))
        process_identity._process_project_id = None  # force lazy re-resolve
        with fresh_tracer.trace("root"):
            pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        # W5.1: project_id resolves symlinks so it agrees with SpanWriter._path.
        assert spans[0]["project_id"] == str(Path("/tmp/mycms").resolve())

    def test_explicit_session_id_overrides_process(self, fresh_tracer, tmp_path):
        """Explicit kwarg wins over process default."""
        process_identity.set_process_session_id("process-session")
        with fresh_tracer.trace("root", session_id="explicit-session"):
            pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        assert spans[0]["session_id"] == "explicit-session"

    def test_explicit_project_id_overrides_process(self, fresh_tracer, tmp_path, monkeypatch):
        """Explicit project_id kwarg wins over lazy cwd."""
        monkeypatch.setattr(Path, "cwd", lambda: Path("/tmp/wrong-cwd"))
        process_identity._process_project_id = None
        with fresh_tracer.trace("root", project_id="my-explicit-project"):
            pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        assert spans[0]["project_id"] == "my-explicit-project"

    def test_trace_with_no_process_identity_emits_null_session(
        self, fresh_tracer, tmp_path, monkeypatch
    ):
        """When neither kwarg nor process_identity is set, session_id is null
        and project_id falls back to 'default'.

        This preserves pre-W5.0 behavior for non-CLI callers (library use,
        unit tests that don't mint a session).
        """

        # Force Path.cwd() to fail so project_id also falls back.
        def _raise():
            raise OSError("cwd unavailable")

        monkeypatch.setattr(Path, "cwd", _raise)
        process_identity._process_session_id = None
        process_identity._process_project_id = None

        with fresh_tracer.trace("root"):
            pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        assert spans[0]["session_id"] is None
        assert spans[0]["project_id"] == "default"


class TestChildSpanInheritsSessionProject:
    """A.2: child spans (span() + start_span()) inherit session_id + project_id
    from the active TraceContext."""

    def test_child_span_inherits_session_id(self, fresh_tracer, tmp_path):
        """span() inside trace(session_id=...) inherits the session_id."""
        with fresh_tracer.trace("root", session_id="my-session"):
            with fresh_tracer.span("llm:call", "llm"):
                pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        child = next(s for s in spans if s["name"] == "llm:call")
        assert child["session_id"] == "my-session"

    def test_child_span_inherits_project_id(self, fresh_tracer, tmp_path):
        """span() inside trace(project_id=...) inherits the project_id."""
        with fresh_tracer.trace("root", project_id="my-project"):
            with fresh_tracer.span("llm:call", "llm"):
                pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        child = next(s for s in spans if s["name"] == "llm:call")
        assert child["project_id"] == "my-project"

    def test_child_span_inherits_process_defaults(self, fresh_tracer, tmp_path, monkeypatch):
        """Child inherits the process-resolved session_id + project_id even
        when trace() didn't receive explicit kwargs (the typical CLI path)."""
        process_identity.set_process_session_id("cli-session")
        monkeypatch.setattr(Path, "cwd", lambda: Path("/tmp/cli-project"))
        process_identity._process_project_id = None

        with fresh_tracer.trace("root"):
            with fresh_tracer.span("llm:call", "llm"):
                pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        child = next(s for s in spans if s["name"] == "llm:call")
        assert child["session_id"] == "cli-session"
        # W5.1: project_id resolves symlinks so it agrees with SpanWriter._path.
        assert child["project_id"] == str(Path("/tmp/cli-project").resolve())

    def test_start_span_inherits_session_project(self, fresh_tracer, tmp_path):
        """start_span() (manual API) inherits session_id + project_id too.

        Regression guard: SpanWrappedProvider uses start_span, not span().
        """
        with fresh_tracer.trace("root", session_id="root-session", project_id="root-proj"):
            span = fresh_tracer.start_span("llm:call", "llm")
            fresh_tracer.finish_span(span)

        spans = _read_spans(tmp_path / "spans.jsonl")
        llm = next(s for s in spans if s["name"] == "llm:call")
        assert llm["session_id"] == "root-session"
        assert llm["project_id"] == "root-proj"
