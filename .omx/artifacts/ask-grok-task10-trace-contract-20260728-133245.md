I'll review the Task 10 JOIN contract end-to-end: route for the right skill, then inspect the real orchestrator/plan_tracker code and tests against Q1–Q5.Routing matched autopilot, which doesn't fit a focused contract review. I'll override and inspect the real code paths for Q1–Q5.Next I'll verify tracer noop behavior, PlanTracker storage path resolution, and whether anything mutates the plan after `create_plan`.**Routing note:** `vibe route` suggested `omx/autopilot` (66%). Overrode for a focused contract review of commit `d85ed06` — five explicit questions, not an autonomous multi-skill loop. Tests: **9/9 passed** `[executed]`.

---

## Q1. JOIN contract correctness

**Verdict: PASS** (one small CONCERN on the gate)

**Evidence:**
- Root span id is threaded correctly: `orchestrate()` → `trace_id=root_span.trace_id` → `_orchestrate_impl` (`orchestrator.py:77–86`).
- Write path: `plan.metadata["trace_id"] = trace_id` then `create_plan(plan)` (`orchestrator.py:434–438`).
- Read path: `metadata.get("trace_id") == trace_id` (`plan_tracker.py:198–199`).
- Noop when disabled: `ObservabilityTracer.trace` yields `_Span(..., trace_id="")` (`tracer.py:171–172`).
- Contract test asserts plan JSONL `trace_id` equals the `orchestrate` span’s `trace_id` (`test_plan_tracker_trace_contract.py:180–195`) `[executed]`.

**Analysis:**
- Value written is the **root** task-span id from `trace("orchestrate", ...)`, not a child phase span. Child spans inherit the same `trace_id` under an active context, so JOIN to `spans.jsonl` is coherent.
- `if trace_id:` correctly skips empty/noop ids — you must not write `trace_id=""` and later match empty spans.

**CONCERN (not JOIN-breaking):** the gate wraps **both** metadata assignment **and** `create_plan()`. When tracing is off, the multi-intent plan is not persisted at all (pre-Task-10 behavior for this path). Plan doc 10.3 always called `create_plan` and only set the key. Fine for DAG (no spans either); weaker if other consumers expect PlanTracker history with tracing disabled.

**Fix (optional):**
```python
if trace_id:
    plan.metadata["trace_id"] = trace_id
plan.metadata["orchestration_id"] = plan.plan_id
try:
    self._router._get_plan_tracker().create_plan(plan)
except Exception as e:
    ...
```

---

## Q2. Persistence placement

**Verdict: PASS**

**Evidence:**
- Persist is after adversarial upgrade + per-step `classify_step` (`orchestrator.py:379–426`), before `OrchestrationResult` / `_record_execution` / `_record_plan_sequence` / `on_plan_ready` (`446–475`).
- Stock callbacks do not mutate the plan: `NoOpCallbacks.on_plan_ready` is `pass`; CLI progress only logs step count (`callbacks.py:119–120`, `progress.py:118–125`).
- `_record_plan_sequence` only reads `skill_id`s; does not rewrite plan structure.

**Analysis:**
- Placement matches “final plan after plan_building + step classification,” which is what the rebuilder needs (steps, ids, pattern).
- Post-persist paths do not change step graph in-tree. Callback side effects would only desync in-memory vs JSONL if a custom callback mutates the plan — that is out of contract for stock code.
- A `finally` is the wrong shape: incomplete/failed plan_building should not write a half-built plan, and early single-intent returns never enter this block (covered by `test_single_intent_path_does_not_persist_plan`).

**Fix:** none required. Optional nit: move metadata + `create_plan` to immediately before `return result` only if you later need post-callback enrichment in JSONL (not needed today).

---

## Q3. Best-effort error handling

**Verdict: CONCERN** (policy OK; failure signal is weaker than tests imply)

**Evidence:**
- Outer: `except Exception` + `logger.warning` (`orchestrator.py:439–444`).
- Inner: `PlanTracker._append` already catches `OSError` and only `logger.error`s — **does not re-raise** (`plan_tracker.py:132–138`).
- Test forces raise by monkeypatching `PlanTracker.create_plan` itself (`test_plan_tracker_trace_contract.py:236–245`) — not the real `_append` path.
- Same best-effort pattern as conversation writeback Task 5 (`orchestrator.py:112–130`).

**Analysis:**
- For orchestrate UX: swallowing is correct — routing must not fail on observability IO.
- For DAG rebuilder: missing plan ⇒ empty/flat DAG (same class as the P0-2 bug). Silent log-only is the accepted trade-off for Phase A.
- Production disk-full/`OSError` rarely hits the orchestrator warning; only `_append`’s `logger.error`. No counter/metric/alert hook in this stack.

**Fix:**
1. Keep best-effort (do not propagate `OSError` on the hot path).
2. Prefer making `_append` re-raise (or return `bool`) so the orchestrator warning is the single place, **or** document dual log sites.
3. Phase B: optional counter (`plan_persist_failures`) or `logger.warning` with a stable event key for log-based alerts — not blocking Task 10.

---

## Q4. `load_plans_for_trace` semantics

**Verdict: PASS**

**Evidence:**
- Scan all lines → last dict per `plan_id` → filter `metadata.trace_id` (`plan_tracker.py:176–208`).
- Mirrors `get_plan()` last-write-wins.
- `update_step_status` reloads full plan via `get_plan` → mutates step → `_append(plan.to_dict())`; `metadata` round-trips via `to_dict`/`from_dict` (`models.py:530`, `565`).
- Multi-plan per trace: `test_returns_only_matching_trace_id` expects `{plan-A, plan-C}` for same `trace_1` (`test_plan_tracker_trace_contract.py:291–303`).
- Return type `list[ExecutionPlan]` matches reorchestration under one root.

**Analysis:**
- “Last write wins” for the same `plan_id` after N `update_step_status` appends is correct; latest row still carries `trace_id` if the first create had it.
- `list` is the right API for rebuilder: pick latest, union steps, or show reorchestration history. A single `ExecutionPlan | None` would lose reorchestration.

**Fix:** none. Optional: stable sort by `created_at` / file order for multi-plan traces (document in Task 11/12). `dict.values()` order is first-seen `plan_id` order, which is usually fine.

---

## Q5. Silent failure modes

**Verdict: CONCERN** (real footguns; not regressions of the JOIN key itself)

| Risk | Severity | Evidence | Covered by tests? |
|------|----------|----------|-------------------|
| **storage_dir mismatch** | High for Task 11/12 | Writer: `PlanTracker(storage_dir=host.project_root / ".vibe")` (`orchestration_mixin.py:122`). Reader default: `storage_dir=".vibe"` (CWD-relative) (`plan_tracker.py:152`). | No — tests always pass absolute `tmp_path` |
| **No cross-process lock on plan JSONL** | Medium | Spans use `fcntl` (`span_writer.py`); `PlanTracker._append` plain open+write | No |
| **metadata race / overwrite** | Low | Only this path sets `trace_id`/`orchestration_id` on the plan object; keys merge into existing `metadata` (no full replace). `on_plan_ready` after write is display-only. | No explicit race test |
| **Tracing off ⇒ no plan row** | Low–Med | `if trace_id:` gates entire persist | No disabled-tracer test |
| **Malformed JSONL lines** | Low | Skip on `JSONDecodeError` / `from_dict` errors | Partial (legacy no-key only) |

**Fix:**
1. **Task 11/12 hard rule:** `rebuild_dag(trace_id, storage_dir: Path)` must take project-rooted `Path` (e.g. `project_root / ".vibe"`); never rely on default `".vibe"` from arbitrary CWD. Consider deprecating the relative default or resolving against a known project root.
2. Locking: reuse `cross_process_lock` / flock pattern from span writer when plan JSONL contention shows up (pre-existing PlanTracker debt).
3. Add a small test: `enabled=False` tracer → either no plan (document) or always-persist without key (if you take the Q1 optional fix).

---

## Overall verdict: **SHIP**

Core P0-2 contract is correct and covered: multi-intent orchestrate writes `metadata.trace_id` equal to the root orchestrate span; `load_plans_for_trace` filters and dedupes as specified; single-intent does not leak; best-effort does not break orchestration. **9/9 tests green** `[executed]`.

Not **BLOCK**: nothing corrupts the JOIN key when tracing is on and `storage_dir` is the same absolute path used by the router.

Not **FIX-THEN-SHIP** for Task 10 alone — residual issues are follow-ups for Task 11/12 / ops, not a broken writer.

### Top 3 risks (severity)

1. **`storage_dir` CWD footgun (HIGH for rebuilder)** — write is `project_root/.vibe`; `load_plans_for_trace` default is relative `.vibe`. Wrong CWD ⇒ empty plans ⇒ flat DAG, same symptom as “never called create_plan.” Mitigate in Task 11/12 API, not optional.

2. **Best-effort + silent empty DAG (MEDIUM)** — persistence failures (and tracing-off skip) leave rebuilder empty with only logs. Acceptable for Phase A; no metric/alert. Align with dashboard “rebuild_dag smoke” gate so empty JOIN is visible in CI/E2E (Task 13).

3. **Unlocked concurrent JSONL appends (MEDIUM, pre-existing)** — multi-process orchestrate can theoretically tear plan lines; spans already lock. Lower probability than (1), but worth parity with `SpanWriter` if multi-session use grows.

### Optional polish (non-blocking)

- Split `if trace_id:` so plans always persist on multi-intent success; only the JOIN key is conditional.
- Test `update_step_status` after create preserves `metadata.trace_id` under last-write-wins.
- Test tracing-disabled behavior explicitly.
