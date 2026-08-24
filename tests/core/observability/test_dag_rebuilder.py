"""DAG rebuilder tests (v3 Phase A Task 11+12).

Tests the data pipeline that turns raw spans + plans into a DAG the
dashboard's Orchestration Map view can render.

Task 11 (this file's first half):
- ``build_span_tree(spans)`` groups spans by ``parent_span_id``
- ``DAGNode`` / ``DAGEdge`` / ``DAG`` dataclasses round-trip cleanly

Task 12 will add ``rebuild_dag(trace_id)`` JOIN + sub-agent attachment
(covered by additional test classes added later).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibesop.core.observability.dag_rebuilder import (
    DAG,
    DAGEdge,
    DAGNode,
    build_span_tree,
)

# ---------------------------------------------------------------------------
# DAG dataclasses
# ---------------------------------------------------------------------------


class TestDAGDataclasses:
    """Smoke tests for the DAG dataclasses — verify defaults, kinds, and
    round-trip via dataclass.asdict()."""

    def test_dag_node_defaults(self) -> None:
        node = DAGNode(id="n1", kind="step", label="Step 1")
        assert node.id == "n1"
        assert node.kind == "step"
        assert node.label == "Step 1"
        assert node.metadata == {}
        assert node.children == []

    def test_dag_node_metadata_is_independent_per_instance(self) -> None:
        """mutable default footgun guard — each DAGNode must get its own
        metadata dict + children list (not a shared reference)."""
        n1 = DAGNode(id="n1", kind="step", label="a")
        n2 = DAGNode(id="n2", kind="step", label="b")
        n1.metadata["foo"] = "bar"
        n1.children.append("child")
        assert n2.metadata == {}, "metadata leaked across instances"
        assert n2.children == [], "children leaked across instances"

    def test_dag_edge_kinds(self) -> None:
        for kind in ("parent_child", "dependency", "temporal", "error"):
            edge = DAGEdge(src="a", dst="b", kind=kind)  # type: ignore[arg-type]
            assert edge.src == "a"
            assert edge.dst == "b"
            assert edge.kind == kind

    def test_dag_aggregates_all_fields(self) -> None:
        node = DAGNode(id="n1", kind="orchestrator", label="orch")
        edge = DAGEdge(src="n1", dst="n2", kind="parent_child")
        dag = DAG(
            nodes=[node],
            edges=[edge],
            phases=[{"phase": "routing"}],
            iterations=1,
        )
        assert dag.nodes == [node]
        assert dag.edges == [edge]
        assert dag.phases == [{"phase": "routing"}]
        assert dag.iterations == 1

    def test_dag_defaults_to_empty(self) -> None:
        dag = DAG()
        assert dag.nodes == []
        assert dag.edges == []
        assert dag.phases == []
        assert dag.iterations == 0

    def test_dag_to_dict_serializes_all_fields(self) -> None:
        """``DAG.to_dict`` is the API boundary for the dashboard's
        ``/api/orchestration/dag`` endpoint — must produce a JSON-safe dict
        that mirrors the dataclass shape exactly so FastAPI can return it
        directly."""
        node = DAGNode(
            id="n1",
            kind="step",
            label="step-1",
            metadata={"skill_id": "skill-x", "step_id": "s1"},
            children=["n2", "n3"],
        )
        edge = DAGEdge(src="n1", dst="n2", kind="parent_child")
        dag = DAG(
            nodes=[node],
            edges=[edge],
            phases=[{"phase": "routing", "span_id": "phase-1"}],
            iterations=2,
        )

        result = dag.to_dict()

        assert result == {
            "nodes": [
                {
                    "id": "n1",
                    "kind": "step",
                    "label": "step-1",
                    "metadata": {"skill_id": "skill-x", "step_id": "s1"},
                    "children": ["n2", "n3"],
                }
            ],
            "edges": [{"src": "n1", "dst": "n2", "kind": "parent_child"}],
            "phases": [{"phase": "routing", "span_id": "phase-1"}],
            "iterations": 2,
        }

    def test_dag_to_dict_empty_dag_returns_empty_lists(self) -> None:
        """Empty DAG → all-lists-zero shape, still JSON-safe. The 404 path
        never reaches here, but the 200-with-no-data path does."""
        dag = DAG()
        result = dag.to_dict()
        assert result == {
            "nodes": [],
            "edges": [],
            "phases": [],
            "iterations": 0,
        }

    def test_dag_to_dict_metadata_passthrough_no_mutation(self) -> None:
        """to_dict must NOT deep-copy metadata — it's an API boundary, not a
        snapshot. Mutation of the returned dict's metadata should be visible
        on the dataclass (callers don't expect stealth copies)."""
        original_meta = {"key": "value"}
        node = DAGNode(id="n", kind="plan", label="l", metadata=original_meta)
        dag = DAG(nodes=[node])

        result = dag.to_dict()
        result["nodes"][0]["metadata"]["new_key"] = "new_value"

        assert original_meta["new_key"] == "new_value", (
            "metadata should be the same object (no deep copy) — API boundary"
        )

    def test_dag_node_kind_literal_validates(self) -> None:
        """``kind`` is a Literal — invalid values should be caught at type
        checking time. Runtime is permissive (Python Literals aren't enforced),
        so this test just documents the allowed kinds."""
        allowed = {
            "user_intent",
            "orchestrator",
            "plan",
            "step",
            "sub_agent",
            "llm",
            "tool",
            "output",
        }
        # Construct one of each — ensures no typo in the Literal definition.
        for kind in allowed:
            node = DAGNode(id="x", kind=kind, label="x")  # type: ignore[arg-type]
            assert node.kind in allowed


# ---------------------------------------------------------------------------
# build_span_tree
# ---------------------------------------------------------------------------


def _span(
    span_id: str,
    parent_id: str | None = None,
    trace_id: str = "T1",
    name: str | None = None,
    kind: str = "task",
) -> dict[str, Any]:
    """Helper: build a minimal span dict shaped like SpanWriter output."""
    s: dict[str, Any] = {
        "id": span_id,
        "trace_id": trace_id,
        "name": name or span_id,
        "span_kind": kind,
    }
    if parent_id:
        s["parent_span_id"] = parent_id
    return s


class TestBuildSpanTree:
    """``build_span_tree(spans)`` returns ``{parent_id: [child_ids]}`` for
    fast traversal. Roots (no parent_span_id) appear under the sentinel
    key ``"_root_"`` so callers can find them without scanning the spans
    list again."""

    def test_single_root_no_children(self) -> None:
        spans = [_span("r1")]
        tree = build_span_tree(spans)
        assert tree.get("_root_") == ["r1"]
        assert tree.get("r1") == []

    def test_root_with_one_child(self) -> None:
        spans = [
            _span("r1"),
            _span("c1", parent_id="r1"),
        ]
        tree = build_span_tree(spans)
        assert tree["_root_"] == ["r1"]
        assert tree["r1"] == ["c1"]
        assert tree["c1"] == []

    def test_chained_three_levels(self) -> None:
        """root → mid → leaf maps to nested children lists."""
        spans = [
            _span("root"),
            _span("mid", parent_id="root"),
            _span("leaf", parent_id="mid"),
        ]
        tree = build_span_tree(spans)
        assert tree["_root_"] == ["root"]
        assert tree["root"] == ["mid"]
        assert tree["mid"] == ["leaf"]
        assert tree["leaf"] == []

    def test_multiple_children_under_same_parent(self) -> None:
        spans = [
            _span("root"),
            _span("c1", parent_id="root"),
            _span("c2", parent_id="root"),
            _span("c3", parent_id="root"),
        ]
        tree = build_span_tree(spans)
        assert tree["root"] == ["c1", "c2", "c3"]

    def test_orphan_span_parent_id_set_but_parent_missing(self) -> None:
        """Orphans (parent_id references a span NOT in the input) must NOT
        be silently dropped or treated as roots — they're flagged via the
        ``"_orphan_"`` sentinel so the rebuilder can decide how to attach
        them (e.g. to a synthetic root). Mirrors ``_render_trace_tree``
        semantics in trace_cmd.py."""
        spans = [
            _span("root"),
            _span("orphan", parent_id="missing-parent"),
        ]
        tree = build_span_tree(spans)
        assert tree["_root_"] == ["root"]
        assert tree["_orphan_"] == ["orphan"]

    def test_empty_spans_returns_empty_tree(self) -> None:
        tree = build_span_tree([])
        assert tree == {}

    def test_preserves_input_order_within_siblings(self) -> None:
        """Children must appear in input order — the dashboard's temporal
        layout depends on this (no implicit sort)."""
        spans = [
            _span("root"),
            _span("z", parent_id="root"),
            _span("a", parent_id="root"),
            _span("m", parent_id="root"),
        ]
        tree = build_span_tree(spans)
        assert tree["root"] == ["z", "a", "m"]

    def test_parent_id_none_and_empty_string_both_treated_as_root(self) -> None:
        """Different span writers emit either ``None`` or ``""`` for missing
        parent_id. Both must be treated as roots (defensive normalization)."""
        spans = [
            {"id": "r1", "trace_id": "T1", "name": "r1", "span_kind": "task"},
            {"id": "r2", "trace_id": "T1", "name": "r2", "span_kind": "task", "parent_span_id": ""},
        ]
        tree = build_span_tree(spans)
        assert sorted(tree["_root_"]) == ["r1", "r2"]


# ---------------------------------------------------------------------------
# load_plans_for_trace (re-export smoke — primary tests are in
# test_plan_tracker_trace_contract.py)
# ---------------------------------------------------------------------------


class TestLoadPlansForTraceReExport:
    """``dag_rebuilder`` re-exports ``load_plans_for_trace`` so callers have
    a single import surface. Smoke test only — full coverage lives in
    ``tests/core/orchestration/test_plan_tracker_trace_contract.py``."""

    def test_load_plans_for_trace_importable_from_dag_rebuilder(self) -> None:
        from vibesop.core.observability.dag_rebuilder import load_plans_for_trace

        assert callable(load_plans_for_trace)

    def test_load_plans_for_trace_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        from vibesop.core.observability.dag_rebuilder import load_plans_for_trace

        result = load_plans_for_trace("any-trace", storage_dir=tmp_path / ".vibe")
        assert result == []


# ---------------------------------------------------------------------------
# rebuild_dag() — JOIN plan ↔ span + sub-agent attach (Task 12)
# ---------------------------------------------------------------------------


def _write_plan_fixture(
    storage_dir: Path,
    plan_id: str,
    trace_id: str,
    steps: list[dict[str, Any]],
    dependencies: dict[str, list[str]] | None = None,
) -> None:
    """Write a single ExecutionPlan line to execution_plans.jsonl."""
    import json

    from vibesop.core.models import (
        ExecutionMode,
        ExecutionPlan,
        ExecutionStep,
        WorkflowPattern,
    )

    plan = ExecutionPlan(
        plan_id=plan_id,
        original_query=f"query for {plan_id}",
        steps=[
            ExecutionStep(
                step_id=s["step_id"],
                step_number=i + 1,
                skill_id=s.get("skill_id", "skill-x"),
                intent=s.get("intent", "intent-x"),
                dependencies=dependencies.get(s["step_id"], []) if dependencies else [],
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


def _write_span_fixture(
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
    """Append one span line to observability/spans.jsonl (matches SpanWriter layout)."""
    import json

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


def _write_conversation_fixture(
    storage_dir: Path,
    conversation_id: str,
    *,
    is_subagent: bool = False,
    parent_conversation_id: str | None = None,
    orchestration_id: str | None = None,
    orchestration_trace_id: str | None = None,
    agent_type: str | None = "claude-code",
    description: str | None = None,
) -> Path:
    """Write a conversation JSON file mirroring ConversationContext.save() shape."""
    import json

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
    path = conv_dir / f"{conversation_id}.json"
    path.write_text(json.dumps(payload))
    return path


class TestRebuildDagJoin:
    """``rebuild_dag(trace_id, storage_dir)`` JOINs plan ↔ spans + attaches
    sub-agents. Phase A Task 12 contract."""

    def test_rebuild_dag_returns_empty_when_no_data(self, tmp_path: Path) -> None:
        from vibesop.core.observability.dag_rebuilder import rebuild_dag

        dag = rebuild_dag(trace_id="nonexistent", storage_dir=tmp_path / ".vibe")
        assert dag.nodes == []
        assert dag.edges == []
        assert dag.phases == []
        assert dag.iterations == 0

    def test_rebuild_dag_joins_plan_step_to_llm_span_via_task_id(self, tmp_path: Path) -> None:
        """Plan with step_id='s1' + llm span with task_id='s1' → step node
        has the llm span as a child. JOIN key is task_id == step_id (NOT
        plan_id — grok+pi P0-1 contract)."""
        from vibesop.core.observability.dag_rebuilder import rebuild_dag

        storage = tmp_path / ".vibe"
        _write_plan_fixture(
            storage,
            plan_id="plan-1",
            trace_id="T1",
            steps=[{"step_id": "s1", "skill_id": "skill-a"}],
        )
        _write_span_fixture(
            storage,
            span_id="root",
            trace_id="T1",
            span_kind="task",
            name="orchestrate",
            metadata={"query": "test query"},
        )
        _write_span_fixture(
            storage,
            span_id="llm-1",
            trace_id="T1",
            parent_span_id="root",
            span_kind="llm",
            name="classify",
            task_id="s1",
        )

        dag = rebuild_dag(trace_id="T1", storage_dir=storage)

        step_node = next((n for n in dag.nodes if n.id == "step:plan-1:s1"), None)
        assert step_node is not None, "step node plan-1:s1 must exist"
        assert "llm-1" in step_node.children, (
            f"llm-1 must be a child of step:plan-1:s1 (JOIN via task_id), "
            f"got children={step_node.children}"
        )

    def test_rebuild_dag_creates_dependency_edges_between_steps(self, tmp_path: Path) -> None:
        """Steps with `depends_on` produce ``dependency`` kind edges."""
        from vibesop.core.observability.dag_rebuilder import rebuild_dag

        storage = tmp_path / ".vibe"
        _write_plan_fixture(
            storage,
            plan_id="plan-deps",
            trace_id="T-deps",
            steps=[
                {"step_id": "s1"},
                {"step_id": "s2"},
                {"step_id": "s3"},
            ],
            dependencies={"s2": ["s1"], "s3": ["s1", "s2"]},
        )
        _write_span_fixture(
            storage,
            span_id="root",
            trace_id="T-deps",
            span_kind="task",
            name="orchestrate",
        )

        dag = rebuild_dag(trace_id="T-deps", storage_dir=storage)

        dep_edges = [e for e in dag.edges if e.kind == "dependency"]
        edge_pairs = {(e.src, e.dst) for e in dep_edges}
        assert ("step:plan-deps:s1", "step:plan-deps:s2") in edge_pairs
        assert ("step:plan-deps:s1", "step:plan-deps:s3") in edge_pairs
        assert ("step:plan-deps:s2", "step:plan-deps:s3") in edge_pairs

    def test_rebuild_dag_attaches_subagent_to_plan_via_parent_conversation(
        self, tmp_path: Path
    ) -> None:
        """Sub-agent conversation with ``parent_conversation_id`` pointing
        to a main conversation whose ``metadata.orchestration_id`` matches
        a plan → sub_agent node attached to that plan node.

        Chain: sub-agent → parent_conversation_id → main conv metadata.orchestration_id → plan_id.
        Phase A MVP attaches at PLAN level (step-level attachment requires
        tool_use_id matching, deferred to Phase B per design)."""
        from vibesop.core.observability.dag_rebuilder import rebuild_dag

        storage = tmp_path / ".vibe"
        _write_plan_fixture(
            storage,
            plan_id="plan-sub-test",
            trace_id="T-sub",
            steps=[{"step_id": "s1"}],
        )
        _write_span_fixture(
            storage,
            span_id="root",
            trace_id="T-sub",
            span_kind="task",
            name="orchestrate",
        )
        _write_conversation_fixture(
            storage,
            conversation_id="main-conv-1",
            orchestration_id="plan-sub-test",
            orchestration_trace_id="T-sub",
        )
        _write_conversation_fixture(
            storage,
            conversation_id="main-conv-1-sub-agent-abc",
            is_subagent=True,
            parent_conversation_id="main-conv-1",
            agent_type="claude-code",
            description="investigator",
        )

        dag = rebuild_dag(trace_id="T-sub", storage_dir=storage)

        sub_nodes = [n for n in dag.nodes if n.kind == "sub_agent"]
        assert len(sub_nodes) == 1
        sub_node = sub_nodes[0]
        assert sub_node.metadata.get("plan_id") == "plan-sub-test"

        # plan node has sub_node as child
        plan_node = next((n for n in dag.nodes if n.id == "plan:plan-sub-test"), None)
        assert plan_node is not None
        assert sub_node.id in plan_node.children, (
            f"sub_agent must be attached to plan node, got children={plan_node.children}"
        )

    def test_rebuild_dag_user_intent_node_uses_query_from_root_span(self, tmp_path: Path) -> None:
        """Root 'orchestrate' span metadata.query becomes the user_intent
        node label — preserves the original user request in the map."""
        from vibesop.core.observability.dag_rebuilder import rebuild_dag

        storage = tmp_path / ".vibe"
        _write_span_fixture(
            storage,
            span_id="root",
            trace_id="T-intent",
            span_kind="task",
            name="orchestrate",
            metadata={"query": "analyse my code and add tests"},
        )

        dag = rebuild_dag(trace_id="T-intent", storage_dir=storage)

        ui_nodes = [n for n in dag.nodes if n.kind == "user_intent"]
        assert ui_nodes, "user_intent node must exist when root span present"
        assert "analyse my code" in ui_nodes[0].label

    def test_rebuild_dag_emits_orchestrator_and_phase_nodes(self, tmp_path: Path) -> None:
        """Root 'orchestrate' span becomes orchestrator node; workflow_node
        phase spans become its children. dag.phases carries the phase list."""
        from vibesop.core.observability.dag_rebuilder import rebuild_dag

        storage = tmp_path / ".vibe"
        _write_span_fixture(
            storage,
            span_id="root",
            trace_id="T-phase",
            span_kind="task",
            name="orchestrate",
            metadata={"query": "q"},
        )
        for phase in ("routing", "detection", "plan_building", "complete"):
            _write_span_fixture(
                storage,
                span_id=f"phase-{phase}",
                trace_id="T-phase",
                parent_span_id="root",
                span_kind="workflow_node",
                name=f"orchestrate:{phase}",
                metadata={"phase": phase},
            )

        dag = rebuild_dag(trace_id="T-phase", storage_dir=storage)

        orch_nodes = [n for n in dag.nodes if n.kind == "orchestrator"]
        assert orch_nodes, "orchestrator node must exist"
        orch = orch_nodes[0]
        # phase nodes attached as children
        for phase in ("routing", "detection", "plan_building", "complete"):
            phase_id = f"phase-{phase}"
            assert phase_id in orch.children, (
                f"phase {phase} must be child of orchestrator, got children={orch.children}"
            )

        phase_names = {p["phase"] for p in dag.phases}
        assert {"routing", "detection", "plan_building", "complete"}.issubset(phase_names)

    def test_rebuild_dag_iterations_falls_back_to_plan_count_without_history(
        self, tmp_path: Path
    ) -> None:
        """``iterations`` falls back to plan count when no
        ``reorchestration_history`` exists. Covers the rare multi-plan case
        (two orchestrate() calls under same trace_id) — most production
        traces have one plan and zero history, yielding iterations=1."""
        from vibesop.core.observability.dag_rebuilder import rebuild_dag

        storage = tmp_path / ".vibe"
        _write_span_fixture(
            storage,
            span_id="root",
            trace_id="T-iter",
            span_kind="task",
            name="orchestrate",
        )
        _write_plan_fixture(
            storage,
            plan_id="plan-iter-1",
            trace_id="T-iter",
            steps=[{"step_id": "s1"}],
        )
        _write_plan_fixture(
            storage,
            plan_id="plan-iter-2",
            trace_id="T-iter",
            steps=[{"step_id": "s2"}],
        )

        dag = rebuild_dag(trace_id="T-iter", storage_dir=storage)
        assert dag.iterations == 2

    def test_rebuild_dag_iterations_derives_from_reorchestration_history(
        self, tmp_path: Path
    ) -> None:
        """``iterations`` = ``max(reorchestration_history) + 1`` —
        ``loop_until_dry`` keeps ONE ``plan_id`` and accumulates history,
        so counting plans under-counts real loop rounds.

        Regression for grok Q3 finding: a single plan with 2 history
        entries means 3 rounds total (initial + 2 reorchestrations).
        Pre-fix this returned iterations=1 because ``len(plans) == 1``.
        """
        import json

        from vibesop.core.models import (
            ExecutionMode,
            ExecutionPlan,
            ExecutionStep,
            WorkflowPattern,
        )
        from vibesop.core.observability.dag_rebuilder import rebuild_dag

        storage = tmp_path / ".vibe"
        _write_span_fixture(
            storage,
            span_id="root",
            trace_id="T-loop",
            span_kind="task",
            name="orchestrate",
        )
        plan = ExecutionPlan(
            plan_id="plan-loop",
            original_query="loop test",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="skill-x",
                    intent="intent-x",
                )
            ],
            workflow_pattern=WorkflowPattern.SEQUENTIAL,
            execution_mode=ExecutionMode.SEQUENTIAL,
        )
        plan.metadata["trace_id"] = "T-loop"
        plan.reorchestration_history = [
            {"round": 1, "reason": "step failed"},
            {"round": 2, "reason": "validation gap"},
        ]
        storage.mkdir(parents=True, exist_ok=True)
        with (storage / "execution_plans.jsonl").open("a") as f:
            f.write(json.dumps(plan.to_dict()) + "\n")

        dag = rebuild_dag(trace_id="T-loop", storage_dir=storage)
        assert dag.iterations == 3, (
            f"1 plan + 2 reorchestration rounds = 3 iterations; got {dag.iterations}"
        )

    def test_rebuild_dag_multi_plan_shared_step_id_attaches_span_once(self, tmp_path: Path) -> None:
        """Multi-plan trace where two plans share the same ``step_id``
        must produce **distinct** plan-scoped step node ids, and a single
        matching span must attach to AT MOST ONE step.

        Regression for grok+pi Q1 finding: pre-fix, both plans got
        ``step:s1`` (id collision) and the span was attached to BOTH,
        producing a corrupted graph with duplicate node ids.
        """
        from vibesop.core.observability.dag_rebuilder import rebuild_dag

        storage = tmp_path / ".vibe"
        _write_span_fixture(
            storage,
            span_id="root",
            trace_id="T-collide",
            span_kind="task",
            name="orchestrate",
        )
        _write_plan_fixture(
            storage,
            plan_id="plan-A",
            trace_id="T-collide",
            steps=[{"step_id": "s1", "skill_id": "skill-a"}],
        )
        _write_plan_fixture(
            storage,
            plan_id="plan-B",
            trace_id="T-collide",
            steps=[{"step_id": "s1", "skill_id": "skill-b"}],
        )
        _write_span_fixture(
            storage,
            span_id="llm-shared",
            trace_id="T-collide",
            parent_span_id="root",
            span_kind="llm",
            name="classify",
            task_id="s1",
        )

        dag = rebuild_dag(trace_id="T-collide", storage_dir=storage)

        node_ids = [n.id for n in dag.nodes]
        # No duplicate node ids anywhere in the DAG
        assert len(node_ids) == len(set(node_ids)), f"duplicate node ids detected: {node_ids}"
        # Both plan-scoped step ids exist
        assert "step:plan-A:s1" in node_ids
        assert "step:plan-B:s1" in node_ids
        # The span attaches to exactly one step (first plan wins)
        step_a = next(n for n in dag.nodes if n.id == "step:plan-A:s1")
        step_b = next(n for n in dag.nodes if n.id == "step:plan-B:s1")
        a_has = "llm-shared" in step_a.children
        b_has = "llm-shared" in step_b.children
        assert a_has != b_has, (
            f"span must attach to exactly one step, plan-A={a_has} plan-B={b_has}"
        )
        # Exactly one llm span node exists
        llm_nodes = [n for n in dag.nodes if n.id == "llm-shared"]
        assert len(llm_nodes) == 1, f"span should not be duplicated in DAG, found {len(llm_nodes)}"

    def test_rebuild_dag_load_span_trace_id_filter(self, tmp_path: Path) -> None:
        """``load_spans_for_trace`` filters by trace_id — spans from other
        traces must NOT leak into the rebuilt DAG."""
        from vibesop.core.observability.dag_rebuilder import (
            load_spans_for_trace,
            rebuild_dag,
        )

        storage = tmp_path / ".vibe"
        _write_span_fixture(
            storage,
            span_id="span-A",
            trace_id="T-A",
            span_kind="task",
            name="orchestrate-A",
        )
        _write_span_fixture(
            storage,
            span_id="span-B",
            trace_id="T-B",
            span_kind="task",
            name="orchestrate-B",
        )

        spans_a = load_spans_for_trace("T-A", storage_dir=storage)
        ids_a = {s["id"] for s in spans_a}
        assert ids_a == {"span-A"}, f"T-B span leaked into T-A result: {ids_a}"

        dag = rebuild_dag(trace_id="T-A", storage_dir=storage)
        node_ids = {n.id for n in dag.nodes}
        assert "span-A" in node_ids
        assert "span-B" not in node_ids
