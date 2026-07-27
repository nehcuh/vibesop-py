"""Agent-internal observability: span tracing for LLM calls, tool calls, and skill execution.

Provides a lightweight tracer that records spans to JSONL storage
(``.vibe/observability/spans.jsonl``), which the Dashboard and
aggregator consume for metric-driven loops and instinct learning.

Usage::

    from vibesop.core.observability import ObservabilityTracer, get_tracer

    tracer = get_tracer()
    with tracer.trace("my-task", task_id="t1") as span:
        with tracer.span("llm:gpt-4o", kind="llm", parent=span) as llm_span:
            # ... LLM call ...
            llm_span.set_output({"response": "..."})
"""

from vibesop.core.observability.models import Span, SpanKind, SpanStatus, TraceContext
from vibesop.core.observability.span_writer import SpanWriter
from vibesop.core.observability.tracer import ObservabilityTracer, bind_task_context, get_tracer

__all__ = [
    "ObservabilityTracer",
    "Span",
    "SpanKind",
    "SpanStatus",
    "SpanWriter",
    "TraceContext",
    "bind_task_context",
    "get_tracer",
]
