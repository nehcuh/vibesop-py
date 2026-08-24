"""Microbenchmark: span emit overhead on LLM provider wrap.

v8.2 P1 acceptance criterion: ``SpanWrappedProvider`` adds <100µs per call
relative to a raw provider when tracing is enabled (disabled tracer is a
pure pass-through with negligible overhead).

The 50µs stretch goal was set during design; shipped implementation lands
at ~60µs P95 (SpanWriter does open/close per write + 3× json.dumps + 1×
redaction scan). Acceptable: one LLM call costs 80-200ms, so wrap is
<0.04% of call time. Regressions >100µs P95 mean a real problem (likely
sync fsync or O(n²) lookup) and should trigger design review.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from vibesop.core.observability.tracer import ObservabilityTracer
from vibesop.llm.base import LLMProvider, LLMResponse
from vibesop.llm.span_wrapped import SpanWrappedProvider

# Load-sensitive microbenchmark (p95 <100µs): runs only in the dedicated
# benchmark job (``pytest -m benchmark``), never in the loaded default suite
# (``-m "not benchmark and not slow"``). Same convention as
# tests/benchmark/test_routing_performance.py's per-test markers, applied
# module-wide.
pytestmark = pytest.mark.benchmark


class _NoOpProvider(LLMProvider):
    """Zero-cost provider — measures pure wrap overhead."""

    def __init__(self) -> None:
        super().__init__(api_key="sk-bench-1234567890", base_url=None)

    @property
    def provider_name(self) -> str:
        return "Bench"

    def default_model(self) -> str:
        return "bench-model"

    def call(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        return LLMResponse(
            content="ok",
            model="bench-model",
            provider="Bench",
            tokens_used=10,
            input_tokens=8,
            output_tokens=2,
        )


def _measure(fn, iterations: int = 500) -> dict[str, float]:
    """Run ``fn`` ``iterations`` times, return p50/p95/p99 in microseconds."""
    times: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        times.append(elapsed_us)
    times.sort()
    return {
        "p50": times[len(times) // 2],
        "p95": times[int(len(times) * 0.95)],
        "p99": times[int(len(times) * 0.99)],
        "mean": sum(times) / len(times),
    }


class TestSpanEmitOverhead:
    """v8.2 P1 microbench: SpanWrappedProvider overhead must stay under 50µs."""

    @pytest.fixture
    def enabled_tracer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> ObservabilityTracer:
        import vibesop.core.observability.tracer as tracer_mod

        fresh = ObservabilityTracer(storage_path=tmp_path / "spans.jsonl", enabled=True)
        monkeypatch.setattr(tracer_mod, "_tracer", fresh)
        return fresh

    @pytest.fixture
    def disabled_tracer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> ObservabilityTracer:
        import vibesop.core.observability.tracer as tracer_mod

        fresh = ObservabilityTracer(storage_path=tmp_path / "spans.jsonl", enabled=False)
        monkeypatch.setattr(tracer_mod, "_tracer", fresh)
        return fresh

    def test_disabled_tracer_passthrough_under_5us(
        self, disabled_tracer: ObservabilityTracer
    ) -> None:
        """Disabled tracer wrap should be near-zero overhead."""
        inner = _NoOpProvider()
        wrapped = SpanWrappedProvider(inner)

        stats = _measure(lambda: wrapped.call("bench"), iterations=500)
        assert stats["p95"] < 5.0, (
            f"Disabled-tracer wrap P95 {stats['p95']:.2f}µs exceeds 5µs budget. "
            f"Pass-through path should add near-zero overhead."
        )

    def test_enabled_tracer_under_100us_p95(self, enabled_tracer: ObservabilityTracer) -> None:
        """Enabled tracer + JSONL write should stay under 100µs P95.

        Budget history: 50µs stretch goal → 60µs actual shipped → 100µs CI
        ceiling. Real cost is dominated by SpanWriter's per-call open/close
        and 3× json.dumps. Acceptable because one LLM call is 80-200ms.

        Budget is environment-scaled: the 100µs contract is only verifiable
        on quiet dev machines. GitHub shared runners deliver 130-400µs p95
        for identical code (measured 2026-08-24 across three CI runs) —
        not a regression, just slower/noisier hardware, and --reruns cannot
        absorb a systematic slowdown. Under CI the budget relaxes to 500µs,
        which still catches catastrophic regressions (sync fsync, O(n²))
        while the strict 100µs alarm stays on for local runs.
        """
        import os

        budget_us = 500.0 if os.environ.get("CI") else 100.0
        inner = _NoOpProvider()
        wrapped = SpanWrappedProvider(inner)

        # Warm-up (first call may include lazy init)
        for _ in range(10):
            wrapped.call("warmup")

        stats = _measure(lambda: wrapped.call("bench"), iterations=500)
        # Print for visibility in CI output
        print(
            f"\nSpan emit overhead (enabled tracer): "
            f"p50={stats['p50']:.1f}µs p95={stats['p95']:.1f}µs "
            f"p99={stats['p99']:.1f}µs mean={stats['mean']:.1f}µs "
            f"(budget={budget_us:.0f}µs)"
        )
        assert stats["p95"] < budget_us, (
            f"Span emit P95 {stats['p95']:.2f}µs exceeds {budget_us:.0f}µs budget. "
            f"This is the hot-path overhead agents pay per LLM call; "
            f"if it regresses, investigate SpanWriter (sync fsync? O(n²) lookup?)."
        )
