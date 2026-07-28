"""Integration smoke: orchestrate() → rebuild_dag() on one tmp_path.

Closes the Phase A "main gate" gap flagged independently by grok+pi
closeout review (Q4): fixture E2E proves the JOIN logic, but does not
prove that the **producer side** (orchestrate → SpanWriter + PlanTracker
+ ConversationContext) writes to the same `.vibe` root that the
**consumer side** (rebuild_dag) reads from.

This test runs the full in-process pipeline with stubbed LLM (zero cost,
deterministic) and verifies rebuild_dag can reconstruct the DAG from the
artefacts orchestrate() actually wrote.

Per grok's recommendation in the closeout review:
> One zero-LLM integration test (or scripted smoke): Task-4-style stubbed
> orchestrate() + PlanTracker + rebuild_dag on the same tmp_path, assert
> ≥1 plan, ≥1 step, ≥1 llm child via real JSONL.

That's exactly this file.
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
from vibesop.core.observability.dag_rebuilder import rebuild_dag
from vibesop.core.observability.tracer import ObservabilityTracer
from vibesop.core.routing import UnifiedRouter
from vibesop.llm.base import LLMProvider, LLMResponse
from vibesop.llm.span_wrapped import SpanWrappedProvider

# ---------------------------------------------------------------------------
# Stubs — same pattern as test_orchestrator_step_binding.py
# ---------------------------------------------------------------------------


class _StubLLMProvider(LLMProvider):
    """Returns deterministic step-classification JSON."""

    def __init__(self) -> None:
        super().__init__(api_key="sk-fake-key-1234567890", base_url=None)

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
        return LLMResponse(
            content='{"role": "implementer"}',
            model="stub-model",
            provider="StubProvider",
            tokens_used=20,
            input_tokens=15,
            output_tokens=5,
        )


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
    return ClassifierResult(
        pattern=WorkflowPattern.SEQUENTIAL,
        confidence=0.9,
        reasoning="stubbed plan-level",
    )


class _StubBuilder:
    """Fixed plan_id + step_ids so the test can assert against them."""

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
                    dependencies=["step-1"],
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
def production_layout_tracer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ObservabilityTracer:
    """Override global tracer to write spans under ``tmp_path/.vibe/observability``
    — the production layout. This is the key fixture: existing Task 4 tests
    use ``tmp_path/observability`` (no `.vibe` prefix) which doesn't match
    rebuild_dag's reader path."""
    import vibesop.core.observability.tracer as tracer_mod

    span_file = tmp_path / ".vibe" / "observability" / "spans.jsonl"
    span_file.parent.mkdir(parents=True, exist_ok=True)
    fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return fresh


@pytest.fixture
def stubbed_router(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> UnifiedRouter:
    """UnifiedRouter with project_root=tmp_path + stubbed multi-intent
    components + SpanWrappedProvider(stub_llm) — full producer-side pipeline
    with zero LLM cost."""
    router = UnifiedRouter(project_root=tmp_path)
    monkeypatch.setattr(router, "_get_multi_intent_detector", _StubDetector)
    monkeypatch.setattr(router, "_get_task_decomposer", _StubDecomposer)
    monkeypatch.setattr(router, "_get_plan_builder", _StubBuilder)
    monkeypatch.setattr(
        "vibesop.core.orchestration.classifier.ClassifierAgent.classify",
        _stub_classify,
    )
    monkeypatch.setattr(router, "_llm", SpanWrappedProvider(_StubLLMProvider()))
    return router


# ---------------------------------------------------------------------------
# Integration smoke
# ---------------------------------------------------------------------------


def test_orchestrate_to_rebuild_dag_full_pipeline_zero_llm(
    production_layout_tracer: ObservabilityTracer,
    stubbed_router: UnifiedRouter,
    tmp_path: Path,
) -> None:
    """Full producer→consumer pipeline on one tmp_path with stubbed LLM.

    Validates the gap fixture E2E cannot: that orchestrate() actually
    writes plan + spans + conversations to ``tmp_path/.vibe/`` in the
    shape rebuild_dag reads, and trace_id propagates correctly across
    all three writers.

    Phase A "main gate" per plan §Verification checklist — replaces paid
    real-LLM smoke for the JOIN logic specifically (real LLM still useful
    for catching encoding/partial-write edge cases; deferred to manual).
    """
    storage = tmp_path / ".vibe"

    # Producer: run orchestrate() (writes spans + plan + conversation meta)
    result = stubbed_router.orchestrate("do task a then task b")
    assert result.execution_plan is not None, "stub must produce a plan"
    plan = result.execution_plan
    trace_id = plan.metadata.get("trace_id")
    assert trace_id, (
        "plan.metadata.trace_id must be set by orchestrator (Task 10 P0-2) — "
        "without it rebuild_dag cannot JOIN plan ↔ spans"
    )

    # Sanity: artefact files exist on disk in the production layout
    spans_file = storage / "observability" / "spans.jsonl"
    plans_file = storage / "execution_plans.jsonl"
    assert spans_file.exists(), (
        f"SpanWriter did not write to production path {spans_file}"
    )
    assert plans_file.exists(), (
        f"PlanTracker did not write to production path {plans_file}"
    )

    # Consumer: rebuild_dag reads the same .vibe dir
    dag = rebuild_dag(trace_id=trace_id, storage_dir=storage)

    # ---- Phase A gate assertions ------------------------------------
    # ≥1 user_intent
    ui_nodes = [n for n in dag.nodes if n.kind == "user_intent"]
    assert ui_nodes, "user_intent node missing from rebuilt DAG"

    # ≥1 orchestrator
    orch_nodes = [n for n in dag.nodes if n.kind == "orchestrator"]
    assert orch_nodes, "orchestrator node missing"

    # ≥2 step nodes (plan-scoped ids per Task 12 polish)
    step_nodes = [n for n in dag.nodes if n.kind == "step"]
    assert len(step_nodes) >= 2, (
        f"expected ≥2 step nodes from stub plan, got {len(step_nodes)}: "
        f"{[n.id for n in step_nodes]}"
    )
    step_ids = {n.id for n in step_nodes}
    assert f"step:{plan.plan_id}:step-1" in step_ids
    assert f"step:{plan.plan_id}:step-2" in step_ids

    # Dependency edge present (step-1 → step-2 from _StubBuilder)
    dep_edges = {(e.src, e.dst) for e in dag.edges if e.kind == "dependency"}
    expected_dep = (
        f"step:{plan.plan_id}:step-1",
        f"step:{plan.plan_id}:step-2",
    )
    assert expected_dep in dep_edges, (
        f"dependency edge {expected_dep} not in {dep_edges}"
    )

    # ≥1 llm span attached to a step via task_id == step_id (P0-1 contract)
    llm_nodes = [n for n in dag.nodes if n.kind == "llm"]
    assert llm_nodes, (
        "no llm nodes attached to steps — bind_task_context not propagating "
        "task_id to SpanWrappedProvider, OR rebuild_dag JOIN broken"
    )
    # Each llm node's parent must be a step (not a plan, not the orchestrator)
    step_node_ids = step_ids
    for llm in llm_nodes:
        parent_edges = [
            e for e in dag.edges
            if e.dst == llm.id and e.kind == "parent_child"
        ]
        assert parent_edges, f"llm node {llm.id} has no parent edge"
        parent_id = parent_edges[0].src
        assert parent_id in step_node_ids, (
            f"llm node {llm.id} attached to {parent_id}, not a step node — "
            "P0-1 violation: span should attach via task_id == step_id"
        )

    # iterations: single plan, no reorchestration history → 1
    assert dag.iterations == 1, (
        f"single-plan no-history case should yield iterations=1, "
        f"got {dag.iterations}"
    )


def test_orchestrate_persists_trace_id_for_cross_process_join(
    production_layout_tracer: ObservabilityTracer,
    stubbed_router: UnifiedRouter,
    tmp_path: Path,
) -> None:
    """Plan persisted to disk must carry trace_id — the cross-process JOIN
    key. Re-read the JSONL file directly (no in-memory plan object) to
    verify what rebuild_dag will actually see."""
    storage = tmp_path / ".vibe"

    result = stubbed_router.orchestrate("do task a then task b")
    assert result.execution_plan is not None
    expected_trace_id = result.execution_plan.metadata["trace_id"]

    plans_file = storage / "execution_plans.jsonl"
    assert plans_file.exists()
    # Read back the persisted plan as-is (no PlanTracker helpers)
    with plans_file.open() as f:
        persisted_plans = [json.loads(line) for line in f if line.strip()]

    assert persisted_plans, "no plans persisted to disk"
    matching = [
        p for p in persisted_plans
        if (p.get("metadata") or {}).get("trace_id") == expected_trace_id
    ]
    assert matching, (
        f"no persisted plan carries trace_id={expected_trace_id} — "
        "cross-process JOIN impossible without it (Task 10 P0-2 regression)"
    )


def test_rebuild_dag_uses_absolute_storage_dir_no_cwd_footgun(
    production_layout_tracer: ObservabilityTracer,
    stubbed_router: UnifiedRouter,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rebuild_dag must work when called from a different CWD, as long as
    storage_dir is absolute. This is the CWD footgun flagged in the
    rebuild_dag docstring — the dashboard server process won't always
    run from the project root."""
    storage = tmp_path / ".vibe"

    result = stubbed_router.orchestrate("do task a then task b")
    trace_id = result.execution_plan.metadata["trace_id"]  # type: ignore[union-attr]

    # Change CWD to somewhere completely different
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    # storage_dir is absolute → rebuild_dag must still find the artefacts
    dag = rebuild_dag(trace_id=trace_id, storage_dir=storage)
    assert any(n.kind == "user_intent" for n in dag.nodes), (
        "rebuild_dag returned empty DAG when CWD differs but storage_dir is "
        "absolute — CWD-relative path resolution bug"
    )
    assert any(n.kind == "step" for n in dag.nodes)
