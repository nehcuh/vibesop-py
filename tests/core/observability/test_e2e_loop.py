"""End-to-end test: SpanWrappedProvider → SpanWriter → SpanAggregator → CLI.

Validates the v8.2 P1 observability loop:
1. A fake routing call enters ``agent_runtime`` (simulated by ``tracer.trace``).
2. Inside the trace, an LLM call goes through ``SpanWrappedProvider``.
3. Span is persisted to spans.jsonl by SpanWriter.
4. SpanAggregator attributes it to the right skill via trace_id map.
5. CLI ``vibe trace replay`` renders the trace as a tree.

This catches integration regressions that unit tests on each component miss
(e.g. metadata schema mismatch between writer and aggregator, parent_span_id
linkage broken, orphan handling inconsistent).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.trace_cmd import app
from vibesop.core.observability.aggregator import SpanAggregator
from vibesop.core.observability.tracer import ObservabilityTracer
from vibesop.llm.base import LLMProvider, LLMResponse
from vibesop.llm.span_wrapped import SpanWrappedProvider


class _StaticProvider(LLMProvider):
    """Returns a fixed response — no network."""

    def __init__(self) -> None:
        super().__init__(api_key="sk-static-key-1234567890", base_url=None)

    @property
    def provider_name(self) -> str:
        return "Static"

    def default_model(self) -> str:
        return "static-model"

    def call(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        return LLMResponse(
            content="routed to mcp-install",
            model="static-model",
            provider="Static",
            tokens_used=150,
            input_tokens=120,
            output_tokens=30,
        )


@pytest.fixture
def e2e_tracer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ObservabilityTracer:
    """Patch the global tracer singleton with a fresh enabled instance."""
    import vibesop.core.observability.tracer as tracer_mod

    fresh = ObservabilityTracer(
        storage_path=tmp_path / "spans.jsonl", enabled=True
    )
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return fresh


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_e2e_full_loop(
    e2e_tracer: ObservabilityTracer,
    tmp_path: Path,
    runner: CliRunner,
) -> None:
    """The full P1 loop: wrap → write → aggregate → replay → attribute."""
    spans_path = tmp_path / "spans.jsonl"
    wrapped = SpanWrappedProvider(_StaticProvider())

    # Simulate agent_runtime.handle_query: open a trace, run LLM, close.
    with e2e_tracer.trace(
        "route:install mcp server",
        task_id=None,  # agent_runtime currently passes None
        metadata={"query": "install mcp server", "platform": "claude-code"},
    ) as task_span:
        # Routing happens, decision is made, then we call the LLM (triage).
        wrapped.call(
            "classify intent: install mcp server",
            model="static-model",
            max_tokens=100,
        )
        # Backfill skill_id like agent_runtime.py:551 does after routing.
        task_span.metadata["skill_id"] = "mcp-install"
        task_span.metadata["mode"] = "single"
        task_span.metadata["confidence"] = 0.85

    # ---- Span file now has 2 entries: task + llm ----
    assert spans_path.exists()
    lines = [ln for ln in spans_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2

    # ---- Aggregator attributes correctly ----
    agg = SpanAggregator(spans_path=spans_path)
    metrics = agg.get_skill_metrics("mcp-install", use_analytics_fallback=False)

    assert metrics.source == "spans"
    assert metrics.total_executions == 1
    assert metrics.llm_call_count == 1
    assert metrics.llm_success_rate == 1.0
    # Token counts from llm-span, not the zero-filled task-span
    assert metrics.avg_tokens == 150  # 120 in + 30 out
    assert "mcp-install" in agg.get_all_skill_ids()

    # ---- CLI replay renders the tree ----
    result = runner.invoke(app, ["replay", "--span-file", str(spans_path)])
    assert result.exit_code == 0
    assert "route:install mcp server" in result.output
    assert "llm:Static:static-model" in result.output
    assert "skill=mcp-install" in result.output


def test_e2e_orphan_llm_span_when_no_active_trace(
    e2e_tracer: ObservabilityTracer,
    tmp_path: Path,
    runner: CliRunner,
) -> None:
    """LLM call outside any ``tracer.trace()`` block produces an orphan span.

    The span lands in spans.jsonl (GAP-1 literally closed) but has no
    trace_id linkage to attribute it to a skill. Replay skips orphans.
    Aggregator excludes it from skill metrics.
    """
    spans_path = tmp_path / "spans.jsonl"
    wrapped = SpanWrappedProvider(_StaticProvider())

    # No active trace — simulate hook path before agent_runtime opens one
    wrapped.call("orphan LLM call", model="static-model")

    # File has 1 entry
    lines = [ln for ln in spans_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["span_kind"] == "llm"
    assert record["task_id"] is None
    # trace_id was generated (standalone), parent_span_id is None
    assert record["parent_span_id"] is None

    # Aggregator: skill metrics see no data for any skill
    agg = SpanAggregator(spans_path=spans_path)
    metrics = agg.get_skill_metrics("any-skill", use_analytics_fallback=False)
    assert metrics.source == "none"
    assert metrics.llm_call_count == 0

    # Replay: the orphan trace renders but contains only the single llm span
    result = runner.invoke(app, ["replay", "--span-file", str(spans_path)])
    assert result.exit_code == 0
    assert "llm:Static:static-model" in result.output


def test_e2e_multiple_skills_one_session(
    e2e_tracer: ObservabilityTracer,
    tmp_path: Path,
) -> """Two traces, two skills, no cross-contamination.""":
    spans_path = tmp_path / "spans.jsonl"
    wrapped = SpanWrappedProvider(_StaticProvider())

    # Trace 1: routes to skill-a
    with e2e_tracer.trace("route:query a", metadata={"platform": "test"}) as t1:
        wrapped.call("classify a")
        t1.metadata["skill_id"] = "skill-a"

    # Trace 2: routes to skill-b
    with e2e_tracer.trace("route:query b", metadata={"platform": "test"}) as t2:
        wrapped.call("classify b")
        t2.metadata["skill_id"] = "skill-b"

    agg = SpanAggregator(spans_path=spans_path)

    m_a = agg.get_skill_metrics("skill-a", use_analytics_fallback=False)
    m_b = agg.get_skill_metrics("skill-b", use_analytics_fallback=False)

    assert m_a.total_executions == 1
    assert m_a.llm_call_count == 1
    assert m_b.total_executions == 1
    assert m_b.llm_call_count == 1
    # No cross-contamination
    assert m_a.skill_id == "skill-a"
    assert m_b.skill_id == "skill-b"
    assert agg.get_all_skill_ids() == {"skill-a", "skill-b"}
