"""ObservabilityTracer — the primary entry point for span-based observability.

Provides context-manager APIs for creating traces and nested spans.
All spans are persisted via ``SpanWriter`` to ``.vibe/observability/spans.jsonl``.

Concurrency-safety: uses ``contextvars.ContextVar`` for trace context
isolation. This is asyncio-aware — each ``asyncio.Task`` gets its own
copy of the context, so concurrent ``asyncio.gather`` calls cannot
interleave their span stacks (which was the bug with ``threading.local``).
Sync code behaves the same as before: each thread has its own context.
Signal-safety: registers SIGINT/SIGTERM handlers and atexit hook for flush.
"""

from __future__ import annotations

import atexit
import contextvars
import logging
import signal
import sys
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibesop.core.observability.models import SpanKind, TraceContext

from vibesop.core.observability.models import Span as _Span
from vibesop.core.observability.process_identity import (
    get_process_project_id,
    get_process_session_id,
)
from vibesop.core.observability.span_writer import SpanWriter

logger = logging.getLogger(__name__)

# Module-level singleton (lazy-initialised on first get_tracer()).
_tracer: ObservabilityTracer | None = None
_lock = threading.Lock()


def get_tracer(
    storage_path: Path | str | None = None,
    enabled: bool = True,
) -> ObservabilityTracer:
    """Return the module-level ObservabilityTracer singleton.

    Args:
        storage_path: Where to write spans (default: ``.vibe/observability/spans.jsonl``).
        enabled: If False, all tracing calls are no-ops.

    Call this once during initialisation. Subsequent calls return the
    same instance (ignoring arguments).
    """
    global _tracer
    if _tracer is None:
        with _lock:
            if _tracer is None:
                _tracer = ObservabilityTracer(storage_path=storage_path, enabled=enabled)
    return _tracer


def _reset_tracer_for_tests() -> None:
    """Tear down the singleton so the next ``get_tracer()`` call re-creates it.

    Test-only escape hatch: the singleton's SpanWriter captures CWD +
    is_dev_environment() at construction, which couples it to the first
    test that triggered creation. Tests that need to verify path routing
    end-to-end should call this in setup to start fresh.

    Not exported via ``__all__`` — internal use only.
    """
    global _tracer
    with _lock:
        _tracer = None


@contextmanager
def bind_task_context(
    task_id: str | None, role_id: str | None = None
) -> Generator[None, None, None]:
    """Bind ``task_id`` / ``role_id`` to the active trace context.

    Descendant spans emitted inside this block (via ``tracer.span()`` or
    ``start_span()``) will inherit these values instead of the trace root's.
    Useful when orchestrator iterates ``plan.steps`` and wants each step's
    LLM calls tagged with ``step.step_id`` + ``step.assigned_role``.

    No-op if no active trace or tracer disabled. Callers should run inside
    ``with tracer.trace(...)`` for binding to take effect.

    **Concurrency limitation**: uses mutation-based binding on the shared
    ``TraceContext`` object. Safe for **sequential** step iteration
    (``for step in plan.steps: with bind_task_context(...): ...``).
    **NOT safe for concurrent coroutines inside a single trace** via
    ``asyncio.gather()`` — coroutines share the same ``TraceContext``
    reference (``contextvars`` copies the binding, not the object), so
    interleaved binds corrupt each other. For parallel steps, run each
    in its own ``tracer.trace()`` (which calls ``_set_context(new_ctx)``
    creating an independent object).

    **Cross-process limitation**: ``contextvars`` does NOT cross process
    boundaries. Sub-agent execution (Claude Code CLI etc.) runs as a
    separate OS process — bind has no effect there. Cross-process task
    attribution is established via the mirror hook writing
    ``metadata.parent_session``, which the DAG rebuilder joins on.
    See dashboard v3 Phase A "Data Boundary" doc for the full picture.
    """
    tracer = get_tracer()
    if not tracer._enabled:
        yield
        return

    ctx = tracer._get_context()
    if ctx is None:
        # No active trace — binding is meaningless but not an error
        yield
        return

    old_task = ctx.current_task_id
    old_role = ctx.current_role_id
    ctx.current_task_id = task_id
    ctx.current_role_id = role_id
    try:
        yield
    finally:
        ctx.current_task_id = old_task
        ctx.current_role_id = old_role


class ObservabilityTracer:
    """Core trace/span manager with context-manager APIs.

    Usage::

        tracer = get_tracer()
        with tracer.trace("my-task", task_id="t1") as task_span:
            with tracer.span("llm:gpt-4o", kind="llm") as llm_span:
                # ... LLM call ...
                llm_span.set_output({"response": "..."})
                llm_span.with_tokens(100, 200).with_cost(0.001)
    """

    def __init__(
        self,
        storage_path: Path | str | None = None,
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._writer = SpanWriter(storage_path=storage_path) if enabled else None
        # ContextVar (not threading.local) so concurrent asyncio.gather tasks
        # each get an isolated span stack. asyncio's create_task copies the
        # context (PEP 567) so each Task gets its own binding.
        #
        # WARNING: ``loop.run_in_executor`` and ``ThreadPoolExecutor.submit``
        # do NOT propagate the calling context — workers get a fresh default
        # context, so spans emitted inside them are orphaned (standalone
        # trace_id). This was equally broken under threading.local. If you
        # need to emit spans from inside an executor, use
        # ``contextvars.copy_context().run(fn)`` to propagate explicitly, or
        # ``asyncio.to_thread`` (which copies context by default).
        self._ctx_var: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
            "vibesop_trace_context"
        )
        self._installed_handlers = False
        if enabled:
            self._install_handlers()

    # ------------------------------------------------------------------
    # Context managers
    # ------------------------------------------------------------------

    @contextmanager
    def trace(
        self,
        name: str,
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
        role_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[_Span, None, None]:
        """Start a top-level trace. Yields the root task span.

        Automatically sets span status to 'ok' on normal exit or 'error' on
        exception. The span is always persisted regardless of outcome.

        ``session_id`` / ``project_id`` default to ``process_identity``
        values (set by CLI entry point — one UUID per CLI run, cwd-as-project).
        Explicit kwargs override. Both are stashed on ``TraceContext`` so
        descendant spans inherit them without each call site plumbing them.
        """
        if not self._enabled:
            yield _Span(id="", trace_id="", name="noop", span_kind="task")  # type: ignore[arg-type]
            return

        # W5.0.A.3: pull process-level defaults when caller didn't pass explicit values.
        # session_id: None if process_identity wasn't seeded (non-CLI callers, tests).
        # project_id: lazy-computes str(cwd); falls back to "default" if unavailable
        # to preserve Span.project_id's data contract.
        actual_session_id = session_id or get_process_session_id()
        actual_project_id = project_id or get_process_project_id() or "default"

        trace_id = _Span.new_trace_id()
        span = _Span(
            id=_Span.new_id(),
            trace_id=trace_id,
            name=name,
            span_kind="task",
            task_id=task_id,
            session_id=actual_session_id,
            agent_id=agent_id,
            role_id=role_id,
            metadata=metadata or {},
            project_id=actual_project_id,
        )
        self._push(span.id, trace_id)
        # Stash task_id / role_id / session_id / project_id on the context so
        # descendant spans (llm-spans emitted by SpanWrappedProvider, etc.)
        # can inherit them without call-site plumbing. See v8.2 GAP-1
        # attribution fix + v3 Phase A Task 1 for role_id extension +
        # W5.0.A.2 for session_id / project_id extension.
        ctx = self._get_context()
        if ctx is not None:
            ctx.current_task_id = task_id
            ctx.current_role_id = role_id
            ctx.current_session_id = actual_session_id
            ctx.current_project_id = actual_project_id

        try:
            yield span
            span.set_ok()
        except Exception:
            span.set_error(str(sys.exc_info()[1]) if sys.exc_info()[1] else "unknown error")
            raise
        finally:
            self._pop()
            self._persist(span)

    @contextmanager
    def span(
        self,
        name: str,
        kind: SpanKind,
        *,
        parent_span_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[_Span, None, None]:
        """Create a child span. Yields the span for caller to enrich.

        If no ``parent_span_id`` is given, the current active span from the
        thread-local stack is used as parent.
        """
        if not self._enabled:
            yield _Span(id="", trace_id="", name="noop", span_kind=kind)  # type: ignore[arg-type]
            return

        ctx = self._get_context()
        if ctx is None:
            # No active trace — create a standalone span
            trace_id = _Span.new_trace_id()
        else:
            trace_id = ctx.trace_id

        actual_parent = parent_span_id or (ctx.current_span_id if ctx else None)
        # ctx.current_project_id is None when the trace root was opened without
        # a process_identity seed (e.g. legacy tests) — fall back to "default"
        # to preserve Span.project_id's str contract.
        ctx_project_id = (ctx.current_project_id if ctx else None) or "default"
        span = _Span(
            id=_Span.new_id(),
            trace_id=trace_id,
            name=name,
            span_kind=kind,
            parent_span_id=actual_parent,
            task_id=ctx.current_task_id if ctx else None,
            role_id=ctx.current_role_id if ctx else None,
            session_id=ctx.current_session_id if ctx else None,
            project_id=ctx_project_id,
            metadata=metadata or {},
        )
        self._push(span.id, trace_id)

        try:
            yield span
            span.set_ok()
        except Exception:
            span.set_error(str(sys.exc_info()[1]) if sys.exc_info()[1] else "unknown error")
            raise
        finally:
            self._pop()
            self._persist(span)

    # ------------------------------------------------------------------
    # Background span tracking (for async / callback-based flows)
    # ------------------------------------------------------------------

    def start_span(
        self,
        name: str,
        kind: SpanKind,
        *,
        parent_span_id: str | None = None,
        task_id: str | None = None,
        role_id: str | None = None,
        session_id: str | None = None,
        project_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> _Span:
        """Manually start a span (without context manager). Caller MUST call
        ``finish_span()`` or ``fail_span()`` to persist it.

        If ``task_id`` / ``role_id`` / ``session_id`` / ``project_id`` are not
        provided but there is an active trace, the context's current values
        are inherited. This lets inner call sites (LLM providers, tool
        wrappers) gain task + session + project attribution automatically
        when they run inside a ``with tracer.trace(...)`` block or
        ``bind_task_context(...)`` block.
        """
        if not self._enabled:
            return _Span(id="", trace_id="", name="noop", span_kind=kind)  # type: ignore[arg-type]

        ctx = self._get_context()
        trace_id = ctx.trace_id if ctx else _Span.new_trace_id()
        actual_parent = parent_span_id or (ctx.current_span_id if ctx else None)
        actual_task_id = task_id or (ctx.current_task_id if ctx else None)
        actual_role_id = role_id or (ctx.current_role_id if ctx else None)
        actual_session_id = session_id or (ctx.current_session_id if ctx else None)
        # Fall back to "default" when neither kwarg nor ctx provides a project_id
        # (preserves Span.project_id's str contract).
        actual_project_id = project_id or (ctx.current_project_id if ctx else None) or "default"

        span = _Span(
            id=_Span.new_id(),
            trace_id=trace_id,
            name=name,
            span_kind=kind,
            task_id=actual_task_id,
            role_id=actual_role_id,
            session_id=actual_session_id,
            project_id=actual_project_id,
            parent_span_id=actual_parent,
            metadata=metadata or {},
        )
        self._push(span.id, trace_id)
        return span

    def finish_span(self, span: _Span) -> None:
        """End a span successfully and persist it."""
        if not self._enabled or span.id == "":
            return
        span.set_ok()
        self._pop()
        self._persist(span)

    def fail_span(self, span: _Span, error: str) -> None:
        """End a span with error and persist it."""
        if not self._enabled or span.id == "":
            return
        span.set_error(error)
        self._pop()
        self._persist(span)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_context(self) -> TraceContext | None:
        return self._ctx_var.get(None)

    def _set_context(self, ctx: TraceContext | None) -> None:
        # Intentionally not tracking tokens — the span stack's push/pop is
        # symmetric within a single Task, and asyncio.Task isolation handles
        # the cross-task case. Token tracking would only matter if we needed
        # to support nested context restoration within the same Task, which
        # we don't (the _push/_pop pair already handles nesting via the
        # span_id stack on the context object itself).
        self._ctx_var.set(ctx)

    def _push(self, span_id: str, trace_id: str) -> None:
        from vibesop.core.observability.models import TraceContext

        ctx = self._get_context()
        if ctx is None:
            ctx = TraceContext(trace_id=trace_id)
            self._set_context(ctx)
        ctx.push_span(span_id)

    def _pop(self) -> None:
        ctx = self._get_context()
        if ctx:
            remaining = ctx.pop_span()
            if remaining is None:
                self._set_context(None)

    def _persist(self, span: _Span) -> None:
        if self._writer is None:
            return
        try:
            self._writer.write_span(span)
        except Exception:
            logger.exception("Failed to persist span %s", span.id)

    def flush(self) -> None:
        """No-op for JSONL writer (spans are written synchronously on each persist)."""
        pass

    # ------------------------------------------------------------------
    # Crash safety
    # ------------------------------------------------------------------

    def _install_handlers(self) -> None:
        """Install signal handlers and atexit hook for graceful shutdown."""
        if self._installed_handlers:
            return

        def _on_exit(*_args: Any) -> None:
            self.flush()

        # Best-effort: not all platforms support all signals.
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _on_exit)
            except (ValueError, OSError):
                pass

        atexit.register(_on_exit)
        self._installed_handlers = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        if not self._enabled:
            self._enabled = True
            self._writer = SpanWriter()
            self._install_handlers()

    def disable(self) -> None:
        self._enabled = False
        self._writer = None
