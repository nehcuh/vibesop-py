# M5 P1 Final Review Brief — Observability Loop Closure

You are giving the **final sign-off review** for v8.2 P1 observability loop closure. P1 ships 5 milestones (M1-M5); this is your chance to block release if any systemic issue remains.

## P1 scope (as shipped)

| # | Component | Status |
|---|-----------|--------|
| M1 | Span schema additions (`schema_version` + `project_id`) | ✅ 9 tests |
| M2 | `SpanWrappedProvider` wraps `create_provider` factory | ✅ 16 tests |
| M3 | `SpanAggregator` trace_id-based attribution + `total_cost_usd` + `llm_call_count` | ✅ 11 tests |
| M4 | `vibe trace replay` CLI command | ✅ 12 tests |
| M5 | E2E integration tests + microbenchmark | ✅ 3 E2E + 2 bench |

**Total: 4431 pass / 14 skipped / 0 regressions. ruff clean. basedpyright 0 errors.**

## Architecture (as shipped)

```
vibe route "<query>"
  └─ agent_runtime.handle_query
      └─ with tracer.trace(...) as task_span          [root task-span]
          ├─ routing decision → task_span.metadata["skill_id"] = X
          ├─ triage_service._llm.call(...)            [wrapped]
          │   └─ SpanWrappedProvider emits llm-span   [child of task]
          ├─ classifier._llm.call(...)                [wrapped, llm-span]
          └─ multi_intent_detector._llm.call(...)     [wrapped, llm-span]

Spans land in .vibe/observability/spans.jsonl (synchronously).

Downstream:
- SpanAggregator.get_skill_metrics(skill_id)
    - reads spans, builds trace_id→skill_id map from task-spans
    - attributes llm-spans via trace_id propagation
    - returns SkillMetrics with avg_tokens / total_cost_usd / llm_success_rate
- vibe trace replay --trace-id <id>
    - renders task → llm → tool_call tree
    - orphan spans (no trace_id) skipped; mid-tree orphans marked ORPHAN
```

## Performance

| Metric | Value | Budget |
|--------|-------|--------|
| Span emit (disabled tracer) | <5µs P95 | <5µs |
| Span emit (enabled tracer) | 45.7µs p50 / 63.4µs p95 / 71.8µs p99 | <100µs P95 |
| Cost relative to one LLM call (80-200ms) | <0.04% | – |

## What changed from original design

| Originally planned (§4) | As shipped | Reason |
|------------------------|------------|--------|
| L2 Echo Mode (in-process answer engine) | **Withdrawn** | Empirical research (§21.3) showed LLM calls already happen 308× in current logs; EchoEngine was "fictional solution to fictional problem" |
| `LoopSpec.analyzer_id` field | **Replaced** with polymorphic `target: SkillRef \| WorkflowRef \| AnalyzerRef` | Category error flagged by both Kimi + Pi |
| P1 then P2 phase order | **Reversed** | Both reviewers flagged: analyzers (P2) must precede metric trigger (P3) |
| 4 gaps from initial audit | **5 gaps** | Deeper audit found SpanAggregator had 0 callers (GAP-3) |
| GAP-1 = "agent-internal span emission missing" | **Revised**: GAP-1 = "wrap LLM provider so existing 308 calls become spans" | Original premise was wrong (calls existed, weren't spanned) |

## Known limitations (deferred to P2/P3)

1. **Async tracer LIFO under concurrency**: `tracer.py` uses `threading.local()`; `asyncio.gather` of 2+ LLM calls in same thread can interleave push/pop in non-LIFO order, mis-attributing parents. Fix: P2 tracer refactor with asyncio task-local context.
2. **No `--follow` tail mode on `vibe trace replay`**: debugging workflow requires manual `--trace-id` lookup. Fix: P2.
3. **`set_llm_factory` injection channel bypass**: third-party code can inject a factory that returns unwrapped providers. Contract-level risk, not code-level. Fix: P2 contract enforcement.
4. **Cost estimation is `p1_not_available`**: M3 didn't ship a pricing table. `cost_usd` stays 0.0 with metadata flag until P2 adds `llm/pricing.py`.
5. **Nested task-spans per trace**: `_build_attribution_map` uses last-writer-wins for trace_id→skill_id; safe today (only `agent_runtime` opens traces), breaks if future code nests. Fix: P2.
6. **Storage path is CWD-relative**: pre-existing v8.1 issue; running `vibe` from different directories scatters spans. Fix: P2 absolute path resolution.

## What I want from you

Sign-off or block. Be terse.

**Section A — Verdict**: score 1-5 on each:
1. Is P1 ready to ship as-is (with documented limitations list)?
2. Does the empirical research → L2 withdrawal decision hold up?
3. Are the 6 deferred items above the right cut (or should any be P1)?
4. Is the test coverage (4431 pass) adequate to catch future regressions?
5. Is the cost model sound for P1 (cost_usd=0 + metadata flag, pricing in P2)?

**Section B — Ship blockers**: anything that MUST be fixed before P1 lands.

**Section C — One-sentence overall verdict**.

Do not summarize back. I wrote this. Find weaknesses.
