# Dashboard v3 Phase A — Data Instrumentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the persistence contracts + JOIN keys that the Phase B/C Dashboard Map view needs to render — plan↔trace, step structure, `parent_session`. NOT in-process fill rate cosmetics.

**v3 design doc:** `docs/decisions/2026-07-27-dashboard-v3-orchestration-map-and-reflection.md` § 3
**Review trail:** `docs/decisions/_review-dashboard-v3-phase-a-plan-merged.md` (grok+pi CONDITIONAL, 4 P0 + 3 P1 + 1 Nit absorbed)

**Scope:**
- **IN:** 5 instrumentation fixes + Plan↔Trace contract (PlanTracker wiring) + DAG rebuilder + Reflection Store (data layer only)
- **OUT:** AgentPrefs (→ Phase E), Dashboard UI (→ Phase B/C), Reflection closed-loop actions (→ Phase E), HTTP API endpoints (→ Phase B/C)

**Verification targets:**
- All existing tests pass (currently 4434+)
- New tests: ~50
- `uv run ruff check src/ tests/` clean
- `uv run basedpyright src/` 0 errors (4 pre-existing warnings OK if not in scope)
- **Real-data DAG smoke** (replaces fill-rate metric — see Verification §)

---

## Data Boundary: In-process vs Cross-process

> **Critical context (from grok+pi review):** contextvars does NOT cross process boundaries. VibeSOP process builds the plan; the actual step execution happens in external agent CLIs (Claude Code, etc.) as separate OS processes. Sub-agents are also separate processes.

| Data | Source | contextvars? | Correct wiring |
|------|--------|--------------|----------------|
| plan / step / dependencies | `execution_plans.jsonl` | No | **Task 10**: Orchestrator calls `PlanTracker.create_plan()` + writes `trace_id` |
| orchestrator phase boundaries | Task 2-3 `workflow_node` spans | In-process OK | `tracer.span(...)` |
| step → VibeSOP-internal LLM calls (classify / decompose / build_plan) | `bind_task_context` at execution boundary | **Yes (in-process only)** | Task 1 + Task 4 |
| step → external agent / sub-agent | conversation + `parent_session` metadata | **No** | Task 6: `--include-subagents` flag + parent_session join contract |
| plan ↔ trace JOIN | `plan.metadata["trace_id"]` | No | Task 10 |

**Hard rule**: Fill rate is NOT a success metric. The success metric is `rebuild_dag(trace_id)` returning a DAG with step nodes that have children or sub_agent edges. A step node with zero children means the JOIN failed, regardless of what `task_id` fill rate says.

**Map MVP allows**: step nodes with no llm children if the work was done in an external agent — the step's `skill_id` + `dependencies` + attached sub_agent conversations still produce a meaningful DAG.

---

## File Structure

### New files

| Path | Responsibility |
|------|----------------|
| `src/vibesop/observability/reflection.py` | `Reflection` dataclass + `ReflectionStore` (append-only jsonl writer with cross-process lock) |
| `src/vibesop/observability/dag_rebuilder.py` | `DAG` dataclass + `rebuild_dag(trace_id)` algorithm |
| `tests/observability/test_reflection.py` | Reflection dataclass + Store TDD tests |
| `tests/observability/test_dag_rebuilder.py` | DAG rebuilder TDD tests (fixture-based, zero LLM) |
| `tests/core/routing/test_orchestrator_workflow_spans.py` | Orchestrator phase + trace context tests (stub LLM) |
| `tests/core/conversation/test_mirror_subagent_import.py` | Mirror hook → import_subagent contract test |

### Modified files

| Path | What changes |
|------|--------------|
| `src/vibesop/core/observability/tracer.py` | **Extend existing `current_task_id` (don't add new ContextVar)** — see Task 1 |
| `src/vibesop/core/routing/orchestrator.py` | Wrap `orchestrate()` in `tracer.trace(...)`; wrap each phase in `workflow_node` span; **bind step-level task_id** during plan_building iteration (no plan_id fallback); **call `PlanTracker.create_plan(plan)` with `trace_id` metadata** in completion phase; write `orchestration_id` to conversation metadata |
| `src/vibesop/core/orchestration/plan_tracker.py` | Confirm `create_plan()` signature; add `metadata["trace_id"]` write path if missing |
| `src/vibesop/adapters/templates/claude-code/hooks/vibesop-mirror-session-end.sh.j2` | Add `--include-subagents` flag to `vibe conversation import-claude` call |
| `src/vibesop/core/conversation_import.py` | No code change expected — confirm `import_subagent` + `derive_subagent_conversation_id` stability; add **parent_session ↔ conversation_id contract test** |

### Out of scope (Phase B/C/E)

- `src/vibesop/dashboard/server.py` — no new HTTP endpoints in Phase A
- Dashboard frontend (`templates/index.html`) — untouched
- `src/vibesop/core/instinct/agent_prefs.py` — **deferred to Phase E** (grok+pi P1-2)

---

## Tasks

### Task 1: Extend existing `current_task_id` to carry role_id

**Why:** grok `[inspected]`: `TraceContext.current_task_id` already exists in the `tracer.trace(task_id=...)` inheritance path; child spans already inherit task_id. Adding a parallel `_task_ctx_var` would create a second inconsistent path. Extend what's there.

- [ ] **1.1** Grep `current_task_id` in `src/vibesop/core/observability/tracer.py` and `tests/core/observability/`:
  ```bash
  grep -rn "current_task_id" src/ tests/
  ```
  Document the existing signature: where is it set? Where is it read? Does it already propagate to child spans?
- [ ] **1.2** Write failing test `tests/core/observability/test_tracer_task_role_context.py`:
  ```python
  def test_bind_task_context_propagates_task_and_role():
      """Inside bind_task_context(task_id="t1", role_id="r1"), child spans
      must have both task_id and role_id populated."""
      # ... use existing tracer.trace(task_id=...) entry, add role

  def test_bind_task_context_does_not_leak_after_exit():
      """After exit, new spans must NOT inherit task_id/role_id."""
      # ...
  ```
- [ ] **1.3** Run — confirm fail.
- [ ] **1.4** Extend the existing `current_task_id` mechanism (don't create new ContextVar):
  - If it's a single value, upgrade to `(task_id, role_id)` tuple or add a parallel `_role_ctx_var` only if extending the existing one breaks API.
  - Modify `ObservabilityTracer.start_span()` to read the extended context and populate `task_id` + `role_id` on the new span if not already set.
- [ ] **1.5** Run — confirm pass. Commit: `feat(observability): extend current_task_id to carry role_id — single context path`

### Task 2: Wrap `Orchestrator.orchestrate()` in trace context

**Why:** Currently only 2 places open trace context. Orchestrator is the natural trace root for any complex query.

- [ ] **2.1** Write failing test `tests/core/routing/test_orchestrator_workflow_spans.py`:
  ```python
  def test_orchestrate_opens_trace_context(tmp_path, monkeypatch):
      """Calling orchestrate() must emit a root workflow span whose trace_id
      is shared by all phase child spans."""
      # stub should_decompose / classifier to avoid LLM (per Task 13 pattern)
      result = orchestrator.orchestrate("complex multi-intent query", ...)
      spans = load_jsonl(tmp_path / "observability/spans.jsonl")
      trace_ids = {s["trace_id"] for s in spans}
      assert len(trace_ids) == 1
  ```
- [ ] **2.2** Run — confirm fail.
- [ ] **2.3** Modify `src/vibesop/core/routing/orchestrator.py`:
  - Import tracer.
  - Wrap entire body of `orchestrate()` (L32-333) in `with get_tracer().trace("orchestrate", metadata={"query": query}):`.
- [ ] **2.4** Run — confirm pass. Existing `tests/core/routing/test_orchestrator.py` still green.
- [ ] **2.5** Commit: `feat(orchestrator): wrap orchestrate() in trace context`

### Task 3: Emit `workflow_node` span per phase

**Why:** Map view needs phase boundaries.

- [ ] **3.1** Write failing test:
  ```python
  def test_orchestrate_emits_workflow_node_span_per_phase(...):
      """For a multi-intent query, emit >=5 workflow_node spans:
      orchestrate:routing, orchestrate:detection, orchestrate:decomposition,
      orchestrate:plan_building, orchestrate:completion."""
      # stub LLM
      orchestrator.orchestrate("complex query")
      spans = load_jsonl(...)
      phase_names = {s["name"] for s in spans if s["span_kind"] == "workflow_node"}
      expected = {"orchestrate:routing", "orchestrate:detection",
                  "orchestrate:decomposition", "orchestrate:plan_building",
                  "orchestrate:completion"}
      assert expected.issubset(phase_names)
  ```
- [ ] **3.2** Run — confirm fail.
- [ ] **3.3** Modify `orchestrator.py`: wrap each phase in `with tracer.span(f"orchestrate:{phase}", kind="workflow_node") as phase_span:` + `phase_span.set_metadata({"phase": phase, "query": query[:200]})`. Phases (per Explore):
  - L51-70 → `routing`
  - L77-98 → `detection`
  - L101-136 → `decomposition`
  - L139-185 → `classification` (optional)
  - L187-301 → `plan_building`
  - L303-333 → `completion`
- [ ] **3.4** Run — confirm pass.
- [ ] **3.5** Commit: `feat(orchestrator): emit workflow_node span per phase`

### Task 4: Step-level task_id / role_id binding (NO plan_id fallback)

**Why:** This is the actual fix for `Span.task_id` (0%) + `Span.role_id` (0%). **grok+pi P0-1**: removing the `plan_id` fallback is non-negotiable. The DAG JOIN contract is `step.spans = [s for s in spans if s.task_id == step.step_id]`; any plan_id binding makes every step node empty.

- [ ] **4.1** Write failing test:
  ```python
  def test_orchestrate_binds_step_level_task_id(...):
      """When PlanBuilder iterates plan.steps during plan_building, each
      classification / decomposition LLM span must carry the step_id of
      the step currently being planned (NOT the plan_id)."""
      # stub classifier to capture span context
      orchestrator.orchestrate("complex query")
      spans = load_jsonl(...)
      llm_spans = [s for s in spans if s["span_kind"] == "llm"]
      # Assert: each llm span's task_id matches one of the plan's step_ids
      plan = load_latest_plan(...)
      step_ids = {s.step_id for s in plan.steps}
      bound_llm_spans = [s for s in llm_spans if s.get("task_id")]
      assert bound_llm_spans, "at least one llm span must have step-level task_id"
      assert all(s["task_id"] in step_ids for s in bound_llm_spans), \
          "task_id must be a step_id, NOT the plan_id"
  ```
- [ ] **4.2** Run — confirm fail.
- [ ] **4.3** Modify `orchestrator.py` + `plan_builder.py`:
  - **Option A (preferred)**: Refactor `PlanBuilder.build_plan()` to iterate `plan.steps` explicitly at the orchestrator level, wrapping each iteration:
    ```python
    for step in plan.steps:
        with bind_task_context(task_id=step.step_id, role_id=step.assigned_role or "default"):
            # ... existing step planning logic
    ```
  - **Option B (only if Option A requires >1 day refactor)**: Push step-level binding to `agent_runtime.arun()` and document explicitly in `tracer.py` that VibeSOP-internal Orchestrator LLM calls bind at plan level (with plan_id, NOT step_id) — **but this requires changing the DAG JOIN contract** to also match `task_id == plan_id` as a fallback. **This is NOT the same as the original R1 fallback** — it's a documented architectural choice. Prefer Option A.
- [ ] **4.4** Run — confirm pass. Re-read the test: does it actually prove step_id binding (not plan_id)? If `bound_llm_spans[0].task_id == plan.plan_id`, the test must fail.
- [ ] **4.5** Commit: `feat(orchestrator): step-level task_id binding (no plan_id fallback)`

### Task 5: Write `orchestration_id` to conversation metadata

**Why:** Dashboard needs to join conversation sessions to orchestration traces.

- [ ] **5.1** Write failing test `tests/core/routing/test_orchestrator_metadata_writeback.py`:
  ```python
  def test_orchestrate_writes_orchestration_id_to_conversation(tmp_path):
      orchestrator.orchestrate("query", conversation_id="conv-123")
      conv = load_conversation(tmp_path / "conversations" / "cli-conv-123.json")
      assert conv["metadata"]["orchestration_id"] == result.plan.plan_id
      assert conv["metadata"]["orchestration_trace_id"] is not None
  ```
- [ ] **5.2** Run — confirm fail.
- [ ] **5.3** Modify `orchestrator.py`:
  - Add `conversation_id: str | None = None` param to `orchestrate()` (default None = backward compat).
  - In `completion` phase, after OrchestrationResult is built:
    ```python
    if conversation_id:
        ctx = ConversationContext(conversation_id, storage_dir, max_history=10)
        ctx.metadata["orchestration_id"] = result.plan.plan_id
        ctx.metadata["orchestration_trace_id"] = current_trace_id
        ctx.save()
    ```
- [ ] **5.4** Run — confirm pass.
- [ ] **5.5** Commit: `feat(orchestrator): write orchestration_id + trace_id to conversation metadata`

### Task 6: Mirror hook `--include-subagents` flag + parent_session join contract

**Why:** **grok+pi P0-3**: hook template already calls `vibe conversation import-claude` but never passes `--include-subagents`. Sub-agent import in production mirror path = 0%. Also: `parent_session_id=path.stem` (full session id) vs conv id `mirror-claude-{session[:20]}` — DAG JOIN will miss.

- [ ] **6.1** Locate and read `src/vibesop/adapters/templates/claude-code/hooks/vibesop-mirror-session-end.sh.j2`:
  ```bash
  grep -rn "import-claude\|include-subagents" src/vibesop/adapters/templates/
  ```
- [ ] **6.2** Write failing test `tests/core/conversation/test_mirror_subagent_import.py`:
  ```python
  def test_mirror_hook_template_includes_subagents_flag():
      """The rendered hook template MUST pass --include-subagents to
      vibe conversation import-claude."""
      rendered = render_template("vibesop-mirror-session-end.sh.j2", context={...})
      assert "--include-subagents" in rendered

  def test_parent_session_resolves_to_parent_conversation_id(tmp_path):
      """End-to-end: render hook → run on a fixture JSONL with one sub-agent
      ToolUse → discover_subagents returns records whose parent_session
      resolves to the parent conversation_id (not raw path.stem)."""
      # write fixture main conversation JSONL
      # run hook (or simulate its effect)
      records = discover_subagents(storage_dir=tmp_path)
      assert records
      parent_conv = load_conversation(records[0].meta["parent_session"])
      assert parent_conv is not None  # resolvable, not orphan
  ```
- [ ] **6.3** Implement:
  - Add `--include-subagents` to the hook template (after `--storage-dir "$_STORAGE_DIR"`).
  - Verify `derive_subagent_conversation_id` produces IDs that resolve back to the parent. If `parent_session_id=path.stem` doesn't match `mirror-claude-{session[:20]}`, **double-write** both `parent_session_id` (raw) and `parent_conversation_id` (resolved) in metadata, OR change `parent_session_id` to be the resolved conversation_id (breaking change — needs migration).
- [ ] **6.4** Run — confirm both pass.
- [ ] **6.5** Commit: `feat(conversation): mirror hook --include-subagents flag + parent_session join contract`

### Task 7: `Reflection` dataclass + JSON round-trip

**Why:** Foundation for the Reflection Store.

- [ ] **7.1** Write failing test `tests/observability/test_reflection.py`:
  ```python
  def test_reflection_round_trip():
      r = Reflection(target_type="route_span", target_id="span-abc",
                    task_id="task-xyz", kind="routing_miss",
                    content="should have routed to code-review", severity="warn")
      d = r.to_dict()
      r2 = Reflection.from_dict(d)
      assert r2 == r
      assert r2.id == r.id

  def test_reflection_kind_must_be_valid():
      with pytest.raises((ValidationError, ValueError)):
          Reflection(target_type="x", target_id="y", task_id="z",
                    kind="invalid_kind", content="c")
  ```
- [ ] **7.2** Run — confirm fail.
- [ ] **7.3** Create `src/vibesop/observability/reflection.py`:
  ```python
  from dataclasses import dataclass, field
  from datetime import datetime, timezone
  from typing import Literal
  import uuid

  ReflectionKind = Literal[
      "routing_miss", "skill_misuse", "trigger_vague",
      "cost_blow", "agent_choice", "positive_pattern", "context_note",
  ]
  ReflectionStatus = Literal["open", "addressed", "dismissed"]
  TargetType = Literal["route_span", "skill_span", "task", "subagent", "decision_node"]

  @dataclass
  class Reflection:
      target_type: TargetType
      target_id: str
      task_id: str
      kind: ReflectionKind
      content: str
      severity: Literal["info", "warn", "critical"] = "info"
      id: str = field(default_factory=lambda: uuid.uuid4().hex)
      created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
      status: ReflectionStatus = "open"
      linked_action: dict | None = None

      def to_dict(self) -> dict: ...
      @classmethod
      def from_dict(cls, d: dict) -> "Reflection": ...

  __all__ = ["Reflection", "ReflectionKind", "ReflectionStatus", "TargetType"]
  ```
- [ ] **7.4** Run — confirm pass.
- [ ] **7.5** Commit: `feat(observability): Reflection dataclass — 7 kinds, status lifecycle, JSON round-trip`

### Task 8: `ReflectionStore` — append with cross-lock

- [ ] **8.1** Write failing test:
  ```python
  def test_reflection_store_append_round_trip(tmp_path):
      store = ReflectionStore(storage_dir=tmp_path)
      r = Reflection(target_type="task", target_id="t1", task_id="task-1",
                    kind="cost_blow", content="$0.50 vs $0.20 baseline")
      store.append(r)
      loaded = store.list_all()
      assert len(loaded) == 1
      assert loaded[0].id == r.id

  def test_reflection_store_concurrent_writes_safe(tmp_path):
      """Two threads appending 50 each → 100 lines, all parse correctly."""
      # threading.Barrier to align start
  ```
- [ ] **8.2** Run — confirm fail.
- [ ] **8.3** Implement `ReflectionStore` in `reflection.py`:
  ```python
  class ReflectionStore:
      FILENAME = "reflections.jsonl"
      def __init__(self, storage_dir: Path): ...
      def append(self, reflection: Reflection) -> None:
          # cross_process_lock + atomic jsonl append (pattern from SpanWriter._locked_append)
      def list_all(self) -> list[Reflection]: ...
  ```
  - File: `<storage_dir>/.vibe/observability/reflections.jsonl`
- [ ] **8.4** Run — confirm pass.
- [ ] **8.5** Commit: `feat(observability): ReflectionStore — append-only with cross-process lock`

### Task 9: `ReflectionStore` — query + status update

- [ ] **9.1** Write failing test:
  ```python
  def test_list_by_task_filters_correctly(...): ...
  def test_list_open_returns_only_open(...): ...
  def test_update_status_changes_state(...):
      store.append(r)
      store.update_status(r.id, "addressed")
      assert store.list_all()[0].status == "addressed"
  ```
- [ ] **9.2** Run — confirm fail.
- [ ] **9.3** Implement `list_by_task`, `list_open`, `update_status`. `update_status` rewrites the entire file atomically (read → mutate → AtomicWriter).
- [ ] **9.4** Run — confirm pass.
- [ ] **9.5** Commit: `feat(observability): ReflectionStore — list_by_task / list_open / update_status`

### Task 10: Plan↔Trace contract — Orchestrator wires PlanTracker (mandatory)

**Why:** **grok+pi P0-2**: This is the most underestimated risk. `PlanTracker` is fully implemented and writes complete `ExecutionPlan` to `.vibe/execution_plans.jsonl`. But `Orchestrator.orchestrate()` never calls it — only `_record_plan_sequence` (which writes instinct skill sequence, not the plan). Without this, `load_plans_for_trace()` returns empty → DAG rebuilder produces a flat tree with no step nodes, no dependency edges. Map view dependency edges literally cannot be rendered. **Same class of bug as v2's "Work Task 实体未定义".**

- [ ] **10.1** Read `src/vibesop/core/orchestration/plan_tracker.py` end-to-end. Document:
  - `create_plan()` signature
  - Where it writes (file path)
  - Whether `plan.metadata` is preserved
- [ ] **10.2** Write failing test `tests/core/orchestration/test_plan_tracker_trace_contract.py`:
  ```python
  def test_orchestrate_persists_plan_with_trace_id(tmp_path, monkeypatch):
      """After orchestrate() completes, .vibe/execution_plans.jsonl must
      contain a plan whose metadata.trace_id matches the active trace."""
      result = orchestrator.orchestrate("complex query")
      plans = load_jsonl(tmp_path / ".vibe/execution_plans.jsonl")
      matching = [p for p in plans if p["plan_id"] == result.plan.plan_id]
      assert matching
      assert matching[0]["metadata"]["trace_id"] is not None
      assert matching[0]["metadata"]["trace_id"] == result.trace_id

  def test_load_plans_for_trace_returns_only_matching(tmp_path):
      """Given 2 plans with different trace_ids, load_plans_for_trace
      returns exactly the matching one."""
      ...
  ```
- [ ] **10.3** Modify `orchestrator.py` completion phase (L303-333):
  ```python
  from vibesop.core.orchestration.plan_tracker import PlanTracker
  
  # After OrchestrationResult is built:
  tracker = PlanTracker(storage_dir=storage_dir)
  plan.metadata["trace_id"] = current_trace_id
  plan.metadata["orchestration_id"] = plan.plan_id  # for conversation JOIN
  tracker.create_plan(plan)
  ```
  - If `PlanTracker.create_plan()` doesn't accept metadata passthrough, add it.
- [ ] **10.4** Implement `load_plans_for_trace(trace_id, storage_dir) -> list[ExecutionPlan]` in `dag_rebuilder.py` (or `plan_tracker.py` if more natural). Filter by `metadata.trace_id == trace_id`.
- [ ] **10.5** Run — confirm both pass. Commit: `feat(orchestrator): wire PlanTracker.create_plan() with trace_id — JOIN contract for DAG rebuilder`

### Task 11: DAG rebuilder — load plans + build span tree

**Why:** First half of `rebuild_dag(trace_id)`. Depends on Task 10 (plans must have trace_id).

- [ ] **11.1** Write failing test `tests/observability/test_dag_rebuilder.py`:
  ```python
  def test_load_plans_for_trace_returns_matching_plans(tmp_path):
      """2 plans with different trace_ids → load returns only matching."""
      ...

  def test_build_span_tree_groups_by_parent(tmp_path):
      """spans with parent_span_id chain root→mid→leaf → nested tree."""
      ...
  ```
- [ ] **11.2** Run — confirm fail.
- [ ] **11.3** Create `src/vibesop/observability/dag_rebuilder.py`:
  ```python
  @dataclass
  class DAGNode:
      id: str
      kind: Literal["user_intent", "orchestrator", "plan", "step",
                    "sub_agent", "llm", "tool", "output"]
      label: str
      metadata: dict
      children: list[str] = field(default_factory=list)

  @dataclass
  class DAGEdge:
      src: str
      dst: str
      kind: Literal["parent_child", "dependency", "temporal", "error"]

  @dataclass
  class DAG:
      nodes: list[DAGNode]
      edges: list[DAGEdge]
      phases: list[dict]
      iterations: int

  def load_plans_for_trace(trace_id: str, storage_dir: Path) -> list[ExecutionPlan]: ...
  def build_span_tree(spans: list[dict]) -> dict[str, list[str]]: ...
  ```
  - Reuse tree logic from `trace_cmd.py:321-394` (`_render_trace_tree`).
- [ ] **11.4** Run — confirm pass.
- [ ] **11.5** Commit: `feat(observability): DAG rebuilder skeleton — load plans + build span tree`

### Task 12: DAG rebuilder — JOIN plan↔span + attach sub-agents

- [ ] **12.1** Write failing test:
  ```python
  def test_rebuild_dag_joins_plan_to_spans(tmp_path):
      """plan with step_id='s1' + 3 spans with task_id='s1' → step node 's1'
      has 3 span children (NOT the plan node)."""
      ...

  def test_rebuild_dag_attaches_subagent_via_parent_session(tmp_path):
      """main conversation with orchestration_id='plan-1' + mirror file with
      metadata.parent_session pointing to main → sub-agent attached to
      corresponding step."""
      ...
  ```
- [ ] **12.2** Run — confirm fail.
- [ ] **12.3** Implement `rebuild_dag(trace_id, storage_dir)`:
  1. `plans = load_plans_for_trace(trace_id)` (Task 10)
  2. `spans = load_spans_for_trace(trace_id)`; `span_tree = build_span_tree(spans)`
  3. For each plan, for each step: `step.spans = [s for s in spans if s.task_id == step.step_id]` — **must be step_id, never plan_id**
  4. Load conversations; for each `is_subagent=True`: find parent via `parent_session` (Task 6 ensures this resolves) → attach to corresponding step's span
  5. Build `DAG` (nodes + edges + phases + iterations)
- [ ] **12.4** Run — confirm pass.
- [ ] **12.5** Commit: `feat(observability): rebuild_dag() — JOIN via step_id + parent_session contract`

### Task 13: Fixture-based E2E integration test (ZERO LLM)

**Why:** **grok+pi P0-4**: Real LLM in CI = $0.05-0.20 per run, flaky, slow. The E2E is testing the **data pipeline** (plan → spans → mirror → rebuild_dag), not LLM routing quality. Use pre-constructed fixtures.

- [ ] **13.1** Write `tests/observability/test_dag_rebuilder_e2e.py`:
  ```python
  def test_full_pipeline_with_fixtures(tmp_path):
      """End-to-end using pre-built fixtures (NO LLM calls):
      - fixture execution_plans.jsonl: 1 plan with trace_id='T1' + 3 steps
        with step_ids s1/s2/s3 and dependencies [[], [s1], [s1, s2]]
      - fixture spans.jsonl: workflow_node spans (phases) + llm spans with
        task_id matching s1/s2/s3
      - fixture mirror-*.json: 2 sub-agent conversations with
        metadata.parent_session resolving to parent conv
      Then rebuild_dag('T1') must return:
      - >= 1 user_intent node
      - >= 1 orchestrator node with 5+ phase children
      - exactly 3 step nodes (s1/s2/s3)
      - dependency edges: s1→s2, s1→s3, s2→s3
      - 2 sub_agent nodes attached to corresponding steps
      - iterations == 1
      """
      # write fixtures
      dag = rebuild_dag(trace_id="T1", storage_dir=tmp_path)
      # assert structure
  ```
- [ ] **13.2** Run — likely fails on missing pieces (e.g., Task 12 attach logic, fixture format). Iterate until green.
- [ ] **13.3** Once fixture E2E passes, run full suite:
  ```bash
  uv run pytest -m "not benchmark and not slow"
  uv run ruff check src/ tests/
  uv run basedpyright src/
  ```
- [ ] **13.4** **Manual smoke** (optional, not in default CI):
  ```bash
  echo "complex multi-intent query" | vibe orchestrate
  # verify .vibe/execution_plans.jsonl has new plan with trace_id
  # verify .vibe/observability/spans.jsonl has llm spans with step-level task_id
  # run rebuild_dag via python -c "..."
  ```
- [ ] **13.5** Commit: `test(observability): fixture-based E2E for orchestrate → mirror → rebuild_dag (zero LLM)`

---

## Verification checklist (Phase A done when all green)

- [ ] All 13 task commits landed
- [ ] `uv run pytest` — existing 4434+ tests pass + ~50 new tests pass
- [ ] `uv run ruff check src/ tests/` — 0 errors
- [ ] `uv run basedpyright src/` — 0 errors (4 pre-existing warnings OK)
- [ ] **Real-data DAG smoke** (replaces fill-rate metric):
  - [ ] `vibe orchestrate "complex multi-intent query"` → `.vibe/execution_plans.jsonl` new plan with `metadata.trace_id` non-null
  - [ ] `.vibe/observability/spans.jsonl` has **at least one llm span whose `task_id` equals a `step.step_id`** (NOT plan_id — this is the P0-1 contract)
  - [ ] Trigger a real session with sub-agents → `mirror-*.json.metadata.parent_session` resolves to parent conversation_id
  - [ ] **`rebuild_dag(trace_id)`** returns DAG with: ≥1 user_intent + ≥1 orchestrator + ≥2 step + dependency edges + sub_agent attachment
  - [ ] **This is the main gate.** Fill rate is informational only.

---

## Review trail (grok+pi CONDITIONAL — absorbed)

Original 4 self-admitted risks **all underestimated** per grok+pi:

| Risk | Original plan attitude | Revised after review |
|------|------------------------|---------------------|
| R1 task_id fallback | "Acceptable degradation" | **Removed** (P0-1). Step-level binding is mandatory. |
| R2 mirror no Python entry | "Add CLI subcommand" | **Misdiagnosed** (P0-3). Shell hook already calls `vibe conversation import-claude`; real fix is `--include-subagents` flag + parent_session contract test. |
| R3 execution_plans.jsonl may not exist | "Optional Task 11.5" | **Mandatory** (P0-2 → Task 10). File exists via PlanTracker; Orchestrator never calls it. Same class as v2's "Work Task 实体未定义". |
| R4 discover_subagents needs trace_id filter | "Optional param" | Demoted to Nit. Real gap is `plan.trace_id` (covered by Task 10). |

Additional grok+pi findings absorbed:
- P1-1: Task 1 extends existing `current_task_id` (no new ContextVar)
- P1-2: Task 10 (AgentPrefs) deferred to Phase E → replaced by new Task 10 (Plan↔Trace contract)
- P1-3: Top-level "Data Boundary" section added (in-process vs cross-process)
- Nit-1: Task 5 adds `conversation_id` param to `orchestrate()`

---

## What's next (Phase B preview)

Once Phase A is green:
- **Phase B** (Dashboard P0): HTTP endpoints `/api/orchestration/dag?trace_id=<id>`, `/api/reflections` (POST/GET/PATCH). Render Live → Latest Task with Decision Path narrative.
- **Phase C** (Dashboard P1): Vite + vanilla TS, Cytoscape.js + ELK, cmd+k, Map view toggle.
- **Phase D** (Reflection P0 UI): inline reflection panel + 7-type radio + `r` shortcut. Consumes Task 7-9 ReflectionStore.
- **Phase E** (Reflection closed loop + AgentPrefs): depends on v8.2 P2 InsightAnalyzer. Includes Task 10 (AgentPrefsStore) deferred from this plan.

Phase B/C/D/E plans written separately as their prerequisites firm up.
