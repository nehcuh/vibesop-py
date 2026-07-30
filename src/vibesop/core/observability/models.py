"""Span data models — lightweight dataclasses for agent-internal observability.

These models are intentionally simple (no pydantic dependency) so they
can be created cheaply on hot paths. Persistence is handled by SpanWriter.

Schema versioning (v8.2):
    Every span carries ``schema_version``. Readers MUST accept spans whose
    version ≤ CURRENT_SPAN_SCHEMA_VERSION. Writers always emit the current
    version. ``project_id`` discriminates spans across projects so that
    per-skill aggregations (e.g. p25 confidence) are not contaminated by
    other projects' codebases.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

SpanKind = Literal["task", "llm", "tool_call", "file_edit", "workflow_node"]
SpanStatus = Literal["running", "ok", "error"]

CURRENT_SPAN_SCHEMA_VERSION = 1


@dataclass
class Span:
    """A single observability span for one unit of work.

    Lifecycle:
        created with status='running' → span.set_ok() or span.set_error(...).

    Top-level task span: parent_span_id=None, trace_id=UUID.
    Nested spans (LLM calls, tool calls): link via parent_span_id.
    """

    id: str
    trace_id: str
    name: str
    span_kind: SpanKind
    task_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    role_id: str | None = None
    parent_span_id: str | None = None
    status: SpanStatus = "running"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = CURRENT_SPAN_SCHEMA_VERSION
    # TODO(v8.2 M3): aggregator must filter by project_id to avoid cross-project
    # contamination. Pre-v8.2 spans default to "default" silently — until M3
    # lands, treat "default" project spans as untrusted when querying from a
    # different project context.
    project_id: str = "default"

    # -- lifecycle helpers --

    def set_ok(self) -> None:
        self.status = "ok"
        self.ended_at = datetime.now(UTC)

    def set_error(self, message: str) -> None:
        self.status = "error"
        self.error_message = message
        self.ended_at = datetime.now(UTC)

    def set_output(self, data: dict[str, Any]) -> None:
        self.output_data = data

    def set_input(self, data: dict[str, Any]) -> None:
        self.input_data = data

    def with_tokens(self, input_tokens: int, output_tokens: int) -> Span:
        """Fluent setter for token counts. Returns self."""
        self.tokens_input = input_tokens
        self.tokens_output = output_tokens
        return self

    def with_cost(self, cost: float) -> Span:
        self.cost_usd = cost
        return self

    def with_project_id(self, project_id: str) -> Span:
        """Fluent setter for project discriminator. Returns self."""
        self.project_id = project_id
        return self

    # -- serialisation --

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "role_id": self.role_id,
            "name": self.name,
            "span_kind": self.span_kind,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "cost_usd": self.cost_usd,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "duration_ms": (
                round((self.ended_at - self.started_at).total_seconds() * 1000)
                if self.ended_at
                else None
            ),
        }

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:16]

    @staticmethod
    def new_trace_id() -> str:
        return uuid.uuid4().hex[:16]


@dataclass
class TraceContext:
    """Per-context trace state, tracking the active trace/span hierarchy.

    Bound to a ``contextvars.ContextVar`` (not ``threading.local``) so
    ``asyncio.gather`` tasks each get their own binding.

    ``current_task_id`` / ``current_role_id`` are set by ``tracer.trace(...)``
    and inherited by descendant spans via ``start_span(...)``. This lets
    llm-spans emitted deep in the call stack (e.g. inside ``SpanWrappedProvider``)
    carry task attribution without each call site having to plumb task_id
    through their signatures. ``bind_task_context(...)`` further mutates
    these mid-trace to support step-level binding (e.g. orchestrator
    iterating ``plan.steps``).

    ``current_session_id`` / ``current_project_id`` (W5.0.A.2): same
    inheritance pattern, but for session-level and project-level identity.
    Set by ``tracer.trace(...)`` from kwargs or ``process_identity`` defaults;
    child spans pick them up so all spans in one CLI run share a session_id
    and project_id even when emitted from nested call sites.
    """

    trace_id: str
    current_span_id: str | None = None
    current_task_id: str | None = None
    current_role_id: str | None = None
    current_session_id: str | None = None
    current_project_id: str | None = None
    span_stack: list[str] = field(default_factory=list)

    def push_span(self, span_id: str) -> None:
        self.span_stack.append(span_id)
        self.current_span_id = span_id

    def pop_span(self) -> str | None:
        if self.span_stack:
            self.span_stack.pop()
        self.current_span_id = self.span_stack[-1] if self.span_stack else None
        return self.current_span_id
