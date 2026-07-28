Usage: vibe route [OPTIONS] {query}
Try 'vibe route --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Got unexpected extra argument(s) (multi-intent query\ → verify               │
│ .vibe/execution_plans.jsonl has new plan with trace_id; spans.jsonl has llm  │
│ spans with task_id matching step.step_id; rebuild_dag returns DAG with ≥1    │
│ user_intent + ≥1 orchestrator + ≥2 step + dependency edges + sub_agent       │
│ attachment. **This is the main gate.** Fill rate is informational only.  We  │
│ have NOT run this yet — only the zero-LLM fixture E2E. Is it acceptable to   │
│ declare Phase A done without the real-data smoke, given:   - The fixture E2E │
│ exercises the same JOIN logic with realistic shape   - Real LLM calls cost   │
│ $0.05–0.20/run + are flaky   - The orchestrator integration is unit-tested   │
│ (Task 10 contract test verifies `plan.metadata[\trace_id\]` is set after     │
│ `orchestrate()`)  Or should the user be told \Phase A is code-complete       │
│ pending real-data smoke\ before they ship?  **Q5. Phase B readiness          │
│ handoff.** Phase B will add HTTP endpoints                                   │
│ `/api/orchestration/dag?trace_id=<id>` and `/api/reflections`. Given the DAG │
│ data structure + rebuild_dag API surface shipped today, is anything          │
│ obviously missing that Phase B will need? For example:   - Sorting           │
│ guarantees (are `dag.nodes` / `dag.edges` in stable order for caching?)   -  │
│ Pagination / streaming for large DAGs   - Error reporting when trace_id not  │
│ found (currently returns empty DAG — should it raise?)   - Caching layer     │
│ (currently full JSONL scan per request — Q5 from Task 12 review)  ## Output  │
│ format  For each question Q1-Q5: - **Verdict**: SHIP / FIX-THEN-SHIP / BLOCK │
│ - **Evidence**: file/test/line ref - **Fix (if not SHIP)**: concrete change  │
│ End with: **Overall verdict** (PHASE A DONE / PHASE A DONE-PENDING-SMOKE /   │
│ BLOCK) and **top 3 risks** ranked by severity.  ## Source files for          │
│ reference  - `src/vibesop/core/observability/dag_rebuilder.py` — 635 lines - │
│ `tests/core/observability/test_dag_rebuilder.py` — 758 lines, 26 tests -     │
│ `tests/core/observability/test_dag_rebuilder_e2e.py` — 462 lines, 4 tests -  │
│ `src/vibesop/core/orchestration/plan_tracker.py` — added                     │
│ `load_plans_for_trace` - `src/vibesop/core/routing/orchestrator.py` — wires  │
│ PlanTracker.create_plan with trace_id -                                      │
│ `tests/core/orchestration/test_plan_tracker_trace_contract.py` — 11 contract │
│ tests)                                                                       │
╰──────────────────────────────────────────────────────────────────────────────╯
Now I have all the evidence I need. Here's the full review:

---

## Phase A Closeout Review — Dashboard v3 Data Instrumentation

---

### Q1. JOIN contract — `task_id == step_id` (P0-1)

**Verdict: SHIP**

The contract is tight and the E2E test proves it end-to-end.

If you changed `task_id="s1"` to `task_id="plan-e2e"` in the fixture, the test **would fail** at `test_dag_rebuilder_e2e.py:162-168`:

```python
assert f"span-llm-{step_id}" in step_node.children, (
    f"llm span for {step_id} not attached to step "
    f"(JOIN via task_id == step_id), children={step_node.children}"
)
```

The JOIN path: `dag_rebuilder.py:328-333` uses `spans_by_task.get(step.step_id, [])` — no plan_id fallback exists. A mismatched `task_id` would produce orphans, logged at `dag_rebuilder.py:349-355` as `vibesop.orphan_span`.

The contract is **defensive on both sides**:

| Layer | Mechanism | Evidence |
|-------|-----------|---------|
| Emit | `bind_task_context(step.step_id, ...)` wraps per-step LLM calls | `orchestrator.py:422-424` |
| JOIN | `spans_by_task.get(step.step_id, [])` matches exactly | `dag_rebuilder.py:328` |
| Dedup | `matched_span_ids` set — each span attaches to ≤1 step | `dag_rebuilder.py:320, 335-338` |
| Detect | `vibesop.orphan_span` debug log for unmatched task_ids | `dag_rebuilder.py:349-355` |
| Verify | E2E fixture asserts `f"span-llm-{step_id}" in step_node.children` | `test_dag_rebuilder_e2e.py:162-168` |

The dashboard will never show orphan work silently — unmatched spans are logged and the `matched_span_ids` dedup prevents double-attachment across plans sharing step_ids.

---

### Q2. Multi-plan + reorchestration semantics

**Verdict: SHIP**

Both regression tests exercise their respective paths concretely:

**Plan-scoped step ids** (`test_dag_rebuilder.py:543-589`):
- Two plans (plan-A, plan-B) share step_id `"s1"`
- Pre-fix: both got node id `step:s1` → duplicate id collision
- Post-fix: `step:plan-A:s1` and `step:plan-B:s1` — distinct
- Removing the fix (plan-scoped prefix) **would** break the test at line 578: `assert len(node_ids) == len(set(node_ids))` catches duplicates

**Iterations from `reorchestration_history`** (`test_dag_rebuilder.py:510-542`):
- 1 plan with 2 history entries → 3 iterations
- Pre-fix: `len(plans)=1` → iterations=1 (under-counting)
- Post-fix: `_derive_iterations` returns `max(len(plans), max_rounds + 1) = 3`
- Removing the fix **would** break at line 540: `assert dag.iterations == 3`

**Edge case: two orchestrate() calls sharing a trace_id.** This is a pathological scenario (trace_ids are UUIDs, never intentionally shared). The fallback `max(len(plans), max_rounds + 1)` handles it reasonably: if trace_id leaks across two independent `orchestrate()` calls AND one loop_until_dry plan exists, iterations might be slightly off (`max(2, 3)=3` vs actual 4 calls). But this is NOT a real production path — the dashboard shouldn't be designed around accidental trace_id reuse. The `_derive_iterations` docstring at `dag_rebuilder.py:480` explicitly documents the rule. **No fix needed.**

---

### Q3. Sub-agent attachment MVP

**Verdict: SHIP**

**Acceptable for Phase A.** The design plan §Out of scope explicitly deferred step-level attachment to Phase B. Current MVP attaches sub-agents at the PLAN level — sufficient to show the dashboard "this plan spawned sub-agents."

**E2E test asserts the right thing** (`test_dag_rebuilder_e2e.py:234-249`):
```python
assert sub.metadata.get("plan_id") == "plan-e2e"
assert sub.id in plan_node.children
```
It does NOT assert `sub.id in step_node.children` — correctly matching the MVP contract.

**TODO is documented clearly:**
- Code: `dag_rebuilder.py:460-463` — `# TODO(Phase B): step-level attachment via tool_use_id matching — current MVP attaches to the PLAN, not the step that spawned it. Flagged as acceptable by grok+pi Q2.`
- Docstring: `dag_rebuilder.py:263-264` — same text in the public API docs
- The `_discover_subagents` function has a clear, single responsibility that Phase B can extend with `tool_use_id` matching without restructuring

**Will it be forgotten?** It's in the code (grep for `Phase B` hits 2 locations in `dag_rebuilder.py`), the docstring, and the design plan. The `TODO(Phase B)` tag is greppable. Risk of forgetting is low.

---

### Q4. Real-data smoke gap

**Verdict: FIX-THEN-SHIP**

The plan §Verification checklist says:

> **Real-data DAG smoke** … **This is the main gate.** Fill rate is informational only.

This has NOT been run. Arguments each way:

| Factor | Weight |
|--------|--------|
| Fixture E2E exercises same JOIN logic with realistic shape | Strong mitigation |
| Orchestrator integration verified via Task 10 stub-backed contract test (`test_plan_tracker_trace_contract.py:150-168`) | Strong mitigation |
| Real LLM runs cost ~$0.05-0.20 + flaky | Low actual cost |
| Real data surfaces edge cases fixtures miss: encoding, partial writes, malformed spans, large JSONL | Unknown risk |

The real-data smoke catches exactly the class of bugs that fixtures miss: encoding issues, partial writes during crashes, malformed metadata from real LLM responses. Running it once costs $0.20 and 30 seconds.

**Recommendation:** Run the smoke once manually. If green, declare Phase A done. If it fails, the failure itself is valuable signal. Do NOT skip this gate — the plan explicitly calls it the main verification step, and the grok+pi review called out P0-2 (plan↔trace contract) as the same class of bug as v2's "Work Task 实体未定义" — invisible until real data flows.

**Fix:** Run this and record output:
```bash
vibe orchestrate "analyze src/ for code quality issues and suggest improvements"
# Verify execution_plans.jsonl has trace_id
# Run rebuild_dag and assert structure
```

Then append a one-line evidence note to the closeout.

**Overall:** Phase A is **code-complete**, not gate-passed. Declare it **DONE-PENDING-SMOKE** pending the one real-data run.

---

### Q5. Phase B readiness handoff

**Verdict: SHIP** (with 3 minor observations)

The DAG data structure is well-prepared for Phase B. Three items to document for the Phase B team:

**1. Sorting guarantees — DOCUMENT, don't change.** `dag.nodes` is insertion-ordered (Python dict/append semantics). The insertion order is: user_intent → orchestrator → phases → plan → steps → llm/tool spans → sub_agents. This is deterministic per run but NOT explicitly documented. Phase B's caching layer needs this stability. **Action:** Add a docstring note to `rebuild_dag` stating node insertion order is guaranteed stable per `trace_id`.

**2. Empty DAG vs "not found" — weak signal for Phase B.** `rebuild_dag` returns empty `DAG()` when `trace_id` doesn't match any data (`dag_rebuilder.py:284-285`). The HTTP endpoint `/api/orchestration/dag?trace_id=<id>` needs to distinguish 200-with-empty-DAG (valid trace, no data) from 404 (invalid trace — `execution_plans.jsonl` doesn't even contain the trace_id). Current implementation can't tell these apart without scanning all plans for trace existence. **Minor Phase B concern** — they can check `load_plans_for_trace` first for a 200 vs 404 signal.

**3. Caching scan cost — Phase B problem, Phase A priced-in.** Full JSONL scan per request. The `matched_span_ids` / `spans_by_task` indexes are built in-memory per `rebuild_dag` call — O(N) in span count. Phase B will need a TTL cache keyed on `trace_id` + `storage_dir`. Structure is already clean for this: `rebuild_dag` is a pure function of `(trace_id, storage_dir)`, so caching is trivial to add. **No blocker.**

**What's NOT missing:** Conversation turn data is not needed in DAG nodes (Phase B Live view reads conversations directly), pagination not needed (DAGs are ≤50 nodes), streaming not needed (full DAG fits in memory).

---

## Overall Verdict

### PHASE A DONE-PENDING-SMOKE

One blocking item remains: the real-data DAG smoke (Q4). Everything else — contract tightness (Q1), multi-plan correctness (Q2), sub-agent attachment (Q3), Phase B handoff (Q5) — is SHIP-ready.

### Top 3 risks (ranked by severity)

| Rank | Risk | Severity | Mitigation |
|------|------|----------|------------|
| 1 | **Real-data smoke not run** — plan↔trace JOIN may silently fail with real spans (encoding, partial writes, malformed metadata). Exactly the class of bug v2's "Work Task 实体未定义" was. | **HIGH** | Run the one-off smoke per Q4 fix. 30 seconds, $0.20. |
| 2 | **Empty DAG indistinguishable from "not found"** — Phase B HTTP endpoint needs 200 vs 404 signal. Current `rebuild_dag` returns empty DAG for both cases. Not a Phase A bug, but Phase B will trip over it. | **MEDIUM** | Document in handoff. Phase B can add `trace_exists(trace_id)` helper before calling `rebuild_dag`. |
| 3 | **Node ordering undocumented** — Phase B's caching layer may assume stable order implicitly. Order IS stable today (insertion order), but not documented as a contract. If future refactors change iteration order, cache keys break. | **LOW** | Add one docstring line to `rebuild_dag` return value documenting insertion order guarantee. |
