# Dashboard v3 Phase A Plan — PI Review

**Date:** 2026-07-27
**Reviewer:** PI (coding agent)
**Reviewed:** `docs/plans/2026-07-27-dashboard-v3-phase-a-data-instrumentation.md` (13 tasks)
**Against:** `docs/decisions/2026-07-27-dashboard-v3-orchestration-map-and-reflection.md` (design doc §3, §6)
**Evidence:** `src/vibesop/core/observability/tracer.py`, `src/vibesop/core/routing/orchestrator.py`, `src/vibesop/core/orchestration/plan_tracker.py`, `src/vibesop/core/conversation_import.py`, `src/vibesop/adapters/templates/claude-code/hooks/vibesop-mirror-session-end.sh.j2`

---

## Verdict: **CONDITIONAL** — 6 mandatory fixes before entering Task 1

---

## Axis 1: Spec fidelity (does the plan faithfully implement the design doc?)

### Finding S1 — Task 4 fallback `task_id=plan_id` contradicts DAG design (CRITICAL)

**Design doc §3.3 DAG algorithm step 3:**

> ```python
> step.spans = [s for s in spans if s.task_id == step.step_id]
> ```

The plan's R1 fallback: "if step-level binding isn't reachable, bind `task_id=plan_id`."

**Evidence from codebase:** `ExecutionStep` already has `step_id` / `assigned_role` / `dependencies` / `parallel_group` fully populated (`models.py:321-397`, confirmed by Explore agent). The orchestrator iterates `plan.steps` in the plan_building phase.

**What breaks:** If all spans get `task_id=plan_id`, the DAG rebuilder attaches every span to the plan node. Every step node becomes an empty shell — no children, no evidence of execution. The Map view shows a flat tree with step hexagons that have nothing underneath. The metric "task_id fill rate 0% → 100%" is technically true and semantically worthless. **This is the prototype of "tests pass, production broken."**

**Fix required (F1):** Remove the fallback. Commit to step-level binding. If `PlanBuilder.build_plan()` doesn't expose step iteration at the orchestrator level, refactor it in Task 4.3. Step-level binding is non-negotiable for the DAG to be meaningful.

### Finding S2 — Mirror hook template doesn't import sub-agents (CRITICAL)

**Design doc §3.1 target:** `mirror-*.json.metadata.parent_session` fill rate 100%.

**Plan Task 6:** "Hook `import_subagent` into mirror_session_end."

**Evidence from codebase:** The hook template (`vibesop-mirror-session-end.sh.j2`) calls:

```bash
vibe conversation import-claude --source "$_JSONL" --conversation-id "$_CONV_ID" --storage-dir "$_STORAGE_DIR"
```

No `--include-subagents` flag. The CLI command supports it (`conversation_cmd.py:135-137`), but the hook never passes it. Sub-agent import from the automated mirror path is **0% in production**. The only path is manual `vibe conversation import-claude --include-subagents` from the CLI.

**What breaks:** The hook "works" (conversation is mirrored, exits 0) but `parent_session` stays empty for all sub-agents. DAG rebuilder step 4 (attach sub-agent conversations via `parent_session`) gets nothing to attach. Sub-agent nodes in the Map view are absent.

**Fix required (F2):** Add `--include-subagents` to the hook template. Add a test verifying that SessionEnd hook triggers sub-agent import (not just idempotency).

### Finding S3 — ExecutionPlan persistence gap (CRITICAL)

**Design doc §3.3 DAG algorithm step 1:**

> ```python
> plans = load_plans_for_trace(trace_id)
> ```

**Plan R3:** "`execution_plans.jsonl` may not exist." Plan proposes Task 11.5 as a "check if."

**Evidence from codebase:** `PlanTracker` (`plan_tracker.py`) is fully implemented — writes full `ExecutionPlan.to_dict()` (all steps, dependencies, parallel_group preserved) to `.vibe/execution_plans.jsonl`. But `Orchestrator.orchestrate()` never calls it. `_record_plan_sequence` at `orchestrator.py:335` routes to `instinct_learner.record_sequence()` — telemetry only, no ExecutionPlan structure written.

**What breaks:** Without `execution_plans.jsonl`, `load_plans_for_trace()` returns empty. The DAG rebuild produces:

```
user_intent → orchestrator → (50 orphan spans) → output
```

No step nodes, no dependency edges. **Map view dependency edges literally cannot be rendered.** This is the same class of bug as v2's "Work Task 实体未定义" — a missing persistence contract.

**Fix required (F3):** Task 11.5 is mandatory, not conditional. Wire `Orchestrator.orchestrate()` → `PlanTracker.create_plan(plan)` in the completion phase. Store `trace_id` in plan metadata for the DAG JOIN.

### Finding S4 — ReflectionStore pulled forward from Phase D without justification

**Design doc §6 route map:** Reflection is Phase D (2–3 days, parallel with Library).

**Plan:** Adds ReflectionStore (Task 7–9) and AgentPrefs (Task 10) in Phase A. No justification provided for the scope expansion.

**Impact:** +4 task commits, ~1 extra day. New schemas (`reflections.jsonl`, `agent-prefs.json`) that Phase B/C don't consume. Risk of schema churn when Phase D design evolves. The brief's hypothesis ("Phase B dashboard needs reflection badges") doesn't hold — Phase B's v2 §7 P0 doesn't require reflection display.

**Fix required (F5):** Move Task 7–10 to Phase D. Phase A ships: 5 field fixes + PlanTracker wiring + DAG rebuilder + fixture-based E2E. 9 tasks, matching the design doc's 2–3 day scope.

---

## Axis 2: Hidden assumptions (places where "tests pass" ≠ "production works")

### Finding H1 — E2E test uses live LLM calls (COST + FLAKINESS)

**Plan Task 13:** `orchestrator.orchestrate("complex query")` triggers `ClassifierAgent.classify()`, `MultiIntentDetector`, `TaskDecomposer` — all LLM calls.

**Evidence from codebase:** Existing `test_orchestrate.py` avoids LLM by using short/disabled queries. No mock-LLM pattern exists in the orchestrator test suite.

**What breaks:** Real LLM in CI costs $0.05–0.20 per run, non-deterministic (flaky), and slow (10–30s). But the E2E is testing the **data pipeline** (span → task_id → DAG), not LLM routing quality.

**Fix required (F4):** Task 13 must use pre-constructed test fixtures:
- Pre-built `ExecutionPlan` with step_ids
- Pre-written `spans.jsonl` with `task_id=step_id` populated
- Pre-written mirror files with `parent_session` set
- Then verify `rebuild_dag()` returns the expected DAG structure

This tests the actual new code (the pipeline) without depending on LLM at all.

### Finding H2 — contextvars doesn't cross process boundaries

**Plan Task 1:** `contextvars.ContextVar` for `bind_task_context`.

**Evidence from codebase:** `tracer.py:88–93` already documents: "do NOT propagate the calling context — workers get a fresh default context." Claude Code sub-agents are separate OS processes. `contextvars` is in-process only.

**What breaks:** If anyone assumes `bind_task_context` propagates task_id to sub-agent spans, they'll discover at Phase C that sub-agent LLM spans have no task_id. The spans from the sub-agent's *own* conversation won't be attributed via contextvars.

**The architecture is correct** — cross-process attribution happens via an entirely different path: Task 6's mirror hook → `import_subagent` with `parent_session` metadata → DAG rebuilder joins sub-agent conversations to steps via `parent_session`, not via `Span.task_id`. But the plan never calls this out.

**Fix required (F6):** Document the two-path model explicitly in both the plan and `tracer.py`:
1. **In-process** (Orchestrator's own LLM): `bind_task_context` via contextvars
2. **Cross-process** (sub-agent execution): mirror hook metadata (`parent_session` → `import_subagent` → DAG join)

### Finding H3 — Idempotency concern is misdirected; real gap is 0% hook coverage

**Plan concern (Q2):** "Repeated import_subagent might duplicate."

**Evidence from codebase:** `import_subagent` already uses `_append_dedup_turns` with content-hash dedup. `derive_subagent_conversation_id` produces stable IDs from `parent_conv_id + agent_id`. Re-running produces `new_count == 0`. Idempotency is handled.

**The real gap** is Finding S2 above: the hook template doesn't call `--include-subagents` at all. The plan should test "hook triggers import" not "import is idempotent."

---

## Summary

| # | Finding | Severity | Fix |
|---|---------|----------|-----|
| S1 | Task 4 `task_id=plan_id` fallback breaks DAG semantics | CRITICAL | Remove fallback; mandate step-level binding |
| S2 | Mirror hook template missing `--include-subagents` | CRITICAL | Add flag to hook template |
| S3 | Orchestrator never calls PlanTracker; `execution_plans.jsonl` stays empty | CRITICAL | Wire PlanTracker.create_plan() in completion phase |
| S4 | ReflectionStore pulled forward from Phase D to Phase A | MEDIUM | Defer to Phase D |
| H1 | E2E test depends on live LLM calls | MEDIUM | Use pre-constructed fixtures |
| H2 | contextvars limitation not documented | LOW | Document two-path attribution model |

**3 findings produce "metrics green, production broken":**
1. **F1/S1**: `task_id` fill rate hits 100% but all spans point to plan, step nodes are empty
2. **F2/S2**: Mirror hook exits 0 (success) but `parent_session` stays 0%
3. **F3/S3**: DAG rebuilder runs without error but produces flat tree, no dependency edges

**Worst single issue:** F1 — the `task_id=plan_id` fallback produces a DAG where every span points to the plan node and all step nodes are empty. The Map view's core value proposition (showing which step produced which work) is destroyed. The metric would show "task_id: 100% filled" while the production dashboard is non-functional.

**Overall:** Plan architecture is sound. Self-admitted risks (R1, R2, R3) are all underestimated — each needs mandatory action, not conditional "check if." Apply 6 fixes → SHIP.
