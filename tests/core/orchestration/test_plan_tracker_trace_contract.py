"""Plan ↔ Trace JOIN contract (v3 Phase A Task 10, P0-2 mandatory).

When ``Orchestrator.orchestrate()`` completes the plan_building path, the
resulting ``ExecutionPlan`` MUST be persisted via ``PlanTracker.create_plan()``
with ``metadata.trace_id`` set to the active trace root's id.

Without this contract:
- ``load_plans_for_trace(trace_id)`` returns empty
- DAG rebuilder produces a flat tree with no step nodes
- Dashboard Map view's dependency edges cannot be rendered
- Same class of bug as v2's "Work Task 实体未定义"

Test strategy: stub detector/decomposer/classifier/builder (same as
``test_orchestrator_workflow_spans.py``) to avoid real LLM calls. Verify
the persisted JSONL line carries ``metadata.trace_id`` matching the
``orchestrate`` root span's ``trace_id``.
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

# ---------------------------------------------------------------------------
# Stubs (mirrors test_orchestrator_workflow_spans.py — no LLM)
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


def _stub_classify(
    self: Any, query: str, sub_tasks: Any
) -> ClassifierResult:
    return ClassifierResult(
        pattern=WorkflowPattern.SEQUENTIAL,
        confidence=0.9,
        reasoning="stubbed",
    )


def _stub_classify_step(self: Any, step: Any, sub_task: Any) -> None:
    """No-op step classifier — span emission is exercised elsewhere."""
    return None


class _StubBuilder:
    def build_plan(
        self,
        query: str,
        sub_tasks: Any,
        workflow_pattern: WorkflowPattern = WorkflowPattern.SEQUENTIAL,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionPlan:
        return ExecutionPlan(
            plan_id="stub-plan-trace-contract",
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
def fresh_tracer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ObservabilityTracer:
    """Reset the module-level tracer singleton to write into tmp_path."""
    import vibesop.core.observability.tracer as tracer_mod

    span_file = tmp_path / "observability" / "spans.jsonl"
    span_file.parent.mkdir(parents=True, exist_ok=True)
    fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return fresh


@pytest.fixture
def stubbed_router(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> UnifiedRouter:
    router = UnifiedRouter(project_root=tmp_path)
    monkeypatch.setattr(router, "_get_multi_intent_detector", _StubDetector)
    monkeypatch.setattr(router, "_get_task_decomposer", _StubDecomposer)
    monkeypatch.setattr(router, "_get_plan_builder", _StubBuilder)
    monkeypatch.setattr(
        "vibesop.core.orchestration.classifier.ClassifierAgent.classify",
        _stub_classify,
    )
    monkeypatch.setattr(
        "vibesop.core.orchestration.classifier.ClassifierAgent.classify_step",
        _stub_classify_step,
    )
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


def _read_plans(path: Path) -> list[dict]:
    if not path.exists():
        return []
    plans: list[dict] = []
    with path.open() as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if stripped:
                plans.append(json.loads(stripped))
    return plans


# ---------------------------------------------------------------------------
# Contract: orchestrate() persists plan with trace_id
# ---------------------------------------------------------------------------


class TestOrchestratePersistsPlanWithTraceId:
    """P0-2 contract: ``.vibe/execution_plans.jsonl`` must contain a plan whose
    ``metadata.trace_id`` matches the active trace root after orchestrate()
    completes the multi-intent path."""

    def test_plan_jsonl_has_matching_trace_id(
        self,
        fresh_tracer: ObservabilityTracer,
        stubbed_router: UnifiedRouter,
        tmp_path: Path,
    ) -> None:
        stubbed_router.orchestrate("do task a then task b")

        # The trace root id is the trace_id of the 'orchestrate' span.
        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        root = next(s for s in spans if s["name"] == "orchestrate")
        expected_trace_id = root["trace_id"]

        plans = _read_plans(tmp_path / ".vibe" / "execution_plans.jsonl")
        matching = [p for p in plans if p["plan_id"] == "stub-plan-trace-contract"]
        assert matching, (
            "PlanTracker.create_plan() was never called — plan JSONL is empty "
            "or missing the stub-plan-trace-contract entry"
        )
        latest = matching[-1]
        assert latest["metadata"].get("trace_id") == expected_trace_id, (
            f"plan.metadata.trace_id={latest['metadata'].get('trace_id')!r} "
            f"expected root trace_id={expected_trace_id!r}"
        )

    def test_plan_orchestration_id_matches_plan_id(
        self,
        fresh_tracer: ObservabilityTracer,
        stubbed_router: UnifiedRouter,
        tmp_path: Path,
    ) -> None:
        """``metadata.orchestration_id`` must equal ``plan_id`` so the
        conversation↔plan JOIN has a stable key on both sides."""
        stubbed_router.orchestrate("do task a then task b")

        plans = _read_plans(tmp_path / ".vibe" / "execution_plans.jsonl")
        latest = next(p for p in plans if p["plan_id"] == "stub-plan-trace-contract")
        assert latest["metadata"].get("orchestration_id") == latest["plan_id"]

    def test_single_intent_path_does_not_persist_plan(
        self,
        fresh_tracer: ObservabilityTracer,
        tmp_path: Path,
    ) -> None:
        """Short single-intent queries must NOT trigger PlanTracker.create_plan().
        The fast path returns before plan_building — verify no entry is appended."""
        router = UnifiedRouter(project_root=tmp_path)
        router.orchestrate("help")  # short → single-skill path

        plans = _read_plans(tmp_path / ".vibe" / "execution_plans.jsonl")
        assert not plans, (
            f"single-intent path leaked a plan entry: {plans}"
        )

    def test_plan_persistence_failure_does_not_break_orchestration(
        self,
        fresh_tracer: ObservabilityTracer,
        stubbed_router: UnifiedRouter,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If PlanTracker.create_plan() raises (disk full, permissions, ...),
        orchestrate() must still return a result — persistence is best-effort."""

        def boom(_plan: Any) -> None:
            raise OSError("simulated disk full")

        from vibesop.core.orchestration.plan_tracker import PlanTracker

        monkeypatch.setattr(PlanTracker, "create_plan", boom)

        result = stubbed_router.orchestrate("do task a then task b")
        assert result.execution_plan is not None
        assert result.execution_plan.plan_id == "stub-plan-trace-contract"


# ---------------------------------------------------------------------------
# load_plans_for_trace(): filter contract
# ---------------------------------------------------------------------------


class TestLoadPlansForTrace:
    """``load_plans_for_trace(trace_id, storage_dir)`` returns only plans
    whose ``metadata.trace_id`` matches."""

    def _write_plan(
        self,
        storage_dir: Path,
        plan_id: str,
        trace_id: str | None,
    ) -> None:
        from vibesop.core.models import (
            ExecutionMode,
            ExecutionPlan,
            ExecutionStep,
            WorkflowPattern,
        )

        plan = ExecutionPlan(
            plan_id=plan_id,
            original_query="q",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="skill-a",
                    intent="task-a",
                )
            ],
            workflow_pattern=WorkflowPattern.SEQUENTIAL,
            execution_mode=ExecutionMode.SEQUENTIAL,
        )
        if trace_id is not None:
            plan.metadata["trace_id"] = trace_id
        storage_dir.mkdir(parents=True, exist_ok=True)
        plans_file = storage_dir / "execution_plans.jsonl"
        with plans_file.open("a") as f:
            f.write(json.dumps(plan.to_dict()) + "\n")

    def test_returns_only_matching_trace_id(self, tmp_path: Path) -> None:
        from vibesop.core.orchestration.plan_tracker import load_plans_for_trace

        storage = tmp_path / ".vibe"
        self._write_plan(storage, "plan-A", "trace-1")
        self._write_plan(storage, "plan-B", "trace-2")
        self._write_plan(storage, "plan-C", "trace-1")

        result = load_plans_for_trace("trace-1", storage_dir=storage)
        ids = {p.plan_id for p in result}
        assert ids == {"plan-A", "plan-C"}, (
            f"expected plan-A + plan-C (both trace-1), got {ids}"
        )

    def test_returns_empty_when_no_match(self, tmp_path: Path) -> None:
        from vibesop.core.orchestration.plan_tracker import load_plans_for_trace

        storage = tmp_path / ".vibe"
        self._write_plan(storage, "plan-A", "trace-1")

        result = load_plans_for_trace("nonexistent", storage_dir=storage)
        assert result == []

    def test_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        from vibesop.core.orchestration.plan_tracker import load_plans_for_trace

        result = load_plans_for_trace("anything", storage_dir=tmp_path / ".vibe")
        assert result == []

    def test_skips_plans_without_trace_id_metadata(self, tmp_path: Path) -> None:
        """Plans persisted before Task 10 lack ``metadata.trace_id`` — they
        must be skipped (NOT crashed on) so historical data stays readable."""
        from vibesop.core.orchestration.plan_tracker import load_plans_for_trace

        storage = tmp_path / ".vibe"
        self._write_plan(storage, "legacy-plan", trace_id=None)
        self._write_plan(storage, "plan-A", "trace-1")

        result = load_plans_for_trace("trace-1", storage_dir=storage)
        ids = {p.plan_id for p in result}
        assert ids == {"plan-A"}, (
            "legacy plan without metadata.trace_id leaked into result"
        )

    def test_dedupes_plan_id_keeping_latest(self, tmp_path: Path) -> None:
        """Plans are append-only; latest entry for a plan_id wins (matches
        PlanTracker.get_plan() semantics)."""
        from vibesop.core.orchestration.plan_tracker import load_plans_for_trace

        storage = tmp_path / ".vibe"
        # Same plan_id twice — second append is the "latest" state.
        self._write_plan(storage, "plan-A", "trace-1")
        self._write_plan(storage, "plan-A", "trace-1")

        result = load_plans_for_trace("trace-1", storage_dir=storage)
        assert len(result) == 1, (
            f"expected dedup to 1 entry, got {len(result)}"
        )
