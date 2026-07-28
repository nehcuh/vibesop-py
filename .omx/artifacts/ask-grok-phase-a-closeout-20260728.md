I'll route this review request, then inspect the Phase A pipeline code and tests against Q1–Q5.Routing suggested design; this is a Phase A gate review of shipped code, so I'll use the review path and inspect the source files and tests directly.Digging into regression tests, JOIN logic, and Phase B handoff gaps.Checking producer/consumer field-name alignment and whether real SpanWriter shape matches fixtures.Real tracer output showed `task_id: null` under `bind_task_context` — verifying whether that's a producer bug.The bind failure was likely a separate tracer instance. Re-testing with the global tracer path.**Routing override:** `omx/design` is the wrong skill for a shipped-code Phase A gate review. This is a focused Q1–Q5 closeout review of the 6 commits + tests (not a design-doc workflow).

**Tests re-run:** 41/41 green on `test_dag_rebuilder.py` + `test_dag_rebuilder_e2e.py` + `test_plan_tracker_trace_contract.py` `[executed]`.

---

## Q1. JOIN contract — `task_id == step_id` (P0-1)

**Verdict: SHIP**

**Evidence**

| Layer | Where | What it proves |
|--------|--------|----------------|
| Producer (Task 4) | `tests/core/routing/test_orchestrator_step_binding.py:241–249` | LLM spans get `task_id` = **step_id**, not plan_id |
| Rebuilder JOIN | `dag_rebuilder.py:413–442` | Attach only when `spans_by_task[step.step_id]` matches; kinds limited to `llm` / `tool` / `tool_call` |
| Unit | `test_dag_rebuilder.py:365–407` | `task_id="s1"` → child of `step:plan-1:s1` |
| E2E | `test_dag_rebuilder_e2e.py:183–197`, `272–280` | Per-step assert: `span-llm-{step_id} in step_node.children` |

**Counterfactual (executed):** if fixture used `task_id="plan-e2e"` instead of `"s1"`, step children stay empty, no `llm` node is created, and E2E line 277 fails. Wrong key does **not** attach to the plan.

**Orphan / “never show orphan work”**

- Unmatched `task_id` spans are **not** DAG nodes; they are only `logger.debug` orphan logs (`dag_rebuilder.py:444–455`).
- So the map never shows floating “orphan” work.
- Tradeoff: mismatched work is **silent** (empty steps), not a visible orphan bucket. That is acceptable for Phase A if fill-rate / orphan metrics stay Phase B.

**Contract tightness:** tight enough for the dashboard **if** producers keep Task 4 semantics. E2E + unit tests would fail if JOIN key drifts to plan_id. Not a guarantee against future producer bugs without continuous producer tests.

---

## Q2. Multi-plan + reorchestration semantics

**Verdict: SHIP**

**Evidence — regressions would break if fixes were removed**

| Fix | Test | Break if removed |
|-----|------|------------------|
| Plan-scoped step ids `step:{plan_id}:{step_id}` | `test_rebuild_dag_multi_plan_shared_step_id_attaches_span_once` (`test_dag_rebuilder.py:659–725`) | Duplicate node ids; span attached to both plans; E2E expects `step:plan-e2e:s1` etc. |
| Span attaches once (`matched_span_ids`) | same test, lines 712–720 | `a_has != b_has` fails |
| `iterations` from `reorchestration_history` | `test_rebuild_dag_iterations_derives_from_reorchestration_history` (`:601–657`) | Pre-fix: `len(plans)==1` → `iterations=1`; post-fix expects `3` |
| Fallback to plan count | `test_rebuild_dag_iterations_falls_back_to_plan_count_without_history` (`:568–599`) | Two plans, no history → `iterations==2` |

Implementation: `_derive_iterations` (`dag_rebuilder.py:516–540`):  
`max(len(plans), max_history_len + 1)` when history non-empty, else `len(plans)`.

**Other multi-plan edges for the dashboard**

| Case | Behavior | Risk |
|------|----------|------|
| Two `orchestrate()` accidentally share `trace_id`, no history | `iterations = len(plans)` (e.g. 2); both plans under one root if spans share that id | `iterations` is still sensible as “plans under this trace,” not true loop rounds. Misleading label if UI says “reorchestration rounds.” |
| `loop_until_dry` one plan + history | Correct via history | Covered by regression test |
| Shared `step_id` across plans | First plan wins span attach | Documented; production `uuid[:8]` step_ids make collision rare |

**Recommendation (non-blocking):** UI copy for `iterations` should prefer “orchestration rounds (history or plan count)” over “reorchestration count only.” No code change required for Phase A.

---

## Q3. Sub-agent attachment MVP

**Verdict: SHIP**

**Evidence**

- MVP attaches to **plan**, not step: `dag_rebuilder.py:457–485` (`plan:{attach['plan_id']}` parent).
- E2E asserts the right thing:
  - `sub.metadata["plan_id"] == "plan-e2e"` (`test_dag_rebuilder_e2e.py:290–294`)
  - `sub.id in plan_node.children` (`:295–298`)
  - **No** `step_id` / step-child assert (correct for deferred work).
- Unit: `test_rebuild_dag_attaches_subagent_to_plan_via_parent_conversation` (`test_dag_rebuilder.py:443–498`).

**Acceptable for Phase A?** Yes. Plan-level placement is enough for Orchestration Map v1; step-level needs `tool_use_id` and cross-process attribution that Phase A explicitly deferred.

**Phase B TODO findability**

- Code: `TODO(Phase B): step-level attachment via tool_use_id` (`dag_rebuilder.py:460–462`)
- Docstring on `rebuild_dag` (`:261–264`)
- Test docstrings echo the deferral

**Gap (nit, not BLOCK):** no issue/ROADMAP ticket id on that TODO. Worth one line in `PROJECT_CONTEXT` / Phase B plan so it is not only a source comment.

---

## Q4. Real-data smoke gap

**Verdict: FIX-THEN-SHIP (process / gate, not code)**

**Evidence of what *is* covered**

| Gate | Status |
|------|--------|
| Fixture E2E (Task 13) | Full JOIN shape, zero LLM |
| Task 10 contract | Real `orchestrate()` → `plan.metadata["trace_id"]` |
| Task 4 binding | Real stubbed orchestrate → LLM spans with step-level `task_id` |
| SpanWriter shape | `id` / `task_id` / `span_kind` / stringified `metadata` handled in `load_spans_for_trace` (`:215–221`) |

**What real-data (or equivalent) still uniquely catches**

- Full chain: **one** `storage_dir` write of plan JSONL + spans + conversation → **one** `rebuild_dag` call (today split across Task 4 / 10 / 13 fixtures).
- CWD / absolute `.vibe` path footgun called out in `rebuild_dag` docstring (`:245–249`).
- Conversation writeback + sub-agent mirror path in a live multi-intent run.
- Fill-rate / silent orphan rate under real providers (informational per plan).

**Acceptable to declare Phase A “code complete”?** Yes.  
**Acceptable to declare “pipeline ready for Phase B UI” without any smoke?** Only if you reframe the gate.

The plan text calls real-data DAG smoke the **main gate**. Fixture E2E is a strong substitute for JOIN logic, not a full substitute for “artefacts land where the rebuilder reads them.”

**Minimal fix (prefer over paid LLM smoke):**

1. One **zero-LLM integration** test (or scripted smoke): Task-4-style stubbed `orchestrate()` + `PlanTracker` + `rebuild_dag` on the same `tmp_path`, assert ≥1 plan, ≥1 step, ≥1 llm child via real JSONL.
2. Optional: one manual/paid multi-intent run later; do not block Phase B scaffolding on $0.05–0.20 flaky runs.

**Ship language:**  
**“Phase A code-complete; pipeline gate = fixture E2E + layered unit contracts; real-data / stubbed-orchestrate→rebuild smoke still open.”**  
Do not claim “main gate green” without (1) or a real run.

---

## Q5. Phase B readiness handoff

**Verdict: SHIP** (for starting B; known API/product decisions, not Phase A blockers)

| Concern | Current behavior | Phase B action |
|---------|------------------|----------------|
| **API surface** | `rebuild_dag(trace_id, storage_dir) -> DAG` only; no `to_dict` / JSON helpers | Add `DAG.to_dict()` (or pydantic model) for FastAPI response |
| **Stable order** | Construction / JSONL input order; no sort on `nodes`/`edges`; span siblings preserve input order (`build_span_tree` docstring `:136–137`) | Enough for content-hash ETags; if clients need sorted ids, sort at API boundary |
| **Pagination / streaming** | Full DAG, full JSONL scan | Defer until real traces blow payload; document “MVP: whole DAG” |
| **Trace not found** | Empty `DAG` when no spans and no plans (`:279–280`); same shape as “found but empty-ish” | Prefer **404** (or `{found: false}`) when both loads empty; 200 + partial DAG when only plans or only spans (resilience tests already define that) |
| **Caching** | Full scan per call (Task 12 Q5 known) | mtime/size cache or index by `trace_id` before heavy UI traffic |
| **Sub-agent step attach** | Plan-level only + TODO | Phase B feature |
| **Reflections** | Separate store (Tasks 7–9); not in `rebuild_dag` | `/api/reflections` independent of DAG |

Nothing **obviously missing** that blocks scaffolding `/api/orchestration/dag?trace_id=`. Empty-DAG vs 404 is the only decision that should be locked before UI assumes “empty = error.”

---

## Overall verdict

### **PHASE A DONE-PENDING-SMOKE**

Code + contract tests for Tasks 10–13 are solid enough to start Phase B scaffolding. Do **not** mark the plan’s “main gate” green until either:

1. a **stubbed** `orchestrate → rebuild_dag` integration smoke (recommended, free), or  
2. one real multi-intent run with the checklist in §Verification.

Call it **code-complete Phase A**; hold the phrase “data pipeline fully verified for UI” until that smoke.

---

### Top 3 risks (by severity)

1. **P0 — Silent JOIN miss on producer drift**  
   Wrong/missing `task_id` yields empty step children and debug-only orphan logs (`dag_rebuilder.py:444–455`). Dashboard looks “healthy” with empty steps. Mitigate: keep Task 4 tests in CI; optional orphan counter in Phase B metrics.

2. **P1 — No single-process producer→rebuilder smoke**  
   Layers are tested in isolation; the plan’s main gate was real-data (or equivalent) and is still open. Highest chance of “works in unit, empty in dashboard” from path/`storage_dir`/writeback bugs.

3. **P2 — Multi-plan / accidental shared `trace_id` semantics**  
   `iterations` and dual plans under one root are defined, but UI may mislabel “2 plans / 1 trace” as reorchestration. Sub-agents remain plan-scoped until Phase B `tool_use_id` work.

---

**Scorecard**

| Q | Verdict |
|---|---------|
| Q1 JOIN | **SHIP** |
| Q2 Multi-plan / iterations | **SHIP** |
| Q3 Sub-agent MVP | **SHIP** |
| Q4 Real-data smoke | **FIX-THEN-SHIP** (process gate) |
| Q5 Phase B handoff | **SHIP** (with 404 + serialize notes) |
| **Overall** | **PHASE A DONE-PENDING-SMOKE** |
