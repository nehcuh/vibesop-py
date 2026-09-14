# M2 Implementation Review Brief — GAP-1 LLM Provider Wrap

You are reviewing the **M2 implementation** of v8.2 P1: SpanWrappedProvider — a decorator that wraps every `LLMProvider.call()` / `acall()` to emit an llm-span.

## Context (one paragraph)

v8.2 P1 originally scoped L2 Echo Mode. After Pi's review (§21) + empirical validation, L2 was **withdrawn** because LLM calls already happen (308 calls logged, $0.23 / 226k tokens in current spans.jsonl) but are not span-wrapped. GAP-1 is now: **wrap at the `create_provider` factory so every caller gets spans automatically**. M2 ships that wrap. M1 already shipped `schema_version` + `project_id` fields on Span.

## What shipped

**Three files**:

1. `src/vibesop/llm/span_wrapped.py` (new, ~160 lines)
   - `SpanWrappedProvider(LLMProvider)` decorator class
   - Sync `call()` and async `acall()` both use `start_span` + `try/except BaseException` + `finish_span/fail_span`
   - Non-call methods (`provider_name`, `default_model`, `configured`, `stats`) delegate to inner
   - Token fallback: if `input_tokens`/`output_tokens` missing but `tokens_used` present, split 50/50
   - Cost: left at `0.0` with `metadata.cost_estimation="p1_not_available"` (pricing table is M3)
   - Prompt preview truncated to 500 chars

2. `src/vibesop/llm/factory.py` (modified, 3 lines changed)
   - All three provider construction paths now return `SpanWrappedProvider(inner)`
   - `create_from_env` unchanged — it already calls `create_provider`, so wrap propagates

3. `tests/llm/test_span_wrapped.py` (new, 13 tests)
   - Delegation tests
   - Sync call: emits llm-span with tokens + metadata on success
   - Async call: emits llm-span same way
   - Error propagation: span marked `status="error"`, exception re-raised
   - Disabled tracer: pass-through, no span emitted
   - Token fallback: `tokens_used=99` → (49, 50)

4. `tests/llm/test_llm_factory.py` (4 tests updated)
   - Added `_unwrap()` helper to access inner provider for type assertions

## Self-adversarial pass before this review

| # | Challenge | Finding |
|---|-----------|---------|
| C-1 | LLMProvider ABC.__init__ not called | OK — all public methods overridden; `self.api_key`/`base_url` set via `getattr(inner, ...)` |
| C-2 | KeyboardInterrupt / asyncio.CancelledError leak | **FIXED** — switched from `with tracer.span(...)` (Exception-only) to explicit `start_span` + `except BaseException` |
| C-3 | `get_tracer()` is module singleton, no per-wrap config | Acceptable for P1; user disables via `get_tracer(enabled=False)` at init |
| C-4 | `_inner` exposed as "private" but tests access it | Acceptable Python convention; could add `unwrap()` method later |
| C-5 | SpanWrappedProvider doubles `provider_name` property dispatch | Trivial overhead (<10µs); acceptable |
| C-6 | `create_from_env` chain propagates wrap | Verified via existing test `test_create_from_env_prefers_preferred_when_configured` |
| C-7 | Duck-typed callers (`SemanticIntentAnalyzer`, `CollaborationProtocol`) that accept `llm_client: LLMProvider \| None` | Receive SpanWrappedProvider transparently — duck typing preserves |

## Full test results

- New tests: **13/13 pass** (`tests/llm/test_span_wrapped.py`)
- Existing llm tests: **39/39 pass** (factory tests updated for new return type)
- Full suite: **4347 pass / 14 skipped / 0 regressions** (98 seconds)
- ruff: clean
- basedpyright: 0 errors on span_wrapped.py

## What I want from you

Independent verdict on the implementation. Be terse. Find what I missed.

**Section A — Verdict**: score 1-5 on each:
1. Is `create_provider` the right wrap point (vs each call site, vs ABC method override)?
2. Is the BaseException handling correct (covers cancellation + SIGINT)?
3. Are token / cost accounting choices sound for P1?
4. Is the test surface adequate (does it cover the real risk cases)?
5. Does this actually close GAP-1 (i.e., after this ships, will real hook-path LLM calls show up as llm-spans in spans.jsonl)?

**Section B — Top 3 concerns**: the three issues most likely to bite in production.

**Section C — Duck-typing audit**: Are there LLM call sites in the codebase that bypass `create_provider`? (I checked `distiller.py`, `agent_runtime.py`, `cli/main.py`, `skill_commands.py`, `init.py`, `_index.py`, `quickstart_runner.py`, `pack_installer.py` — all go through `create_provider`. What did I miss?)

**Section D — Schema regression risk**: Existing spans.jsonl has 13 task-spans with `tokens_input=0`. After M2 ships, new llm-spans will appear. Does SpanAggregator (currently 0 callers per §4 GAP-3) handle the new span_kind correctly today, or will it crash on read?

**Section E — One-sentence overall verdict**.

Do not summarize back. I wrote this. Find weaknesses.
