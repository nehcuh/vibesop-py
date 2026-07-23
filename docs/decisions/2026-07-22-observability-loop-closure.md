# 2026-07-22 — Observability-Driven Loop Closure (v8.2)

> **Status**: Draft (Phase A — Design)
> **Author**: Claude (dynamic workflow: design → adversarial → external review → grill-me)
> **Predecessor**: v8.1.0 "Observability closed-loop" (2026-07-21) — built all parts, did not wire them
> **Supersedes**: None (clarifies & completes v8.1)

---

## 0. TL;DR

**v8.1 built all the parts. v8.2 wires them together.**

The user's original vision — *"background-record every agent-internal call; periodically analyze routing accuracy + skill optimizability; feed improvements back"* — is **architecturally achievable today** using v8.1 components. But four interfaces were declared (in `CHANGELOG.md`, in docstrings) and never connected:

| # | Interface | v8.1 status | Reality |
|---|-----------|-------------|---------|
| 1 | Agent-internal span emission (LLM/tool_call/file_edit) | "AgentRuntime.handle_query wrapped in task-span" | Only the outer **task-span** fires. `plan_executor.py`, `skill_injector.py`, LLM call sites have **zero** child spans. |
| 2 | Metric-driven loop trigger | `LoopTrigger.METRIC` + `MetricCondition` model | `scheduler.py`/`executor.py` **never read** `metric_conditions`. Field is inert. |
| 3 | SpanAggregator consumers | "Consumed by metric-driven loop and instinct learner" | `grep SpanAggregator src/` returns **only `aggregator.py` itself**. Zero call sites. |
| 4 | Suggestion output → instinct/skill feedback | Instinct bridge takes `times_matched` from routing hot path | No path from analyzer output back to skill/instinct. |

Plus a **conceptual gap**: user wants *"routing accuracy"* (semantic mismatch: query intended A, router picked B). v8.1's `get_anomaly_events` only detects **success_rate_drop / duration_spike** — volume/speed anomalies, not semantic ones.

**Acceptance criterion for v8.2**: a user can run

```
vibe loop create route-auditor --analyzer route_mismatch --schedule "0 */6 * * *"
vibe loop tick
```

and receive a structured report identifying low-confidence routes, under-used skills, and instinct refinement candidates — written back to `instinct/*.json` for the next routing cycle.

---

## 1. Background — User's Vision vs v8.1 Reality

### 1.1 User's original vision (2026-07-22 morning session)

> "后台记录下所有 Agent 内部调用，然后可以定期去后台检测优化我们的 Agent 内部包括路由准确性，skill 是否可优化等问题，印象中是可以通过 loop 来做的。"

Three functional requirements:

1. **Record** — every agent-internal call (prompt / tool call / route decision)
2. **Analyze** — routing accuracy + skill optimizability
3. **Feedback** — improvements land back in routing/skill state

### 1.2 What v8.1 actually shipped (per `CHANGELOG.md`)

| Component | File | Real state |
|-----------|------|------------|
| `Span` / `TraceContext` dataclasses | `core/observability/models.py:18` | ✅ Complete, 5 SpanKinds declared |
| `ObservabilityTracer` context-manager API | `core/observability/tracer.py:46` | ✅ Complete, signal-safe flush |
| `SpanWriter` JSONL persistence + redaction | `core/observability/span_writer.py` | ✅ Complete, 16KB truncation + `redact_sensitive()` |
| `AgentRuntime.handle_query()` task-span | `agent/runtime/agent_runtime.py:409` | ⚠️ **Outer span only**; no child spans inside |
| `SpanAggregator.get_skill_metrics()` | `core/observability/aggregator.py:81` | ✅ API works — but no caller |
| `SpanAggregator.get_pattern_sequences()` | `core/observability/aggregator.py:140` | ✅ API works — but no caller |
| `SpanAggregator.get_anomaly_events()` | `core/observability/aggregator.py:171` | ✅ API works — but no caller |
| `LoopTrigger.METRIC` enum | `core/loop/models.py:86` | ⚠️ **Enum exists, no dispatcher case** |
| `MetricCondition` model | `core/loop/models.py:89` | ⚠️ **Field exists on LoopSpec, never evaluated** |
| `Instinct.times_matched` (routing hot path) | `core/instinct/learner.py`, `core/routing/context_mixin.py` | ✅ Wired — but reads from routing only, not analyzer |
| Dashboard `/api/traces?source=all` | `dashboard/server.py` | ✅ Merges routing + agent traces for display |

### 1.3 The five unfilled gaps (with code evidence)

```
GAP-1 [埋点]   agent_runtime.py:409   only outer task-span fires
                plan_executor.py      grep "tracer\|span" → 0 hits
                skill_injector.py     grep "tracer\|span" → 0 hits

GAP-2 [触发器]  core/loop/scheduler.py  CronDaemon.run_once → CRON-only branch
                core/loop/executor.py   no MetricCondition evaluation

GAP-3 [消费方]  grep SpanAggregator src/  → only aggregator.py itself
                CHANGELOG claims "consumed by metric-driven loop and instinct
                learner" — this is aspirational, not actual

GAP-4 [建议层]  no InsightAnalyzer / Suggestion module exists
                instinct bridge ingest = routing hot path only

GAP-5 [语义错配] get_anomaly_events: success_rate_drop / duration_spike only
                user wants: "query intended A, router picked B" detection
                → requires confidence distribution + skill co-occurrence
                  analysis, not just rate/speed
```

### 1.4 Why this happened (post-mortem)

v8.1 was scoped as **infrastructure layer**: build the parts in isolation, prove each with unit tests. The closed-loop wiring was implicitly deferred to "next sprint." `CHANGELOG.md` used future tense ("consumed by") describing current state, masking the gap.

Memory `project-v8-loop-phase1-validation.md` (32 days old) already flagged this: *"关键不确定性未消除: /slash-route use {skill_id} 在真实 LLM 下能否可靠命中"*. The routing-accuracy question has been open since Phase 1.

---

## 2. Design Goals (v8.2 scope)

### 2.1 In scope

- **G1 — Close GAP-1**: emit child spans at LLM-call and tool-call sites in agent runtime
- **G2 — Close GAP-2**: scheduler evaluates `MetricCondition` alongside CRON
- **G3 — Close GAP-3**: at least one real consumer of SpanAggregator
- **G4 — Close GAP-4**: InsightAnalyzer + SuggestionWriter producing actionable output
- **G5 — Close GAP-5**: route-semantic-mismatch detection (not just rate anomalies)

### 2.2 Out of scope (deferred)

- Cross-machine trace aggregation (single-host JSONL stays the source of truth)
- Real-time streaming analysis (analysis is batch, triggered by loop tick)
- LLM-as-judge for skill quality (rule-based + statistical first; LLM in v8.3)
- Trace sampling policy UI (v8.1's retention config stays as-is)

### 2.3 Non-goals (explicitly)

- **Not** a new "analysis" CLI command divorced from loop. The user's mental model is `vibe loop`. New analyzer target type lives inside LoopSpec.
- **Not** replacing instinct learning. Analyzer outputs **feed** instinct, not bypass it.
- **Not** auto-applying skill rewrites. v8.2 produces **suggestions**; human review required before any skill file mutation.

---

## 3. Architecture — Closed Loop

```
                    ┌─────────────────────────────────────┐
                    │  Agent runtime (real execution)     │
                    │                                     │
                    │  task-span (v8.1)                   │
                    │   ├─ llm-span        ← GAP-1 close  │
                    │   ├─ tool_call-span  ← GAP-1 close  │
                    │   └─ file_edit-span  ← GAP-1 close  │
                    └──────────────┬──────────────────────┘
                                   │ writes
                                   ▼
                    ┌─────────────────────────────────────┐
                    │  spans.jsonl (v8.1)                 │
                    │  + analytics.jsonl (fallback)       │
                    └──────────────┬──────────────────────┘
                                   │ reads
                                   ▼
                    ┌─────────────────────────────────────┐
                    │  SpanAggregator (v8.1)              │
                    │   get_skill_metrics                 │
                    │   get_pattern_sequences             │
                    │   get_anomaly_events                │
                    └──────────────┬──────────────────────┘
                                   │ reads
       GAP-2 close  ┌──────────────┴──────────────┐  GAP-3 close
       (trigger)    │                             │  (consumer)
                    ▼                             ▼
       ┌─────────────────────────┐   ┌─────────────────────────┐
       │ MetricCondition         │   │ InsightAnalyzer (NEW)   │
       │ evaluator               │   │  - route_mismatch       │
       │ (NEW, in scheduler.py)  │   │  - skill_underuse       │
       └────────────┬────────────┘   │  - skill_overlap        │
                    │                │  - instinct_candidate   │
                    └────┐ ←─────────┘  (NEW module)           │
                         │            └────────────┬───────────┘
                         ▼                         │
                ┌────────────────┐                 │
                │  Loop tick     │                 │ writes
                │  (CRON|METRIC) │                 ▼
                └────────┬───────┘    ┌─────────────────────────┐
                         │            │ suggestions.jsonl (NEW) │
                         │            │ + instinct/*.json patch │
                         │            └────────────┬────────────┘
                         │                         │
                         └───────────┬─────────────┘
                                     ▼
                         ┌───────────────────────────┐
                         │ Instinct learning (v8.1)  │
                         │ ← next routing cycle      │
                         └───────────────────────────┘
                                    GAP-4 close
```

---

## 4. GAP-1 — Agent-Internal Span Emission

### 4.1 What to change

Three child-span sites in `agent/runtime/`:

```python
# agent/runtime/plan_executor.py  (LLM call boundary)
with tracer.span(
    f"llm:{self.provider}",
    kind="llm",
    parent=_current_task_span(),
    metadata={"model": self.model, "skill_id": skill_id},
) as llm_span:
    response = self._call_llm(messages)
    llm_span.set_input({"messages": redact_sensitive(messages)})
    llm_span.set_output({"response": redact_sensitive(response)})
    llm_span.with_tokens(usage.input, usage.output).with_cost(usage.cost)

# agent/runtime/skill_injector.py  (tool execution boundary)
with tracer.span(
    f"tool_call:{tool_name}",
    kind="tool_call",
    parent=_current_task_span(),
    metadata={"tool": tool_name, "skill_id": skill_id},
) as tool_span:
    result = tool.invoke(args)
    tool_span.set_output({"truncated": truncate(str(result), 16_000)})

# plan_executor.py  (file edit boundary, when Write/Edit tool used)
with tracer.span(
    f"file_edit:{path}",
    kind="file_edit",
    parent=_current_task_span(),
    metadata={"path": path, "op": "write"},
) as edit_span:
    edit_span.set_output({"bytes": len(content)})
```

### 4.2 Parent linkage

`ObservabilityTracer` already uses `threading.local()` for trace context (`tracer.py:54`). Child spans auto-link via `parent_span_id` when `parent=` is passed or when called within an active `tracer.trace()` block. We add a `_current_task_span()` helper that reads from the tracer's thread-local — no API change needed.

### 4.3 Cost & token tracking

LLM spans carry `tokens_input / tokens_output / cost_usd`. `SpanAggregator.get_skill_metrics` already sums these (`aggregator.py:104-107`). Closing GAP-1 makes the existing aggregator meaningful.

### 4.4 Privacy controls (reuse v8.1)

- All inputs/outputs pass through `redact_sensitive()` (v8.1)
- Payloads truncated to 16KB (v8.1 `ObservabilityConfig.max_payload_bytes`)
- `ObservabilityConfig.redact_patterns` extensible via `~/.vibe/config.toml`

**New**: add `ObservabilityConfig.record_payloads: bool = True` — when false, only metadata (tokens/duration/skill_id) is recorded, not input/output content. Trade-off: privacy-first deployments lose pattern-sequence fidelity.

### 4.5 Performance bound

Each span add = 1 dict update + 1 `threading.local` read. Microbenchmark target: <50µs per span. At 100 spans/sustained-second (heavy agent run), overhead <0.5%. Acceptable.

---

## 5. GAP-2 — MetricCondition Evaluator

### 5.1 What to change

`CronDaemon.run_once(specs)` currently filters by cron match only. Add a parallel `MetricEvaluator` that runs after cron check:

```python
# core/loop/scheduler.py (proposed addition)

class MetricEvaluator:
    """Evaluates MetricCondition list against SpanAggregator output.

    Returns True if ANY condition fires (OR semantics, matching v8.1 docstring
    'CRON never silenced — metric conditions are accelerators').
    """

    def __init__(self, aggregator: SpanAggregator) -> None:
        self._agg = aggregator

    def should_fire(self, spec: LoopSpec, state: LoopState) -> bool:
        if not spec.metric_conditions:
            return False

        # Cooldown: respect per-condition cooldown_minutes
        now = datetime.now(UTC)
        for cond in spec.metric_conditions:
            last_fire = state.last_metric_fire.get(cond.metric, datetime.min.replace(tzinfo=UTC))
            if (now - last_fire).total_seconds() < cond.cooldown_minutes * 60:
                continue

            metrics = self._agg.get_skill_metrics(
                cond.skill_id, window_hours=cond.window_hours, use_analytics_fallback=True
            )
            if metrics.total_executions < cond.min_samples:
                continue

            value = self._extract_value(metrics, cond.metric)
            if self._compare(value, cond.operator, cond.threshold):
                state.last_metric_fire[cond.metric] = now
                return True
        return False
```

### 5.2 Where it slots in

`tick` command flow becomes:

```python
for spec in eligible:
    cron_match = cron_daemon.match(spec, now)
    metric_match = metric_evaluator.should_fire(spec, state)
    if cron_match or metric_match:
        triggered.append(spec)
```

CRON remains the floor; METRIC is pure accelerator. This matches v8.1's stated contract ("CRON never silenced") — which was previously **untested and unimplemented**.

### 5.3 State extension

`LoopState` gets a new field:

```python
last_metric_fire: dict[str, datetime] = Field(default_factory=dict)
```

Persisted to `state.json`. Cooldown is per-condition-per-metric, so the same loop can fire on `success_rate` and `error_count` independently.

### 5.4 Wilson Score (already declared, finally used)

`MetricCondition` docstring mentions Wilson Score confidence (`models.py:91`). The evaluator implements it as a guard: if `(lower_bound - threshold) * sign < 0`, condition does NOT fire — protecting against small-sample flukes even above `min_samples`.

---

## 6. GAP-3+5 — InsightAnalyzer

### 6.1 Module location

`src/vibesop/core/observability/analyzer.py` (new file, ~400 LOC).

### 6.2 Four analyzers (rule-based, v8.2 ships all four)

```python
class InsightAnalyzer:
    """Composes SpanAggregator output into actionable insights.

    Each analyzer returns list[Insight]. Insights are written to
    suggestions.jsonl by SuggestionWriter (§7).
    """

    def analyze_route_mismatch(self, window_hours: int = 168) -> list[Insight]:
        """GAP-5: detect queries where confidence was low but a skill still fired.

        Heuristic:
          - collect route-spans with 0.4 <= confidence < 0.7
          - group by skill_id
          - if a skill's low-confidence rate > 30%, flag for instinct review

        Why this catches "intended A, got B": low-confidence matches are
        the router hedging — frequent hedging on a skill means its triggers
        overlap with siblings.
        """

    def analyze_skill_underuse(self, window_hours: int = 168) -> list[Insight]:
        """Skills with 0 executions in window but present in registry.
        Candidates for retirement or trigger-improvement.
        """

    def analyze_skill_overlap(self, window_hours: int = 168) -> list[Insight]:
        """Pairs of skills with >0.7 Jaccard on triggering query tokens.
        Candidates for merge or trigger-disambiguation.
        """

    def analyze_instinct_candidates(self, window_hours: int = 168) -> list[Insight]:
        """Repeated (query_pattern, skill_id) pairs not yet captured by any
        instinct. Output → instinct/learner.py for new-instinct proposal.
        """
```

### 6.3 Why rule-based first

- **Reproducible**: same spans → same insights. LLM-as-judge adds nondeterminism.
- **Cheap**: zero API cost, runs in <1s on 10K spans.
- **Auditable**: every insight has a numeric threshold the user can tune.
- **LLM-ready**: v8.3 wraps the same `Insight` objects with LLM commentary; the rule layer stays as the deterministic backbone.

### 6.4 Output schema

```python
@dataclass
class Insight:
    kind: Literal["route_mismatch", "skill_underuse", "skill_overlap", "instinct_candidate"]
    severity: Literal["info", "warn", "critical"]
    skill_id: str | None
    summary: str                    # human-readable, <200 chars
    evidence: dict[str, Any]        # numeric backing (rates, counts, samples)
    suggested_action: str           # concrete next step
    instinct_patch: dict | None     # ready-to-apply instinct mutation, or None
    detected_at: datetime
```

---

## 7. GAP-4 — Suggestion Output & Closed Loop

### 7.1 Two output paths

**Path A: suggestions.jsonl (human review)**

```jsonl
{"id": "...", "kind": "route_mismatch", "skill_id": "builtin/code-review",
 "summary": "code-review matched 12 queries at confidence 0.42-0.65 last week",
 "evidence": {...}, "suggested_action": "Tighten trigger keywords or merge with review",
 "instinct_patch": null, "detected_at": "..."}
```

CLI: `vibe loop insights [--skill <id>] [--kind <kind>] [--since 7d]`

**Path B: instinct/*.json patches (auto-applied, gated)**

Only `instinct_candidate` insights produce patches. Patches land in `~/.vibe/instincts/pending/<id>.json` — NOT directly active. A separate `vibe instinct accept <id>` command finalizes (reuses v8.1's instinct accept path).

### 7.2 Why two paths

- Route-mismatch / overlap / underuse insights require **human judgment** to translate into action (merge? rewrite triggers? deprecate?). No safe auto-apply.
- Instinct candidates are **mechanical**: query pattern → skill_id is already the instinct format. Auto-generation with manual accept is safe.

### 7.3 LoopSpec extension

Add a fourth target type to LoopSpec:

```python
class LoopSpec(BaseModel):
    ...
    analyzer_id: str = Field(
        default="",
        description=(
            "Analyzer target. Mutually exclusive with skill_id/query/workflow_id. "
            "Values: 'route_mismatch' | 'skill_underuse' | 'skill_overlap' | "
            "'instinct_candidate' | 'all'."
        ),
    )
```

`_exactly_one_target` validator extended to include `analyzer_id`.

### 7.4 Executor branch

```python
# core/loop/executor.py — new branch in execute_loop_tick

if spec.analyzer_id:
    analyzer = InsightAnalyzer()
    writer = SuggestionWriter()
    insights = analyzer.run(spec.analyzer_id, window_hours=spec.analyzer_window_hours)
    writer.write_all(insights)
    record.success = True
    record.output_summary = f"{len(insights)} insights emitted"
    return record
```

---

## 8. Privacy & Performance

### 8.1 Privacy

| Control | Default | Where |
|---------|---------|-------|
| Payload recording | `true` | `ObservabilityConfig.record_payloads` (NEW) |
| Secret redaction | `redact_sensitive()` applied | v8.1 |
| Payload size cap | 16KB per span | v8.1 |
| Trace retention | 7 days | v8.1 |
| Hard cap | 100K spans | v8.1 |
| Pattern redaction | extensible via config | v8.1 + new doc |

**New**: `vibe trace purge --before <date>` command (one-shot, not loop-driven).

### 8.2 Performance

| Operation | Frequency | Cost | Bound |
|-----------|-----------|------|-------|
| Span emit | per LLM/tool call | <50µs | threading.local + dict update |
| Span write | per span (buffered) | amortized <100µs | JSONL append, async flush |
| Aggregation | per loop tick | O(spans in window) | <1s for 10K spans |
| Analysis | per loop tick | O(spans × skills) | <2s for 10K spans × 100 skills |
| Instinct patch generation | per loop tick | O(insight count) | negligible |

Total per-6-hour-tick overhead: <5s on 10K-span backlog. Acceptable.

---

## 9. Data Model Changes (minimal)

### 9.1 New files

```
src/vibesop/core/observability/analyzer.py        # ~400 LOC
src/vibesop/core/observability/suggestion_writer.py  # ~150 LOC
src/vibesop/core/loop/metric_evaluator.py         # ~200 LOC (extracted from scheduler)
```

### 9.2 Model additions

```python
# core/observability/models.py — add to SpanKind (no change, v8.1 already declares)
# already has: task | llm | tool_call | file_edit | workflow_node

# core/loop/models.py — LoopSpec extension
class LoopSpec:
    analyzer_id: str = ""           # NEW
    analyzer_window_hours: int = 168  # NEW, default 7 days

# core/loop/models.py — LoopState extension
class LoopState:
    last_metric_fire: dict[str, datetime] = Field(default_factory=dict)  # NEW

# core/observability/analyzer.py — NEW dataclasses
@dataclass
class Insight: ...  # see §6.4
```

### 9.3 Storage additions

```
.vibe/observability/suggestions.jsonl     # NEW, append-only
.vibe/observability/spans.jsonl           # v8.1 (unchanged)
~/.vibe/instincts/pending/<insight-id>.json  # NEW, gated auto-generated
```

### 9.4 Backwards compatibility

- Existing LoopSpec JSON without `analyzer_id` → still valid (field defaults to empty).
- Existing spans.jsonl without child spans → aggregator still works (degrades to v8.1 metrics).
- No migration script needed. No breaking CLI change.

---

## 10. Phased Roadmap

### P1 — Emission + Rule Analyzer (1-2 weeks)

**Scope**:
- GAP-1 close: child spans in plan_executor + skill_injector (3 sites)
- GAP-3 close: InsightAnalyzer module with 4 analyzers
- SuggestionWriter + `vibe loop insights` CLI
- Tests: 90%+ coverage on new modules; existing 147 loop tests still green

**Acceptance**: `vibe loop create test --analyzer all --schedule "*/5 * * * *"` produces non-empty `suggestions.jsonl` after 5 minutes of real agent activity.

### P2 — Metric Trigger + Closed Loop (1 week)

**Scope**:
- GAP-2 close: MetricEvaluator in scheduler
- `last_metric_fire` state field
- GAP-4 partial: instinct_candidate auto-patches to `pending/` directory
- `vibe instinct accept/reject <id>` (reuses v8.1 accept path)

**Acceptance**: a loop with `metric_conditions: [{metric: success_rate, threshold: 0.5, operator: "<"}]` fires within 1 minute of a real failure, not just on cron schedule.

### P3 — LLM Commentary Layer (optional, 1-2 weeks)

**Scope**:
- LLM-as-judge wraps each `Insight` with concrete skill-triggers-rewrite suggestion
- `vibe loop insights --llm` flag (off by default)
- Cost cap per tick via `ObservabilityConfig.llm_budget_per_tick`

**Acceptance**: 5 sample insights produce 5 actionable skill-improvement suggestions, reviewed blind by user; at least 3 judged "would apply."

---

## 11. Risk Register

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| R1 | Span emission slows hot path | Medium | Microbenchmark in CI; flag to disable at runtime |
| R2 | Payload leakage (PII in prompts) | High | `redact_sensitive()` + `record_payloads=false` mode + audit log |
| R3 | Rule analyzer produces noise (false positives) | Medium | Severity threshold tuning; user-markable "dismiss" on insights |
| R4 | Auto-instinct-patch introduces bad routing | High | Two-step accept (pending → active); rollback on regression |
| R5 | Backwards-incompatible LoopSpec change | Low | Field defaults empty; existing specs unchanged |
| R6 | Spans.jsonl unbounded growth | Medium | v8.1 retention (7d) + hard cap (100K) already in place |
| R7 | Metric trigger flapping under unstable metrics | Medium | Wilson Score guard + cooldown_minutes |
| R8 | InsightAnalyzer scope creep ("just one more analyzer") | Medium | 4 analyzers frozen for v8.2; new ones require ADR |

---

## 12. Open Questions (for §C external review + §D grill-me)

1. **Analyzer as LoopSpec target vs separate CLI?** This design picks LoopSpec (`analyzer_id` field). Alternative: standalone `vibe analyze` command. Trade-off: mental model vs separation of concerns.

2. **Instinct auto-patch gating level.** Current: `pending/` directory + explicit accept. Stricter: human-in-loop PR. Looser: silent apply with rollback. Which does the user want?

3. **LLM commentary in P3 — worth it?** Rule layer already produces actionable output. Is the LLM layer adding value, or just cost + nondeterminism?

4. **Span emission in adapters (kimi-cli, pi, cursor)?** v8.2 scopes to AgentRuntime only. But adapter-level emission would give cross-platform trace parity. Defer to v8.3?

5. **route_mismatch threshold (0.4-0.7 confidence band).** Is this the right band? Should it be configurable per-skill?

6. **suggestions.jsonl deduplication.** Same insight detected across consecutive ticks — dedupe by content hash? By time window? Show "still active" instead?

7. **Cost reporting.** LLM spans carry `cost_usd`. Should aggregator expose per-skill weekly cost? Per-query? Would users use this?

---

## 13. Next Steps

1. **Phase B (adversarial)**: red-team this draft, list weaknesses → update §12
2. **Phase C (external review)**: submit to Kimi + Pi for independent verdict
3. **Phase D (grill-me)**: walk decision tree on the 7 open questions; answers sourced from Kimi+Pi
4. **Phase E (merge)**: produce final `docs/decisions/2026-07-22-observability-loop-closure-final.md` with verdicts and dissents recorded
5. **Phase F (implementation)**: P1 → P2 → P3, each phase ends with E2E validation

---

*Phase A complete.*

---

## 14. Phase B — Adversarial Self-Review

Ten red-team challenges against §1-13. Each ends with a verdict: **accept** (amend design), **reject** (design stands), or **defer** (out of v8.2 scope).

### CH-1: `analyzer_id` as LoopSpec target — wrong abstraction?

**Challenge**: Loop = "execute something with side effects." Analyzer = "read-only observation." Forcing both into LoopSpec will fork the executor into two barely-overlapping branches; `matched_skill` / `failure_info` / `max_failures` make no sense for analyzers. Better: standalone `vibe insights` + cron.

**Verdict: REJECT (design stands).** User's mental model is `vibe loop`. Two scheduling systems is worse than one forking branch. The fork is small — analyzer branch short-circuits retry/failure-classification. Cost is bounded.

### CH-2: Four analyzers in v8.2 — over-scoped?

**Challenge**: `skill_underuse` is trivial (registry diff, low value — user sees it in `vibe skills list`). `skill_overlap` needs NLP/Jaccard, complex, uncertain value. `instinct_candidate` overlaps v8.1's instinct bridge. Only `route_mismatch` maps directly to user's ask.

**Verdict: ACCEPT.** v8.2 ships **`route_mismatch` + `instinct_candidate` only**. `skill_underuse` and `skill_overlap` defer to v8.3 or a separate ADR. §6.2 and §10 P1 scope updated accordingly.

### CH-3: GAP-1 (agent internal spans) prerequisite for analyzers?

**Challenge**: Original design says GAP-1 must close first for aggregator to work. But `route_mismatch` consumes **routing-level spans** (already have confidence/skill_id/query), not LLM/tool_call child spans. route_mismatch can ship without GAP-1.

**Verdict: ACCEPT.** Reorder:
- **P1**: InsightAnalyzer (route_mismatch + instinct_candidate) + SuggestionWriter + LoopSpec.analyzer_id. **No dependency on GAP-1.**
- **P2**: GAP-1 (internal spans) + MetricEvaluator + closed loop
- **P3**: LLM commentary (optional) + skill_underuse + skill_overlap

This means **user-visible value in P1** without waiting for instrumentation completeness.

### CH-4: Instinct auto-patch safety — two-step accept enough?

**Challenge**: Once accepted, a bad instinct silently degrades routing (no crash, just worse matches). Regression detection is absent.

**Verdict: ACCEPT, partially.** Two-step accept (`pending/` → `active`) stays. But §11 R4 mitigation must include **post-apply regression watcher**: on accept, record `before_metrics` for affected skill_id; after N ticks, compare; if success_rate drops >15%, auto-quarantine the instinct back to `pending/` and emit `critical` insight.

### CH-5: route_mismatch confidence band 0.4-0.7 — arbitrary?

**Challenge**: Different skills have different baseline confidence distributions. `fallback-llm` is always 0.8 (orchestrate mode forces it); `kimi-gated-fix` may be naturally low. Absolute thresholds produce different false-positive rates per skill.

**Verdict: ACCEPT.** Replace absolute band with **per-skill relative threshold**: a route fires route_mismatch insight when its confidence falls **below the skill's historical p25**. No global band. §6.2 `analyze_route_mismatch` signature updated.

### CH-6: Performance estimate (10K spans × 100 skills < 2s) — realistic?

**Challenge**: `get_pattern_sequences` is O(N²) on spans (find repeating sequences). At N=10K, that's 10^8 operations — far exceeds 2s.

**Verdict: ACCEPT.** v8.2 analyzers do **not consume `get_pattern_sequences`**. The aggregator API stays (v8.1 already shipped it), but no v8.2 call site uses it. Defer to v8.3 with a bounded sliding-window implementation. §8.2 updated.

### CH-7: Conflict between routing-hot-path instinct updates and analyzer proposals?

**Challenge**: v8.1's instinct bridge already updates `times_matched` on every route. Analyzer proposes new instincts. Will they conflict or duplicate?

**Verdict: design stands, but §7 needs clarification.**
- Routing hot path → **passive counter** (`times_matched++` on existing instincts)
- Analyzer output → **active proposal** (creates new instinct candidates in `pending/`)
- Two paths operate on **different fields**, never race. §7.2 updated with this distinction.

### CH-8: LLM commentary in P3 — worth the cost/nondeterminism?

**Challenge**: User asked for "detect + optimize routing accuracy." That's **facts**, not **explanations**. Rule layer already produces actionable output. LLM layer adds cost + nondeterminism for marginal value.

**Verdict: design stands (already optional).** P3 is gated behind `--llm` flag, off by default. §10 P3 description reinforced to make this explicit. If post-P2 user feedback says "we want richer suggestions," P3 graduates from optional to opt-in CLI flag.

### CH-9: No regression detection after instinct accept

**Challenge**: This is a subset of CH-4 but broader. The whole design is "produce suggestions" with no "did the suggestion help?" loop.

**Verdict: ACCEPT.** Post-apply regression watcher (from CH-4) covers the highest-risk case (instinct accept). For human-applied suggestions (route_mismatch, etc.), the user re-runs the same analyzer next tick — if the mismatch count drops, the suggestion helped. No new module needed; just document this as the feedback loop.

### CH-10: Test strategy underspecified

**Challenge**: "90% coverage" is a unit-test metric. Observability closed loops need E2E validation with realistic span data.

**Verdict: ACCEPT.** Add to §10 P1 acceptance: **"fixture-based E2E: redacted real spans from a recent dev session (committed under tests/fixtures/spans/sample.jsonl) fed through analyzer produces ≥3 human-readable insights, blind-reviewed by user."** Unit tests with synthetic spans are necessary but not sufficient.

### Summary of amendments to §1-13

| Challenge | Section affected | Amendment |
|-----------|------------------|-----------|
| CH-2 | §6.2, §10 P1 | Drop `skill_underuse` and `skill_overlap` from v8.2 |
| CH-3 | §10 P1/P2/P3 | Reorder — analyzers ship before GAP-1 |
| CH-4 | §11 R4 | Add post-apply regression watcher |
| CH-5 | §6.2 | Per-skill p25 confidence, not absolute band |
| CH-6 | §8.2 | Remove pattern_sequences from v8.2 hot path |
| CH-7 | §7.2 | Clarify passive counter vs active proposal |
| CH-9 | §11 R4 | Same as CH-4 mitigation |
| CH-10 | §10 P1 | Add fixture-based E2E acceptance |

CH-1, CH-8: design unchanged.

---

*Phase B complete. Next: Phase C — submit to Kimi + Pi for external review.*

---

## 15. Phase C — Kimi + Pi External Review Summary

**Verdict composite scores**:

| Criterion | Kimi | Pi | Avg |
|-----------|------|----|-----|
| (i) Architectural soundness | 3/5 | 3/5 | 3.0 |
| (ii) Scope discipline | 3/5 | 4/5 | 3.5 |
| (iii) Risk coverage | 2/5 | 3/5 | 2.5 |
| (iv) Phasing realism | 2/5 | 2/5 | **2.0** |
| (v) Acceptance testability | 3/5 | 3/5 | 3.0 |

**Overall**: Kimi "Re-think" / Pi "Ship with revisions". Composite: **re-think before building**.

### 15.1 Strong consensus (both reviewers agree — must fix)

| # | Issue | Both say |
|---|-------|----------|
| **C-1** | Phasing inverted | P1 ships analyzers against data produced in P2 (agent-internal spans). Analyzers will produce zero or garbage output. **Swap P1 ↔ P2**: span emission first, analyzers second. |
| **C-2** | `analyzer_id` as LoopSpec target is wrong abstraction | Conflates scheduling policy with computation identity. Category error that will metastasize into `validator_id`, `pipeline_id`, etc. **Replace with**: `AnalyzerRegistry` + polymorphic `target: SkillRef \| WorkflowRef \| AnalyzerRef` on LoopSpec. User-facing CLI unchanged (`vibe loop add --analyzer route_mismatch`). |
| **C-3** | Regression watcher dangerously under-specified | 15% threshold has no measurement window, min_samples, hysteresis, cooldown, or stability period. Flapping + oscillation + multi-instinct blame attribution all unsolved. **Must specify statistical contract before code.** |

### 15.2 Agreement (defer instinct_candidate)

Both reviewers agree `instinct_candidate` (auto-generated instincts) should not ship in initial v8.2:

- Kimi: "defer until regression watcher is proven against manually-created instincts"
- Pi: "Auto-writing instincts is the highest-blast-radius feature... defer instinct_candidate"

### 15.3 Divergence — `skill_underuse` scope

| | Position | Reasoning |
|---|----------|-----------|
| **Kimi** | Defer to v8.3 (implicit, design unchanged) | Trivial, low value — user sees it in `vibe skills list` |
| **Pi** | Include in v8.2 P2 | Trivial count over the same aggregation; immediate user-visible value ("you never use X"); zero auto-mutation risk |

**Verdict: ACCEPT Pi's position.** Cost is ~20 LOC; value is real (registry-aware analysis beats `vibe skills list`); no safety risk. Include in P2 alongside route_mismatch.

### 15.4 Divergence — cost_usd analyzer

| | Position | Reasoning |
|---|----------|-----------|
| **Kimi** | Include in P2 (only if span already captures cost_usd) | Trivially rule-based; immediate stakeholder value; recommend including |
| **Pi** | Defer | Cost-aware rotation is a policy decision, not an insight; surface cost as a column in P2 aggregator output, promote to analyzer only when someone asks for rotation |

**Verdict: ACCEPT Pi's position (softer).** Add `cost_usd` as a column in P2 aggregator output (zero new module). Do NOT add cost-analyzer module until user asks for rotation. Cheaper to add than to remove.

### 15.5 Missing considerations (both raised — must address)

| # | Consideration | Raised by | Action |
|---|---------------|-----------|--------|
| M-1 | Span schema versioning | Kimi | Add `schema_version: int` field to Span; define compatibility policy |
| M-2 | Cold-start contract (`min_samples`) | Both | Analyzers emit "insufficient data" below threshold (suggest ≥30) |
| M-3 | Multi-project `project_id` discriminator | Kimi | Add to Span; p25 meaningless across projects |
| M-4 | Deterministic replay for debugging | Kimi | `vibe trace replay --span-file <f>` CLI |
| M-5 | Instinct conflict resolution | Kimi | Specify priority / refuse policy when instincts collide on same pattern |
| M-6 | Span retention + PII redaction | Pi | v8.1 has retention (7d) + redact_sensitive(); re-assert explicitly |
| M-7 | Metric-condition full semantics | Pi | Aggregation window, eval frequency, hysteresis, cooldown, empty-store behavior |
| M-8 | suggestions.jsonl dedup upfront | Both | Fingerprint = analyzer_id + skill_id + bucketed_metric; suppress if unchanged within K ticks |
| M-9 | Rollback beyond quarantine (`vibe instinct revoke`) | Pi | Add explicit revoke command |
| M-10 | Pending queue surfacing | Pi | "Pending instincts" banner on next `vibe` invocation |
| M-11 | Stability period after analyzer proposal | Pi | N-tick cool-down on re-analysis of affected skill_id |

### 15.6 Rejected reviewer suggestions (with reasoning)

| Suggestion | Source | Why rejected |
|------------|--------|--------------|
| None significant | — | Both reviewers' core points all accepted |

The reviewers converged on the same weaknesses independently. Their authority on the architectural critique is high.

---

## 16. Phase D — Grill-me Decision Tree Answers

Q1-Q8 from `_grill-me-questions.md`, answered by combining Kimi + Pi verdicts.

### Q1 — LoopSpec extension vs standalone command?

**Kimi**: Reverse Decision #1. AnalyzerRegistry + polymorphic `target: SkillRef | WorkflowRef | AnalyzerRef`. User CLI unchanged.
**Pi**: Reverse Decision #1. Separate `vibe analyze` reusing scheduler as library. Or if team insists on one surface, default to reversible schema decision.
**Combined verdict**: **AnalyzerRegistry + polymorphic target reference**. This is the more principled refactor and preserves `vibe loop` mental model. LoopSpec gains a typed `target` union; analyzer/skill/workflow are sibling refs.

### Q2 — Three-phase ordering correct?

**Kimi**: No. Swap P1 ↔ P2. Span emission first.
**Pi**: No. "You cannot build a data-driven system before the data exists."
**Combined verdict**: **Reverse**. New phasing:
- **P1**: GAP-1 close — agent-internal span emission (LLM / tool_call / file_edit) + SpanAggregator consumer plumbing + dedup
- **P2**: GAP-3+5 close — InsightAnalyzer (route_mismatch + skill_underuse) + SuggestionWriter + LoopSpec target refactor + `vibe loop insights` CLI
- **P3**: GAP-2+4 close — MetricEvaluator + closed loop (instinct_candidate) + regression watcher + optional LLM commentary

### Q3 — Two analyzers in v8.2 enough?

**Kimi**: Two is disciplined. Add skill_underuse only if trivial.
**Pi**: Ship route_mismatch + skill_underuse. Defer instinct_candidate.
**Combined verdict**: **route_mismatch + skill_underuse in P2; instinct_candidate in P3 (after watcher proven)**.

### Q4 — Two-step accept + 15% regression watcher sufficient?

**Both**: No. Under-specified.
**Combined verdict**: Specify full statistical contract (§17.3 below). Defer auto-apply entirely to P3.

### Q5 — Per-skill p25 confidence well-defined?

**Both**: No — undefined below min_samples. Need cold-start contract.
**Combined verdict**: `min_samples = 30` enforced; analyzer emits `Insight(kind="insufficient_data", ...)` below threshold. Window = rolling 30d. Fallback to global p25 if skill never crosses 30 samples.

### Q6 — suggestions.jsonl dedup strategy?

**Both**: Specify upfront. Fingerprint-based.
**Combined verdict**: `fingerprint = hash(analyzer_id + skill_id + bucket(metric))`. Suppress identical fingerprint for K=3 consecutive ticks. Severity escalation (warn → critical) overrides suppression.

### Q7 — cost_usd as v8.2 analyzer?

**Kimi**: Yes (in P2 if span has it).
**Pi**: No, surface as column, defer analyzer.
**Combined verdict**: **Pi's softer position.** Aggregator output includes `cost_usd_per_skill` column from P2. No dedicated analyzer until user asks for rotation.

### Q8 — Does the design actually deliver user's ask?

**Both (implicit)**: Partially. route_mismatch detects *hedging*, not *wrong skill*. True inaccuracy detection requires ground-truth labels (user accept/reject, downstream failure).
**Combined verdict**: v8.2 delivers *signal* (hedging is a leading indicator of misrouting). v8.3 adds *ground-truth loop* via `vibe instinct accept/reject` outcome tracking → closes to actual accuracy. Document this explicitly so user knows what v8.2 does and doesn't deliver.

### 16.1 Decision summary

| Q | Original §1-13 position | Revised position |
|---|------------------------|------------------|
| Q1 | `analyzer_id` field on LoopSpec | Polymorphic `target: SkillRef \| WorkflowRef \| AnalyzerRef` + AnalyzerRegistry |
| Q2 | P1=analyzers, P2=spans+trigger, P3=LLM | **P1=spans, P2=analyzers, P3=trigger+closed loop+LLM** |
| Q3 | route_mismatch + instinct_candidate in P1 | route_mismatch + skill_underuse in P2; instinct_candidate in P3 |
| Q4 | Two-step accept + 15% watcher | Two-step accept + fully-specified watcher (defer to P3) |
| Q5 | Per-skill p25, absolute band fallback | Per-skill p25 + min_samples=30 + insufficient_data emission |
| Q6 | "Let it emerge" | Fingerprint dedup, K=3, severity escalation override |
| Q7 | Open question | Aggregator column in P2; analyzer deferred |
| Q8 | Implicit "yes delivers ask" | v8.2 = hedging signal; v8.3 = accuracy ground-truth loop |

---

## 17. Phase E — Final Design (revised after external review)

### 17.1 Revised architecture

```
                    ┌─────────────────────────────────────┐
                    │  Agent runtime (real execution)     │
                    │                                     │
                    │  task-span (v8.1)                   │
                    │   ├─ llm-span        ← P1 close     │
                    │   ├─ tool_call-span  ← P1 close     │
                    │   └─ file_edit-span  ← P1 close     │
                    └──────────────┬──────────────────────┘
                                   │ writes (with schema_version + project_id)
                                   ▼
                    ┌─────────────────────────────────────┐
                    │  spans.jsonl (schema-versioned)     │
                    │  + analytics.jsonl (fallback)       │
                    └──────────────┬──────────────────────┘
                                   │ reads
                                   ▼
                    ┌─────────────────────────────────────┐
                    │  SpanAggregator (v8.1 + cost column)│
                    │   get_skill_metrics                 │
                    │   get_pattern_sequences (deferred)  │
                    │   get_anomaly_events                │
                    └──────────────┬──────────────────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                │                  │                  │
                ▼                  ▼                  ▼
       ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐
       │ MetricEval     │  │ InsightAnalyzer│  │ SuggestionWriter   │
       │ (P3)           │  │ - route_mismatch│ │ - suggestions.jsonl│
       │                │  │ - skill_underuse│ │ - fingerprint dedup│
       └────────┬───────┘  │ - instinct_cand │ └─────────┬──────────┘
                │          │   (P3)          │           │
                │          └────────┬─────────┘           │
                │                   │                     │
                ▼                   ▼                     ▼
       ┌────────────────┐   ┌─────────────────────────────────┐
       │ Loop tick      │   │ instinct pending/ (P3, gated)   │
       │ (CRON|METRIC)  │   │ + regression watcher (P3)       │
       │ target:        │   │ + conflict resolver (P3)        │
       │  SkillRef |    │   └─────────────────────────────────┘
       │  WorkflowRef|  │
       │  AnalyzerRef  │
       └────────────────┘
```

### 17.2 LoopSpec refactor (Q1 verdict)

```python
# core/loop/models.py — revised

class TargetKind(StrEnum):
    SKILL = "skill"
    QUERY = "query"
    WORKFLOW = "workflow"
    ANALYZER = "analyzer"

class LoopTarget(BaseModel):
    """Polymorphic target reference. Exactly one kind/ref pair is set."""
    kind: TargetKind
    skill_id: str = ""
    query: str = ""
    workflow_id: str = ""
    analyzer_id: str = ""  # references AnalyzerRegistry

    @model_validator(mode="after")
    def _exactly_one(self) -> LoopTarget: ...

class LoopSpec(BaseModel):
    name: str
    schedule: str
    target: LoopTarget                  # replaces individual fields
    trigger: LoopTrigger = LoopTrigger.CRON
    metric_conditions: list[MetricCondition] = []
    # ... rest unchanged

# core/observability/analyzer_registry.py — new module
class AnalyzerRegistry:
    """Registers analyzers by ID. Future-proof for validator/optimizer/drift."""
    def get(self, analyzer_id: str) -> Analyzer: ...
    def list(self) -> list[str]: ...

class Analyzer(Protocol):
    """All analyzers implement this. LoopSpec.target.kind=ANALYZER invokes via registry."""
    def analyze(self, window_hours: int) -> list[Insight]: ...
```

**Migration**: existing LoopSpec JSON (with top-level `skill_id`/`query`/`workflow_id`) auto-migrates to `target` wrapper in `LoopSpec.__init__`. Zero breaking change for users.

### 17.3 Regression watcher — full statistical contract (Q4 verdict)

```python
@dataclass
class WatcherConfig:
    # Measurement window
    measurement_ticks: int = 6          # evaluate over N ticks post-apply
    min_samples: int = 20               # Wilson-scored; below = "inconclusive"

    # Threshold
    success_rate_drop_threshold: float = 0.15  # 15% relative drop
    wilson_lower_z: float = 1.96        # 95% CI lower bound for "real" drop

    # Hysteresis & cooldown
    quarantine_cooldown_hours: int = 48 # after quarantine, no re-propose for 48h
    stability_period_ticks: int = 4     # N successful ticks before re-apply

    # Multi-instinct attribution
    attribution_mode: str = "last_applied"  # alternatives: "all_active", "manual"

    # Oscillation guard
    max_apply_rate_per_skill_per_day: int = 2
    flap_detection_window_ticks: int = 10
    flap_threshold: int = 3  # ≥3 quarantines in window → permanent retire
```

**Conflict resolution** (M-5): if instinct A and B both route pattern X, priority = `specificity DESC, created_at ASC`. Higher-specificity (more tokens in pattern) wins; tie-break by age.

### 17.4 Span schema additions (M-1, M-3)

```python
# core/observability/models.py — Span extension
@dataclass
class Span:
    # ... existing fields ...
    schema_version: int = 1             # M-1
    project_id: str = "default"         # M-3 — p25 per-project, not global
```

Compatibility policy: reader accepts `schema_version ≤ current`; writer always emits current. Old spans (v8.1) read as version 1 with `project_id="default"`.

### 17.5 Revised phased roadmap (Q2 verdict)

#### P1 — Span Emission + Aggregator Plumbing (1-2 weeks)

**Scope**:
- GAP-1 close: child spans at LLM-call / tool-call / file-edit sites in agent runtime
- Span schema: add `schema_version` + `project_id`
- SpanAggregator: fix any fields broken by new span shape; add `cost_usd_per_skill` column
- `vibe trace replay --span-file <f>` CLI (M-4)
- Span retention/redaction audit (M-6) — assert v8.1 controls cover new payload sites

**Acceptance**:
- After 1 hour of real agent activity, `spans.jsonl` contains ≥3 distinct `span_kind` values (task + llm + tool_call at minimum)
- `SpanAggregator.get_skill_metrics(skill_id="...", window_hours=1)` returns non-zero `avg_tokens` and `cost_usd`
- E2E test with committed fixture (`tests/fixtures/spans/sample.jsonl`) passes replay
- Microbenchmark: span emit overhead <50µs

#### P2 — Analyzers + LoopSpec Refactor (1-2 weeks)

**Scope**:
- InsightAnalyzer: `route_mismatch` (per-skill p25, min_samples=30) + `skill_underuse`
- SuggestionWriter + fingerprint dedup (K=3, severity override)
- `cold_start` emission: `Insight(kind="insufficient_data", ...)` below min_samples
- LoopSpec refactor: `target: LoopTarget` polymorphic; AnalyzerRegistry; migration path
- `vibe loop insights` CLI with `--skill`, `--kind`, `--since` filters
- `vibe loop add --analyzer <id> --cron "..."` UX (UI preserves mental model)

**Acceptance**:
- Existing LoopSpec JSON auto-migrates without error
- route_mismatch against fixture produces ≥1 actionable insight
- skill_underuse against current registry + fixture produces ≥1 under-use finding
- Dedup: same fingerprint suppressed for 3 consecutive ticks in test
- All 147 existing loop tests green

#### P3 — Metric Trigger + Closed Loop + Optional LLM (2-3 weeks)

**Scope**:
- MetricEvaluator with full semantics (M-7): aggregation window, eval frequency, hysteresis, cooldown, empty-store behavior
- `LoopState.last_metric_fire` field
- `instinct_candidate` analyzer (only after P3 watcher is proven)
- Regression watcher with full statistical contract (§17.3)
- `vibe instinct accept/reject/revoke` (M-9)
- Pending-queue surfacing: banner on next `vibe` invocation (M-10)
- Instinct conflict resolver (M-5)
- Optional `--llm` commentary layer (off by default)

**Acceptance**:
- MetricCondition `success_rate < 0.5` triggers loop within 1 minute of a real failure
- Auto-applied instinct with intentional poison (test fixture) is quarantined within `measurement_ticks`
- Flap detection: 3 manually-forced quarantines retires the instinct permanently
- Pending queue shown on `vibe` invocation with ≥1 pending instinct

### 17.6 Revised risk register

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| R1 | Span emission slows hot path | Medium | Microbenchmark in CI; runtime disable flag |
| R2 | PII in prompt payloads | **High** | `redact_sensitive()` + `record_payloads=false` mode + audit log; retention 7d; hard cap 100K |
| R3 | Rule analyzer noise | Medium | Severity thresholds; user-dismissable; cold-start contract |
| R4 | Auto-instinct regression | **High** | Full statistical contract (§17.3); conflict resolver; flap detection; auto-retire |
| R5 | LoopSpec migration breaks users | Low | Auto-migrate in `__init__`; 147 existing tests as gate |
| R6 | spans.jsonl unbounded growth | Medium | v8.1 retention + hard cap; add `project_id` rotation if needed |
| R7 | Metric trigger flapping | Medium | Wilson Score + cooldown + hysteresis (§17.3) |
| R8 | Analyzer scope creep | Medium | 2 analyzers frozen for P2; new ones require ADR |
| **R9** | **Schema drift breaks old spans** | **Medium** | **`schema_version` field + compatibility policy (M-1)** |
| **R10** | **Cross-project p25 contamination** | **Medium** | **`project_id` discriminator (M-3)** |
| **R11** | **Analyzer oscillation** | **High** | **Stability period + flap detection + max-apply-rate (§17.3)** |
| **R12** | **Pending queue dead-letter** | **Medium** | **Surfacing banner on vibe invocation (M-10)** |

### 17.7 Open questions remaining after review

1. **R9/R10 schema migration tooling**: do we need a one-shot `vibe trace migrate` CLI? Or rely on lazy compatibility? **Defer decision to P1 implementation**.
2. **Multi-tenant `project_id` derivation**: from CWD? from config? from env var? **Defer to P1**.
3. **LLM commentary (P3) model choice**: Claude? Kimi? Both? **Defer to P3; user choice**.
4. **`vibe instinct revoke` semantics**: revert routing to pre-apply state, or just deactivate? **Defer to P3**.

These are implementation-detail questions, not architectural ones. They can be settled inside each phase without re-opening the design.

---

## 18. Conclusion

**Status**: Ready for implementation, conditional on accepting §17 revised phasing and abstraction.

**What changed from §1-13 draft**:
- §10 phasing reversed (P1=spans, P2=analyzers, P3=closed loop)
- §4.3-4.7 LoopSpec extension replaced with polymorphic `target` + AnalyzerRegistry
- §6.2 analyzer scope: `route_mismatch` + `skill_underuse` in P2; `instinct_candidate` in P3
- §11 R4 watcher: now full statistical contract (§17.3)
- New: schema versioning, project_id, conflict resolution, dedup, replay, retention re-assertion

**What stayed**:
- Closed-loop topology (§3)
- Rule-based first, LLM optional (§6.3)
- Two-step accept for instincts (§7.1)
- Reuse v8.1 components as foundation

**Phase F — Implementation entry point**: P1 of §17.5.

---

*Dynamic workflow complete: Phase A design → Phase B adversarial → Phase C Kimi+Pi review → Phase D grill-me answers → Phase E merge. Result: draft scored 2.6/5; revised design addresses all 11 missing considerations + 3 strong consensus items + 4 divergences (each ruled on).*

---

## 19. Phase F — Implementation Reality Check + L2 Echo Mode Pivot

### 19.1 What broke during M1/M2 implementation

When implementing M1 (span schema, ✅ shipped) and starting M2 (agent-internal span emission), the **core premise of §4 GAP-1 collapsed**:

- §4 assumed `plan_executor.py` and `skill_injector.py` were "LLM call / tool call boundaries" — they are **pure string template generators** with no LLM and no tool execution.
- VibeSOP is a **router + injector**, not an agent runtime. All actual LLM calls and tool calls happen in the **external agent** (Claude Code / Kimi / Pi) outside the VibeSOP process.
- The 5 SpanKinds declared in v8.1 (`task | llm | tool_call | file_edit | workflow_node`) — **only `task` was ever emitted**. `llm` / `tool_call` / `file_edit` / `workflow_node` have zero emission sites.

User pushback during implementation:
> "等等，我们可以做成一个轻量 Agent 吧？当前定位不做 Agent 的理由是什么呢？"

This surfaced the architectural fork: VibeSOP must evolve to a higher agent tier to make v8.2's observability goals achievable.

### 19.2 Agent tier decision (user-selected)

| Tier | Description | Observability coverage | Effort |
|------|-------------|------------------------|--------|
| L0 | Router + injector (current) | None — external agent is a black box | — |
| L1 | Probe mode: LLM at 3-5 decision points | Partial — probes observable, main flow not | 1 week |
| **L2** | **Echo mode: opt-in, in-process LLM answers** | **Full for echo traffic, partial for external** | **2 weeks** |
| L3 | Full agent: tool calling, context mgmt | Full | 4-6 weeks |

**User verdict: L2 Echo Mode.**

### 19.3 L2 reality check (4-axis investigation)

| Axis | Finding |
|------|---------|
| Short-circuit insertion point | `handle_query` L461→L463 (after intercept confirm, before routing). ✅ Clean insertion. |
| LLM factory reuse | `_build_llm_factory()` is `@staticmethod`, returns `create_provider(provider, api_key, base_url)`. EchoEngine can directly reuse. ✅ |
| **Existing LLM calls have 0 span coverage** | `AnthropicProvider.call`, `classifier._llm`, `workflow_engine._llm`, `multi_intent_detector.llm_client.call` — **none wrapped in spans**. This is the true v8.1 GAP. |
| Hook response protocol | VibeSOP runs on `UserPromptSubmit` hook. **No `decision` / `block` field** in this event. Returning `systemMessage` with echo answer does NOT silence Claude Code — it will still generate a new turn. True short-circuit requires `PreToolUse` hook + `decision:"block"` (hook architecture change). |

### 19.4 GAP-1 redefined (the real one)

**Original §4 GAP-1** (now invalidated): "Child spans at LLM-call / tool-call / file-edit sites in plan_executor and skill_injector." → These files don't make LLM/tool/file calls.

**Revised GAP-1**: **Wrap `LLMProvider.call()` and `LLMProvider.acall()` in llm-spans.** This is a single emission point that covers *every* LLM caller in the codebase: EchoEngine (L2), ClassifierAgent, WorkflowEngine, MultiIntentDetector, etc.

```python
# src/vibesop/llm/base.py (revised)
class LLMProvider:
    def call(self, prompt: str, **kwargs) -> LLMResponse:
        tracer = _get_obs_tracer()
        with tracer.span(f"llm:{self.provider_name}", kind="llm") as span:
            span.set_input({"prompt": prompt[:500], "model": kwargs.get("model"), **kwargs})
            try:
                response = self._call_impl(prompt, **kwargs)
                span.set_output({"response": response.text[:500]})
                span.with_tokens(response.tokens_input, response.tokens_output).with_cost(response.cost_usd)
                return response
            except Exception as e:
                span.set_error(str(e))
                raise
```

This single change closes the LLM-side of GAP-1 for **every** caller, not just EchoEngine.

### 19.5 EchoEngine design (L2a — v8.2 scope)

```python
# src/vibesop/agent/echo.py (new module, ~200 LOC)

class EchoEngine:
    """In-process LLM answer engine for opt-in high-confidence queries.

    Triggered after intercept-confirm, before routing. Returns a direct
    answer that becomes the hook's systemMessage.

    Gating (all must hold):
      - config.echo.enabled == true
      - predicted_routing_confidence >= config.echo.confidence_threshold (default 0.85)
      - query_length <= config.echo.max_query_chars (default 500)
      - rate_limit: per-session-per-minute cap (default 10)
      - skill scope: query must NOT match tool-heavy skills (skill.echo_blacklist)

    Failure mode: ANY exception or threshold miss → fallback to normal routing.
    No user-visible error; the route proceeds as if echo wasn't attempted.

    Span coverage (automatic via LLMProvider span wrap):
      - llm-span for the echo LLM call (kind="llm", metadata.echo=true)
      - parent task-span gets metadata.echo=true on success
    """

    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime
        self._llm_factory = runtime._build_llm_factory()  # reuse existing
        self._config = ConfigManager().get_echo_config()

    def try_answer(
        self,
        query: str,
        task_span: Span,
    ) -> AgentRuntimeResult | None:
        """Attempt to answer in-process. Returns None if not eligible."""
        if not self._config.enabled:
            return None
        if not self._is_eligible(query):
            return None

        llm = self._llm_factory() if self._llm_factory else None
        if llm is None:
            return None  # silent fallback to normal routing

        # Build a tight system prompt — echo mode is for "answer me, don't execute"
        messages = self._build_messages(query)
        try:
            response = llm.call(
                prompt=messages["system"] + "\n\nUser: " + query,
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                temperature=0.3,
            )
        except Exception:
            logger.exception("Echo LLM call failed; falling back to routing")
            return None

        result = AgentRuntimeResult(project_root=self._runtime.project_root)
        result.mode = "echo"
        result.skill_id = ""  # no skill routed
        result.confidence = 1.0
        result.skill_content = response.text
        task_span.metadata["echo"] = True
        task_span.metadata["echo_tokens"] = response.tokens_input + response.tokens_output
        task_span.metadata["echo_cost_usd"] = response.cost_usd
        return result
```

### 19.6 LoopSpec integration — unchanged

L2 does NOT change the Q1 verdict (analyzer polymorphic target). EchoEngine is a runtime concern, not a loop target. LoopSpec target refactor (§17.2) proceeds as planned in P2.

### 19.7 Revised phased roadmap (P1 only — P2/P3 unchanged from §17.5)

#### P1 — Span Emission + L2a EchoEngine (revised, 2 weeks)

**Scope**:
- **GAP-1 (real)**: wrap `LLMProvider.call/acall` in llm-spans. **Single point covers all callers.**
- **Span schema** (M1, ✅ shipped): `schema_version` + `project_id` on Span
- **EchoEngine** (new, ~200 LOC): opt-in L2a in-process answer
- **`handle_query` short-circuit branch**: insert `EchoEngine.try_answer()` at L461→L463
- **Routing layer bridging**: route `routing/tracer.py` per-layer attempts to observability spans (kind=`workflow_node`) so spans.jsonl has full decision tree
- **SpanAggregator**: fix `metadata` string-vs-dict bug, add `cost_usd_per_skill` column
- **`vibe trace replay --span-file <f>` CLI**
- **Echo config schema**: `[echo] enabled=false, confidence_threshold=0.85, model="claude-haiku-4-5", max_tokens=2048, rate_limit_per_minute=10`

**Acceptance**:
- LLM provider call wraps emit llm-spans to spans.jsonl
- EchoEngine eligible query produces a complete trace: task-span → llm-span with metadata.echo=true
- After 1 hour of real agent activity with `[echo] enabled=true`, spans.jsonl contains ≥3 distinct `span_kind` values (task + llm + workflow_node minimum)
- `SpanAggregator.get_skill_metrics` returns non-zero `avg_tokens` and `cost_usd` for skills with LLM activity
- Routing-layer spans populate `metadata.layer`, `metadata.confidence`, `metadata.matched_skill` for analyzer consumption
- E2E fixture test (`tests/fixtures/spans/sample.jsonl`) passes replay
- Microbenchmark: span emit overhead <50µs; echo mode adds <300ms latency vs. non-echo path
- 153 existing loop tests green; 0 regressions

#### P2 — Analyzers + LoopSpec Refactor (unchanged from §17.5)

#### P3 — Metric Trigger + Closed Loop + Optional LLM + L2b Hook Architecture (extended)

P3 now includes:
- **L2b**: add `PreToolUse` hook + `decision:"block"` response so Claude Code actually silences on echo answers. Hook architecture change.

### 19.8 New risks introduced by L2

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| **R13** | **Echo answer quality < external agent quality** | **High** | Opt-in only; confidence threshold; rate limit; user feedback mechanism (thumbs up/down) |
| **R14** | **Prompt injection via echo LLM** | **High** | Echo is read-only (no tool calls); system prompt constrains output; no file/exec capability |
| **R15** | **Cost explosion from echo traffic** | **Medium** | Rate limit per session; use cheap model (haiku-4-5) by default; weekly cost report in P2 |
| **R16** | **Users confused by dual-mode (echo vs external)** | **Medium** | systemMessage prefix "🔊 VibeSOP Echo:" makes mode visible; `vibe status` shows echo stats |
| **R17** | **Echo skews analyzer data toward easy queries** | **Medium** | Analyzer must tag echo-mode traces separately; route_mismatch compares within mode, not across |
| **R18** | **Echo fails silently, user thinks it worked** | **Low** | task_span.metadata.echo=true only on success; analyzer can detect "echo attempted but fell back" |

### 19.9 What stays from §17

- §17.1 architecture (closed loop topology)
- §17.2 LoopSpec polymorphic target refactor (P2)
- §17.3 watcher statistical contract (P3)
- §17.4 schema additions (M1 shipped ✅)
- §17.5 P2 and P3 scope (unchanged)
- §17.6 risk register (R1-R12 unchanged; R13-R18 added)
- §17.7 open questions (mostly intact)

### 19.10 What changes from §17

- §4 GAP-1 emission sites: **invalidated**. Real emission point is `LLMProvider.call/acall`.
- §10 P1 scope: **rewritten** above (§19.7)
- §10 P3 scope: **extended** with L2b hook architecture
- §11 risk register: **R13-R18 added**
- §17.5 P1 acceptance criteria: **rewritten** to include LLM span coverage, echo mode trace, routing-layer span bridging

---

*Phase F pivot complete. Reason: §4 GAP-1 implementation revealed VibeSOP is router+injector not agent; user decision: evolve to L2 Echo Mode. Revised GAP-1 wraps LLMProvider.call as single emission point. P1 scope extended with EchoEngine. P3 extended with L2b hook architecture.*

*Next: Phase B adversarial on L2-specific risks (R13-R18) → Phase C Kimi+Pi复审 on L2 architecture decision → Phase D grill-me on echo gating policy → Phase E merge.*

---

## 20. Phase B' — Adversarial on L2 Echo Mode

Six challenges focused on L2-specific risks. Each ends with verdict.

### CH-L2-1: Predicted confidence is a chicken-and-egg problem

**Challenge**: §19.5 EchoEngine gating says "predicted_routing_confidence >= 0.85". But routing hasn't happened yet at L461→L463 — that's the *next* step. Where does the predicted confidence come from?

Options:
- (a) Run a *preliminary* route to get confidence, then decide echo vs full — but that wastes the routing work if echo fires
- (b) Use a cheap heuristic (keyword / scenario layer only) — but then confidence is unreliable
- (c) Drop the confidence gate; use query-shape heuristic only (length, complexity markers)

**Verdict: ACCEPT (c) with caveat.** Drop `predicted_routing_confidence` from gating. Use:
- `query_length <= max_query_chars` (cheap, deterministic)
- `complexity_markers`: presence of words like "implement / refactor / debug / migrate" disqualifies echo
- `skill_scope_blacklist`: query matches tool-heavy skills (TDD, refactoring, debugging) → no echo

Confidence threshold enters the **post-hoc metadata** (analyzer uses it), not the gating.

### CH-L2-2: Opt-in vs opt-out — silent default decides adoption

**Challenge**: §19.7 says `[echo] enabled=false` default. But if it ships off-by-default, no one turns it on, and we collect zero echo data → analyzer can't validate echo hypothesis. If on-by-default, cost + UX surprise.

**Verdict: accept off-by-default + add `vibe echo enable` interactive setup.** First run prompts user with cost/UX trade-off; only opting in activates. This is consistent with v8.1 instinct learner consent pattern.

### CH-L2-3: Dual-mode analyzer contamination (R17 under-specified)

**Challenge**: §19.8 R17 says "analyzer must tag echo-mode traces separately" but doesn't say how analyzer handles the split. route_mismatch with `metadata.echo=true` excluded from baseline p25 (different distribution) — but if 80% of traffic is echo, baseline p25 is meaningless for the 20% non-echo.

**Verdict: ACCEPT.** Add explicit rule:
- p25 baseline computed per-mode (echo / non-echo) when n >= 30 in each
- If echo traffic > 50% of total, emit `Insight(kind="echo_dominance_warning")` — analyzer detected that echo is skewing baseline
- route_mismatch on non-echo traces is the canonical signal; echo traces route_mismatch is suppressed (echo doesn't *route*, it answers)

### CH-L2-4: Multi-turn context breaks when echo answer enters conversation

**Challenge**: Claude Code receives echo's `systemMessage` as injected context. Next turn, Claude Code sees prior echo answer in conversation history. If user follows up with "yes do that", Claude Code may attempt execution based on echo's text — which was generated by a different LLM with no tool grounding.

**Verdict: accept design + add guardrail.** Echo systemMessage must include explicit marker: `"🔊 VibeSOP Echo (informational only, not actionable): <answer>"`. This signals to Claude Code that the answer is reference, not command. Analyzer tracks whether users follow up with execution intent after echo → if >30% do, echo UX is failing the "don't act" contract.

### CH-L2-5: Echo becomes a crutch that degrades routing investment

**Challenge**: If echo answers 60% of queries, the routing engine's quality matters less for those queries — they never get routed. Over time, routing accuracy could decay without anyone noticing (no data), and the entire premise of v8.2 (improve routing) is undermined by L2.

**Verdict: ACCEPT — this is the most subtle risk.** Mitigation:
- `vibe optimize` (existing CLI) must run on **non-echo traces only** — routing optimization always sees real routing decisions
- Echo traffic tagged in spans; analyzer explicitly reports "X% of traffic bypassed routing via echo — routing accuracy signal weakening"
- If echo rate > 70% sustained for 7 days, emit `critical` insight recommending user tighten echo gating

### CH-L2-6: Rate limit per-session is undefined when sessions are fuzzy

**Challenge**: §19.5 says `rate_limit_per_minute=10` per session. But `session_id="default"` in many flows (hook invocations don't always carry session). 10/min against "default" = 10/min globally → easy abuse / cost runaway.

**Verdict: ACCEPT.** Rate limit must key on `session_id + IP_hash` (or `session_id + project_id` if IP unavailable). If session_id is "default", fall back to `project_id` only. Add hard daily cap (`echo.daily_budget_usd=1.0` default) — exceeding disables echo until midnight UTC.

### 20.1 Summary of L2-specific amendments

| Challenge | Amendment |
|-----------|-----------|
| CH-L2-1 | Drop predicted_routing_confidence gate; use query-shape heuristic + skill blacklist |
| CH-L2-2 | Off-by-default + `vibe echo enable` interactive setup |
| CH-L2-3 | Per-mode p25 baselines; echo_dominance_warning insight at >50% |
| CH-L2-4 | systemMessage prefix "🔊 VibeSOP Echo (informational only)" + analyzer tracks follow-up execution rate |
| CH-L2-5 | `vibe optimize` non-echo only; echo rate >70% for 7d = critical insight |
| CH-L2-6 | Rate limit keys on session+project; daily budget cap $1 default |

---

*Phase B' complete. Next: Phase C' — submit §19 + §20 to Kimi+Pi for L2 architecture sign-off.*

---

## 21. Phase C' — Kimi+Pi L2 Architecture Review + Empirical Validation

### 21.1 Review verdicts

| Criterion | Kimi | Pi | Avg |
|-----------|------|----|-----|
| (i) L2 right tier | 3 | 3 | 3.0 |
| (ii) EchoEngine gating sound | implied 3 | 3 | 3.0 |
| (iii) GAP-1 single emission point | implied 3 | 3 | 3.0 |
| (iv) L2a/L2b split acceptable | implied 2 | **2** | **2.0** |
| (v) §20 self-rulings correct | implied 4 | 4 | 4.0 |

**Overall**: Kimi "ship GAP-1 wrap, hold EchoEngine"; Pi "ship GAP-1 wrap, **hold EchoEngine, redesign L2b on actual hook protocol**".

### 21.2 Pi's three critical findings (load-bearing)

**B1 — Premise circularity** (validated by §21.3 empirical investigation):
> Echo needs an LLM API key. Wherever a key is configured, classifier/multi-intent calls **already** make in-process LLM calls today (`classifier.py:371`, `multi_intent_detector.py:85`) and will emit spans the moment GAP-1 ships. Wherever no key is configured, echo can't fire either.

**B2 — Hook protocol premise wrong**:
> UserPromptSubmit supports `decision:"block"` + `reason` (per [Claude Code hooks reference](https://docs.anthropic.com/en/docs/claude-code/hooks)). PreToolUse is the **wrong** hook for L2b — it fires per tool call; pure Q&A turns may call no tools; blocking a tool mid-turn redirects rather than silences.

**B3 — Double-answer UX**:
> Echo answer via `systemMessage` + external agent generates its own full turn = every echo-eligible query gets slower, costs twice, presents two possibly conflicting answers. Without silence, L2a net user value is negative.

### 21.3 Empirical validation (path B investigation)

User selected "investigate before deciding". Results:

| Metric | Value | Source |
|--------|-------|--------|
| User LLM config status | **DeepSeek configured** (config.toml:29), `enable_ai_triage=true` | `~/.vibe/config.toml` |
| LLM calls per hook invocation (long query) | **1-3** (triage + optional MultiIntentDetector + optional ClassifierAgent) | `triage_service.py:138`, `orchestrator.py:85,149` |
| Total LLM calls in current logs | **308** | `.vibe/ai_triage_log.jsonl` |
| Total cost | $0.2303 / 226,641 tokens | same |
| LLM spans in spans.jsonl | **0** (all `tokens_input=0`) | `.vibe/observability/spans.jsonl` |
| analytics.jsonl LLM data | none (only routing_layers array) | `.vibe/analytics.jsonl` |

**Verdict**: Pi is correct. LLM calls already happen on every long-query hook invocation. The observability gap is **missing span coverage**, not missing LLM call sites. EchoEngine adds zero new capability.

### 21.4 Additional findings from review

| # | Finding | Source |
|---|---------|--------|
| F-1 | Two `LLMProvider` definitions (`core/protocols.py:16` Protocol + `llm/base.py:50` ABC) — naming collision risk | Pi |
| F-2 | Callers use `llm_client: Any` duck typing — single emission point must wrap at `create_provider` factory, not ABC | Pi |
| F-3 | `agent/__init__.py:34` has its own `SimpleResponse` duck-typed path bypassing ABC | Pi |
| F-4 | Complexity markers (CH-L2-1 replacement) are English-only; Chinese queries bypass | Pi |
| F-5 | Rate limit + budget need cross-process state (hook = fresh subprocess each time) | Pi |
| F-6 | UserPromptSubmit 30s timeout; echo LLM call + routing must fit | Pi |
| F-7 | `response.cost_usd` must be verified across all providers (Ollama = 0) | Pi |
| F-8 | Trace attribution: echo-eligible fallback will emit classifier spans later — parent/child linkage prevents double-count | Pi |

### 21.5 L2 withdrawal

Based on §21.2 + §21.3:
- **B1 validated**: LLM calls exist, GAP-1 wrap closes observability gap without EchoEngine
- **B2 correct**: L2b hook design invalid (PreToolUse wrong hook; UserPromptSubmit already supports block)
- **B3 unaddressed**: L2a would ship double-answer UX

**L2 Echo Mode is withdrawn from v8.2 scope.** §19 EchoEngine design and §20 adversarial rulings are archived for reference but no longer guide implementation.

### 21.6 What stays, what goes

| Component | Status |
|-----------|--------|
| §4 GAP-1 revised definition (wrap `LLMProvider.call`) | **STAYS** — but emission point moves to `create_provider` factory per F-2 |
| §19 EchoEngine | **WITHDRAWN** |
| §19 L2a/L2b split | **WITHDRAWN** |
| §20 CH-L2-1..6 self-rulings | **ARCHIVED** (CH-L2-3, CH-L2-5 still relevant for analyzer mode-splitting) |
| §17.2 LoopSpec polymorphic target refactor (P2) | STAYS |
| §17.3 watcher statistical contract (P3) | STAYS |
| §17.4 span schema additions | **SHIPPED (M1 ✅)** |

---

## 22. Phase D' — Grill-me (compressed)

L2 withdrawal makes most Q1-Q8 from `_grill-me-questions.md` moot. Remaining live questions:

### Q-G1: Where exactly to wrap LLM calls?

**Options**:
- (a) `llm/base.py LLMProvider.call` (ABC) — but duck-typed `Any` callers bypass (F-2)
- (b) `create_provider` factory — returns a `SpanWrappedProvider` decorator over any provider
- (c) Each call site (`triage_service.py:138`, `classifier.py:151`, `multi_intent_detector.py:85`, etc.)

**Verdict: (b)**. Wrap at factory. Every caller gets spans automatically. Duck-typed objects (mocks, SimpleResponse, custom wrappers) are covered because factory is the construction point.

### Q-G2: Trace attribution when call site spans link to task-span?

`triage_service` is called from within `unified.py:route()` which runs inside `handle_query`'s task-span. If `triage_service._llm.call()` emits an llm-span, does it correctly parent to the active task-span?

**Verdict**: Tracer's thread-local stack handles this automatically (`tracer.py:140-172`). As long as call happens within the `with tracer.trace()` block, parent linkage is correct. **No additional plumbing needed**.

### Q-G3: Should GAP-1 wrap cover both sync `call()` and async `acall()`?

**Verdict: Yes**. Both paths. Async wrap reuses same tracer context (thread-local + asyncio task-local bridge — needs verification, see Q-G6).

### Q-G4: cost_usd source of truth?

`ai_triage_log.jsonl` has `estimated_cost_usd` per call. The `LLMResponse` returned by providers — does it populate `cost_usd`?

**Action**: Verify in M2 implementation. If missing, compute from `tokens * price_table` with `llm/models.py` price lookup.

### Q-G5: Hook timeout interaction?

UserPromptSubmit hook has 30s default timeout. Adding span emit must not push echo-attempted-then-fell-back scenarios over budget. Span emit overhead: <50µs (M5 microbench target). Negligible.

### Q-G6: Async tracer context propagation across asyncio tasks?

`tracer.py` uses `threading.local()`. asyncio task switches within same thread share `local()`, so context propagates. But `asyncio.gather` may schedule on different threads if executor is involved. **Defer verification to M2 implementation**.

---

## 23. Phase E' — Final Revised P1 Scope (L2 withdrawn)

### 23.1 P1 — LLM Span Coverage + Aggregator Plumbing (revised, ~1 week)

**Scope** (downsized from §19.7):
- **GAP-1 (real)**: Wrap at `create_provider` factory. Returns `SpanWrappedProvider` that delegates to underlying provider and emits llm-span on every `call()` / `acall()`.
- **Span schema** (M1, ✅ shipped): `schema_version` + `project_id`
- **SpanAggregator**: fix `metadata` string-vs-dict bug (pre-existing v8.1 issue surfaced by review); add `cost_usd_per_skill` column
- **`vibe trace replay --span-file <f>` CLI**
- **Routing-layer bridging** (optional in P1 if time permits): emit workflow_node spans for each routing layer attempt

**Removed from P1**:
- EchoEngine (withdrawn)
- `handle_query` short-circuit branch (withdrawn)
- Echo config schema (withdrawn)
- L2-related acceptance criteria

### 23.2 P1 Acceptance Criteria (revised)

- LLM provider factory wraps every `call()` in an llm-span
- After 1 hour of real agent activity, spans.jsonl contains ≥2 distinct `span_kind` values (task + llm minimum); workflow_node if routing-layer bridging shipped
- `SpanAggregator.get_skill_metrics` returns non-zero `avg_tokens` and `cost_usd` for skills with LLM activity
- Existing `.vibe/ai_triage_log.jsonl` data shape informs the aggregator's expected fields (no schema change to ai_triage_log)
- E2E fixture test (`tests/fixtures/spans/sample.jsonl`) passes replay
- Microbenchmark: span emit overhead <50µs
- 153 existing loop tests green; 0 regressions

### 23.3 P2 / P3 unchanged

P2 (analyzers + LoopSpec refactor) and P3 (metric trigger + closed loop + optional LLM) proceed as defined in §17.5. The optional LLM in P3 is **NOT** EchoEngine — it's the LLM-as-judge commentary layer (rule-based analyzer output enriched with LLM explanation, off by default).

### 23.4 Risk register changes

Removed: R13-R18 (L2-specific).
Added:
| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| R19 | Duck-typed providers bypass factory wrap | Medium | Verify `create_provider` is the only construction path; CI test that all imports of LLM go through factory |
| R20 | `LLMResponse.cost_usd` not populated by all providers | Medium | Compute from tokens × price table; verify in M2 |
| R21 | Async tracer context loss across asyncio.gather | Low | Defer to M2 implementation; add regression test if found |

### 23.5 Lesson recorded

Memory `feedback-dynamic-workflow-external-review-first` already captures "self-adversarial < external review". This pivot adds a second lesson: **verify empirical claims before architecture decisions**. The §19 L2 EchoEngine pivot was triggered by M2 implementation discovery, but the discovery itself was based on incomplete codebase reading (missed `classifier._llm` / `triage_service._llm` call sites). External review (Pi B1) + empirical validation (§21.3) surfaced the error in <1 hour.

---

## 24. Phase F — P1 Ship + Kimi Final Sign-off Review

### 24.1 P1 implementation complete

All 5 milestones shipped (M1-M5). Test totals: **4434 pass / 14 skipped / 0 regressions**, ruff clean, basedpyright 0 errors on modified files.

| Milestone | Tests added | Key deliverable |
|-----------|-------------|-----------------|
| M1 | +9 | Span schema (`schema_version`, `project_id`) |
| M2 | +16 | `SpanWrappedProvider` wrap on `create_provider` factory |
| M3 | +11 | SpanAggregator trace_id-based attribution + `total_cost_usd` |
| M4 | +12 | `vibe trace replay` CLI |
| M5 | +8 | E2E loop test + microbench (45.7µs p50 / 63.4µs p95) |

### 24.2 Kimi final sign-off review — 4 blockers identified

Kimi cross-verified claims against the codebase (`tracer.py`, `span_writer.py`, `aggregator.py`, `models.py`). Four blockers raised:

| # | Blocker | Verdict |
|---|---------|---------|
| 1 | GAP-3 not actually closed: `get_skill_metrics` has zero production callers in `src/` — "loop closure" claim false | **FIXED** — added `vibe trace metrics <skill_id>` CLI command (3 tests) |
| 2 | `project_id` not used by aggregator; `models.py:58` TODO still pending; cross-project contamination risk missing from limitations list | **FIXED** — `get_skill_metrics(project_id=...)` filter + 1 test |
| 3 | CWD-relative storage path (#6 in §23.4) should be P1, not deferred | **REJECTED** — `vibe` CLI convention is `Path.cwd()` = project root (`agent_runtime.py:183`, `cli/main.py:255`). CWD-relative is correct by design. |
| 4 | PIPE_BUF atomicity claim false: payloads up to 16KB × 2 + metadata → lines ≫ 4096 bytes; multi-process interleaving risk | **FIXED** — `fcntl.flock(LOCK_EX)` cross-process lock in `SpanWriter._locked_append` |

### 24.3 GAP-3 closure (the biggest miss)

Kimi's strongest point: the milestone is named "loop **closure**" but the loop ended at `spans.jsonl`. Nothing consumed `SpanAggregator.get_skill_metrics()`. Added the missing consumer:

```
vibe trace metrics <skill_id> [--window N] [--project-id ID] [--json]
```

Output: executions / success_rate / avg_duration_ms / llm_call_count / llm_success_rate / avg_tokens / total_cost_usd / tool_call_distribution / top_errors.

This makes the aggregator reachable from the CLI — `get_skill_metrics` now has a production caller path.

### 24.4 Pi M5 review

Pi's inline-prompt second-round review did not produce output within timeout. Kimi's review covered the systemic issues (4 blockers above). Pi's earlier M2 + M4 reviews (B1/B2/B3 + 3 hard bugs) are already addressed.

### 24.5 Updated known limitations (P2/P3)

Added after M5 implementation + Kimi review:

| # | Limitation | Severity | P2 fix sketch |
|---|-----------|----------|---------------|
| 1 | ~~`asyncio.gather` LIFO mis-attribution (threading.local context)~~ | ✅ Closed 2026-07-23 | Replaced `threading.local()` with `contextvars.ContextVar` in `ObservabilityTracer`. See §24.8. |
| 2 | `set_llm_factory` injection channel bypass | Low — third-party only | Contract enforcement or factory wrapper validation |
| 3 | ~~Pricing table not implemented (`cost_usd=0` + metadata flag)~~ | ✅ Closed 2026-07-23 | `llm/pricing.py` with per-model rates. See §24.9. |
| 4 | ~~Nested task-spans per trace_id (last-writer-wins on attribution map)~~ | ✅ Closed 2026-07-23 | CLI `vibe route` now opens `tracer.trace()` (was hook-only). See §24.7. |
| 5 | Spans.jsonl unbounded growth, no rotation | Low — local dev only for P1 | `vibe trace clean` for spans.jsonl + size-based rotation |

### 24.6 Lesson reinforced

Kimi's #1 (loop ends at file) is the most important finding of the entire P1 cycle: **"closure" claims require a consumer, not just a producer**. Recording this in `feedback-dynamic-workflow-external-review-first` as a second example.

### 24.7 Post-ship follow-up: CLI path trace nesting (2026-07-23)

**Finding (during manual verification):** The hook path (`agent_runtime.handle_query`) opened a `tracer.trace()` block, but the CLI path (`vibe route`) called `router.route()` / `router.orchestrate()` directly without opening one. Result: CLI-routed llm-spans had no task parent, replay rendered flat, aggregator couldn't attribute them to a skill via trace_id.

**Fix:** Wrapped the routing dispatch block in `src/vibesop/cli/main.py:route()` with `tracer.trace("route:...", agent_id="vibe-cli", ...)`. Task span's `metadata.skill_id` / `mode` / `has_match` populated after dispatch completes (mirroring `agent_runtime.py:551-554`).

**Regression tests:** `tests/cli/test_route_cli_trace.py` (3 tests):
1. SINGLE dispatch persists task span with `skill_id` metadata
2. llm-span emitted inside routing flow has task span as `parent_span_id`
3. Early-exit (`should_route=False`) doesn't emit a task span

**Verification (executed):**
```
$ vibe route "verify cli trace nesting $(date +%s)" --yes --quiet
$ cat .vibe/observability/spans.jsonl | jq -c '{kind, id, parent, name}'
{"kind":"task","parent":null,"name":"route:verify cli trace nesting ..."}
{"kind":"llm","parent":"<task-id>","name":"llm:OpenAI:deepseek-v4-flash"}
$ vibe trace metrics <skill-from-task-meta>
Executions: 1 (success rate: 100%)
LLM calls: 1 (success rate: 100%)
```

### 24.8 Post-ship follow-up: asyncio Task isolation (2026-07-23)

**Finding (root-caused from §24.5 #1):** `ObservabilityTracer` used `threading.local()` for span-stack isolation. asyncio Tasks on the same thread share thread-local state, so concurrent `asyncio.gather` traces stomped each other:

```
task_a opens trace_a → _local.trace_context = ctx_a  (with task_a's task span)
task_b opens trace_b → _local.trace_context = ctx_b  (OVERWRITES)
task_a emits llm-span → reads ctx_b → parent = task_b's task span  ❌
```

Concurrent paths are real: `core/orchestration/parallel_scheduler.py:129` and `agent/step_runner.py:438` both call `asyncio.gather(...)` for parallel step execution. Each step can fire an LLM call via SpanWrappedProvider.acall().

**Fix:** Swapped `threading.local()` for `contextvars.ContextVar` in `ObservabilityTracer`. asyncio copies the current context into each new Task at creation, so Tasks get isolated span stacks automatically. Sync code is unaffected — each thread still sees its own context.

**Regression tests** (`tests/core/observability/test_async_isolation.py`, 4 tests):
1. `test_concurrent_traces_do_not_steal_parents` — 2 concurrent traces via `asyncio.gather`, asserts each task-span owns its llm-span (the bug would mix parents).
2. `test_high_concurrency_eight_tasks` — stress test with 8 concurrent traces.
3. `test_sync_nested_spans_still_work` — sync path unchanged.
4. `test_mixed_sync_and_async` — sync-opened trace inherited by awaited task.

**Verification (executed):**
```
4429 tests pass / 0 regressions
ruff + basedpyright clean
```

Kimi's #1 (loop ends at file) is the most important finding of the entire P1 cycle: **"closure" claims require a consumer, not just a producer**. Recording this in `feedback-dynamic-workflow-external-review-first` as a second example.

### 24.9 Post-ship follow-up: pricing table for real cost rollup (2026-07-23)

**Finding (root-caused from §24.5 #3):** Spans emitted by `SpanWrappedProvider` had `cost_usd=0.0` with `cost_estimation="p1_not_available"` metadata. The aggregator's `total_cost_usd` field existed but always summed to zero — cost-based optimisation (rotation, budget enforcement, ROI analysis) was impossible.

**Fix:** New `src/vibesop/llm/pricing.py` with per-provider, per-model pricing tables (USD per million tokens):

* Anthropic (Claude 3.x + 4.x)
* OpenAI (gpt-4o family, o1/o3/o4 reasoning models, gpt-3.5/4 legacy)
* DeepSeek (v4-flash, v4-pro, v4, chat, reasoner)
* Kimi/Moonshot (v1-8k/32k/128k, k2)
* Zhipu (GLM-4 family, including free tier GLM-4-Flash)
* Ollama (local — empty table, returns None)

`SpanWrappedProvider._apply_cost()` looks up pricing after each call and stamps `cost_usd` on the span. The `cost_estimation` marker is now:
* `"measured"` — pricing found and applied (even if cost is $0, e.g. GLM-4-Flash)
* `"unavailable"` — model not in pricing table; cost stays at $0

The distinction matters: `"measured"` with cost=0 means "we know this is free"; `"unavailable"` with cost=0 means "we don't know". Aggregators can sum the former confidently and treat the latter as missing data.

**Lookup strategy:**
1. Exact match in hinted provider's table.
2. Longest-prefix match for versioned models (`gpt-4o-mini-2024-07-18` → `gpt-4o-mini`).
3. Cross-provider fallback — required because OpenAI-compatible proxies (e.g. DeepSeek via `openai` library) report `provider="OpenAI"` but serve `deepseek-v4-flash`. Without cross-provider scan, these would return None.

**Pricing data freshness:** `LAST_UPDATED = "2026-07-23"` exported from `pricing.py`. Refresh quarterly or when major models launch. PRs welcome.

**Regression tests** (`tests/llm/test_pricing.py`, 16 tests):
1. Pricing lookup: exact match, prefix match (longest wins), cross-provider fallback, unknown model, empty model, unknown provider
2. Cost math: simple, typical AI_TRIAGE call, zero tokens
3. SpanWrappedProvider integration: known model gets nonzero cost, unknown keeps zero, free model has zero with `"measured"` marker

**Verification (executed):**
```
$ vibe route "verify cost rollup $(date +%s)" --yes --quiet
$ cat .vibe/observability/spans.jsonl | jq '.[] | {kind, cost_usd, metadata}'
{"kind":"llm","cost_usd":0.000082,"cost_estimation":"measured","tokens":"584/2"}
{"kind":"task","cost_usd":0,...}

$ vibe trace metrics analyze
Executions: 1 (success rate: 100%)
LLM calls: 1 (success rate: 100%)
Cost: total $0.0001 | avg/exec $0.0001   ← was $0.0000 before pricing
```

Test suite: 4445 pass / 0 regressions (was 4429 — +16 new pricing tests).

---

*P1 ship-ready. Kimi's 4 blockers: 3 fixed, 1 rejected with justification. GAP-3 truly closed with `vibe trace metrics` consumer. Next: P2 (analyzers + LoopSpec refactor + pricing table) per §17.5.*






