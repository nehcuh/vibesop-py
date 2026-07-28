/bin/sh: -c: line 0: syntax error near unexpected token `('
/bin/sh: -c: line 0: `vibe route --json --yes "You are reviewing **Phase A Task 10** of VibeSOP's Dashboard v3 instrumentation. This is a P0-2 mandatory fix: wire \`PlanTracker.create_plan()\` with \`metadata.trace_id\` so the DAG rebuilder can JOIN \`execution_plans.jsonl\` ↔ \`spans.jsonl\`.  ## Context  - Codebase: Python 3.12+, strict typing, TDD. - \`Orchestrator.orchestrate()\` wraps work in a root trace span (Task 2). - \`PlanTracker\` is append-only JSONL at \`.vibe/execution_plans.jsonl\`. - This task adds: (1) persist final plan with \`metadata.trace_id\` after plan_building, (2) \`load_plans_for_trace(trace_id, storage_dir)\` filter function. - Downstream consumer: \`rebuild_dag(trace_id)\` (Task 11/12, not yet implemented) will call \`load_plans_for_trace\` and JOIN with spans by \`trace_id\`.  ## What changed  \`\`\`diff DIFF BELOW — review the actual code, not just the description \`\`\`  ## Source diff (orchestrator.py + plan_tracker.py)  @/tmp/task10_diff.patch  ## Test file (test_plan_tracker_trace_contract.py)  The 9 tests at \`tests/core/orchestration/test_plan_tracker_trace_contract.py\` (348 lines) — please read on disk if you want full detail. Summary of test classes:  1. \`TestOrchestratePersistsPlanWithTraceId\` (4 tests): plan JSONL has matching trace_id; orchestration_id == plan_id; single-intent path does NOT persist; persistence failure doesn't break orchestration. 2. \`TestLoadPlansForTrace\` (5 tests): filter correctness; empty when no match; empty when file missing; skips legacy entries without trace_id; dedupes plan_id keeping latest.  ## Five review questions (focused)  **Q1. JOIN contract correctness.** The DAG rebuilder will read \`plan.metadata[\\"trace_id\\"]\` to JOIN against \`span.trace_id\`. Is this contract wired correctly end-to-end? Specifically: - Is the \`trace_id\` value being written the **root trace id** of the orchestrate() call (not a child span's trace_id, not a noop trace_id when tracing is disabled)? - What happens if tracing is disabled (\`get_tracer().trace(...)\` returns noop span with empty trace_id)? The code guards with \`if trace_id:\` — is that the right gate?  **Q2. Persistence placement.** I put the \`create_plan(plan)\` call AFTER per-step classification (final plan state) but BEFORE the \`complete\` phase span + OrchestrationResult construction. Is this the right point? Specifically: - Could anything between \`create_plan(plan)\` and the return mutate the plan (e.g. \`cb.on_plan_ready(plan)\` side effects, \`_record_plan_sequence\`, \`_record_execution\`)? If so, the persisted state would diverge from the returned state. - Should persistence be moved to a \`finally\` block?  **Q3. Best-effort error handling.** Persistence failures are caught + logged (warning). Is this the right policy? Specifically: - Should an OSError (disk full, permissions) propagate to the caller instead, given the DAG rebuilder silently produces empty output without the persisted plan? - Is there any monitoring / alerting hook that should fire when persistence fails repeatedly?  **Q4. load_plans_for_trace semantics.** The function reads all lines, dedupes by plan_id (last write wins), filters by metadata.trace_id. Specifically: - Is \\"last write wins\\" correct given PlanTracker also supports \`update_step_status\` (which appends a new line for the same plan_id)? Consider: plan created with trace_id T1 → step status updated 5 times (still T1 in metadata since update re-writes the whole plan) → load_plans_for_trace(T1) returns 1 plan. Correct? - The function returns \`list[ExecutionPlan]\`. Could there be >1 distinct plan per trace_id? (Yes — reorchestration creates a new plan under the same trace root.) Is the API shape right for downstream consumption?  **Q5. Silent failure modes.** Identify any way the JOIN could silently break in production that the tests don't cover: - Storage dir mismatch (orchestrate uses \`router.project_root/.vibe\`, but \`load_plans_for_trace(trace_id, storage_dir=\\".vibe\\")\` default — relative path). Is this footgun? - Concurrent orchestrate() calls writing the same JSONL (no cross-process lock on \`_append\`)? - Any race between \`plan.metadata[\\"trace_id\\"] = trace_id\` and another code path that might overwrite metadata?  ## Output format  For each question Q1-Q5: - **Verdict**: PASS / CONCERN / BLOCKER - **Evidence**: code line ref or test ref - **Fix (if not PASS)**: concrete change  End with: **Overall verdict** (SHIP / FIX-THEN-SHIP / BLOCK) and **top 3 risks** ranked by severity. commit d85ed06f535ae35e5e8fb26d447e3f4b001e4588 Author: huchen <curiousbull@outlook.com> Date:   Tue Jul 28 13:31:37 2026 +0800      feat(orchestrator): wire PlanTracker.create_plan() with trace_id — JOIN contract for DAG rebuilder          Phase A Task 10 (P0-2 mandatory). Orchestrator.orchestrate() now persists     the final ExecutionPlan via PlanTracker.create_plan() with metadata.trace_id     matching the root trace span. Without this, load_plans_for_trace() returns     empty and the DAG rebuilder produces a flat tree with no step nodes — same     class of bug as v2's \\"Work Task 实体未定义\\".          Changes:     - Orchestrator._orchestrate_impl() accepts trace_id (passed from       orchestrate()'s root span context); after per-step classification,       writes plan.metadata[\\"trace_id\\"] + orchestration_id and calls       PlanTracker.create_plan(). Persistence failures are logged + swallowed       (best-effort, never breaks orchestration).     - plan_tracker.load_plans_for_trace(trace_id, storage_dir) filters       plans by metadata.trace_id; dedupes by plan_id (latest wins); silently       skips pre-Task-10 legacy entries without metadata.trace_id.     - 9 new tests: contract (4) + filter (5). No LLM calls.          Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>  diff --git a/src/vibesop/core/orchestration/plan_tracker.py b/src/vibesop/core/orchestration/plan_tracker.py index 2647bc8..118c9a7 100644 --- a/src/vibesop/core/orchestration/plan_tracker.py +++ b/src/vibesop/core/orchestration/plan_tracker.py @@ -14,6 +14,8 @@ from vibesop.core.models import ExecutionPlan, PlanStatus, StepStatus    logger = logging.getLogger(__name__)   +__all__ = [\\"PlanTracker\\", \\"load_plans_for_trace\\"] +    class PlanTracker:      \\"\\"\\"Tracks execution plan state with append-only JSONL storage. @@ -143,3 +145,64 @@ class PlanTracker:          fields survive the to_dict() → from_dict() round-trip.          \\"\\"\\"          return ExecutionPlan.from_dict(data) + + +def load_plans_for_trace( +    trace_id: str, +    storage_dir: str | Path = \\".vibe\\", +) -> list[ExecutionPlan]: +    \\"\\"\\"Return all plans whose \`\`metadata.trace_id\`\` matches \`\`trace_id\`\`. + +    Cross-process JOIN contract (v3 Phase A Task 10): the DAG rebuilder uses +    this to find plans that belong to a given trace root. Plans persisted +    before Task 10 lack \`\`metadata.trace_id\`\` and are silently skipped +    (NOT crashed on) so historical data stays readable. + +    Args: +        trace_id: The root trace id produced by \`\`orchestrate()\`\`. +        storage_dir: Directory containing \`\`execution_plans.jsonl\`\`. Defaults +            to \`\`.vibe\`\` — same default as \`\`PlanTracker\`\`. + +    Returns: +        Plans whose latest persisted state has \`\`metadata.trace_id == trace_id\`\`, +        deduplicated by \`\`plan_id\`\` (latest entry wins, mirroring +        \`\`PlanTracker.get_plan()\`\` semantics). Empty list if no match or the +        JSONL file does not exist. +    \\"\\"\\" +    plans_path = Path(storage_dir) / \\"execution_plans.jsonl\\" +    if not plans_path.exists(): +        return [] + +    seen: dict[str, dict[str, Any]] = {} +    try: +        with plans_path.open(\\"r\\", encoding=\\"utf-8\\") as f: +            for raw_line in f: +                line = raw_line.strip() +                if not line: +                    continue +                try: +                    data = json.loads(line) +                except json.JSONDecodeError: +                    continue +                plan_id = data.get(\\"plan_id\\") +                if plan_id: +                    # Last write wins — append-only model means later lines +                    # supersede earlier ones for the same plan_id. +                    seen[plan_id] = data +    except OSError as e: +        logger.warning(\\"Failed to read plans from %s: %s\\", plans_path, e) +        return [] + +    result: list[ExecutionPlan] = [] +    for data in seen.values(): +        metadata = data.get(\\"metadata\\") or {} +        if metadata.get(\\"trace_id\\") == trace_id: +            try: +                result.append(ExecutionPlan.from_dict(data)) +            except Exception as e: +                logger.warning( +                    \\"Skipping malformed plan entry while loading trace %s: %s\\", +                    trace_id, +                    e, +                ) +    return result diff --git a/src/vibesop/core/routing/orchestrator.py b/src/vibesop/core/routing/orchestrator.py index ef2bd25..2a2efad 100644 --- a/src/vibesop/core/routing/orchestrator.py +++ b/src/vibesop/core/routing/orchestrator.py @@ -77,7 +77,13 @@ class Orchestrator:              \\"orchestrate\\",              metadata={\\"query\\": query[:500]},          ) as root_span: -            result = self._orchestrate_impl(query, candidates, context, callbacks) +            result = self._orchestrate_impl( +                query, +                candidates, +                context, +                callbacks, +                trace_id=root_span.trace_id, +            )              if conversation_id:                  self._writeback_to_conversation(                      conversation_id=conversation_id, @@ -129,8 +135,17 @@ class Orchestrator:          candidates: list[dict[str, Any]] | None = None,          context: RoutingContext | None = None,          callbacks: Any | None = None, +        *, +        trace_id: str = \\"\\",      ) -> OrchestrationResult: -        \\"\\"\\"Actual orchestration logic — see \`\`orchestrate()\`\` for trace wrapping.\\"\\"\\" +        \\"\\"\\"Actual orchestration logic — see \`\`orchestrate()\`\` for trace wrapping. + +        \`\`trace_id\`\` is the root trace's id (passed in by \`\`orchestrate()\`\`). +        It's written into \`\`plan.metadata\`\` so the DAG rebuilder can JOIN +        plan ↔ spans.jsonl via \`\`metadata.trace_id == span.trace_id\`\` (v3 +        Phase A Task 10, P0-2 mandatory). Empty string = tracing disabled +        → JOIN key omitted (DAG rebuilder will skip the plan). +        \\"\\"\\"          from vibesop.core.orchestration.callbacks import (              ErrorPolicy,              NoOpCallbacks, @@ -410,6 +425,24 @@ class Orchestrator:                  with bind_task_context(step.step_id, step.assigned_role):                      step_classifier.classify_step(step, sub_task)   +            # Persist final plan state via PlanTracker so the DAG rebuilder +            # can JOIN plan ↔ spans.jsonl (v3 Phase A Task 10, P0-2). The +            # trace_id is the cross-process JOIN key — contextvars does NOT +            # cross process boundaries, so the rebuilder reads it from +            # \`\`plan.metadata[\\"trace_id\\"]\`\` instead. Best-effort: persistence +            # failure must never break orchestration. +            if trace_id: +                plan.metadata[\\"trace_id\\"] = trace_id +                plan.metadata[\\"orchestration_id\\"] = plan.plan_id +                try: +                    self._router._get_plan_tracker().create_plan(plan) +                except Exception as e: +                    logger.warning( +                        \\"Failed to persist plan %s via PlanTracker: %s\\", +                        plan.plan_id, +                        e, +                    ) +          duration_ms = (time.perf_counter() - start_time) * 1000            result = OrchestrationResult("'
Now I have all the data. Here's my review.

---

## Phase A Task 10: Plan ↔ Trace JOIN Contract — Review

### Q1. JOIN contract correctness — `trace_id` source and disabled-tracing gate

**Verdict: PASS**

**Evidence:**

- `orchestrate()` extracts `trace_id` from `root_span.trace_id` (line 86), which is the root trace's id produced by `get_tracer().trace("orchestrate", ...)`. All child spans under this root inherit the same `trace_id` via `ctx.trace_id` (tracer line 230).
- When tracing is **disabled**, tracer line 172 yields `_Span(id="", trace_id="", name="noop", ...)`, so `root_span.trace_id == ""`. The gate `if trace_id:` at orchestrator line 437 correctly skips persistence — `""` is falsy.
- When tracing is **enabled**, `_Span.new_trace_id()` generates a real UUID. This value is written to `plan.metadata["trace_id"]` AND is the same value on every span in the tree. The JOIN key is consistent.

No child-span `trace_id` leaks into the plan. No noop trace_id is persisted.

---

### Q2. Persistence placement — before `complete` phase and `OrchestrationResult`

**Verdict: PASS** (with minor observation)

**Evidence:** After `create_plan(plan)` at line 440, the code does:
1. `OrchestrationResult(execution_plan=plan, ...)` — stores the same in-memory object reference
2. `_record_execution(query, result)` — reads `result.mode`, not `plan`
3. `_record_plan_sequence(query, plan, context)` — reads `plan.steps[].skill_id`, does not mutate `plan`
4. `cb.on_plan_ready(plan)` — **this is the only mutation risk**

If a user-provided callback mutates `plan.metadata["trace_id"]` inside `on_plan_ready`, the persisted JSONL line would say one thing and the returned `OrchestrationResult.execution_plan` would say another. But this is a callback contract violation, not a placement bug. No built-in callback (`NoOpCallbacks`) mutates the plan.

**No** — `finally` would be wrong. `finally` fires on exceptions and fallback paths (`return self._router._to_orchestration_result(single_result, query)` at lines 262, 271, etc.). Persisting a half-built or abandoned plan would pollute the store.

Placement is optimal: after the last plan mutation (per-step classification), before the return.

---

### Q3. Best-effort error handling

**Verdict: CONCERN**

**Evidence:** Orchestrator lines 441-446 — all exceptions caught and logged as `warning`. `logger.warning` is a standard library call; there's no structured monitoring hook.

The policy of **not propagating** is correct. Orchestration correctness must survive telemetry failure. But the absence of any alerting mechanism means:
- A full disk that persists for hours produces zero dashboard-visible plans with zero alerts
- Operators discover the gap only when they look at the dashboard and find it empty

**Fix:** Add a metric counter or structured log event that an external monitor can alert on — or at minimum log at `ERROR` level so log-based alerting can detect it:

```python
# Replace logger.warning with:
logger.error(
    "PlanTracker persistence failure — dashboard DAG will be incomplete. "
    "plan_id=%s error=%s",
    plan.plan_id,
    e,
)
```

Rating this CONCERN (not BLOCKER) because the plan is still returned and executable; only visualization degrades.

---

### Q4. `load_plans_for_trace` semantics

**Verdict: PASS**

**Evidence:**

- **"Last write wins" for dedup**: `update_step_status` does `plan = self.get_plan(plan_id)` → mutates step → `self._append(plan.to_dict())`. `plan.to_dict()` includes `self.metadata` (models.py line 532), and `get_plan` → `from_dict` round-trips `metadata` correctly (models.py line 577). So all 5 `update_step_status` lines carry the same `trace_id`. `load_plans_for_trace` takes the highest-numbered line per `plan_id` → returns 1 plan. ✅
- **Multiple distinct plans per trace**: `test_returns_only_matching_trace_id` writes `plan-A` and `plan-C`, both with `trace-1`, and asserts both are returned. ✅
- **API shape**: `list[ExecutionPlan]` is correct — reorchestration creates a new plan (new `plan_id`) under the same root trace. The DAG rebuilder can iterate all plans and add step nodes for each. ✅
- **Legacy skip**: `test_skips_plans_without_trace_id_metadata` confirms `metadata` missing `trace_id` → skipped, not crashed. ✅

---

### Q5. Silent failure modes

**Verdict: CONCERN**

Three failure modes, ranked:

**A. CWD-relative `storage_dir` defaults (HIGH risk)**

`PlanTracker(storage_dir=".vibe")` resolves relative to **CWD**, as does `load_plans_for_trace(trace_id, storage_dir=".vibe")` (plan_tracker.py lines 27 and 166).

If the DAG rebuilder runs from a different working directory (e.g., a subprocess, a cron job, or a different terminal), `load_plans_for_trace` silently reads a **different** `.vibe/execution_plans.jsonl` — or none at all if the directory doesn't exist — and returns `[]`. No error. No warning. Dashboard shows a flat tree.

No test covers this scenario. The stubbed router uses `UnifiedRouter(project_root=tmp_path)`, which resolves `.vibe` inside `tmp_path` — the test CWD happens to match. In production, they can diverge.

**Fix:** Either:
- Make `project_root` the canonical source and pass it through; or
- Resolve `storage_dir` to an absolute path at construction time and document that `load_plans_for_trace` must receive the same absolute path.

**B. Concurrent writes without cross-process lock (LOW risk)**

`_append` uses `open(file, "a")` — POSIX guarantees atomicity for writes ≤ `PIPE_BUF` (typically 4KB on Linux). A plan with many steps could exceed this, causing interleaved lines. Low probability in practice (single-user CLI), but a parallel `team` mode or multiple shells could trigger it.

**C. No race on `plan.metadata["trace_id"]` (PASS — not a failure mode)**

`plan.metadata` is `default_factory=dict` — each `ExecutionPlan` instance gets its own dict. The `plan_metadata` dict built from `classification.metadata` is a *different* dict passed to `builder.build_plan(metadata=plan_metadata)`. No sharing. No overwrite risk. ✅

---

## Overall Verdict: **FIX-THEN-SHIP**

### Top 3 Risks (ranked by severity)

| # | Risk | Severity | Fix |
|---|------|----------|-----|
| 1 | **CWD-relative storage path mismatch** — DAG rebuilder silently returns `[]` when CWD ≠ project_root | HIGH | Resolve `storage_dir` to absolute path in `PlanTracker.__init__` and expose it; document that `load_plans_for_trace` consumers must use the same absolute path |
| 2 | **No alerting on persistence failure** — Disk full produces zero dashboard plans with only a `logger.warning` | MEDIUM | Upgrade to `logger.error` or add a metrics counter for external monitoring |
| 3 | **JSONL line interleaving** under concurrent writes (line > PIPE_BUF) | LOW | Not worth fixing now; if parallel orchestration becomes common, add file-level `fcntl.flock` or switch to per-plan files |

The core JOIN contract — `plan.metadata["trace_id"] == span.trace_id` — is **correctly wired**. The two CONCERNs are deployment-edge risks, not logic bugs.
ses, same risk. The symptom is interleaved/corrupted JSON lines. However, the current `orchestrate()` is synchronous (`def`, not `async def`), so within a single thread only one call executes at a time. Cross-process is the real scenario: multiple `vibe` CLI invocations writing simultaneously. JSONL's line-oriented format is resilient (corrupt lines are skipped), but data loss is possible.

#### 5c. Race on `plan.metadata["trace_id"]`

**Verdict: PASS**

`plan.metadata["trace_id"] = trace_id` at line 435 and `create_plan(plan)` at line 438 are sequential with no `await` or yield point between them. No other code path mutates `plan.metadata["trace_id"]` concurrently. ✓

---

## Overall Verdict: **FIX-THEN-SHIP**

### Top 3 risks (ranked by severity)

| # | Risk | Severity | Fix |
|---|------|----------|-----|
| 1 | **Storage dir mismatch**: `load_plans_for_trace` default is relative `.vibe`; `_get_plan_tracker` writes to absolute `project_root/.vibe`. DAG rebuilder silently gets `[]` if CWD ≠ project root. | **BLOCKER** | Remove the default value for `storage_dir` — force callers to pass it explicitly; or accept `project_root: Path` and construct internally. |
| 2 | **`cb.on_plan_ready(plan)` mutation after persistence**: persisted JSONL can diverge from the `ExecutionPlan` returned in `OrchestrationResult` if a callback mutates `plan`. DAG rebuilder sees a different state than downstream consumers. | Medium | Snapshot plan dict before `create_plan()` OR document immutability contract on `OrchestrationCallbacks.on_plan_ready`. |
| 3 | **`_append` silently swallows IO errors**: `create_plan`'s outer `try/except` never fires for disk-full because `_append` catches it internally. Schema bugs (`to_dict` failure) are the only trigger, and they're caught with just `logger.warning` — zero observability. | Medium | Add `extra={"vibesop_check": "plan_persist_failed"}` to the warning; consider elevating `_append` OSError to caller. |
