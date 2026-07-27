"""Tests for step-level task_id binding (v3 Phase A Task 4).

Verifies that llm spans emitted during plan_building carry ``task_id`` equal
to a ``step.step_id`` of the built plan — NOT the plan_id. This is the data
the dashboard's DAG rebuilder joins on
(``step.spans = [s for s in spans if s.task_id == step.step_id]``); any
plan_id fallback would make every step node empty (grok+pi P0-1).

Implementation path:
- ``ClassifierAgent.classify_step(step, sub_task)`` is a new per-step LLM call
  that emits an llm span via SpanWrappedProvider.
- ``Orchestrator.orchestrate()`` wraps each ``classify_step`` call in
  ``bind_task_context(step.step_id, step.assigned_role)`` so the llm span
  inherits task_id from the active trace context.

Uses stub LLM provider (wrapped in SpanWrappedProvider) + stubbed
detector/decomposer/classifier/builder to avoid real network calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vibesop.core.models import (
    ClassifierResult,
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    WorkflowPattern,
)
from vibesop.core.observability.tracer import ObservabilityTracer
from vibesop.core.routing import UnifiedRouter
from vibesop.llm.base import LLMProvider, LLMResponse
from vibesop.llm.span_wrapped import SpanWrappedProvider

# ---------------------------------------------------------------------------
# Stub LLM provider — wrapped in SpanWrappedProvider so .call() emits llm spans
# ---------------------------------------------------------------------------


class _StubLLMProvider(LLMProvider):
    """Minimal LLMProvider stub returning deterministic step-classification JSON.

    The response content is irrelevant — the test only cares that .call()
    emits an llm span via SpanWrappedProvider and that the span inherits
    task_id from the active bind_task_context block.
    """

    def __init__(self) -> None:
        super().__init__(api_key="sk-fake-key-1234567890", base_url=None)
        self.calls: list[str] = []

    @property
    def provider_name(self) -> str:
        return "StubProvider"

    def default_model(self) -> str:
        return "stub-model"

    def call(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        self.calls.append(prompt)
        return LLMResponse(
            content='{"role": "implementer"}',
            model="stub-model",
            provider="StubProvider",
            tokens_used=20,
            input_tokens=15,
            output_tokens=5,
        )


# ---------------------------------------------------------------------------
# Stub multi-intent components (mirrors test_orchestrator_workflow_spans.py)
# ---------------------------------------------------------------------------


class _StubDetector:
    def should_decompose(
        self, query: str, single_result: Any, llm_client: Any = None
    ) -> bool:
        return True


class _StubDecomposer:
    def decompose(
        self, query: str, skills: Any = None
    ) -> list[dict[str, Any]]:
        return [
            {"intent": "task-a", "query_segment": "do task a"},
            {"intent": "task-b", "query_segment": "do task b"},
        ]


def _stub_classify(self: Any, query: str, sub_tasks: Any = None) -> ClassifierResult:
    """Stub plan-level ClassifierAgent.classify to skip its LLM call.

    Only classify_step (per-step) should emit llm spans in this test —
    plan-level classify is short-circuited so its llm span doesn't pollute
    the bound_llm_spans assertion.
    """
    return ClassifierResult(
        pattern=WorkflowPattern.SEQUENTIAL,
        confidence=0.9,
        reasoning="stubbed plan-level",
    )


class _StubBuilder:
    """Builds a plan with FIXED step_ids so the test can assert against them."""

    def build_plan(
        self,
        query: str,
        sub_tasks: Any,
        workflow_pattern: WorkflowPattern = WorkflowPattern.SEQUENTIAL,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionPlan:
        return ExecutionPlan(
            plan_id="stub-plan-id",
            original_query=query,
            steps=[
                ExecutionStep(
                    step_id="step-1",
                    step_number=1,
                    skill_id="skill-a",
                    intent="task-a",
                ),
                ExecutionStep(
                    step_id="step-2",
                    step_number=2,
                    skill_id="skill-b",
                    intent="task-b",
                ),
            ],
            detected_intents=["task-a", "task-b"],
            workflow_pattern=workflow_pattern,
            execution_mode=ExecutionMode.SEQUENTIAL,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_tracer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ObservabilityTracer:
    import vibesop.core.observability.tracer as tracer_mod

    span_file = tmp_path / "observability" / "spans.jsonl"
    span_file.parent.mkdir(parents=True, exist_ok=True)
    fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return fresh


@pytest.fixture
def stub_llm() -> _StubLLMProvider:
    return _StubLLMProvider()


@pytest.fixture
def stubbed_router_with_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_llm: _StubLLMProvider
) -> UnifiedRouter:
    """Router with multi-intent stubs + SpanWrappedProvider(stub_llm) injected
    as ``router._llm`` so ClassifierAgent.classify_step's .call() emits spans."""
    router = UnifiedRouter(project_root=tmp_path)
    monkeypatch.setattr(router, "_get_multi_intent_detector", _StubDetector)
    monkeypatch.setattr(router, "_get_task_decomposer", _StubDecomposer)
    monkeypatch.setattr(router, "_get_plan_builder", _StubBuilder)
    monkeypatch.setattr(
        "vibesop.core.orchestration.classifier.ClassifierAgent.classify",
        _stub_classify,
    )
    # Crucial: SpanWrappedProvider wraps the stub so .call() emits llm spans.
    wrapped = SpanWrappedProvider(stub_llm)
    monkeypatch.setattr(router, "_llm", wrapped)
    return router


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


_STUB_STEP_IDS = {"step-1", "step-2"}


# ---------------------------------------------------------------------------
# Task 4: step-level task_id binding
# ---------------------------------------------------------------------------


class TestOrchestratorStepTaskIdBinding:
    """Orchestrator must emit llm spans whose ``task_id`` is a ``step.step_id``
    of the built plan — establishing the per-step DAG JOIN contract."""

    def test_at_least_one_llm_span_has_step_level_task_id(
        self,
        fresh_tracer: ObservabilityTracer,
        stubbed_router_with_llm: UnifiedRouter,
        tmp_path: Path,
    ) -> None:
        """P0-1 acceptance: at least one llm span's task_id is a step_id
        (not None, not the plan_id)."""
        stubbed_router_with_llm.orchestrate("do task a then task b")

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        llm_spans = [s for s in spans if s["span_kind"] == "llm"]
        bound_llm_spans = [s for s in llm_spans if s.get("task_id")]

        assert llm_spans, (
            "no llm spans emitted — SpanWrappedProvider not wired or "
            "classify_step not called"
        )
        assert bound_llm_spans, (
            f"none of the {len(llm_spans)} llm spans have task_id — "
            "bind_task_context is not propagating to SpanWrappedProvider"
        )

    def test_llm_span_task_id_is_step_id_not_plan_id(
        self,
        fresh_tracer: ObservabilityTracer,
        stubbed_router_with_llm: UnifiedRouter,
        tmp_path: Path,
    ) -> None:
        """The DAG JOIN contract: ``step.spans = [s for s in spans if
        s.task_id == step.step_id]``. A plan_id binding would make every
        step node empty (grok+pi P0-1)."""
        result = stubbed_router_with_llm.orchestrate("do task a then task b")
        assert result.execution_plan is not None
        plan_id = result.execution_plan.plan_id
        assert plan_id == "stub-plan-id", "test invariant: stub plan_id"

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        llm_spans = [s for s in spans if s["span_kind"] == "llm"]
        bound_llm_spans = [s for s in llm_spans if s.get("task_id")]

        assert bound_llm_spans, "no bound llm spans — see prior test"

        for s in bound_llm_spans:
            assert s["task_id"] in _STUB_STEP_IDS, (
                f"llm span task_id={s['task_id']!r} is not a step_id "
                f"(expected one of {_STUB_STEP_IDS}). "
                f"This looks like a plan_id fallback — P0-1 violation."
            )
            assert s["task_id"] != plan_id, (
                f"llm span task_id={s['task_id']!r} equals plan_id — "
                "P0-1 violation: plan_id fallback would make every step node empty."
            )

    def test_each_step_has_at_least_one_bound_llm_span(
        self,
        fresh_tracer: ObservabilityTracer,
        stubbed_router_with_llm: UnifiedRouter,
        stub_llm: _StubLLMProvider,
        tmp_path: Path,
    ) -> None:
        """Every step in the plan must have ≥1 llm span attributed to it,
        so the dashboard's step node is non-empty."""
        stubbed_router_with_llm.orchestrate("do task a then task b")

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        llm_spans = [s for s in spans if s["span_kind"] == "llm"]
        # Build map: step_id → count of llm spans bound to it
        bound_per_step: dict[str, int] = dict.fromkeys(_STUB_STEP_IDS, 0)
        for s in llm_spans:
            tid = s.get("task_id")
            if tid in bound_per_step:
                bound_per_step[tid] += 1

        empty_steps = [sid for sid, n in bound_per_step.items() if n == 0]
        assert not empty_steps, (
            f"steps {empty_steps} have no bound llm spans — "
            f"distribution: {bound_per_step}"
        )

    def test_classify_step_emits_llm_span_via_span_wrapped_provider(
        self,
        fresh_tracer: ObservabilityTracer,
        stubbed_router_with_llm: UnifiedRouter,
        stub_llm: _StubLLMProvider,
        tmp_path: Path,
    ) -> None:
        """Sanity: the stub LLM was actually called (proving classify_step
        reaches the provider through SpanWrappedProvider)."""
        stubbed_router_with_llm.orchestrate("do task a then task b")

        # 2 steps → at least 2 calls (one per step)
        assert len(stub_llm.calls) >= 2, (
            f"expected ≥2 stub LLM calls (1 per step), got {len(stub_llm.calls)}: "
            f"{stub_llm.calls}"
        )
