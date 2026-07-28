"""DAG rebuilder — reconstruct the Orchestration Map DAG from persisted data.

Reads the JSONL artefacts written during orchestration:

* ``.vibe/execution_plans.jsonl`` — plans (with ``metadata.trace_id``)
* ``.vibe/observability/spans.jsonl`` — span tree (workflow_node + llm + tool)
* ``.vibe/conversations/*.json`` — conversation metadata (parent_session JOIN)

…and reconstructs a ``DAG`` the dashboard's Orchestration Map view renders.

Phase A Task 11:
- ``DAGNode`` / ``DAGEdge`` / ``DAG`` dataclasses
- ``build_span_tree(spans)`` — group spans by parent_span_id (fast traversal)
- Re-export ``load_plans_for_trace`` for single import surface

Phase A Task 12:
- ``load_spans_for_trace`` — read + filter spans.jsonl by trace_id
- ``rebuild_dag(trace_id, storage_dir)`` — full JOIN + sub-agent attach
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from vibesop.core.orchestration.plan_tracker import load_plans_for_trace

logger = logging.getLogger(__name__)

__all__ = [
    "DAG",
    "ORPHAN_SENTINEL",
    "ROOT_SENTINEL",
    "DAGEdge",
    "DAGNode",
    "build_span_tree",
    "load_plans_for_trace",
    "load_spans_for_trace",
    "rebuild_dag",
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


# ---------------------------------------------------------------------------
# load_spans_for_trace
# ---------------------------------------------------------------------------


def load_spans_for_trace(
    trace_id: str,
    storage_dir: str | Path = ".vibe",
) -> list[dict[str, Any]]:
    """Read ``observability/spans.jsonl`` and return spans matching ``trace_id``.

    Args:
        trace_id: The trace root id produced by ``orchestrate()``.
        storage_dir: Project ``.vibe`` directory (absolute path recommended
            — relative resolves against CWD; see ``load_plans_for_trace``
            docstring for the same footgun).

    Returns:
        Span dicts whose ``trace_id`` matches. Empty list if file missing
        or no match. ``metadata`` field is decoded from JSON string to dict
        if necessary (SpanWriter serialises it that way).
    """
    spans_path = Path(storage_dir) / "observability" / "spans.jsonl"
    if not spans_path.exists():
        return []

    result: list[dict[str, Any]] = []
    try:
        with spans_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    span = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if span.get("trace_id") != trace_id:
                    continue
                # Decode metadata if serialised as JSON string (SpanWriter does this).
                meta = span.get("metadata")
                if isinstance(meta, str):
                    try:
                        span["metadata"] = json.loads(meta)
                    except json.JSONDecodeError:
                        span["metadata"] = {}
                result.append(span)
    except OSError as e:
        logger.warning("Failed to read spans from %s: %s", spans_path, e)
        return []
    return result


# ---------------------------------------------------------------------------
# rebuild_dag — the main entry point
# ---------------------------------------------------------------------------


def rebuild_dag(
    trace_id: str,
    storage_dir: str | Path = ".vibe",
) -> DAG:
    """Reconstruct the Orchestration Map DAG for a given trace root.

    Reads plans + spans + conversations from ``storage_dir`` and builds a
    ``DAG`` the dashboard's Orchestration Map view renders.

    Args:
        trace_id: The trace root id produced by ``orchestrate()``.
        storage_dir: Project ``.vibe`` directory. **Must be absolute** —
            the orchestrator writes to ``project_root / ".vibe"`` and the
            reader resolves relative paths against CWD. Mismatched CWD
            silently returns an empty DAG (flagged independently by grok
            and pi review of Task 10).

    Returns:
        ``DAG`` with:

        * ``user_intent`` node (from root span ``metadata.query``)
        * ``orchestrator`` node (the ``orchestrate`` root span)
        * Phase children (``workflow_node`` spans)
        * ``plan`` node per ExecutionPlan
        * ``step`` nodes per plan.steps with ``dependency`` edges
        * ``llm``/``tool`` spans attached to steps via ``task_id == step_id``
          (P0-1 contract — never via plan_id)
        * ``sub_agent`` nodes attached to plans via
          ``parent_conversation_id`` → main conversation's
          ``orchestration_id`` chain (MVP: plan-level attachment; step-level
          requires ``tool_use_id`` matching, deferred to Phase B)
        * ``iterations`` = number of plans (reorchestration creates new plans)

        Empty ``DAG`` if no spans AND no plans match the trace id.
    """
    dag = DAG()
    storage = Path(storage_dir)

    spans = load_spans_for_trace(trace_id, storage_dir=storage)
    plans = load_plans_for_trace(trace_id, storage_dir=storage)

    if not spans and not plans:
        return dag

    # ------------------------------------------------------------------
    # user_intent + orchestrator nodes (from root span)
    # ------------------------------------------------------------------
    root_span = _find_root_span(spans)
    user_intent_id: str | None = None
    orch_id: str | None = None

    if root_span is not None:
        meta = root_span.get("metadata") or {}
        query = meta.get("query") or trace_id
        user_intent_id = f"user_intent:{trace_id}"
        dag.nodes.append(
            DAGNode(
                id=user_intent_id,
                kind="user_intent",
                label=str(query)[:80],
                metadata={"trace_id": trace_id, "query": query},
            )
        )

        orch_id = root_span.get("id", "")
        if orch_id:
            orch_node = DAGNode(
                id=orch_id,
                kind="orchestrator",
                label="orchestrate",
                metadata={"trace_id": trace_id, "span_id": orch_id},
            )
            dag.nodes.append(orch_node)
            if user_intent_id:
                dag.edges.append(
                    DAGEdge(
                        src=user_intent_id,
                        dst=orch_id,
                        kind="parent_child",
                    )
                )
                dag.nodes[-2].children.append(orch_id)

        # Phase children of orchestrator
        phase_spans = [
            s for s in spans
            if s.get("span_kind") == "workflow_node"
            and s.get("parent_span_id") == orch_id
        ]
        for ps in phase_spans:
            phase_meta = ps.get("metadata") or {}
            phase = phase_meta.get("phase", "unknown")
            dag.phases.append({"phase": phase, "span_id": ps.get("id", "")})

            phase_node = DAGNode(
                id=ps.get("id", f"phase:{phase}"),
                kind="orchestrator",  # phase nodes are sub-orchestrator
                label=f"phase:{phase}",
                metadata=phase_meta,
            )
            dag.nodes.append(phase_node)
            if orch_id:
                dag.edges.append(
                    DAGEdge(src=orch_id, dst=phase_node.id, kind="parent_child")
                )
                for n in dag.nodes:
                    if n.id == orch_id:
                        n.children.append(phase_node.id)
                        break

    # ------------------------------------------------------------------
    # Plan + step nodes
    # ------------------------------------------------------------------
    for plan in plans:
        plan_node_id = f"plan:{plan.plan_id}"
        plan_node = DAGNode(
            id=plan_node_id,
            kind="plan",
            label=f"plan:{plan.plan_id[:8]}",
            metadata={
                "plan_id": plan.plan_id,
                "pattern": plan.workflow_pattern.value,
                "step_count": len(plan.steps),
                "trace_id": trace_id,
            },
        )
        dag.nodes.append(plan_node)
        if orch_id:
            dag.edges.append(
                DAGEdge(src=orch_id, dst=plan_node_id, kind="parent_child")
            )
            for n in dag.nodes:
                if n.id == orch_id:
                    n.children.append(plan_node_id)
                    break

        # Step nodes
        step_node_ids: list[str] = []
        for step in plan.steps:
            step_node_id = f"step:{step.step_id}"
            step_node_ids.append(step_node_id)
            step_node = DAGNode(
                id=step_node_id,
                kind="step",
                label=step.skill_id or step.step_id,
                metadata={
                    "step_id": step.step_id,
                    "skill_id": step.skill_id,
                    "role": step.assigned_role,
                },
            )
            dag.nodes.append(step_node)
            dag.edges.append(
                DAGEdge(src=plan_node_id, dst=step_node_id, kind="parent_child")
            )
            plan_node.children.append(step_node_id)

        # Dependency edges (from step.dependencies)
        for step in plan.steps:
            for dep in step.dependencies or []:
                dag.edges.append(
                    DAGEdge(
                        src=f"step:{dep}",
                        dst=f"step:{step.step_id}",
                        kind="dependency",
                    )
                )

        # Attach llm/tool spans to steps via task_id == step_id (P0-1)
        for step in plan.steps:
            attached = [
                s for s in spans
                if s.get("task_id") == step.step_id
                and s.get("span_kind") in ("llm", "tool", "tool_call")
            ]
            for s in attached:
                span_kind = s.get("span_kind")
                node_kind: NodeKind = "llm" if span_kind == "llm" else "tool"
                span_node = DAGNode(
                    id=s.get("id", f"span:{step.step_id}"),
                    kind=node_kind,
                    label=(s.get("name") or s.get("id", ""))[:60],
                    metadata={"trace_id": s.get("trace_id", trace_id)},
                )
                dag.nodes.append(span_node)
                step_node_id = f"step:{step.step_id}"
                dag.edges.append(
                    DAGEdge(
                        src=step_node_id,
                        dst=span_node.id,
                        kind="parent_child",
                    )
                )
                for n in dag.nodes:
                    if n.id == step_node_id:
                        n.children.append(span_node.id)
                        break

    # ------------------------------------------------------------------
    # Sub-agent nodes (attached to plans via parent_conversation_id chain)
    # ------------------------------------------------------------------
    subagent_attachments = _discover_subagents(storage, plans)
    for attach in subagent_attachments:
        sub_node = DAGNode(
            id=f"subagent:{attach['conversation_id']}",
            kind="sub_agent",
            label=attach.get("description")
            or attach.get("agent_type")
            or "sub-agent",
            metadata={
                "agent_type": attach.get("agent_type"),
                "parent_conversation_id": attach.get("parent_conversation_id"),
                "plan_id": attach.get("plan_id"),
                "conversation_id": attach.get("conversation_id"),
            },
        )
        dag.nodes.append(sub_node)
        plan_node_id = f"plan:{attach['plan_id']}"
        dag.edges.append(
            DAGEdge(src=plan_node_id, dst=sub_node.id, kind="parent_child")
        )
        for n in dag.nodes:
            if n.id == plan_node_id:
                n.children.append(sub_node.id)
                break

    # Iterations = number of plans (reorchestration rounds)
    dag.iterations = len(plans)

    return dag


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_root_span(spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the root orchestrate span: prefer the 'orchestrate' task span
    with no parent_span_id. Fall back to any root if name differs."""
    roots = [
        s for s in spans
        if not s.get("parent_span_id")
        and s.get("span_kind") == "task"
    ]
    if not roots:
        return None
    named = [s for s in roots if s.get("name") == "orchestrate"]
    return named[0] if named else roots[0]


def _discover_subagents(
    storage_dir: Path,
    plans: list[Any],
) -> list[dict[str, Any]]:
    """Walk ``storage_dir / conversations`` for sub-agent conversations.

    Returns a list of attachment descriptors, each carrying:

    * ``conversation_id``: the sub-agent's conversation id
    * ``parent_conversation_id``: the main conversation it was spawned from
    * ``plan_id``: the plan id (looked up via parent's ``orchestration_id``)
    * ``agent_type`` / ``description``: display metadata

    Plans not in ``plans`` are skipped — we only attach to plans visible
    in this trace's rebuild.
    """
    plan_ids = {p.plan_id for p in plans}
    conv_dir = storage_dir / "conversations"
    if not conv_dir.exists():
        return []

    attachments: list[dict[str, Any]] = []
    try:
        for conv_file in conv_dir.glob("*.json"):
            try:
                payload = json.loads(conv_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            meta = payload.get("metadata") or {}
            if not meta.get("is_subagent"):
                continue
            parent_conv_id = meta.get("parent_conversation_id")
            if not parent_conv_id:
                continue

            plan_id = _lookup_orchestration_id(storage_dir, parent_conv_id)
            if not plan_id or plan_id not in plan_ids:
                continue

            attachments.append(
                {
                    "conversation_id": payload.get("conversation_id", conv_file.stem),
                    "parent_conversation_id": parent_conv_id,
                    "plan_id": plan_id,
                    "agent_type": meta.get("agent_type"),
                    "description": meta.get("description"),
                }
            )
    except OSError as e:
        logger.warning("Failed to scan conversations in %s: %s", conv_dir, e)
    return attachments


def _lookup_orchestration_id(
    storage_dir: Path,
    conversation_id: str,
) -> str | None:
    """Read ``conversations/<conversation_id>.json`` and return its
    ``metadata.orchestration_id`` (the plan_id of the orchestration that
    spawned this conversation or its sub-agents)."""
    conv_path = storage_dir / "conversations" / f"{conversation_id}.json"
    if not conv_path.exists():
        return None
    try:
        payload = json.loads(conv_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    meta = payload.get("metadata") or {}
    orch_id = meta.get("orchestration_id")
    return str(orch_id) if orch_id else None
