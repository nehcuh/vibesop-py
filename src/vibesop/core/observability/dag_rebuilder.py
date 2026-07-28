"""DAG rebuilder — reconstruct the Orchestration Map DAG from persisted data.

Reads the JSONL artefacts written during orchestration:

* ``.vibe/execution_plans.jsonl`` — plans (with ``metadata.trace_id``)
* ``.vibe/observability/spans.jsonl`` — span tree (workflow_node + llm + tool)
* ``.vibe/conversations/*.json`` — conversation metadata (parent_session JOIN)

…and reconstructs a ``DAG`` the dashboard's Orchestration Map view renders.

Phase A Task 11 (this file, skeleton):
- ``DAGNode`` / ``DAGEdge`` / ``DAG`` dataclasses
- ``build_span_tree(spans)`` — group spans by parent_span_id (fast traversal)
- Re-export ``load_plans_for_trace`` for single import surface

Phase A Task 12 (next): ``rebuild_dag(trace_id)`` JOIN + sub-agent attach.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from vibesop.core.orchestration.plan_tracker import load_plans_for_trace

__all__ = [
    "DAG",
    "DAGEdge",
    "DAGNode",
    "build_span_tree",
    "load_plans_for_trace",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


NodeKind = Literal[
    "user_intent",  # original query
    "orchestrator",  # the orchestrate() root
    "plan",  # ExecutionPlan node
    "step",  # ExecutionStep node
    "sub_agent",  # external agent / sub-agent conversation
    "llm",  # LLM call span
    "tool",  # tool invocation span
    "output",  # final result
]


EdgeKind = Literal[
    "parent_child",  # tree structure edge
    "dependency",  # plan step dependency (s1 → s2)
    "temporal",  # chronological ordering (no semantic dependency)
    "error",  # error / fallback edge
]


@dataclass
class DAGNode:
    """A single node in the Orchestration Map DAG.

    ``children`` holds outgoing ``parent_child`` edges by reference (child
    node ids). Other edge kinds live on ``DAG.edges``.
    """

    id: str
    kind: NodeKind
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[str] = field(default_factory=list)


@dataclass
class DAGEdge:
    """An edge in the Orchestration Map DAG.

    ``parent_child`` edges are usually implicit (via ``DAGNode.children``)
    but may also be listed here for explicit traversal.
    """

    src: str
    dst: str
    kind: EdgeKind


@dataclass
class DAG:
    """The full reconstructed DAG for a given trace root."""

    nodes: list[DAGNode] = field(default_factory=list)
    edges: list[DAGEdge] = field(default_factory=list)
    phases: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0


# ---------------------------------------------------------------------------
# build_span_tree
# ---------------------------------------------------------------------------


ROOT_SENTINEL = "_root_"
ORPHAN_SENTINEL = "_orphan_"


def build_span_tree(spans: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Group spans by ``parent_span_id`` for fast tree traversal.

    Args:
        spans: List of span dicts (shape: SpanWriter JSONL lines).

    Returns:
        Mapping ``{parent_span_id: [child_span_ids]}``. Two sentinel keys
        carry special-case spans so callers don't have to scan the input
        again:

        * ``"_root_"`` — spans with no ``parent_span_id`` (or empty string).
          These are tree roots (typically the ``orchestrate`` task span).
        * ``"_orphan_"`` — spans whose ``parent_span_id`` references an id
          NOT present in the input. Mirrors ``_render_trace_tree`` orphan
          semantics; the rebuilder decides how to attach them.

        All other keys are real span ids; the value is the list of direct
        children in input order (no implicit sort — temporal layout depends
        on this). Empty input returns ``{}`` (no sentinel keys).
    """
    if not spans:
        return {}

    tree: dict[str, list[str]] = {}
    ids_present = {s.get("id") for s in spans if s.get("id")}
    tree[ROOT_SENTINEL] = []
    tree[ORPHAN_SENTINEL] = []

    for s in spans:
        span_id = s.get("id")
        if not span_id or not isinstance(span_id, str):
            continue

        parent = s.get("parent_span_id")
        if not parent:
            tree[ROOT_SENTINEL].append(span_id)
        elif isinstance(parent, str) and parent in ids_present:
            tree.setdefault(parent, []).append(span_id)
        else:
            tree[ORPHAN_SENTINEL].append(span_id)

        # Ensure every span id has an entry (leaf nodes get []).
        tree.setdefault(span_id, [])

    return tree


# ---------------------------------------------------------------------------
# load_plans_for_trace re-export
#
# Primary implementation lives in vibesop.core.orchestration.plan_tracker
# (kept close to PlanTracker, the canonical source). Re-exported here so
# DAG rebuilder consumers have a single import surface — Task 12's
# rebuild_dag() will use this directly.
# ---------------------------------------------------------------------------

