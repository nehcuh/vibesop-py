# P2 External Review — Kimi

**Date:** 2026-07-23
**Session:** `session_a565f197-f2d4-4170-88d2-837d3af620b2` (resumable via `kimi -r`)
**Scope:** 5 commits (`0dc1ab2..2dc1e1e`) addressing §24.5 #1–#5 follow-ups.

## Bottom line

Nothing is a ship-blocker in the sense of "this breaks something that worked before" — every gap found is either pre-existing (hook-path orphaning) or equally broken under `threading.local`. But two commits overclaim closure:

1. **#1 is narrowed, not closed.** The shared-mutable-`TraceContext` issue in a single trace survives the migration, and the hook path never had working nesting to begin with.
2. **#3 stamps confident wrong prices** on real current models (`gpt-4.1`, `o1-pro`/`o3-pro`) due to missing prefix-boundary check. Cheapest fix in the batch — land before tagging.

## Per-commit verdicts

### `fe56337` — ContextVar migration (#1): **Follow-up**

Tested pattern is fixed, but closure claim is overstated.

**Gap A — the fix doesn't cover concurrent spans inside one shared trace.** `ContextVar` holds a *mutable* `TraceContext`, and `asyncio.Task` context copies are shallow: N tasks spawned by `asyncio.gather` inside a single `tracer.trace()` all bind the same `TraceContext` object. `start_span`/`finish_span` from `SpanWrappedProvider.acall` interleave push/pop on one shared `span_stack`:

```
outer trace → stack [S0]
task A: start_span → [S0, A1]
task B: start_span → [S0, A1, B1]   (B1.parent = A1 — wrong, should be S0)
task A: finish_span → pops B1 (!)   (pop isn't id-checked)
task B: finish_span → pops A1
```

Spans persist and the stack self-heals in the symmetric 2-task case, but parent attribution is corrupted, and with 3+ tasks or mid-flight cancellation it degrades further. This is precisely the `parallel_scheduler.py:129` / `step_runner.py:438` path §24.8 cites as motivation — and none of the 4 tests exercise it (they all open a *fresh trace per task*, the one pattern that works). Fix: copy-on-write — `_push`/`_pop` should `_set_context()` a new `TraceContext` with a copied stack instead of mutating in place, so task contexts actually diverge. Also make `_pop` verify popped id matches (warn on mismatch).

**Gap B — `run_in_executor` drops the context on the hook path.** `agent_runtime.py:698` and `:743` route via `loop.run_in_executor(None, self.router.route, query)`. The trace opened at `agent_runtime.py:409` lives in the coroutine's context; the executor thread gets a fresh default context, so AI-triage llm-span is emitted as orphan with standalone `trace_id`. `asyncio.to_thread` propagates contextvars; `run_in_executor` does not. Pre-existing under `threading.local` (not a regression), but means §24.7's "mirrors hook path" rationale for `0dc1ab2` is citing reference behavior that never worked.

**Gap C — nested `trace()` reuses the outer context.** `trace()` inside an active trace pushes onto the existing `TraceContext` without updating `ctx.trace_id`, and stomps `current_task_id`. No production path nests traces today, but `trace()` should unconditionally install a fresh `TraceContext`.

Also stale: `models.py:139` docstring still says "Thread-local trace context."

Tests insufficient: add a test with two concurrent llm-spans inside *one* trace via gather. That's the missing pattern.

### `54e2f29` — pricing table (#3): **Follow-up (fix boundary bug before tagging)**

- **Prefix match has no boundary check.** `"gpt-4.1".startswith("gpt-4")` is True → priced at $30/$60 when real gpt-4.1 is ~$2/$8 (15x overcount), stamped `cost_estimation="measured"`. Same class: `o1-pro` → `o1` (10x undercount), `o3-pro` → `o3`. Require char after matched prefix to be `-` or end-of-string. The "measured" marker makes this worse than returning None — it's a confident wrong number.
- **Brief misdescribes the third state.** `estimated_50_50_from_tokens_used` is written to `metadata["token_accounting"]` (`span_wrapped.py:164,212`), while `cost_estimation` stays `"measured"`. So an aggregator filtering on `cost_estimation == "measured"` cannot exclude 50/50 guesses. Either mirror the state into `cost_estimation` or document that consumers must check both fields. On math: 50/50 systematically *overestimates* (output rates 3–5x input; real traffic input-heavy). Defensible as conservative bound — but say so, and don't call it "measured".
- **Cross-provider fallback**: first-found-wins is deterministic (insertion order, anthropic first), no model-name collisions today. One comment closes this; no hidden coupling in practice.
- **`LAST_UPDATED`**: `last_updated()` is dead code — only its own test calls it. Either wire date into `vibe trace metrics` output or delete function. CI freshness check is overkill; quarterly manual refresh is proportionate.
- **Missing test formats**: dotted versions (`gpt-4.1`), `-pro`/`-preview` suffixes (`o3-pro`, `kimi-k2-0711-preview`), provider alias case (`provider="Moonshot"`).

### `0dc1ab2` — CLI trace nesting (#4): **Follow-up**

CLI change itself correct. Two problems:

- The "mirrors hook path" rationale is false (see Gap B above). Fix the executor call or stop citing it.
- **Minor bug at `main.py:780`**: `_cli_task_span.metadata["mode"] = getattr(_mode, "value", str(_mode))` — when `result.mode` is `None`, this overwrites the correct `decision.mode.value` (set at line 728) with the literal string `"None"`. Only overwrite when `_mode is not None`.
- Specific concerns are non-issues: 200-char truncation is fine for metadata field; 80-char name collisions are harmless since trace_id is unique.
- Test gap: only SINGLE mode covered. Add parametrized test per mode (SQUAD, ORCHESTRATE, CHAIN).

### `1f71090` — set_llm auto-wrap (#2): **OK to ship**

Strictness/ergonomics call is right. 4-attr shape check is loose but blast radius of false positive is benign (extra span emission you didn't ask for), wrap failure falls back with logged warning, observability-as-best-effort is correct posture. Nits, non-blocking:

- No `__getattr__` delegation: after wrapping, custom methods a third-party provider exposes beyond the ABC surface are unreachable via `router._llm`. Callers holding their own reference unaffected. Document it.
- `span_wrapped.py:48` claims "we proxy `_stats` via the inner provider" — no such proxy exists. Nothing accesses it (grepped), doc bug not code bug.
- Test gap: all 8 tests exercise sync `call()`; auto-wrapped provider's `acall` path (matters for gather scenarios) untested at `set_llm` integration level.

### `2dc1e1e` — trace prune (#5): **Follow-up**

- **Lost-append race is real and doc's atomicity claim is wrong for writers.** Prune doesn't take the `fcntl` lock `SpanWriter` uses. A concurrent `vibe route` appending between prune's read and `replace()` writes to the old inode, which the rename then orphans — those spans vanish silently. "Appenders see old or new file, never half-written" is true for readers; appenders in window lose data. Take exclusive flock on span file across read+write, or document the window explicitly.
- **Temp-file collision**: use `mkstemp(dir=span_file.parent)`. Two concurrent prunes currently collide on `<file>.tmp` and loser exits 1 with confusing error. Two-line fix.
- **Keeping unparseable spans**: correct call. Garbled line is signal of writer corruption; silently dropping would hide that.
- **Windows**: acceptable as-is. `SpanWriter` opens/closes per append, so replace-fails-if-open window is milliseconds; writer already has documented no-flock fallback on Windows (pre-existing).
- **Empty file**: behavior correct (total=0 → "Nothing to prune", no crash) but untested. Add the one test.

## Direct answers to brief's questions

- **Did I miss a correctness landmine in the ContextVar migration?** Yes — mutable value + shallow context copy.
- **Is the pricing fallback chain sound, or hidden coupling?** Sound in structure, but mislabels estimated costs as measured and over-matches on prefixes.
- **Does `set_llm` auto-wrap create "works by accident" bugs?** No meaningful class — failure modes are benign and logged.

## Recommended ship order

1. Land pricing prefix-boundary fix (~5 lines) before tagging.
2. Fix `main.py:780` mode=None bug (one-line conditional).
3. Add the empty-file prune test + parametrized SQUAD/ORCHESTRATE/CHAIN tests.
4. P3 tickets: copy-on-write TraceContext + id-checked pop; `to_thread` in agent_runtime; prune flock; drop dead `last_updated()`.
