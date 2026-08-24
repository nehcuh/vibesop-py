"""Tests for SpanAggregator — skill attribution + cost/token aggregation.

Covers v8.2 GAP-3 attribution fix:
* Llm-spans (no ``metadata.skill_id``) are attributed to a skill via the
  task-span's ``metadata.skill_id`` when they share a ``trace_id``.
* Token + cost metrics prefer llm-span data when present (real numbers)
  and fall back to task-span fields otherwise.
* ``token_accounting == "measured"`` filter prevents estimated tokens
  from polluting ``avg_tokens``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vibesop.core.observability.aggregator import SpanAggregator


def _ts() -> str:
    return datetime.now(UTC).isoformat()


def _write_spans(path: Path, spans: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for s in spans:
            # Match SpanWriter's on-disk shape: metadata + input/output_data
            # are JSON-encoded strings.
            record = dict(s)
            for key in ("metadata", "input_data", "output_data"):
                val = record.get(key)
                if isinstance(val, dict):
                    record[key] = json.dumps(val)
            f.write(json.dumps(record) + "\n")


def _task_span(
    trace_id: str,
    skill_id: str,
    *,
    status: str = "ok",
    duration_ms: int = 100,
    span_id: str = "task-1",
) -> dict:
    return {
        "id": span_id,
        "trace_id": trace_id,
        "span_kind": "task",
        "name": "route:test",
        "status": status,
        "duration_ms": duration_ms,
        "started_at": _ts(),
        "tokens_input": 0,
        "tokens_output": 0,
        "cost_usd": 0.0,
        "metadata": {"skill_id": skill_id},
    }


def _llm_span(
    trace_id: str,
    *,
    parent_span_id: str = "task-1",
    status: str = "ok",
    tokens_in: int = 80,
    tokens_out: int = 20,
    cost_usd: float = 0.001,
    token_accounting: str = "measured",
    span_id: str = "llm-1",
) -> dict:
    return {
        "id": span_id,
        "trace_id": trace_id,
        "parent_span_id": parent_span_id,
        "span_kind": "llm",
        "name": "llm:test-provider:test-model",
        "status": status,
        "started_at": _ts(),
        "tokens_input": tokens_in,
        "tokens_output": tokens_out,
        "cost_usd": cost_usd,
        "metadata": {
            "provider": "test-provider",
            "model": "test-model",
            "token_accounting": token_accounting,
        },
    }


@pytest.fixture
def spans_file(tmp_path: Path) -> Path:
    return tmp_path / "spans.jsonl"


class TestSkillAttribution:
    def test_llm_span_attributed_via_trace_id(self, spans_file: Path) -> None:
        """Llm-span without metadata.skill_id is attributed via trace_id map."""
        _write_spans(
            spans_file,
            [
                _task_span("trace-1", "mcp-install", span_id="task-1"),
                _llm_span("trace-1", span_id="llm-1"),
            ],
        )

        agg = SpanAggregator(spans_path=spans_file)
        metrics = agg.get_skill_metrics("mcp-install", use_analytics_fallback=False)

        assert metrics.source == "spans"
        assert metrics.total_executions == 1
        assert metrics.llm_call_count == 1
        assert metrics.llm_success_rate == 1.0

    def test_llm_span_excluded_when_trace_id_no_skill(self, spans_file: Path) -> None:
        """Llm-span whose trace has no skill_id is not attributed."""
        _write_spans(
            spans_file,
            [
                _task_span("trace-1", "", span_id="task-1"),  # no skill_id
                _llm_span("trace-1", span_id="llm-1"),
            ],
        )

        agg = SpanAggregator(spans_path=spans_file)
        metrics = agg.get_skill_metrics("mcp-install", use_analytics_fallback=False)
        assert metrics.source == "none"

    def test_get_all_skill_ids_uses_attribution(self, spans_file: Path) -> None:
        """Skill IDs visible only on task-spans should still be discovered."""
        _write_spans(
            spans_file,
            [
                _task_span("trace-1", "skill-a", span_id="t1"),
                _llm_span("trace-1", span_id="l1"),
                _task_span("trace-2", "skill-b", span_id="t2"),
            ],
        )

        agg = SpanAggregator(spans_path=spans_file)
        assert agg.get_all_skill_ids() == {"skill-a", "skill-b"}


class TestCostAggregation:
    def test_total_cost_usd_sums_llm_spans(self, spans_file: Path) -> None:
        _write_spans(
            spans_file,
            [
                _task_span("t1", "skill-x", span_id="task-1"),
                _llm_span("t1", cost_usd=0.002, span_id="l1"),
                _llm_span("t1", cost_usd=0.003, span_id="l2"),
            ],
        )

        agg = SpanAggregator(spans_path=spans_file)
        metrics = agg.get_skill_metrics("skill-x", use_analytics_fallback=False)

        assert metrics.llm_call_count == 2
        assert metrics.total_cost_usd == pytest.approx(0.005, abs=1e-6)
        assert metrics.avg_cost_usd == pytest.approx(0.005, abs=1e-6)  # 1 task
        assert metrics.cost_usd_per_execution == pytest.approx(0.005, abs=1e-6)

    def test_avg_tokens_filters_estimated(self, spans_file: Path) -> None:
        """Estimated tokens should not pollute avg_tokens when measured exists."""
        _write_spans(
            spans_file,
            [
                _task_span("t1", "skill-y", span_id="task-1"),
                _llm_span(
                    "t1",
                    tokens_in=80,
                    tokens_out=20,
                    cost_usd=0.001,
                    token_accounting="measured",
                    span_id="l1",
                ),
                _llm_span(
                    "t1",
                    tokens_in=49,
                    tokens_out=50,
                    cost_usd=0.001,
                    token_accounting="estimated_50_50_from_tokens_used",
                    span_id="l2",
                ),
            ],
        )

        agg = SpanAggregator(spans_path=spans_file)
        metrics = agg.get_skill_metrics("skill-y", use_analytics_fallback=False)

        # avg_tokens uses only the measured span (80+20=100), not the estimated one
        assert metrics.avg_tokens == 100

    def test_avg_tokens_uses_estimated_when_no_measured(self, spans_file: Path) -> None:
        """When all llm-spans are estimated, fall back to using them."""
        _write_spans(
            spans_file,
            [
                _task_span("t1", "skill-z", span_id="task-1"),
                _llm_span(
                    "t1",
                    tokens_in=49,
                    tokens_out=50,
                    cost_usd=0.001,
                    token_accounting="estimated_50_50_from_tokens_used",
                    span_id="l1",
                ),
            ],
        )

        agg = SpanAggregator(spans_path=spans_file)
        metrics = agg.get_skill_metrics("skill-z", use_analytics_fallback=False)
        assert metrics.avg_tokens == 99  # 49 + 50

    def test_no_llm_spans_falls_back_to_task_tokens(self, spans_file: Path) -> None:
        """When no llm-spans present, use task-span token fields."""
        task = _task_span("t1", "skill-w", span_id="task-1")
        task["tokens_input"] = 50
        task["tokens_output"] = 30
        task["cost_usd"] = 0.005
        _write_spans(spans_file, [task])

        agg = SpanAggregator(spans_path=spans_file)
        metrics = agg.get_skill_metrics("skill-w", use_analytics_fallback=False)

        assert metrics.avg_tokens == 80
        assert metrics.total_cost_usd == pytest.approx(0.005, abs=1e-6)
        assert metrics.llm_call_count == 0


class TestErrorAggregation:
    def test_llm_error_recorded_in_success_rate(self, spans_file: Path) -> None:
        _write_spans(
            spans_file,
            [
                _task_span("t1", "skill-e", status="ok", span_id="task-1"),
                _llm_span("t1", status="ok", span_id="l1"),
                _llm_span("t1", status="error", span_id="l2"),
            ],
        )

        agg = SpanAggregator(spans_path=spans_file)
        metrics = agg.get_skill_metrics("skill-e", use_analytics_fallback=False)

        assert metrics.llm_call_count == 2
        assert metrics.llm_success_rate == 0.5

    def test_task_errors_collected(self, spans_file: Path) -> None:
        _write_spans(
            spans_file,
            [
                _task_span(
                    "t1",
                    "skill-err",
                    status="error",
                    span_id="task-1",
                ),
            ],
        )
        # Patch the task span to have an error_message
        spans_file.write_text(
            spans_file.read_text().replace(
                '"status": "error"',
                '"status": "error", "error_message": "upstream timeout"',
            )
        )

        agg = SpanAggregator(spans_path=spans_file)
        metrics = agg.get_skill_metrics("skill-err", use_analytics_fallback=False)

        assert "upstream timeout" in metrics.top_errors


class TestHasData:
    def test_has_data_false_for_missing_file(self, tmp_path: Path) -> None:
        agg = SpanAggregator(spans_path=tmp_path / "missing.jsonl")
        assert agg.has_data() is False

    def test_has_data_true_for_nonempty_file(self, spans_file: Path) -> None:
        _write_spans(spans_file, [_task_span("t1", "x")])
        agg = SpanAggregator(spans_path=spans_file)
        assert agg.has_data() is True


class TestTzNaiveTimestamps:
    """deep-diagnosis-2026-07-24 P1-2 regression: tz-naive ``started_at`` /
    ``timestamp`` values used to TypeError against the tz-aware cutoff and
    get silently included via the except branch, masking out-of-window data.
    """

    def test_tz_naive_recent_span_is_included(self, spans_file: Path) -> None:
        """A tz-naive timestamp within the window must be included once the
        naive→UTC coercion lands (it was included *accidentally* before via
        the TypeError fallthrough; the fix makes the inclusion explicit)."""
        recent_naive = datetime.now(UTC).replace(tzinfo=None).isoformat()
        _write_spans(
            spans_file,
            [
                {
                    "id": "s1",
                    "trace_id": "t1",
                    "span_kind": "task",
                    "name": "route:test",
                    "status": "ok",
                    "duration_ms": 100,
                    "started_at": recent_naive,
                    "tokens_input": 0,
                    "tokens_output": 0,
                    "cost_usd": 0.0,
                    "metadata": {"skill_id": "naive-recent"},
                }
            ],
        )
        agg = SpanAggregator(spans_path=spans_file)
        metrics = agg.get_skill_metrics("naive-recent", use_analytics_fallback=False)
        assert metrics.total_executions == 1

    def test_tz_naive_old_span_is_excluded(self, spans_file: Path) -> None:
        """A tz-naive timestamp OUTSIDE the window (48h ago) must be excluded.
        Without the fix: TypeError → except → record appended unconditionally.
        With the fix: naive→UTC coercion lets the cutoff compare correctly."""
        from datetime import timedelta

        old_naive = (datetime.now(UTC) - timedelta(hours=48)).replace(tzinfo=None).isoformat()
        _write_spans(
            spans_file,
            [
                {
                    "id": "s-old",
                    "trace_id": "t-old",
                    "span_kind": "task",
                    "name": "route:test",
                    "status": "ok",
                    "duration_ms": 100,
                    "started_at": old_naive,
                    "tokens_input": 0,
                    "tokens_output": 0,
                    "cost_usd": 0.0,
                    "metadata": {"skill_id": "naive-old"},
                }
            ],
        )
        agg = SpanAggregator(spans_path=spans_file)
        # Default window 24h → 48h-old span excluded; expand to 72h includes it.
        metrics_24h = agg.get_skill_metrics(
            "naive-old", window_hours=24, use_analytics_fallback=False
        )
        assert metrics_24h.total_executions == 0
        metrics_72h = agg.get_skill_metrics(
            "naive-old", window_hours=72, use_analytics_fallback=False
        )
        assert metrics_72h.total_executions == 1
