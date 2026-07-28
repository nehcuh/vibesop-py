/bin/sh: -c: line 0: syntax error near unexpected token `('
/bin/sh: -c: line 0: `vibe route --json --yes "You are reviewing **Phase A Task 12** of VibeSOP's Dashboard v3 instrumentation — the most complex piece of Phase A: \`rebuild_dag(trace_id, storage_dir)\` JOINs plans ↔ spans ↔ conversations and reconstructs a DAG for the dashboard's Orchestration Map view.  ## Context  - Codebase: Python 3.12+, strict typing, TDD. - Phase A data pipeline (Tasks 1-12 shipped):   - Orchestrator wraps \`orchestrate()\` in a root trace span (Task 2)   - Each phase emits \`workflow_node\` spans (Task 3)   - Per-step \`bind_task_context(step_id, role)\` makes downstream llm spans carry \`task_id=step_id\` (Task 4)   - Plan persisted via PlanTracker with \`metadata.trace_id\` (Task 10)   - Sub-agent conversations persisted with \`parent_conversation_id\` + \`is_subagent=True\` (Task 6) - Task 12 (this commit) implements \`rebuild_dag()\` — the consumer of all that data.  ## What \`rebuild_dag\` does  1. Loads plans via \`load_plans_for_trace(trace_id, storage_dir)\` (filtered by \`metadata.trace_id\`) 2. Loads spans via \`load_spans_for_trace(trace_id, storage_dir)\` (filtered by \`span.trace_id\`) 3. Builds:    - \`user_intent\` node from root span \`metadata.query\`    - \`orchestrator\` node (the \`orchestrate\` task span)    - Phase children (\`workflow_node\` spans) → also populate \`dag.phases\`    - \`plan\` node per ExecutionPlan, child of orchestrator    - \`step\` nodes per \`plan.steps\`, child of plan    - \`dependency\` edges from \`step.dependencies\`    - \`llm\`/\`tool\` spans attached to steps via \`task_id == step_id\` (P0-1 contract)    - \`sub_agent\` nodes attached to plans via \`parent_conversation_id\` → main conversation's \`orchestration_id\` → plan_id chain 4. \`iterations = len(plans)\` (reorchestration rounds)  ## Five review questions (focused)  **Q1. JOIN correctness — step ↔ span.** The P0-1 contract says llm/tool spans attach to **steps** via \`task_id == step_id\` (never \`plan_id\`). Verify: - Is the filter \`s.get(\\"task_id\\") == step.step_id\` correct? - What happens to spans with \`task_id\` set but no matching step in any plan (orphan spans)? Are they silently dropped? Should they be attached somewhere (e.g., to the plan node directly)? - What happens when **multiple plans share the same step_id** (reorchestration case)? My code attaches the span to **every** matching step across all plans — could this create duplicate nodes or false positives?  **Q2. JOIN correctness — sub-agent → plan.** The chain is: \`sub-agent.metadata.parent_conversation_id\` → main conv file → \`main.metadata.orchestration_id\` → plan. Verify: - Is this chain resilient to missing files? (e.g., main conversation file deleted but sub-agent file remains) - What if \`orchestration_id\` is in the sub-agent's own metadata (legacy or denormalized)? My code ignores that and only reads from parent — correct? - MVP attaches at plan-level, not step-level. The plan described \\"attach to corresponding step\\" — is plan-level acceptable, or should this be a blocker?  **Q3. \`iterations\` semantics.** I set \`dag.iterations = len(plans)\`. But: - A single orchestrate() call produces 1 plan. If the user calls orchestrate() twice with the same trace_id (shouldn't happen, but...), should iterations be 2? - Reorchestration (loop_until_dry) creates a new plan with a new plan_id under the same trace root. Is counting plans the right metric, or should it be derived from reorchestration_history? - What does \\"iteration\\" mean to the dashboard user? If they see \`iterations=3\`, what do they expect?  **Q4. Empty / partial data resilience.** What does the dashboard show when: - Spans exist but no plans (orchestrator crashed before plan_building)? → my code returns DAG with user_intent + orchestrator + phases, no plans/steps. Correct? - Plans exist but no spans (tracing was disabled but plan was persisted — Task 10 polish case)? → my code returns DAG with plans/steps/sub_agents but no orchestrator/phases/llm children. Is this useful, or should it be an error? - Conversations dir missing entirely? → sub_agent discovery returns [], no error. Correct?  **Q5. Performance + scalability.** The dashboard calls this on every page load. Current complexity: - \`load_plans_for_trace\` reads all lines, dedupes by plan_id, filters — O(N) where N = total plan lines - \`load_spans_for_trace\` reads all lines, filters by trace_id — O(M) where M = total span lines - For each plan's steps, my code does \`[s for s in spans if s.get(\\"task_id\\") == step.step_id]\` — O(steps × spans) - \`_discover_subagents\` does \`glob(\\"*.json\\")\` then reads each conversation file  For a project with 10,000 spans + 500 plans + 100 conversations, is this acceptable for a dashboard page load (<200ms)? If not, what's the cheapest fix?  ## Output format  For each question Q1-Q5: - **Verdict**: PASS / CONCERN / BLOCKER - **Evidence**: code line ref or test ref - **Fix (if not PASS)**: concrete change  End with: **Overall verdict** (SHIP / FIX-THEN-SHIP / BLOCK) and **top 3 risks** ranked by severity.  ## Source diff (dag_rebuilder.py — Task 12 changes)  @/tmp/task12_src.patch  ## Test diff (test_dag_rebuilder.py — Task 12 additions)  @/tmp/task12_test.patch commit 5557a9fa2f93057ec1ea50fec0433c814a76233d Author: huchen <curiousbull@outlook.com> Date:   Tue Jul 28 13:53:09 2026 +0800      feat(observability): rebuild_dag() — JOIN plan ↔ spans + sub-agent attach          Phase A Task 12. Implements the full DAG reconstruction pipeline that     the dashboard's Orchestration Map view consumes.          Public API additions (dag_rebuilder.py):     - load_spans_for_trace(trace_id, storage_dir) — reads       observability/spans.jsonl, filters by trace_id, decodes metadata       JSON-string into dict (SpanWriter serialises that way).     - rebuild_dag(trace_id, storage_dir) — returns DAG with:       * user_intent node from root span metadata.query       * orchestrator node (the 'orchestrate' root span)       * phase children (workflow_node spans → dag.phases)       * plan node per ExecutionPlan       * step nodes with dependency edges (step.dependencies)       * llm/tool spans attached to steps via task_id == step_id         (P0-1 contract — never via plan_id)       * sub_agent nodes attached to plans via parent_conversation_id         → main conversation's orchestration_id chain       * iterations == number of plans (reorchestration rounds)          MVP scope (per design doc §3):     - Sub-agent attachment is PLAN-level, not step-level. Step-level needs       tool_use_id matching across processes (deferred to Phase B).     - Map MVP allows step nodes with no llm children when work was done in       an external agent — the step's skill_id + dependencies + attached       sub_agent still produce a meaningful DAG.          8 new tests covering: empty data, plan-step-span JOIN via task_id,     dependency edges, sub-agent attachment chain, user_intent label,     phase nodes, iterations count, trace_id filter isolation.          24/24 dag_rebuilder tests green; 533 passed in broader regression     (routing + orchestration + observability); lint + type check clean.          Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>  diff --git a/src/vibesop/core/observability/dag_rebuilder.py b/src/vibesop/core/observability/dag_rebuilder.py index d0a4793..42cfadd 100644 --- a/src/vibesop/core/observability/dag_rebuilder.py +++ b/src/vibesop/core/observability/dag_rebuilder.py @@ -8,27 +8,38 @@ Reads the JSONL artefacts written during orchestration:    …and reconstructs a \`\`DAG\`\` the dashboard's Orchestration Map view renders.   -Phase A Task 11 (this file, skeleton): +Phase A Task 11:  - \`\`DAGNode\`\` / \`\`DAGEdge\`\` / \`\`DAG\`\` dataclasses  - \`\`build_span_tree(spans)\`\` — group spans by parent_span_id (fast traversal)  - Re-export \`\`load_plans_for_trace\`\` for single import surface   -Phase A Task 12 (next): \`\`rebuild_dag(trace_id)\`\` JOIN + sub-agent attach. +Phase A Task 12: +- \`\`load_spans_for_trace\`\` — read + filter spans.jsonl by trace_id +- \`\`rebuild_dag(trace_id, storage_dir)\`\` — full JOIN + sub-agent attach  \\"\\"\\"    from __future__ import annotations   +import json +import logging  from dataclasses import dataclass, field +from pathlib import Path  from typing import Any, Literal    from vibesop.core.orchestration.plan_tracker import load_plans_for_trace   +logger = logging.getLogger(__name__) +  __all__ = [      \\"DAG\\", +    \\"ORPHAN_SENTINEL\\", +    \\"ROOT_SENTINEL\\",      \\"DAGEdge\\",      \\"DAGNode\\",      \\"build_span_tree\\",      \\"load_plans_for_trace\\", +    \\"load_spans_for_trace\\", +    \\"rebuild_dag\\",  ]     @@ -161,3 +172,383 @@ def build_span_tree(spans: list[dict[str, Any]]) -> dict[str, list[str]]:  # rebuild_dag() will use this directly.  # ---------------------------------------------------------------------------   + +# --------------------------------------------------------------------------- +# load_spans_for_trace +# --------------------------------------------------------------------------- + + +def load_spans_for_trace( +    trace_id: str, +    storage_dir: str | Path = \\".vibe\\", +) -> list[dict[str, Any]]: +    \\"\\"\\"Read \`\`observability/spans.jsonl\`\` and return spans matching \`\`trace_id\`\`. + +    Args: +        trace_id: The trace root id produced by \`\`orchestrate()\`\`. +        storage_dir: Project \`\`.vibe\`\` directory (absolute path recommended +            — relative resolves against CWD; see \`\`load_plans_for_trace\`\` +            docstring for the same footgun). + +    Returns: +        Span dicts whose \`\`trace_id\`\` matches. Empty list if file missing +        or no match. \`\`metadata\`\` field is decoded from JSON string to dict +        if necessary (SpanWriter serialises it that way). +    \\"\\"\\" +    spans_path = Path(storage_dir) / \\"observability\\" / \\"spans.jsonl\\" +    if not spans_path.exists(): +        return [] + +    result: list[dict[str, Any]] = [] +    try: +        with spans_path.open(\\"r\\", encoding=\\"utf-8\\") as f: +            for raw_line in f: +                line = raw_line.strip() +                if not line: +                    continue +                try: +                    span = json.loads(line) +                except json.JSONDecodeError: +                    continue +                if span.get(\\"trace_id\\") != trace_id: +                    continue +                # Decode metadata if serialised as JSON string (SpanWriter does this). +                meta = span.get(\\"metadata\\") +                if isinstance(meta, str): +                    try: +                        span[\\"metadata\\"] = json.loads(meta) +                    except json.JSONDecodeError: +                        span[\\"metadata\\"] = {} +                result.append(span) +    except OSError as e: +        logger.warning(\\"Failed to read spans from %s: %s\\", spans_path, e) +        return [] +    return result + + +# --------------------------------------------------------------------------- +# rebuild_dag — the main entry point +# --------------------------------------------------------------------------- + + +def rebuild_dag( +    trace_id: str, +    storage_dir: str | Path = \\".vibe\\", +) -> DAG: +    \\"\\"\\"Reconstruct the Orchestration Map DAG for a given trace root. + +    Reads plans + spans + conversations from \`\`storage_dir\`\` and builds a +    \`\`DAG\`\` the dashboard's Orchestration Map view renders. + +    Args: +        trace_id: The trace root id produced by \`\`orchestrate()\`\`. +        storage_dir: Project \`\`.vibe\`\` directory. **Must be absolute** — +            the orchestrator writes to \`\`project_root / \\".vibe\\"\`\` and the +            reader resolves relative paths against CWD. Mismatched CWD +            silently returns an empty DAG (flagged independently by grok +            and pi review of Task 10). + +    Returns: +        \`\`DAG\`\` with: + +        * \`\`user_intent\`\` node (from root span \`\`metadata.query\`\`) +        * \`\`orchestrator\`\` node (the \`\`orchestrate\`\` root span) +        * Phase children (\`\`workflow_node\`\` spans) +        * \`\`plan\`\` node per ExecutionPlan +        * \`\`step\`\` nodes per plan.steps with \`\`dependency\`\` edges +        * \`\`llm\`\`/\`\`tool\`\` spans attached to steps via \`\`task_id == step_id\`\` +          (P0-1 contract — never via plan_id) +        * \`\`sub_agent\`\` nodes attached to plans via +          \`\`parent_conversation_id\`\` → main conversation's +          \`\`orchestration_id\`\` chain (MVP: plan-level attachment; step-level +          requires \`\`tool_use_id\`\` matching, deferred to Phase B) +        * \`\`iterations\`\` = number of plans (reorchestration creates new plans) + +        Empty \`\`DAG\`\` if no spans AND no plans match the trace id. +    \\"\\"\\" +    dag = DAG() +    storage = Path(storage_dir) + +    spans = load_spans_for_trace(trace_id, storage_dir=storage) +    plans = load_plans_for_trace(trace_id, storage_dir=storage) + +    if not spans and not plans: +        return dag + +    # ------------------------------------------------------------------ +    # user_intent + orchestrator nodes (from root span) +    # ------------------------------------------------------------------ +    root_span = _find_root_span(spans) +    user_intent_id: str | None = None +    orch_id: str | None = None + +    if root_span is not None: +        meta = root_span.get(\\"metadata\\") or {} +        query = meta.get(\\"query\\") or trace_id +        user_intent_id = f\\"user_intent:{trace_id}\\" +        dag.nodes.append( +            DAGNode( +                id=user_intent_id, +                kind=\\"user_intent\\", +                label=str(query)[:80], +                metadata={\\"trace_id\\": trace_id, \\"query\\": query}, +            ) +        ) + +        orch_id = root_span.get(\\"id\\", \\"\\") +        if orch_id: +            orch_node = DAGNode( +                id=orch_id, +                kind=\\"orchestrator\\", +                label=\\"orchestrate\\", +                metadata={\\"trace_id\\": trace_id, \\"span_id\\": orch_id}, +            ) +            dag.nodes.append(orch_node) +            if user_intent_id: +                dag.edges.append( +                    DAGEdge( +                        src=user_intent_id, +                        dst=orch_id, +                        kind=\\"parent_child\\", +                    ) +                ) +                dag.nodes[-2].children.append(orch_id) + +        # Phase children of orchestrator +        phase_spans = [ +            s for s in spans +            if s.get(\\"span_kind\\") == \\"workflow_node\\" +            and s.get(\\"parent_span_id\\") == orch_id +        ] +        for ps in phase_spans: +            phase_meta = ps.get(\\"metadata\\") or {} +            phase = phase_meta.get(\\"phase\\", \\"unknown\\") +            dag.phases.append({\\"phase\\": phase, \\"span_id\\": ps.get(\\"id\\", \\"\\")}) + +            phase_node = DAGNode( +                id=ps.get(\\"id\\", f\\"phase:{phase}\\"), +                kind=\\"orchestrator\\",  # phase nodes are sub-orchestrator +                label=f\\"phase:{phase}\\", +                metadata=phase_meta, +            ) +            dag.nodes.append(phase_node) +            if orch_id: +                dag.edges.append( +                    DAGEdge(src=orch_id, dst=phase_node.id, kind=\\"parent_child\\") +                ) +                for n in dag.nodes: +                    if n.id == orch_id: +                        n.children.append(phase_node.id) +                        break + +    # ------------------------------------------------------------------ +    # Plan + step nodes +    # ------------------------------------------------------------------ +    for plan in plans: +        plan_node_id = f\\"plan:{plan.plan_id}\\" +        plan_node = DAGNode( +            id=plan_node_id, +            kind=\\"plan\\", +            label=f\\"plan:{plan.plan_id[:8]}\\", +            metadata={ +                \\"plan_id\\": plan.plan_id, +                \\"pattern\\": plan.workflow_pattern.value, +                \\"step_count\\": len(plan.steps), +                \\"trace_id\\": trace_id, +            }, +        ) +        dag.nodes.append(plan_node) +        if orch_id: +            dag.edges.append( +                DAGEdge(src=orch_id, dst=plan_node_id, kind=\\"parent_child\\") +            ) +            for n in dag.nodes: +                if n.id == orch_id: +                    n.children.append(plan_node_id) +                    break + +        # Step nodes +        step_node_ids: list[str] = [] +        for step in plan.steps: +            step_node_id = f\\"step:{step.step_id}\\" +            step_node_ids.append(step_node_id) +            step_node = DAGNode( +                id=step_node_id, +                kind=\\"step\\", +                label=step.skill_id or step.step_id, +                metadata={ +                    \\"step_id\\": step.step_id, +                    \\"skill_id\\": step.skill_id, +                    \\"role\\": step.assigned_role, +                }, +            ) +            dag.nodes.append(step_node) +            dag.edges.append( +                DAGEdge(src=plan_node_id, dst=step_node_id, kind=\\"parent_child\\") +            ) +            plan_node.children.append(step_node_id) + +        # Dependency edges (from step.dependencies) +        for step in plan.steps: +            for dep in step.dependencies or []: +                dag.edges.append( +                    DAGEdge( +                        src=f\\"step:{dep}\\", +                        dst=f\\"step:{step.step_id}\\", +                        kind=\\"dependency\\", +                    ) +                ) + +        # Attach llm/tool spans to steps via task_id == step_id (P0-1) +        for step in plan.steps: +            attached = [ +                s for s in spans +                if s.get(\\"task_id\\") == step.step_id +                and s.get(\\"span_kind\\") in (\\"llm\\", \\"tool\\", \\"tool_call\\") +            ] +            for s in attached: +                span_kind = s.get(\\"span_kind\\") +                node_kind: NodeKind = \\"llm\\" if span_kind == \\"llm\\" else \\"tool\\" +                span_node = DAGNode( +                    id=s.get(\\"id\\", f\\"span:{step.step_id}\\"), +                    kind=node_kind, +                    label=(s.get(\\"name\\") or s.get(\\"id\\", \\"\\"))[:60], +                    metadata={\\"trace_id\\": s.get(\\"trace_id\\", trace_id)}, +                ) +                dag.nodes.append(span_node) +                step_node_id = f\\"step:{step.step_id}\\" +                dag.edges.append( +                    DAGEdge( +                        src=step_node_id, +                        dst=span_node.id, +                        kind=\\"parent_child\\", +                    ) +                ) +                for n in dag.nodes: +                    if n.id == step_node_id: +                        n.children.append(span_node.id) +                        break + +    # ------------------------------------------------------------------ +    # Sub-agent nodes (attached to plans via parent_conversation_id chain) +    # ------------------------------------------------------------------ +    subagent_attachments = _discover_subagents(storage, plans) +    for attach in subagent_attachments: +        sub_node = DAGNode( +            id=f\\"subagent:{attach['conversation_id']}\\", +            kind=\\"sub_agent\\", +            label=attach.get(\\"description\\") +            or attach.get(\\"agent_type\\") +            or \\"sub-agent\\", +            metadata={ +                \\"agent_type\\": attach.get(\\"agent_type\\"), +                \\"parent_conversation_id\\": attach.get(\\"parent_conversation_id\\"), +                \\"plan_id\\": attach.get(\\"plan_id\\"), +                \\"conversation_id\\": attach.get(\\"conversation_id\\"), +            }, +        ) +        dag.nodes.append(sub_node) +        plan_node_id = f\\"plan:{attach['plan_id']}\\" +        dag.edges.append( +            DAGEdge(src=plan_node_id, dst=sub_node.id, kind=\\"parent_child\\") +        ) +        for n in dag.nodes: +            if n.id == plan_node_id: +                n.children.append(sub_node.id) +                break + +    # Iterations = number of plans (reorchestration rounds) +    dag.iterations = len(plans) + +    return dag + + +# --------------------------------------------------------------------------- +# Internal helpers +# --------------------------------------------------------------------------- + + +def _find_root_span(spans: list[dict[str, Any]]) -> dict[str, Any] | None: +    \\"\\"\\"Find the root orchestrate span: prefer the 'orchestrate' task span +    with no parent_span_id. Fall back to any root if name differs.\\"\\"\\" +    roots = [ +        s for s in spans +        if not s.get(\\"parent_span_id\\") +        and s.get(\\"span_kind\\") == \\"task\\" +    ] +    if not roots: +        return None +    named = [s for s in roots if s.get(\\"name\\") == \\"orchestrate\\"] +    return named[0] if named else roots[0] + + +def _discover_subagents( +    storage_dir: Path, +    plans: list[Any], +) -> list[dict[str, Any]]: +    \\"\\"\\"Walk \`\`storage_dir / conversations\`\` for sub-agent conversations. + +    Returns a list of attachment descriptors, each carrying: + +    * \`\`conversation_id\`\`: the sub-agent's conversation id +    * \`\`parent_conversation_id\`\`: the main conversation it was spawned from +    * \`\`plan_id\`\`: the plan id (looked up via parent's \`\`orchestration_id\`\`) +    * \`\`agent_type\`\` / \`\`description\`\`: display metadata + +    Plans not in \`\`plans\`\` are skipped — we only attach to plans visible +    in this trace's rebuild. +    \\"\\"\\" +    plan_ids = {p.plan_id for p in plans} +    conv_dir = storage_dir / \\"conversations\\" +    if not conv_dir.exists(): +        return [] + +    attachments: list[dict[str, Any]] = [] +    try: +        for conv_file in conv_dir.glob(\\"*.json\\"): +            try: +                payload = json.loads(conv_file.read_text()) +            except (json.JSONDecodeError, OSError): +                continue +            meta = payload.get(\\"metadata\\") or {} +            if not meta.get(\\"is_subagent\\"): +                continue +            parent_conv_id = meta.get(\\"parent_conversation_id\\") +            if not parent_conv_id: +                continue + +            plan_id = _lookup_orchestration_id(storage_dir, parent_conv_id) +            if not plan_id or plan_id not in plan_ids: +                continue + +            attachments.append( +                { +                    \\"conversation_id\\": payload.get(\\"conversation_id\\", conv_file.stem), +                    \\"parent_conversation_id\\": parent_conv_id, +                    \\"plan_id\\": plan_id, +                    \\"agent_type\\": meta.get(\\"agent_type\\"), +                    \\"description\\": meta.get(\\"description\\"), +                } +            ) +    except OSError as e: +        logger.warning(\\"Failed to scan conversations in %s: %s\\", conv_dir, e) +    return attachments + + +def _lookup_orchestration_id( +    storage_dir: Path, +    conversation_id: str, +) -> str | None: +    \\"\\"\\"Read \`\`conversations/<conversation_id>.json\`\` and return its +    \`\`metadata.orchestration_id\`\` (the plan_id of the orchestration that +    spawned this conversation or its sub-agents).\\"\\"\\" +    conv_path = storage_dir / \\"conversations\\" / f\\"{conversation_id}.json\\" +    if not conv_path.exists(): +        return None +    try: +        payload = json.loads(conv_path.read_text()) +    except (json.JSONDecodeError, OSError): +        return None +    meta = payload.get(\\"metadata\\") or {} +    orch_id = meta.get(\\"orchestration_id\\") +    return str(orch_id) if orch_id else None diff --git a/tests/core/observability/test_dag_rebuilder.py b/tests/core/observability/test_dag_rebuilder.py index e62588d..40c3555 100644 --- a/tests/core/observability/test_dag_rebuilder.py +++ b/tests/core/observability/test_dag_rebuilder.py @@ -231,3 +231,398 @@ class TestLoadPlansForTraceReExport:            result = load_plans_for_trace(\\"any-trace\\", storage_dir=tmp_path / \\".vibe\\")          assert result == [] + + +# --------------------------------------------------------------------------- +# rebuild_dag() — JOIN plan ↔ span + sub-agent attach (Task 12) +# --------------------------------------------------------------------------- + + +def _write_plan_fixture( +    storage_dir: Path, +    plan_id: str, +    trace_id: str, +    steps: list[dict[str, Any]], +    dependencies: dict[str, list[str]] | None = None, +) -> None: +    \\"\\"\\"Write a single ExecutionPlan line to execution_plans.jsonl.\\"\\"\\" +    import json + +    from vibesop.core.models import ( +        ExecutionMode, +        ExecutionPlan, +        ExecutionStep, +        WorkflowPattern, +    ) + +    plan = ExecutionPlan( +        plan_id=plan_id, +        original_query=f\\"query for {plan_id}\\", +        steps=[ +            ExecutionStep( +                step_id=s[\\"step_id\\"], +                step_number=i + 1, +                skill_id=s.get(\\"skill_id\\", \\"skill-x\\"), +                intent=s.get(\\"intent\\", \\"intent-x\\"), +                dependencies=dependencies.get(s[\\"step_id\\"], []) if dependencies else [], +            ) +            for i, s in enumerate(steps) +        ], +        workflow_pattern=WorkflowPattern.SEQUENTIAL, +        execution_mode=ExecutionMode.SEQUENTIAL, +    ) +    plan.metadata[\\"trace_id\\"] = trace_id +    storage_dir.mkdir(parents=True, exist_ok=True) +    with (storage_dir / \\"execution_plans.jsonl\\").open(\\"a\\") as f: +        f.write(json.dumps(plan.to_dict()) + \\"\\n\\") + + +def _write_span_fixture( +    storage_dir: Path, +    span_id: str, +    trace_id: str, +    *, +    parent_span_id: str | None = None, +    span_kind: str = \\"task\\", +    name: str | None = None, +    task_id: str | None = None, +    metadata: dict[str, Any] | None = None, +) -> None: +    \\"\\"\\"Append one span line to observability/spans.jsonl (matches SpanWriter layout).\\"\\"\\" +    import json + +    span: dict[str, Any] = { +        \\"id\\": span_id, +        \\"trace_id\\": trace_id, +        \\"name\\": name or span_id, +        \\"span_kind\\": span_kind, +    } +    if parent_span_id: +        span[\\"parent_span_id\\"] = parent_span_id +    if task_id: +        span[\\"task_id\\"] = task_id +    if metadata: +        span[\\"metadata\\"] = metadata +    obs_dir = storage_dir / \\"observability\\" +    obs_dir.mkdir(parents=True, exist_ok=True) +    with (obs_dir / \\"spans.jsonl\\").open(\\"a\\") as f: +        f.write(json.dumps(span) + \\"\\n\\") + + +def _write_conversation_fixture( +    storage_dir: Path, +    conversation_id: str, +    *, +    is_subagent: bool = False, +    parent_conversation_id: str | None = None, +    orchestration_id: str | None = None, +    orchestration_trace_id: str | None = None, +    agent_type: str | None = \\"claude-code\\", +    description: str | None = None, +) -> Path: +    \\"\\"\\"Write a conversation JSON file mirroring ConversationContext.save() shape.\\"\\"\\" +    import json + +    conv_dir = storage_dir / \\"conversations\\" +    conv_dir.mkdir(parents=True, exist_ok=True) +    metadata: dict[str, Any] = {} +    if is_subagent: +        metadata[\\"is_subagent\\"] = True +        if parent_conversation_id: +            metadata[\\"parent_conversation_id\\"] = parent_conversation_id +        if agent_type: +            metadata[\\"agent_type\\"] = agent_type +        if description: +            metadata[\\"description\\"] = description +    if orchestration_id is not None: +        metadata[\\"orchestration_id\\"] = orchestration_id +    if orchestration_trace_id is not None: +        metadata[\\"orchestration_trace_id\\"] = orchestration_trace_id + +    payload = { +        \\"conversation_id\\": conversation_id, +        \\"metadata\\": metadata, +        \\"turns\\": [], +    } +    path = conv_dir / f\\"{conversation_id}.json\\" +    path.write_text(json.dumps(payload)) +    return path + + +class TestRebuildDagJoin: +    \\"\\"\\"\`\`rebuild_dag(trace_id, storage_dir)\`\` JOINs plan ↔ spans + attaches +    sub-agents. Phase A Task 12 contract.\\"\\"\\" + +    def test_rebuild_dag_returns_empty_when_no_data(self, tmp_path: Path) -> None: +        from vibesop.core.observability.dag_rebuilder import rebuild_dag + +        dag = rebuild_dag(trace_id=\\"nonexistent\\", storage_dir=tmp_path / \\".vibe\\") +        assert dag.nodes == [] +        assert dag.edges == [] +        assert dag.phases == [] +        assert dag.iterations == 0 + +    def test_rebuild_dag_joins_plan_step_to_llm_span_via_task_id( +        self, tmp_path: Path +    ) -> None: +        \\"\\"\\"Plan with step_id='s1' + llm span with task_id='s1' → step node +        has the llm span as a child. JOIN key is task_id == step_id (NOT +        plan_id — grok+pi P0-1 contract).\\"\\"\\" +        from vibesop.core.observability.dag_rebuilder import rebuild_dag + +        storage = tmp_path / \\".vibe\\" +        _write_plan_fixture( +            storage, +            plan_id=\\"plan-1\\", +            trace_id=\\"T1\\", +            steps=[{\\"step_id\\": \\"s1\\", \\"skill_id\\": \\"skill-a\\"}], +        ) +        _write_span_fixture( +            storage, +            span_id=\\"root\\", +            trace_id=\\"T1\\", +            span_kind=\\"task\\", +            name=\\"orchestrate\\", +            metadata={\\"query\\": \\"test query\\"}, +        ) +        _write_span_fixture( +            storage, +            span_id=\\"llm-1\\", +            trace_id=\\"T1\\", +            parent_span_id=\\"root\\", +            span_kind=\\"llm\\", +            name=\\"classify\\", +            task_id=\\"s1\\", +        ) + +        dag = rebuild_dag(trace_id=\\"T1\\", storage_dir=storage) + +        step_node = next( +            (n for n in dag.nodes if n.id == \\"step:s1\\"), None +        ) +        assert step_node is not None, \\"step node s1 must exist\\" +        assert \\"llm-1\\" in step_node.children, ( +            f\\"llm-1 must be a child of step:s1 (JOIN via task_id), \\" +            f\\"got children={step_node.children}\\" +        ) + +    def test_rebuild_dag_creates_dependency_edges_between_steps( +        self, tmp_path: Path +    ) -> None: +        \\"\\"\\"Steps with \`depends_on\` produce \`\`dependency\`\` kind edges.\\"\\"\\" +        from vibesop.core.observability.dag_rebuilder import rebuild_dag + +        storage = tmp_path / \\".vibe\\" +        _write_plan_fixture( +            storage, +            plan_id=\\"plan-deps\\", +            trace_id=\\"T-deps\\", +            steps=[ +                {\\"step_id\\": \\"s1\\"}, +                {\\"step_id\\": \\"s2\\"}, +                {\\"step_id\\": \\"s3\\"}, +            ], +            dependencies={\\"s2\\": [\\"s1\\"], \\"s3\\": [\\"s1\\", \\"s2\\"]}, +        ) +        _write_span_fixture( +            storage, +            span_id=\\"root\\", +            trace_id=\\"T-deps\\", +            span_kind=\\"task\\", +            name=\\"orchestrate\\", +        ) + +        dag = rebuild_dag(trace_id=\\"T-deps\\", storage_dir=storage) + +        dep_edges = [e for e in dag.edges if e.kind == \\"dependency\\"] +        edge_pairs = {(e.src, e.dst) for e in dep_edges} +        assert (\\"step:s1\\", \\"step:s2\\") in edge_pairs +        assert (\\"step:s1\\", \\"step:s3\\") in edge_pairs +        assert (\\"step:s2\\", \\"step:s3\\") in edge_pairs + +    def test_rebuild_dag_attaches_subagent_to_plan_via_parent_conversation( +        self, tmp_path: Path +    ) -> None: +        \\"\\"\\"Sub-agent conversation with \`\`parent_conversation_id\`\` pointing +        to a main conversation whose \`\`metadata.orchestration_id\`\` matches +        a plan → sub_agent node attached to that plan node. + +        Chain: sub-agent → parent_conversation_id → main conv metadata.orchestration_id → plan_id. +        Phase A MVP attaches at PLAN level (step-level attachment requires +        tool_use_id matching, deferred to Phase B per design).\\"\\"\\" +        from vibesop.core.observability.dag_rebuilder import rebuild_dag + +        storage = tmp_path / \\".vibe\\" +        _write_plan_fixture( +            storage, +            plan_id=\\"plan-sub-test\\", +            trace_id=\\"T-sub\\", +            steps=[{\\"step_id\\": \\"s1\\"}], +        ) +        _write_span_fixture( +            storage, +            span_id=\\"root\\", +            trace_id=\\"T-sub\\", +            span_kind=\\"task\\", +            name=\\"orchestrate\\", +        ) +        _write_conversation_fixture( +            storage, +            conversation_id=\\"main-conv-1\\", +            orchestration_id=\\"plan-sub-test\\", +            orchestration_trace_id=\\"T-sub\\", +        ) +        _write_conversation_fixture( +            storage, +            conversation_id=\\"main-conv-1-sub-agent-abc\\", +            is_subagent=True, +            parent_conversation_id=\\"main-conv-1\\", +            agent_type=\\"claude-code\\", +            description=\\"investigator\\", +        ) + +        dag = rebuild_dag(trace_id=\\"T-sub\\", storage_dir=storage) + +        sub_nodes = [n for n in dag.nodes if n.kind == \\"sub_agent\\"] +        assert len(sub_nodes) == 1 +        sub_node = sub_nodes[0] +        assert sub_node.metadata.get(\\"plan_id\\") == \\"plan-sub-test\\" + +        # plan node has sub_node as child +        plan_node = next( +            (n for n in dag.nodes if n.id == \\"plan:plan-sub-test\\"), None +        ) +        assert plan_node is not None +        assert sub_node.id in plan_node.children, ( +            f\\"sub_agent must be attached to plan node, got children={plan_node.children}\\" +        ) + +    def test_rebuild_dag_user_intent_node_uses_query_from_root_span( +        self, tmp_path: Path +    ) -> None: +        \\"\\"\\"Root 'orchestrate' span metadata.query becomes the user_intent +        node label — preserves the original user request in the map.\\"\\"\\" +        from vibesop.core.observability.dag_rebuilder import rebuild_dag + +        storage = tmp_path / \\".vibe\\" +        _write_span_fixture( +            storage, +            span_id=\\"root\\", +            trace_id=\\"T-intent\\", +            span_kind=\\"task\\", +            name=\\"orchestrate\\", +            metadata={\\"query\\": \\"analyse my code and add tests\\"}, +        ) + +        dag = rebuild_dag(trace_id=\\"T-intent\\", storage_dir=storage) + +        ui_nodes = [n for n in dag.nodes if n.kind == \\"user_intent\\"] +        assert ui_nodes, \\"user_intent node must exist when root span present\\" +        assert \\"analyse my code\\" in ui_nodes[0].label + +    def test_rebuild_dag_emits_orchestrator_and_phase_nodes( +        self, tmp_path: Path +    ) -> None: +        \\"\\"\\"Root 'orchestrate' span becomes orchestrator node; workflow_node +        phase spans become its children. dag.phases carries the phase list.\\"\\"\\" +        from vibesop.core.observability.dag_rebuilder import rebuild_dag + +        storage = tmp_path / \\".vibe\\" +        _write_span_fixture( +            storage, +            span_id=\\"root\\", +            trace_id=\\"T-phase\\", +            span_kind=\\"task\\", +            name=\\"orchestrate\\", +            metadata={\\"query\\": \\"q\\"}, +        ) +        for phase in (\\"routing\\", \\"detection\\", \\"plan_building\\", \\"complete\\"): +            _write_span_fixture( +                storage, +                span_id=f\\"phase-{phase}\\", +                trace_id=\\"T-phase\\", +                parent_span_id=\\"root\\", +                span_kind=\\"workflow_node\\", +                name=f\\"orchestrate:{phase}\\", +                metadata={\\"phase\\": phase}, +            ) + +        dag = rebuild_dag(trace_id=\\"T-phase\\", storage_dir=storage) + +        orch_nodes = [n for n in dag.nodes if n.kind == \\"orchestrator\\"] +        assert orch_nodes, \\"orchestrator node must exist\\" +        orch = orch_nodes[0] +        # phase nodes attached as children +        for phase in (\\"routing\\", \\"detection\\", \\"plan_building\\", \\"complete\\"): +            phase_id = f\\"phase-{phase}\\" +            assert phase_id in orch.children, ( +                f\\"phase {phase} must be child of orchestrator, \\" +                f\\"got children={orch.children}\\" +            ) + +        phase_names = {p[\\"phase\\"] for p in dag.phases} +        assert {\\"routing\\", \\"detection\\", \\"plan_building\\", \\"complete\\"}.issubset( +            phase_names +        ) + +    def test_rebuild_dag_iterations_counts_plans(self, tmp_path: Path) -> None: +        \\"\\"\\"\`\`iterations\`\` field equals number of plans found for the trace — +        reorchestration rounds each create a new plan, so this counts them.\\"\\"\\" +        from vibesop.core.observability.dag_rebuilder import rebuild_dag + +        storage = tmp_path / \\".vibe\\" +        _write_span_fixture( +            storage, +            span_id=\\"root\\", +            trace_id=\\"T-iter\\", +            span_kind=\\"task\\", +            name=\\"orchestrate\\", +        ) +        _write_plan_fixture( +            storage, +            plan_id=\\"plan-iter-1\\", +            trace_id=\\"T-iter\\", +            steps=[{\\"step_id\\": \\"s1\\"}], +        ) +        _write_plan_fixture( +            storage, +            plan_id=\\"plan-iter-2\\", +            trace_id=\\"T-iter\\", +            steps=[{\\"step_id\\": \\"s1\\"}], +        ) + +        dag = rebuild_dag(trace_id=\\"T-iter\\", storage_dir=storage) +        assert dag.iterations == 2 + +    def test_rebuild_dag_load_span_trace_id_filter(self, tmp_path: Path) -> None: +        \\"\\"\\"\`\`load_spans_for_trace\`\` filters by trace_id — spans from other +        traces must NOT leak into the rebuilt DAG.\\"\\"\\" +        from vibesop.core.observability.dag_rebuilder import ( +            load_spans_for_trace, +            rebuild_dag, +        ) + +        storage = tmp_path / \\".vibe\\" +        _write_span_fixture( +            storage, +            span_id=\\"span-A\\", +            trace_id=\\"T-A\\", +            span_kind=\\"task\\", +            name=\\"orchestrate-A\\", +        ) +        _write_span_fixture( +            storage, +            span_id=\\"span-B\\", +            trace_id=\\"T-B\\", +            span_kind=\\"task\\", +            name=\\"orchestrate-B\\", +        ) + +        spans_a = load_spans_for_trace(\\"T-A\\", storage_dir=storage) +        ids_a = {s[\\"id\\"] for s in spans_a} +        assert ids_a == {\\"span-A\\"}, f\\"T-B span leaked into T-A result: {ids_a}\\" + +        dag = rebuild_dag(trace_id=\\"T-A\\", storage_dir=storage) +        node_ids = {n.id for n in dag.nodes} +        assert \\"span-A\\" in node_ids +        assert \\"span-B\\" not in node_ids"'
# Code Review: Phase A Task 12 — `rebuild_dag()`

I've read the full diff. Here's my detailed analysis.

---

## Q1. JOIN correctness — step ↔ span

**Verdict**: BLOCKER

**Evidence** — `dag_rebuilder.py` lines ~345-370 (span attachment loop):

```python
for plan in plans:                          # outer: all plans
    for step in plan.steps:                 # middle: all steps in plan
        attached = [
            s for s in spans                # inner: linear scan O(steps × spans)
            if s.get("task_id") == step.step_id
            ...
        ]
        for s in attached:
            span_node = DAGNode(
                id=s.get("id", f"span:{step.step_id}"),  # <-- same id across plans
                ...
            )
            dag.nodes.append(span_node)     # <-- APPEND, no dedup guard
```

**Three sub-issues:**

### 1a. P0-1 filter correctness — PASS
The filter `s.get("task_id") == step.step_id` matches the P0-1 contract exactly. No `plan_id` leak.

### 1b. Orphan spans — CONCERN
Spans with `task_id` set but no matching step in any plan are **silently dropped**. They never appear in `dag.nodes`. The dashboard won't surface them.

**Fix**: Log a warning when orphan spans are detected:

```python
matched_span_ids = {s["id"] for s in attached_spans}  # tracked
orphans = [s for s in spans if s.get("task_id") and s["id"] not in matched_span_ids
           and s.get("span_kind") in ("llm", "tool", "tool_call")]
for o in orphans:
    logger.debug("Orphan span %s: task_id=%s has no matching step", o["id"], o.get("task_id"))
```

Or attach orphans to the plan node as a fallback bucket so the dashboard can surface them.

### 1c. Reorchestration duplicate span nodes — BLOCKER
**This is a real data-corruption bug.** The test `test_rebuild_dag_iterations_counts_plans` creates two plans both with `step_id="s1"` but **zero spans with `task_id="s1"`**, so the bug is untested.

Reproduction scenario:
1. User calls `orchestrate("fix auth")` → plan-1 created with step `s1`, llm span `llm-1` with `task_id=s1`
2. Reorchestration (loop_until_dry) → plan-2 created, **also** with step `s1`
3. `rebuild_dag()` loads both plans + the same span `llm-1`
4. `llm-1` is appended to `dag.nodes` **twice** as `DAGNode(id="llm-1", ...)` — duplicate node, same `id`

The dashboard renders two nodes with the same id. Worse, `DAG` is a flat `list[DAGNode]` — no uniqueness constraint.

**Fix**: Build a `task_id → [spans]` index once, then attach with a `seen_span_ids: set` guard:

```python
# Build index once (also fixes Q5)
task_spans: dict[str, list[dict]] = {}
for s in spans:
    tid = s.get("task_id")
    if tid and s.get("span_kind") in ("llm", "tool", "tool_call"):
        task_spans.setdefault(tid, []).append(s)

seen_ids: set[str] = set()
for plan in plans:
    for step in plan.steps:
        for s in task_spans.get(step.step_id, []):
            if s["id"] in seen_ids:
                continue
            seen_ids.add(s["id"])
            # ... create node, attach ...
```

This gives each span exactly one node in the DAG and costs O(steps) instead of O(steps × spans).

---

## Q2. JOIN correctness — sub-agent → plan

**Verdict**: CONCERN (one edge case, not blocking)

**Evidence** — `_discover_subagents()` + `_lookup_orchestration_id()`:

```python
def _lookup_orchestration_id(storage_dir, conversation_id):
    conv_path = storage_dir / "conversations" / f"{conversation_id}.json"
    if not conv_path.exists():
        return None                                # 2a. guarded ✓
    meta = payload.get("metadata") or {}
    orch_id = meta.get("orchestration_id")          # 2b. reads only parent ✓
    return str(orch_id) if orch_id else None
```

### 2a. Missing main conversation file — PASS
Returns `None`, attachment skipped. No crash.

### 2b. Denormalized orchestration_id in sub-agent metadata — PASS
Code ignores sub-agent's own `orchestration_id` and reads only from parent. This is correct per the spec (parent IS the source of truth for the orchestration link).

### 2c. Plan-level vs step-level — CONCERN
MVP attaches at plan-level only. The commit message and design doc explicitly scope this: *"step-level requires tool_use_id matching, deferred to Phase B."*

The risk is that a sub-agent spawned to work on **step s3** gets displayed as a child of the **plan** node, not the step node. The dashboard user can't tell which step triggered the sub-agent. For Phase A MVP this is **acceptable**, but it should be tracked as a Phase B item.

**Recommendation**: Not a blocker. Add a `TODO(Phase B): tool_use_id matching for step-level sub-agent attachment` comment near the attachment code.

---

## Q3. `iterations` semantics

**Verdict**: CONCERN

**Evidence**: `dag.iterations = len(plans)` (line ~384)

### 3a. Two orchestrate() calls with same trace_id — CONCERN
If this happens (shouldn't per design), `iterations` would double-count. But this is a design invariant violation, not a code bug.

### 3b. Reorchestration metric correctness — PASS
Each reorchestration round creates a new plan with a new `plan_id`. `len(plans)` correctly counts the number of orchestration rounds. This is the right metric for MVP.

### 3c. Dashboard user expectation — CONCERN
If the user sees `iterations=3`, they likely expect "3 orchestration rounds." `len(plans)` delivers that. But there's a subtlety: if a plan was created but had zero steps (empty plan), it still counts as an iteration. Is a zero-step reorchestration round meaningful to show?

**Fix**: Document the semantics clearly — `iterations` = number of distinct `ExecutionPlan` objects found. Consider filtering out zero-step plans if they shouldn't count:

```python
dag.iterations = sum(1 for p in plans if p.steps)
```

---

## Q4. Empty / partial data resilience

**Verdict**: PASS

### 4a. Spans exist, no plans (orchestrator crashed before plan_building) — PASS
The code returns a DAG with `user_intent` + `orchestrator` + phases. No plan/step nodes. This is the correct behavior — the dashboard shows what happened before the crash.

### 4b. Plans exist, no spans (tracing disabled, plan persisted) — PASS
`root_span` is `None`, so no orchestrator/user_intent/phase nodes. But plan/step nodes are still created (the `if orch_id:` guards prevent edges to missing orch). The dashboard shows plans without trace context.

The commit message explicitly calls this out: *"Map MVP allows step nodes with no llm children when work was done in an external agent."* This is useful — the dashboard can show the plan structure even without spans. **Not an error.**

### 4c. Conversations dir missing — PASS
`_discover_subagents` returns `[]`, no error. All callers handle empty list correctly.

---

## Q5. Performance + scalability

**Verdict**: BLOCKER

**Evidence** — the triple-nested loop:

```python
for plan in plans:                          # P plans
    for step in plan.steps:                 # S steps per plan
        attached = [s for s in spans        # M spans — full scan each time
                    if s.get("task_id") == step.step_id ...]
```

Complexity: **O(P × S × M)**. For 500 plans × 5 steps × 10,000 spans = **25,000,000 string comparisons** on every page load. With JSON parsing of all span lines on each `load_spans_for_trace()` call (already O(M)), this easily exceeds 200ms.

Plus `_discover_subagents` does `glob("*.json")` + reads every file. For 100 conversations, that's 100 file reads + JSON parses on every dashboard refresh.

**Cheapest fix** — two changes:

1. **Build a `task_id → spans` index once** (also fixes Q1c):

```python
task_id_index: dict[str, list[dict]] = {}
for s in spans:
    tid = s.get("task_id")
    if tid:
        task_id_index.setdefault(tid, []).append(s)
# Then lookup is O(1):
attached = task_id_index.get(step.step_id, [])
```

This drops step↔span JOIN from O(P × S × M) to **O(M + P × S)**.

2. **Build a `conversation_id → orchestration_id` index** instead of reading each file on demand:

```python
conv_orch_index: dict[str, str | None] = {}
for conv_file in conv_dir.glob("*.json"):
    payload = json.loads(conv_file.read_text())
    cid = payload.get("conversation_id", conv_file.stem)
    orch_id = (payload.get("metadata") or {}).get("orchestration_id")
    conv_orch_index[cid] = str(orch_id) if orch_id else None
```

Then `_lookup_orchestration_id` becomes a dict lookup. This costs O(C) one-time instead of O(subagents) file reads.

---

## Overall Verdict

### **FIX-THEN-SHIP**

Two blockers (Q1c + Q5) with a single shared fix. Three concerns that should be addressed but aren't ship-gating.

### Top 3 Risks (ranked by severity)

| # | Risk | Severity | Fix complexity |
|---|------|----------|----------------|
| **1** | **Duplicate span nodes from reorchestration** (Q1c) — spans attach to every matching step across all plans, creating duplicate `DAGNode`s with identical `id` values. Dashboard renders corrupted DAG. | BLOCKER | Low — add `task_id → spans` index + `seen_ids` set |
| **2** | **O(P×S×M) JOIN degrades to seconds on moderate data** (Q5) — 10k spans × 2.5k steps = 25M comparisons per page load. Dashboard becomes unusable for active projects. | BLOCKER | Low — same index fix as #1 |
| **3** | **Orphan spans silently dropped** (Q1b) — spans with `task_id` but no matching step vanish from the DAG. Users can't see work that was done but not attributed. | CONCERN | Low — log warning or attach to plan as fallback bucket |

### Additional concerns (non-blocking)

| # | Issue | Fix |
|---|-------|-----|
| Q2c | Sub-agent attached at plan-level, not step-level | Tracked for Phase B; add TODO comment |
| Q3 | `iterations` counts zero-step plans | Filter `p.steps` or document semantics |
| Q4b | Plans without spans produce isolated nodes | Design intent; no fix needed |
| Q5b | `_discover_subagents` reads all conv files on each call | Build `conv_id → orch_id` index once |

### Recommended fix (single edit, resolves Q1c + Q5 simultaneously)

Replace the step↔span attach block with:

```python
# Build task_id → spans index once
_task_spans: dict[str, list[dict]] = {}
for s in spans:
    tid = s.get("task_id")
    if tid and s.get("span_kind") in ("llm", "tool", "tool_call"):
        _task_spans.setdefault(tid, []).append(s)

_seen_span_ids: set[str] = set()

for plan in plans:
    # ... plan + step node creation ...
    for step in plan.steps:
        for s in _task_spans.get(step.step_id, []):
            if s["id"] in _seen_span_ids:
                continue
            _seen_span_ids.add(s["id"])
            # ... create DAGNode, attach ...
```

And add a regression test: two plans sharing step_id + one span with that task_id → exactly 1 span node in DAG.
