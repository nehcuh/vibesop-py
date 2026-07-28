I'll review Task 12's `rebuild_dag` JOIN logic against the five questions. First I'll route the request and load the full source and test diffs.Routing suggested implement/review squads, but this is a focused design review of shipped code — I'll answer Q1–Q5 from the source and related contracts.**Routing note:** `vibe route` suggested implementer/reviewer squads. This is a pure design/code review of already-shipped Task 12, so I answered Q1–Q5 from source + design plan + a reproduction instead of re-implementing.

---

# Task 12 Review: `rebuild_dag()` JOIN correctness

**Evidence base:** `src/vibesop/core/observability/dag_rebuilder.py`, `tests/core/observability/test_dag_rebuilder.py`, design plan Task 12, `ExecutionPlan.reorchestration_history`, and a live multi-plan collision repro.

---

## Q1. JOIN correctness — step ↔ span

**Verdict: CONCERN** (filter correct; multi-plan identity is wrong)

**Evidence**

```402:430:src/vibesop/core/observability/dag_rebuilder.py
        # Attach llm/tool spans to steps via task_id == step_id (P0-1)
        for step in plan.steps:
            attached = [
                s for s in spans
                if s.get("task_id") == step.step_id
                and s.get("span_kind") in ("llm", "tool", "tool_call")
            ]
            ...
                step_node_id = f"step:{step.step_id}"
                ...
                for n in dag.nodes:
                    if n.id == step_node_id:
                        n.children.append(span_node.id)
                        break
```

Step node identity is also unscoped:

```372:374:src/vibesop/core/observability/dag_rebuilder.py
        for step in plan.steps:
            step_node_id = f"step:{step.step_id}"
```

**Findings**

| Sub-question | Result |
|---|---|
| `s.get("task_id") == step.step_id` | **Correct** for P0-1. SpanWriter puts `task_id` top-level (`Span.to_dict`), not only in metadata. Matches design: never join via `plan_id`. |
| Orphan spans (`task_id` set, no matching step) | **Silently dropped.** No orphan bucket, no attach to plan/orchestrator. Acceptable for MVP if documented; map can under-count work. |
| Multi-plan shared `step_id` | **Real bug.** Repro with 2 plans both using `s1` + one llm span: **duplicate node ids** (`step:s1`×2, `llm-1`×2), children only on the **first** step node, second step empty. False positive: same span claimed by every plan that shares the id. |

Production step_ids are `uuid[:8]` (`plan_builder.py`), so collision probability is low **within normal single-plan traces**. Your own `test_rebuild_dag_iterations_counts_plans` uses `s1` twice and would already emit a corrupted multi-plan graph if it asserted graph shape.

**Fix**

1. Namespace step (and dependency) ids by plan:
   - `step_node_id = f"step:{plan.plan_id}:{step.step_id}"`
   - dependency edges: `src=f"step:{plan.plan_id}:{dep}"` (deps are always intra-plan)
2. Index spans once: `by_task: dict[str, list] = groupby(task_id)`
3. On multi-plan traces, attach a span to **at most one** step (prefer plan whose steps contain that `task_id` and, if ambiguous, latest plan by persistence order) — or document “UUID step_ids assumed unique across plans under a trace”
4. Optional: collect orphans under `orchestrator` or `plan` with `kind` metadata for dashboard “unattributed work”

---

## Q2. JOIN correctness — sub-agent → plan

**Verdict: PASS** (with documented MVP gap)

**Evidence**

```520:522:src/vibesop/core/observability/dag_rebuilder.py
            plan_id = _lookup_orchestration_id(storage_dir, parent_conv_id)
            if not plan_id or plan_id not in plan_ids:
                continue
```

```545:554:src/vibesop/core/observability/dag_rebuilder.py
    conv_path = storage_dir / "conversations" / f"{conversation_id}.json"
    if not conv_path.exists():
        return None
    ...
    orch_id = meta.get("orchestration_id")
    return str(orch_id) if orch_id else None
```

**Findings**

| Sub-question | Result |
|---|---|
| Missing main conversation file | **Resilient.** `_lookup_orchestration_id` → `None` → skip. Sub-agent silently omitted, no crash. Correct for dashboard. |
| Sub-agent’s own `orchestration_id` ignored | **Correct for the canonical chain.** Parent is the source of truth for which orchestration spawned the session. Optional denormalized fallback is a nice-to-have, not required for Phase A. |
| Plan-level vs step-level | **Acceptable MVP, not a blocker.** Design Task 12 text said “attach to corresponding step”; commit + plan §Map MVP defer step-level to Phase B (`tool_use_id` cross-process). Plan-level still satisfies “sub_agent edges exist on the map.” |

**Fix (non-blocking)**

- Fallback: if parent missing, try `meta.get("orchestration_id")` on the sub-agent itself when present and ∈ `plan_ids`
- Log at debug when a sub-agent is skipped (missing parent / plan not in trace) so Task 13 E2E can diagnose JOIN miss

---

## Q3. `iterations` semantics

**Verdict: CONCERN** (metric does not match real reorchestration)

**Evidence**

```460:461:src/vibesop/core/observability/dag_rebuilder.py
    # Iterations = number of plans (reorchestration rounds)
    dag.iterations = len(plans)
```

Reorchestration mutates **the same plan** and stores history on it:

```411:420:src/vibesop/core/orchestration/workflow_engine.py
        plan.reorchestration_history = history
        ...
            reorchestration_rounds=round_count,
```

`load_plans_for_trace` **dedupes by `plan_id`** (latest wins) — so one `orchestrate()` + N reorch rounds still yields **`len(plans) == 1`**.

**Findings**

| Scenario | Current `iterations` | User expectation |
|---|---|---|
| One orchestrate, 3 reorch rounds (same `plan_id`) | **1** | Usually **3** or **4** (“how many times did the loop rework?”) |
| Two plans under same `trace_id` (rare / mis-use) | 2 | Ambiguous — two runs vs two rounds |
| Docstring claim “reorchestration creates new plans” | **False** for current engine | Misleading |

**Fix**

Prefer something like:

```python
# Prefer reorchestration history; fall back to plan count for multi-plan traces
if plans:
    rounds = max(
        (len(getattr(p, "reorchestration_history", None) or []) for p in plans),
        default=0,
    )
    dag.iterations = max(len(plans), rounds + 1 if rounds else len(plans))
else:
    dag.iterations = 0
```

Or more cleanly document dashboard meaning as **“plans under this trace”** and rename the field/UI label to `plan_count`, while exposing `reorchestration_rounds` separately from `ExecutionPlan.reorchestration_history` / workflow state.

Until that is fixed, `iterations=3` on the map **does not** mean “3 reorchestration rounds.”

---

## Q4. Empty / partial data resilience

**Verdict: PASS**

**Evidence**

```275:276:src/vibesop/core/observability/dag_rebuilder.py
    if not spans and not plans:
        return dag
```

Root/phase nodes only if `_find_root_span` succeeds; plans/steps always if plans load; sub-agents:

```502:504:src/vibesop/core/observability/dag_rebuilder.py
    if not conv_dir.exists():
        return []
```

| Scenario | Behavior | Assessment |
|---|---|---|
| Spans, no plans (crash before plan_building) | user_intent + orchestrator + phases only | Correct — shows how far the pipeline got |
| Plans, no spans (tracing off / Task 10 polish) | plans + steps + sub_agents, no orchestrator/llm | **Useful, not an error.** Map still shows structure. Matches MVP “step with no llm children is OK” |
| Conversations dir missing | `[]`, no error | Correct |

No change required for Phase A. Optional later: `dag.metadata.completeness` flags (`has_spans`, `has_plans`, `has_subagents`) for UI badges.

---

## Q5. Performance + scalability

**Verdict: CONCERN** (fine for MVP sizes; not fine forever on full-file scan)

**Evidence**

- Full scan of `execution_plans.jsonl` + `spans.jsonl` per request
- Nested filter `O(steps × spans)` per plan
- `_discover_subagents`: `glob("*.json")` + full read each file + parent lookup (2nd read)

**Rough math (10k spans, 500 plan lines, 100 convs, ~20 steps in matching plans)**

| Work | Order | Wall-clock (SSD, CPython) |
|---|---|---|
| Parse 10k JSONL span lines | O(M) | ~20–80 ms |
| Parse 500 plan lines | O(N) | ~1–5 ms |
| Step×span scan (20×10k) | O(S·M) | ~1–5 ms (filter cheap) |
| 100 conversation JSON reads | O(C) | ~5–20 ms |
| **Total** | | **~30–110 ms** typical; can exceed 200 ms on cold disk / multi-MB files |

So: **acceptable today for modest `.vibe` dirs**; not a hard BLOCKER. Will fail &lt;200 ms once projects accumulate months of spans without pruning.

**Cheapest fixes (in order)**

1. **One-pass index in `rebuild_dag`:**
   ```python
   spans_by_task: dict[str, list[dict]] = {}
   for s in spans:
       tid = s.get("task_id")
       if tid and s.get("span_kind") in (...):
           spans_by_task.setdefault(tid, []).append(s)
   ```
   → attach is O(steps) lookups
2. **Parent orchestration cache** in `_discover_subagents` (don’t re-read the same main conv per sub-agent)
3. **Later (Phase B):** side index `observability/by_trace/{trace_id}.jsonl` or sqlite — only if page load budgets fail under real data

Do **not** micro-optimize the nested list comp alone; the full-file scan dominates.

---

## Overall verdict: **FIX-THEN-SHIP**

Ship is close — P0-1 JOIN key is right, empty-path resilience is good, tests cover the happy path. Two issues should be fixed (or explicitly accepted with UI/docs) before calling Phase A “map-ready”:

### Top 3 risks (by severity)

1. **`iterations = len(plans)` is the wrong metric for reorchestration** (CONCERN → product-facing)  
   Real loop_until_dry keeps one `plan_id` and fills `reorchestration_history`. Dashboard will show `iterations=1` for multi-round runs. Users will mistrust the map.

2. **Step node ids are not plan-scoped** (`step:{step_id}` only) (CONCERN → graph integrity)  
   Multi-plan traces (or any shared step_id) produce duplicate node ids, double-emitted llm nodes, and first-match-only `children` updates. Reproduced under your iterations fixture shape.

3. **Orphan / multi-plan span attribution is silent** (CONCERN → observability fidelity)  
   Spans with unmatched `task_id` disappear; spans matching a reused step_id attach to every plan. No diagnostics for Task 13 “JOIN failed” debugging.

### Suggested pre-ship checklist

| # | Change | Effort |
|---|---|---|
| 1 | `step:{plan_id}:{step_id}` + plan-scoped dependency edges | Small |
| 2 | Derive `iterations` from `reorchestration_history` (or rename UI to plan count) | Small |
| 3 | Index spans by `task_id` once; cache parent orchestration lookups | Small |
| 4 | Test: multi-plan same step_id → unique node ids, span attached once | Small |
| 5 | Test: one plan with `reorchestration_history` length 2 → `iterations` matches product meaning | Small |

**Not blockers for Phase A ship after the above (or explicit “known limitations”):** plan-level sub-agent attach, missing-conversations soft fail, plans-without-spans partial DAG, full JSONL scan at current data sizes.

---

**Calibration:**  
- Multi-plan duplicate ids: **[executed]** (repro script)  
- Reorchestration same `plan_id`: **[inspected]** (`workflow_engine.py` + `load_plans_for_trace` dedupe)  
- P0-1 filter correctness: **[inspected]** (code + Span model)  
- Perf numbers: **[assumed]** order-of-magnitude, not timed on your machine
