# P2 External Review Brief — v8.2 Observability Loop Closure

**Reviewer:** Kimi
**Date:** 2026-07-23
**Review scope:** 5 commits on top of P1 ship (`38c34cc..2dc1e1e`), all addressing follow-up limitations surfaced in §24.5 of `docs/decisions/2026-07-22-observability-loop-closure.md`.

## Context

P1 shipped the v8.2 observability loop: spans → JSONL → aggregator → `vibe trace metrics` consumer. Kimi's earlier review flagged 4 blockers (3 fixed, 1 rejected) and surfaced 5 follow-up limitations (§24.5 #1–#5) for P2. This batch closes all 5.

The design doc is at `docs/decisions/2026-07-22-observability-loop-closure.md` (1670 lines). §24.5 lists the limitations; §24.7–§24.11 document each P2 fix with root cause, design choice, and verification.

## Commits under review

| Commit | Closes | Summary |
|--------|--------|---------|
| `0dc1ab2` | §24.5 #4 | CLI `vibe route` now opens `tracer.trace()` block — task-span parent for CLI-routed llm-spans (was hook-only). |
| `fe56337` | §24.5 #1 | `ObservabilityTracer` replaced `threading.local()` with `contextvars.ContextVar` for asyncio Task isolation. |
| `54e2f29` | §24.5 #3 | `src/vibesop/llm/pricing.py` — per-provider USD/Mtok tables, lookup with cross-provider fallback for OpenAI-compat proxies. |
| `1f71090` | §24.5 #2 | `UnifiedRouter.set_llm()` auto-wraps LLMProvider-shaped providers via `_maybe_wrap_for_spans()`. |
| `2dc1e1e` | §24.5 #5 | `vibe trace prune --days N` CLI command with atomic temp+rename. |

## What I want you to grill

### 1. Correctness of the ContextVar migration (#1)

`ObservabilityTracer` used `threading.local()` to isolate per-call span stacks. Under `asyncio.gather`, all Tasks on the same thread shared the same thread-local, so concurrent traces stomped each other's parent chains.

Fix (`src/vibesop/core/observability/tracer.py`):
```python
self._ctx_var: contextvars.ContextVar["TraceContext | None"] = contextvars.ContextVar(
    "vibesop_trace_context"
)
```

Concerns to check:
- Are there any places where we still rely on thread-local semantics? (E.g. a worker thread spawned from a sync `tracer.trace()` block that should inherit the context — `ContextVar` does NOT propagate to new threads by default.)
- Does `asyncio.create_task()` correctly copy the context? (It should, per PEP 567, but I want a sanity check on whether anything in our code path uses `loop.run_in_executor()` or `asyncio.to_thread()` that would drop it.)
- Tests: `tests/core/observability/test_async_isolation.py` (4 tests) cover 2-way and 8-way `gather`, sync nested, and sync→async handoff. Are these sufficient or is there a concurrency pattern we missed?

### 2. Pricing table correctness and maintenance burden (#3)

`src/vibesop/llm/pricing.py` has hardcoded per-provider tables (USD per million tokens):
- anthropic, openai, deepseek, kimi, zhipu, ollama

Lookup logic:
```python
def get_pricing(model: str, provider: str | None = None) -> ModelPrice | None:
    # 1. Exact match in provider table
    # 2. Longest-prefix match in provider table (e.g. "claude-sonnet-4-6-20250818" → "claude-sonnet-4-6")
    # 3. Cross-provider fallback (for OpenAI-compat proxies that report provider="openai" but model="deepseek-v4-flash")
    # 4. None if no match anywhere
```

Concerns to check:
- The cross-provider fallback is unbounded — if two providers define the same model name with different prices, which wins? (Current behaviour: first-found wins, but dict iteration order is insertion-ordered so this is deterministic but undocumented.)
- Prices will drift as providers update. There's a `LAST_UPDATED = "2026-07-23"` constant. Should we wire this into a CI check or a periodic refresh? Or is "explicit constant + grep-able date" enough?
- `cost_estimation` marker now has three states: `"measured"` (priced), `"unavailable"` (unknown model), `"estimated_50_50_from_tokens_used"` (when `input_tokens`/`output_tokens` are missing but `tokens_used` exists). Is the third state's math (`tokens_used * 0.5 * (in_rate + out_rate)`) defensible, or should we just drop those spans from cost rollups?
- Tests: `tests/llm/test_pricing.py` (16 tests). Are there model-name formats we should test but didn't? (e.g., model names with version suffixes like `claude-sonnet-4-6-20250818` vs `claude-sonnet-4-6`.)

### 3. set_llm auto-wrap — strictness vs. ergonomics (#2)

`_maybe_wrap_for_spans()` (in `src/vibesop/core/routing/unified.py`) wraps if the provider has the LLMProvider shape (`provider_name`, `default_model`, `configured`, `call`). Otherwise it passes through unchanged.

Decision: chose auto-wrap over contract enforcement (`TypeError` on non-LLMProvider). Rationale: agent runtimes pass duck-typed objects with just `.call(prompt)`; forcing them to inherit from our ABC would break integrations.

Concerns to check:
- Is the "shape check" (4 attrs via `hasattr`) too loose? Could a third-party object accidentally satisfy this and get wrapped when it shouldn't?
- The wrap is best-effort: if `SpanWrappedProvider(provider)` raises, we log a warning and use the unwrapped provider. Is silent fallback the right default, or should we surface this harder?
- Tests: `tests/core/routing/test_set_llm_wrap.py` (8 tests). Are there integration paths we missed (e.g., the wrapped provider being called from a sync vs. async code path)?

### 4. vibe trace prune atomicity and ordering (#5)

`vibe trace prune --days N` reads spans.jsonl, filters, writes survivors via temp+rename.

Concerns to check:
- The temp file lives at `<span_file>.tmp`. If another prune runs concurrently (e.g., cron + manual), they'll collide on the temp filename. Should we use `mkstemp` instead? Or is the assumption "prune is run by a human or one cron" sufficient?
- Spans with unparseable `started_at` are kept (defensive). Is this the right call, or should they be dropped on the theory that "if we can't reason about the timestamp, we can't trust the span"?
- The atomic-rename is atomic on POSIX. On Windows, `Path.replace()` may fail if the target is open. The test suite runs on Windows in CI — does the prune path need a Windows-specific code path, or is "Windows users deal with it" acceptable?
- Tests: `tests/cli/test_trace_prune.py` (7 tests). Did we miss the "file truncated to 0 bytes" edge case? (Empty input file → empty output, no crash.)

### 5. CLI trace nesting — metadata propagation (#4)

`src/vibesop/cli/main.py:route()` wraps the dispatch block in `tracer.trace("route:...")`. Metadata (`skill_id`, `mode`, `has_match`) is populated after dispatch completes.

Concerns to check:
- The task span's `metadata.query` is truncated to 200 chars. Is 200 the right cut-off? (If a user runs a long prompt, the trace detail will only show the first 200 chars.)
- The trace name is `route:<first 80 chars of query>`. If two CLI calls have the same first 80 chars but different full queries, their trace names collide. Is that a problem for `vibe trace show <trace_id>`? (trace_id is unique per call, so probably not, but worth confirming.)
- Tests: `tests/cli/test_route_cli_trace.py` (3 tests). Did we miss the SQUAD/CHAIN mode paths? Those have different result shapes (`result.primary` may be absent or different).

## Test suite status

```
$ uv run pytest -q --ignore=tests/api
4472 passed, 14 skipped, 3 warnings in 103.62s
```

P1 baseline was 4445 → P2 added 27 tests across 5 new test files (no regressions).

## What success looks like for this review

For each of the 5 commits, tell me one of:
- **"OK to ship"** with a one-sentence justification, OR
- **"Blocker"** with a specific code change required, OR
- **"Follow-up"** — not blocking the ship but worth a P3 ticket.

Particularly interested in:
- Did I miss a correctness landmine in the ContextVar migration?
- Is the pricing fallback chain sound, or does it create hidden coupling between providers?
- Does `set_llm` auto-wrap create a new class of "works by accident" bugs?

Be specific. "This looks fine" is not useful feedback.
