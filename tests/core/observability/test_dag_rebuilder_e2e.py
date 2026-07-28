"""Fixture-based E2E for the Dashboard v3 Phase A data pipeline.

Exercises the full JOIN — `orchestrate()` JSONL artefacts → `rebuild_dag` —
using pre-constructed fixtures (zero LLM calls). This is the Phase A
verification gate per design plan §13.

Pre-fix this scenario was validated only end-to-end with real LLM calls
at ~$0.05–0.20/run, flaky, and slow. Fixture E2E tests the **data
pipeline**: plan persistence → span emission → mirror hooks → DAG rebuild.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    WorkflowPattern,
)
from vibesop.core.observability.dag_rebuilder import rebuild_dag


def _write_plan_with_trace(
    storage_dir: Path,
    plan_id: str,
    trace_id: str,
    steps: list[dict[str, Any]],
    dependencies: dict[str, list[str]] | None = None,
) -> None:
    """Write an ExecutionPlan with trace_id to execution_plans.jsonl."""
    plan = ExecutionPlan(
        plan_id=plan_id,
        original_query=f"query for {plan_id}",
        steps=[
            ExecutionStep(
                step_id=s["step_id"],
                step_number=i + 1,
                skill_id=s.get("skill_id", "skill-x"),
                intent=s.get("intent", "intent-x"),
                dependencies=dependencies.get(s["step_id"], [])
                if dependencies
                else [],
            )
            for i, s in enumerate(steps)
        ],
        workflow_pattern=WorkflowPattern.SEQUENTIAL,
        execution_mode=ExecutionMode.SEQUENTIAL,
    )
    plan.metadata["trace_id"] = trace_id
    storage_dir.mkdir(parents=True, exist_ok=True)
    with (storage_dir / "execution_plans.jsonl").open("a") as f:
        f.write(json.dumps(plan.to_dict()) + "\n")


def _write_span(
    storage_dir: Path,
    span_id: str,
    trace_id: str,
    *,
    parent_span_id: str | None = None,
    span_kind: str = "task",
    name: str | None = None,
    task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append one span line to observability/spans.jsonl."""
    span: dict[str, Any] = {
        "id": span_id,
        "trace_id": trace_id,
        "name": name or span_id,
        "span_kind": span_kind,
    }
    if parent_span_id:
        span["parent_span_id"] = parent_span_id
    if task_id:
        span["task_id"] = task_id
    if metadata:
        span["metadata"] = metadata
    obs_dir = storage_dir / "observability"
    obs_dir.mkdir(parents=True, exist_ok=True)
    with (obs_dir / "spans.jsonl").open("a") as f:
        f.write(json.dumps(span) + "\n")


def _write_conversation(
    storage_dir: Path,
    conversation_id: str,
    *,
    is_subagent: bool = False,
    parent_conversation_id: str | None = None,
    orchestration_id: str | None = None,
    orchestration_trace_id: str | None = None,
    agent_type: str | None = "claude-code",
    description: str | None = None,
) -> None:
    """Write a conversation JSON file mirroring ConversationContext.save()."""
    conv_dir = storage_dir / "conversations"
    conv_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {}
    if is_subagent:
        metadata["is_subagent"] = True
        if parent_conversation_id:
            metadata["parent_conversation_id"] = parent_conversation_id
        if agent_type:
            metadata["agent_type"] = agent_type
        if description:
            metadata["description"] = description
    if orchestration_id is not None:
        metadata["orchestration_id"] = orchestration_id
    if orchestration_trace_id is not None:
        metadata["orchestration_trace_id"] = orchestration_trace_id

    payload = {
        "conversation_id": conversation_id,
        "metadata": metadata,
        "turns": [],
    }
    (conv_dir / f"{conversation_id}.json").write_text(json.dumps(payload))


# ---------------------------------------------------------------------------
# E2E — full pipeline fixture
# ---------------------------------------------------------------------------


def test_full_pipeline_with_fixtures_zero_llm(tmp_path: Path) -> None:
    """End-to-end data-pipeline test using fixtures (NO LLM calls).

    Validates the full JOIN contract for Dashboard v3 Phase A:
      plan JSONL + span JSONL + conversation JSON → ``rebuild_dag`` → DAG

    Asserts the Phase A data gate criteria from plan §13:
      * ≥1 user_intent + ≥1 orchestrator
      * ≥4 phase children on orchestrator (routing/detection/plan_building/complete)
      * exactly 3 step nodes with plan-scoped ids
      * dependency edges s1→s2, s1→s3, s2→s3
      * llm spans attached to steps via task_id == step_id (P0-1)
      * 2 sub_agent nodes attached to PLAN (step-level deferred to Phase B)
      * iterations == 1 (single plan, no reorchestration history)
    """
    storage = tmp_path / ".vibe"
    trace_id = "T-e2e-1"

    # ---- fixtures --------------------------------------------------------
    _write_plan_with_trace(
        storage,
        plan_id="plan-e2e",
        trace_id=trace_id,
        steps=[
            {"step_id": "s1", "skill_id": "skill-router"},
            {"step_id": "s2", "skill_id": "skill-implementer"},
            {"step_id": "s3", "skill_id": "skill-reviewer"},
        ],
        dependencies={"s1": [], "s2": ["s1"], "s3": ["s1", "s2"]},
    )

    # Root orchestrate span (Task 2)
    _write_span(
        storage,
        span_id="span-root",
        trace_id=trace_id,
        span_kind="task",
        name="orchestrate",
        metadata={"query": "build feature X with tests"},
    )

    # Phase spans (Task 3) — workflow_node children of root
    for phase in ("routing", "detection", "plan_building", "complete"):
        _write_span(
            storage,
            span_id=f"span-phase-{phase}",
            trace_id=trace_id,
            parent_span_id="span-root",
            span_kind="workflow_node",
            name=f"orchestrate:{phase}",
            metadata={"phase": phase},
        )

    # Per-step llm spans with task_id = step_id (Task 4 — P0-1 contract)
    for step_id, skill in [
        ("s1", "skill-router"),
        ("s2", "skill-implementer"),
        ("s3", "skill-reviewer"),
    ]:
        _write_span(
            storage,
            span_id=f"span-llm-{step_id}",
            trace_id=trace_id,
            parent_span_id="span-root",
            span_kind="llm",
            name=f"classify:{skill}",
            task_id=step_id,
        )

    # Main conversation (orchestrator-owned, NOT sub-agent)
    _write_conversation(
        storage,
        conversation_id="conv-main",
        orchestration_id="plan-e2e",
        orchestration_trace_id=trace_id,
    )

    # 2 sub-agent conversations attached via parent_conversation_id chain
    _write_conversation(
        storage,
        conversation_id="conv-main-sub-investigator",
        is_subagent=True,
        parent_conversation_id="conv-main",
        agent_type="claude-code",
        description="investigator",
    )
    _write_conversation(
        storage,
        conversation_id="conv-main-sub-reviewer",
        is_subagent=True,
        parent_conversation_id="conv-main",
        agent_type="claude-code",
        description="reviewer",
    )

    # ---- rebuild + assert structure -------------------------------------
    dag = rebuild_dag(trace_id=trace_id, storage_dir=storage)

    # user_intent + orchestrator
    ui_nodes = [n for n in dag.nodes if n.kind == "user_intent"]
    assert ui_nodes, "user_intent node missing"
    assert "build feature X" in ui_nodes[0].label

    orch_nodes = [n for n in dag.nodes if n.kind == "orchestrator"]
    assert orch_nodes, "orchestrator node missing"
    orch = orch_nodes[0]

    # Phases present (4 emitted by orchestrator)
    phase_names = {p["phase"] for p in dag.phases}
    assert {"routing", "detection", "plan_building", "complete"}.issubset(
        phase_names
    ), f"missing phases, got {phase_names}"

    # Phase spans attached as orchestrator children
    for phase in ("routing", "detection", "plan_building", "complete"):
        assert f"span-phase-{phase}" in orch.children, (
            f"phase {phase} not attached to orchestrator, "
            f"children={orch.children}"
        )

    # Plan + 3 step nodes (plan-scoped ids)
    plan_node = next(
        (n for n in dag.nodes if n.id == "plan:plan-e2e"), None
    )
    assert plan_node is not None, "plan node missing"

    step_ids = {n.id for n in dag.nodes if n.kind == "step"}
    expected_steps = {
        "step:plan-e2e:s1",
        "step:plan-e2e:s2",
        "step:plan-e2e:s3",
    }
    assert step_ids == expected_steps, (
        f"step node ids must be plan-scoped; got {step_ids}"
    )

    # Dependency edges (s1→s2, s1→s3, s2→s3)
    dep_edges = {(e.src, e.dst) for e in dag.edges if e.kind == "dependency"}
    assert ("step:plan-e2e:s1", "step:plan-e2e:s2") in dep_edges
    assert ("step:plan-e2e:s1", "step:plan-e2e:s3") in dep_edges
    assert ("step:plan-e2e:s2", "step:plan-e2e:s3") in dep_edges

    # llm spans attached to steps via task_id == step_id (P0-1 contract)
    for step_id in ("s1", "s2", "s3"):
        step_node = next(
            n for n in dag.nodes if n.id == f"step:plan-e2e:{step_id}"
        )
        assert f"span-llm-{step_id}" in step_node.children, (
            f"llm span for {step_id} not attached to step "
            f"(JOIN via task_id == step_id), children={step_node.children}"
        )

    # 2 sub_agent nodes attached to PLAN (step-level deferred to Phase B)
    sub_nodes = [n for n in dag.nodes if n.kind == "sub_agent"]
    assert len(sub_nodes) == 2, (
        f"expected 2 sub_agent nodes, got {len(sub_nodes)}: "
        f"{[n.id for n in sub_nodes]}"
    )
    sub_descriptions = {n.metadata.get("description") for n in sub_nodes}
    assert sub_descriptions == {"investigator", "reviewer"}
    for sub in sub_nodes:
        assert sub.metadata.get("plan_id") == "plan-e2e", (
            f"sub-agent must attach to plan-e2e, "
            f"got plan_id={sub.metadata.get('plan_id')}"
        )
        assert sub.id in plan_node.children, (
            f"sub-agent {sub.id} must be child of plan node, "
            f"got children={plan_node.children}"
        )

    # iterations == 1 (single plan, no reorchestration history)
    assert dag.iterations == 1, (
        f"single plan with no reorchestration history → iterations=1, "
        f"got {dag.iterations}"
    )

    # No duplicate node ids anywhere (multi-plan shared step_id regression)
    node_ids = [n.id for n in dag.nodes]
    assert len(node_ids) == len(set(node_ids)), (
        f"duplicate node ids: {node_ids}"
    )


def test_pipeline_resilience_when_orchestrator_crashed_before_plan_building(
    tmp_path: Path,
) -> None:
    """Spans exist (orchestrator + phases) but no plan persisted.

    Covers the orchestrator-crashed-before-plan_building case from Q4:
    DAG should still return user_intent + orchestrator + phases so the
    dashboard can show how far the pipeline got, even without plans/steps.
    """
    storage = tmp_path / ".vibe"
    trace_id = "T-crash"

    _write_span(
        storage,
        span_id="span-root",
        trace_id=trace_id,
        span_kind="task",
        name="orchestrate",
        metadata={"query": "q"},
    )
    _write_span(
        storage,
        span_id="span-phase-routing",
        trace_id=trace_id,
        parent_span_id="span-root",
        span_kind="workflow_node",
        metadata={"phase": "routing"},
    )
    _write_span(
        storage,
        span_id="span-phase-detection",
        trace_id=trace_id,
        parent_span_id="span-root",
        span_kind="workflow_node",
        metadata={"phase": "detection"},
    )

    dag = rebuild_dag(trace_id=trace_id, storage_dir=storage)

    # Structure-only DAG, no plans/steps
    assert any(n.kind == "user_intent" for n in dag.nodes)
    assert any(n.kind == "orchestrator" for n in dag.nodes)
    assert {p["phase"] for p in dag.phases} == {"routing", "detection"}
    assert not any(n.kind == "plan" for n in dag.nodes)
    assert not any(n.kind == "step" for n in dag.nodes)
    assert dag.iterations == 0


def test_pipeline_resilience_when_tracing_off_but_plan_persisted(
    tmp_path: Path,
) -> None:
    """Plan exists but no spans (tracing was disabled — Task 10 polish case).

    DAG should still return plan + step structure. Useful partial view for
    the dashboard: "we know what the plan was, even if we don't have span
    evidence of execution." Not an error — Q4 resilience contract.
    """
    storage = tmp_path / ".vibe"
    trace_id = "T-trace-off"

    _write_plan_with_trace(
        storage,
        plan_id="plan-only",
        trace_id=trace_id,
        steps=[
            {"step_id": "s1", "skill_id": "skill-a"},
            {"step_id": "s2", "skill_id": "skill-b"},
        ],
        dependencies={"s2": ["s1"]},
    )

    dag = rebuild_dag(trace_id=trace_id, storage_dir=storage)

    # No orchestrator / phases (no spans)
    assert not any(n.kind == "user_intent" for n in dag.nodes)
    assert not any(n.kind == "orchestrator" for n in dag.nodes)
    assert dag.phases == []

    # Plan + steps present
    plan_node = next(
        (n for n in dag.nodes if n.id == "plan:plan-only"), None
    )
    assert plan_node is not None, "plan node missing even without spans"
    step_ids = {n.id for n in dag.nodes if n.kind == "step"}
    assert step_ids == {"step:plan-only:s1", "step:plan-only:s2"}

    # Dependency edge still present
    dep_edges = {(e.src, e.dst) for e in dag.edges if e.kind == "dependency"}
    assert ("step:plan-only:s1", "step:plan-only:s2") in dep_edges

    assert dag.iterations == 1


def test_pipeline_filters_by_trace_id(tmp_path: Path) -> None:
    """Spans + plans from TWO traces coexist on disk; rebuild_dag must
    only return nodes for the requested trace_id.

    Regression for trace_id filtering — protects against dashboard cross-
    contamination when multiple orchestrate() runs share one .vibe dir.
    """
    storage = tmp_path / ".vibe"

    # Trace A
    _write_plan_with_trace(
        storage,
        plan_id="plan-a",
        trace_id="T-A",
        steps=[{"step_id": "s1"}],
    )
    _write_span(
        storage,
        span_id="span-root-a",
        trace_id="T-A",
        span_kind="task",
        name="orchestrate",
    )

    # Trace B (different trace_id)
    _write_plan_with_trace(
        storage,
        plan_id="plan-b",
        trace_id="T-B",
        steps=[{"step_id": "s1"}],
    )
    _write_span(
        storage,
        span_id="span-root-b",
        trace_id="T-B",
        span_kind="task",
        name="orchestrate",
    )

    dag_a = rebuild_dag(trace_id="T-A", storage_dir=storage)
    dag_b = rebuild_dag(trace_id="T-B", storage_dir=storage)

    a_plan_ids = {n.id for n in dag_a.nodes if n.kind == "plan"}
    b_plan_ids = {n.id for n in dag_b.nodes if n.kind == "plan"}
    assert a_plan_ids == {"plan:plan-a"}
    assert b_plan_ids == {"plan:plan-b"}

    a_span_ids = {
        n.id for n in dag_a.nodes if n.kind in ("orchestrator", "user_intent")
    }
    b_span_ids = {
        n.id for n in dag_b.nodes if n.kind in ("orchestrator", "user_intent")
    }
    assert "span-root-a" in a_span_ids
    assert "span-root-b" not in a_span_ids
    assert "span-root-b" in b_span_ids
    assert "span-root-a" not in b_span_ids
