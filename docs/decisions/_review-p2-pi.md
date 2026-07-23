# P2 External Review — Pi

**Date:** 2026-07-23
**Scope:** Same as kimi review — 5 commits on top of P1 (`0dc1ab2..2dc1e1e`).

## Bottom line

No blockers. Two follow-ups that should land before tagging (pricing boundary fix, mkstemp for prune temp) plus documentation cleanup. The ContextVar migration is correct for live code paths.

## Per-commit verdicts

### `fe56337` — ContextVar migration (#1): **Follow-up**

The docstring at `tracer.py:81` is honest but misleading:

> ThreadPoolExecutor threads also get isolation because ContextVar lookup hits the thread's current context (a fresh one for new threads unless explicitly copied).

The word "isolation" frames context-loss as a feature. It's not — it's `ContextVar`'s default behavior that PEP 567 explicitly does NOT copy context to new threads. For `asyncio.gather`/`create_task`, context IS copied correctly. For `run_in_executor`, it's lost.

Tracing every `run_in_executor` in the codebase:

| Location | Path | Risk |
|----------|------|------|
| `agent_runtime.py:698` | `_single_route()` → `run_in_executor(None, self.router.route, query)` | **Dead** — `_single_route` is only called from `process_query`, which is dead code (zero callers). |
| `agent_runtime.py:743` | `_orchestrate()` → same | Dead path (same reason). |
| `llm/base.py:183` | `acall()` → `run_in_executor` | **Safe** — `SpanWrappedProvider.acall()` calls `start_span` on the event-loop thread BEFORE dispatching. The executor thread only runs the raw LLM call; span management stays on the event-loop thread. |

So the live paths are safe. But the docstring is wrong in a way that could cause a future engineer to drop context across executor boundaries. The comment should explicitly warn against `run_in_executor` inside a trace block.

**Tests**: covers 2-way gather, 8-way gather, sync nested, sync→async handoff. Missing: an explicit test that `run_in_executor` drops context (should fail, to document the limitation).

### `54e2f29` — pricing table (#3): **Follow-up**

**2a: Cross-provider fallback is insertion-order deterministic but undocumented.**
If `deepseek-v4-flash` exists in both the `openai` and `deepseek` tables, the one defined first wins. Currently no collisions, but the comment in `get_pricing` says nothing about ordering. Worse: if the provider hint is wrong (caller says `provider="deepseek"` but model is `gpt-4o` served via a DeepSeek proxy), cross-fallback finds `gpt-4o` in the `openai` table and returns OpenAI pricing — silently wrong. Consider returning `None` when provider hint is set but no match in that provider, OR add a `cross_provider_fallback` marker in metadata.

**2b: `cost_estimation` vs `token_accounting` — brief conflated them.**
| Metadata key | Possible values |
|---|---|
| `cost_estimation` | `"unavailable"`, `"measured"` |
| `token_accounting` | `"measured"`, `"estimated_50_50_from_tokens_used"` |

These are orthogonal. A span can have `cost_estimation="measured"` AND `token_accounting="estimated_50_50"`. The 50/50 math systematically overestimates for asymmetric-priced models:

```
Real call: 900 in / 100 out on Claude Opus ($15/$75 per Mtok)
Real cost: (900*15 + 100*75)/1M = $0.021
50/50 est: (500*15 + 500*75)/1M = $0.045  ← 2.1x overestimate
```

The aggregator doesn't read `token_accounting`, so these spans are summed blindly in cost rollups.

**2c: Missing CI freshness check.**
When a new model is added to `models.py`, pricing silently defaults to None. A CI diff between model catalog and pricing table would make this self-healing. Low priority for now.

### `1f71090` — set_llm auto-wrap (#2): **OK to ship**

**3a: Shape check can produce a "wrong wrap".**
If a duck-typed object has `provider_name`/`default_model`/`configured`/`call` as simple attributes (not properties), construction succeeds. Then `SpanWrappedProvider.call()` accesses `response.content[:_PROMPT_PREVIEW_LIMIT]` AFTER the try/except block — a crash there propagates uncaught. Theoretical concern: `SpanWrappedProvider` only wraps `LLMProvider` subclasses whose `call()` returns `LLMResponse` (strongly typed). False-positive rate is low.

**3b: `_llm` and `_triage_service._llm` share the wrapped instance.**
If `wrapped` fails on triage but not direct router use, failure mode is opaque. The test only checks `isinstance`, not that both targets use the wrapper correctly.

Verdict: OK to ship. Warning-on-failure is the right default.

### `0dc1ab2` — CLI trace nesting (#4): **OK to ship**

**4a: The "CHAIN mode" concern in the brief is moot** — `InterceptionMode` has no CHAIN member (only SINGLE, SINGLE_AGENT, MULTI_AGENT_SQUAD, ORCHESTRATE). All four are handled in the CLI dispatch.

**4b: `result.primary` access is properly defensive.** Double-getattr pattern handles all cases.

**4c: 200-char query truncation** is cosmetic — full query is in routing result elsewhere.

**4d: Trace name collision** is harmless — every trace has a unique UUID.

### `2dc1e1e` — trace prune (#5): **OK to ship with one Follow-up**

**5a: Temp file collision IS a correctness bug.**
Two concurrent prune invocations (manual + cron) writing to the same `<file>.tmp` interleave their writes — the output contains the UNION of survivors from both runs, possibly including spans one intended to delete. **Fix**: `tempfile.mkstemp(dir=parent_dir)` for a unique temp name per invocation.

**5b: Empty file edge case** is safe (total=0, pruned=0, "Nothing to prune") but untested.

**5c: Windows `Path.replace()` atomicity**: NTFS `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING` is atomic. Edge case if file is open by another process — Windows users can close it.

**5d: Unparseable `started_at` keep**: correct call. Alternative (silent drop) would be data loss with no recovery path.

## Merged verdict table (kimi + pi)

| Commit | Kimi | Pi | Action |
|--------|------|----|--------|
| `fe56337` ContextVar | Follow-up | Follow-up | Doc warning for run_in_executor; (kimi-only) copy-on-write for gather-in-one-trace |
| `54e2f29` Pricing | Follow-up + boundary fix | Follow-up | Boundary check applied; (pi-only) document cross-provider ordering |
| `1f71090` set_llm wrap | OK to ship | OK to ship | Ship as-is |
| `0dc1ab2` CLI trace | Follow-up (mode=None bug) | OK to ship | mode=None fix applied; (kimi-only) cite hook path correctly |
| `2dc1e1e` Prune | Follow-up | OK + mkstemp | mkstemp applied; empty-file test added |

## Where kimi and pi disagreed

| Question | Kimi | Pi | Resolution |
|----------|------|----|-----------|
| Is hook-path `run_in_executor` a live bug? | Yes — "mirrors hook path" rationale wrong | No — `_single_route`/`_orchestrate` are dead code | **Pi correct.** `process_query` has zero callers; sync `handle_query` calls `router.route` directly. Verified by grep. |
| Pricing prefix boundary | Fix before tagging (~5 lines) | Not raised | Kimi correct. `gpt-4.1` startswith `gpt-4` is 15x overcount. Fix applied. |
| Concurrent prune temp collision | Ergonomic issue | Correctness bug (UNION of survivors) | Pi correct. Both want mkstemp. Applied. |

Both reviewers agreed on:
- ContextVar migration is sound for tested patterns; latent gaps need P3.
- Pricing needs more granular markers (`token_accounting` should be consumable).
- `set_llm` is OK to ship as best-effort.
- Empty file prune test should exist.
- Misleading docstrings (tracer.py, models.py) should be corrected.
