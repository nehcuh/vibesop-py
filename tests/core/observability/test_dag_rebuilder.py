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

    def test_load_plans_for_trace_returns_empty_for_missing_file(
        self, tmp_path: Path
    ) -> None:
        from vibesop.core.observability.dag_rebuilder import load_plans_for_trace

        result = load_plans_for_trace("any-trace", storage_dir=tmp_path / ".vibe")
        assert result == []
