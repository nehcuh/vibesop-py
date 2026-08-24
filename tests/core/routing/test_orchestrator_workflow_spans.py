"""Tests for orchestrator trace context + phase workflow_node spans (v3 Phase A).

Phase A Task 2: ``Orchestrator.orchestrate()`` opens a trace context so all
spans emitted during orchestration share a single ``trace_id``.

Phase A Task 3: each phase (routing / detection / decomposition / plan_building /
complete) emits a ``workflow_node`` span — the data source for the dashboard's
Orchestration Map view.

Uses short queries + stubbed detector/decomposer/classifier/builder to avoid
real LLM calls — Task 13's fixture-based E2E covers the multi-intent path
with full PlanBuilder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.models import (
    ClassifierResult,
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    WorkflowPattern,
)
from vibesop.core.observability.tracer import ObservabilityTracer
from vibesop.core.routing import UnifiedRouter


@pytest.fixture
def fresh_tracer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ObservabilityTracer:
    """Reset the module-level observability tracer singleton to write into tmp_path."""
    import vibesop.core.observability.tracer as tracer_mod

    span_file = tmp_path / "observability" / "spans.jsonl"
    span_file.parent.mkdir(parents=True, exist_ok=True)
    fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return fresh


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


# ---------------------------------------------------------------------------
# Task 3 stubs: avoid real LLM calls in the multi-intent path
# ---------------------------------------------------------------------------


class _StubDetector:
    def should_decompose(self, query: str, single_result: Any, llm_client: Any = None) -> bool:
        return True


class _StubDecomposer:
    def decompose(self, query: str, skills: Any = None) -> list[dict[str, Any]]:
        return [
            {"intent": "task-a", "query_segment": "do task a"},
            {"intent": "task-b", "query_segment": "do task b"},
        ]


def _stub_classify(self: Any, query: str, sub_tasks: Any) -> ClassifierResult:
    return ClassifierResult(
        pattern=WorkflowPattern.SEQUENTIAL,
        confidence=0.9,
        reasoning="stubbed",
    )


class _StubBuilder:
    def build_plan(
        self,
        query: str,
        sub_tasks: Any,
        workflow_pattern: WorkflowPattern = WorkflowPattern.SEQUENTIAL,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionPlan:
        return ExecutionPlan(
            plan_id="stub-plan",
            original_query=query,
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="skill-a",
                    intent="task-a",
                ),
                ExecutionStep(
                    step_id="s2",
                    step_number=2,
                    skill_id="skill-b",
                    intent="task-b",
                ),
            ],
            detected_intents=["task-a", "task-b"],
            workflow_pattern=workflow_pattern,
            execution_mode=ExecutionMode.SEQUENTIAL,
        )


@pytest.fixture
def stubbed_router(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UnifiedRouter:
    """Router with multi-intent components stubbed to avoid real LLM calls."""
    router = UnifiedRouter(project_root=tmp_path)
    # The router's _get_* methods are factories (return a new instance each call),
    # so binding the stub class directly preserves that semantics.
    monkeypatch.setattr(router, "_get_multi_intent_detector", _StubDetector)
    monkeypatch.setattr(router, "_get_task_decomposer", _StubDecomposer)
    monkeypatch.setattr(router, "_get_plan_builder", _StubBuilder)
    monkeypatch.setattr(
        "vibesop.core.orchestration.classifier.ClassifierAgent.classify",
        _stub_classify,
    )
    return router


_EXPECTED_PHASES: frozenset[str] = frozenset(
    {
        "orchestrate:routing",
        "orchestrate:detection",
        "orchestrate:decomposition",
        "orchestrate:plan_building",
        "orchestrate:complete",
    }
)


# ---------------------------------------------------------------------------
# Task 2: trace context wrapping
# ---------------------------------------------------------------------------


class TestOrchestratorTraceContext:
    """orchestrate() must open a trace context that groups all emitted spans
    under a single trace_id."""

    def test_orchestrate_opens_trace_context(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """Calling orchestrate() must emit a root 'orchestrate' task span
        with a unique trace_id."""
        router = UnifiedRouter(project_root=tmp_path)
        router.orchestrate("help")  # short query → single path, no LLM

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        assert spans, "orchestrate() must emit at least the root span"
        trace_ids = {s["trace_id"] for s in spans}
        assert len(trace_ids) == 1, f"all spans must share one trace_id, got {trace_ids}"
        root_spans = [s for s in spans if s["name"] == "orchestrate"]
        assert root_spans, "must emit a root 'orchestrate' task span"
        assert root_spans[0]["span_kind"] == "task"

    def test_orchestrate_disabled_still_opens_trace(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """Even with orchestration disabled, the trace context must still open
        so any spans emitted during the (early-return) routing path are grouped."""
        config = RoutingConfig(enable_orchestration=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        router.orchestrate("review my code")

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        assert spans, "trace must open even when orchestration is disabled"
        trace_ids = {s["trace_id"] for s in spans}
        assert len(trace_ids) == 1

    def test_two_orchestrate_calls_have_distinct_trace_ids(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """Each orchestrate() call must produce a fresh trace_id (not reused)."""
        router = UnifiedRouter(project_root=tmp_path)
        router.orchestrate("help")
        router.orchestrate("help")

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        root_spans = [s for s in spans if s["name"] == "orchestrate"]
        assert len(root_spans) == 2
        assert root_spans[0]["trace_id"] != root_spans[1]["trace_id"]


# ---------------------------------------------------------------------------
# Task 3: phase workflow_node spans
# ---------------------------------------------------------------------------


class TestOrchestratorPhaseSpans:
    """orchestrate() must emit one ``workflow_node`` span per phase, providing
    the phase-boundary data the dashboard's Orchestration Map visualises."""

    def test_multi_intent_emits_all_phase_spans(
        self,
        fresh_tracer: ObservabilityTracer,
        stubbed_router: UnifiedRouter,
        tmp_path: Path,
    ) -> None:
        stubbed_router.orchestrate("do task a then task b")

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        phase_names = {s["name"] for s in spans if s["name"].startswith("orchestrate:")}
        missing = _EXPECTED_PHASES - phase_names
        assert not missing, f"missing phase workflow_node spans: {missing} (got {phase_names})"

    def test_phase_spans_are_workflow_node_kind(
        self,
        fresh_tracer: ObservabilityTracer,
        stubbed_router: UnifiedRouter,
        tmp_path: Path,
    ) -> None:
        """Phase spans must use ``workflow_node`` kind (not ``task``) — this
        is the type discriminator the dashboard queries on."""
        stubbed_router.orchestrate("do task a then task b")

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        phase_spans = [s for s in spans if s["name"].startswith("orchestrate:")]
        assert phase_spans, "no orchestrate:* phase spans emitted"
        for s in phase_spans:
            assert s["span_kind"] == "workflow_node", (
                f"{s['name']} kind={s['span_kind']} — expected 'workflow_node'"
            )

    def test_phase_spans_share_root_trace_and_parent(
        self,
        fresh_tracer: ObservabilityTracer,
        stubbed_router: UnifiedRouter,
        tmp_path: Path,
    ) -> None:
        """Phase spans must be direct children of the root 'orchestrate' span,
        so the map view can flatten them under one orchestration node."""
        stubbed_router.orchestrate("do task a then task b")

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        root = next(s for s in spans if s["name"] == "orchestrate")
        phase_spans = [s for s in spans if s["name"].startswith("orchestrate:")]
        assert phase_spans, "no phase spans emitted — see test_multi_intent_emits_all_phase_spans"
        for ps in phase_spans:
            assert ps["trace_id"] == root["trace_id"], f"{ps['name']} trace_id differs from root"
            assert ps["parent_span_id"] == root["id"], (
                f"{ps['name']} parent_span_id={ps['parent_span_id']} expected root id={root['id']}"
            )

    def test_phase_span_metadata_has_phase_and_query(
        self,
        fresh_tracer: ObservabilityTracer,
        stubbed_router: UnifiedRouter,
        tmp_path: Path,
    ) -> None:
        """Phase span metadata must record ``phase`` + ``query`` so the map
        view can render labels + replay the originating user request."""
        stubbed_router.orchestrate("do task a then task b")

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        phase_spans = [s for s in spans if s["name"].startswith("orchestrate:")]
        assert phase_spans, "no phase spans emitted — see test_multi_intent_emits_all_phase_spans"
        for s in phase_spans:
            # SpanWriter serialises metadata to a JSON string (redact + truncate),
            # so parse it back into a dict for assertions.
            meta = json.loads(s["metadata"]) if isinstance(s["metadata"], str) else s["metadata"]
            phase = s["name"].split(":", 1)[1]
            assert meta.get("phase") == phase, f"{s['name']} metadata.phase={meta.get('phase')}"
            assert "query" in meta, f"{s['name']} missing metadata.query"

    def test_single_intent_path_emits_only_routing_and_no_plan_spans(
        self,
        fresh_tracer: ObservabilityTracer,
        tmp_path: Path,
    ) -> None:
        """Short single-intent queries that fall out before decomposition must
        NOT emit decomposition / plan_building / complete spans — the map view
        relies on absence to detect single-skill fast paths."""
        router = UnifiedRouter(project_root=tmp_path)
        router.orchestrate("help")  # short query → single path

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        phase_names = {s["name"] for s in spans if s["name"].startswith("orchestrate:")}
        # Single-path orchestrate emits at most routing (or nothing) — must
        # never claim a plan was built.
        assert "orchestrate:plan_building" not in phase_names
        assert "orchestrate:complete" not in phase_names
