# W0 Implementation Review — task_id + dev/prod + embedding benchmark

> 2026-07-29 — review gate before W1
> Implementer: Claude (this session)
> Reviewers: grok + pi (independent)
> Authoritative design: `docs/decisions/2026-07-29-task-memory-product-design.md`

## What was built (W0 complete)

### W0.A — task_id derivation (frozen normalize contract)
- New: `src/vibesop/core/observability/task_id.py`
- `derive_task_id(query) -> str | None`: sha1(normalize(query))[:16], 16 hex chars (64 bits)
- `normalize_query(query) -> str`: NFKC → strip XML wrapper → casefold → strip non-word/non-space/non-hyphen → collapse whitespace
- Frozen contract fixture: `tests/fixtures/task_id_normalize.jsonl` (12 equivalence pairs)
- 22 unit tests in `tests/core/observability/test_task_id.py` — all pass
- `@lru_cache(maxsize=4096)` on `derive_task_id`

### W0.B — dev/prod auto-detection
- New: `src/vibesop/core/observability/dev_detect.py`
- `is_dev_environment() -> bool`:
  1. Env override `VIBESOP_OBSERVABILITY_MODE=dev|prod` wins
  2. `PYTEST_CURRENT_TEST` in env → dev
  3. `sys.argv[0]` endswith `pytest` / `pytest.exe` → dev
  4. `-m pytest` in argv → dev
  5. Else: prod (fail-safe to prod, not dev)
- SpanWriter integration: when `storage_path=None`, route to `spans.dev.jsonl` if dev, else `spans.jsonl`
- 20 unit tests in `test_dev_detect.py` + 5 routing tests in `test_span_writer_dev_routing.py`
- Added idempotent `mkdir(parents=True, exist_ok=True)` on every `write_span` (defensive against CWD changes)

### W0.C — embedding mini-benchmark
- Script: `scripts/benchmark_embeddings.py`
- Gold cluster: 10 real cmspark screenshot-permission queries
- Distractor cluster: 10 unrelated cmspark queries
- Tested: `paraphrase-multilingual-MiniLM-L12-v2` + `bge-small-zh-v1.5` + `bge-base-en-v1.5`
- Report: `docs/decisions/w0-embedding-benchmark.md`
- **Winner: MiniLM-L12-v2** (separation −0.274, perfect precision @ 0.85)
- **Recommended threshold: 0.80** (recall=0.622, precision=0.824, FPR=0.06)
- **Design deviation**: substituted bge-small-zh + bge-base-en for design's bge-m3 + e5-multilingual-small (fastembed doesn't have those exact variants; e5-large was 2.2GB, skipped)

### W0.D — wire task_id into trace call
- `src/vibesop/cli/main.py:724`: added `task_id=_derive_task_id(decision.query)` to route trace
- `src/vibesop/agent/runtime/agent_runtime.py:409`: was hardcoded `task_id=None`, now uses `derive_task_id(query)`
- Added `_reset_tracer_for_tests()` to tracer.py (test escape hatch)
- Fixed bug: `agent_runtime._obs_tracer` module-level cache survived tracer singleton reset, returning stale path
- 3 e2e tests in `test_task_id_e2e.py`: same query → same task_id across calls, different queries → different task_ids, task_id is 16 hex chars

## Total test count: 4936 passed, 0 failed, 14 skipped (full suite)

## Files changed (added or modified)
- `src/vibesop/core/observability/task_id.py` (new, 115 lines)
- `src/vibesop/core/observability/dev_detect.py` (new, 50 lines)
- `src/vibesop/core/observability/span_writer.py` (modified — dev routing + mkdir)
- `src/vibesop/core/observability/tracer.py` (modified — added `_reset_tracer_for_tests`)
- `src/vibesop/cli/main.py` (1-line change — pass task_id)
- `src/vibesop/agent/runtime/agent_runtime.py` (3-line change — pass task_id)
- `tests/core/observability/test_task_id.py` (new, 22 tests)
- `tests/core/observability/test_dev_detect.py` (new, 20 tests)
- `tests/core/observability/test_span_writer_dev_routing.py` (new, 5 tests)
- `tests/core/observability/test_task_id_e2e.py` (new, 3 e2e tests)
- `tests/fixtures/task_id_normalize.jsonl` (new, 12 pairs)
- `scripts/benchmark_embeddings.py` (new)
- `docs/decisions/w0-embedding-benchmark.md` (new)
- `pyproject.toml` (added `fastembed` dep)

## What I want review on

Please critique freely. Specific questions below — but feel free to ignore them and find bigger issues.

### 1. normalize_query correctness (W0.A)
- Is the regex `_KEEP_RE = re.compile(r"[^\w\s-]", re.UNICODE)` correct for "strip all punctuation but preserve word chars + whitespace + hyphen"?
- The frozen fixture has 12 pairs. Are there equivalence cases I missed that would break in production? (e.g. traditional ↔ simplified Chinese, synonym substitution, partial-query matches)
- Hyphen preservation: intentional (so `test-case` ≠ `test case`) or should it be normalized away?

### 2. dev/prod detection false negatives (W0.B)
- I fail-safe to "prod" if no signal matched. Is that the right default? (Cost of false-positive dev = silent loss of prod data; cost of false-negative dev = test pollution)
- I don't inspect the call stack for `/tests/` paths (would catch pytest running via IDE runners). Worth adding, or too expensive per-call?
- `is_dev_environment()` is called in `SpanWriter.__init__`. If a long-running prod process was started inside a pytest session (unusual but possible), it would route to dev. Is this a real concern?

### 3. Embedding benchmark methodology (W0.C)
- 10 gold + 10 distractor = 20 total. Is that enough to pick a model?
- I used real user queries as gold standard, but didn't validate that ALL 10 are actually about the same task (some include "微信没有登陆" + "不可恢复错误" — possibly different bugs in the same family). Should the benchmark require tighter task-equivalence?
- I substituted bge-small-zh + bge-base-en for design's bge-m3 + e5-multilingual-small. Does this substitution invalidate the design's intent?
- The recommended threshold (0.80) contradicts the v3 design's 0.85. Should I update the design doc, or treat this as a W1 kill-switch parameter to tune?

### 4. task_id bug fix scope (W0.D)
- The v3 design only asked to fix `main.py:724`. I also fixed `agent_runtime.py:409` (was hardcoded `task_id=None`). Was that scope creep, or required for the bug to actually be fixed? (AgentRuntime.handle_query is the hook path — arguably more important than the CLI path)
- I added `_reset_tracer_for_tests()` to tracer.py as a test-only escape hatch. It uses `global _tracer`. Is there a cleaner pattern (e.g. dependency injection in tests)?
- The bug "contextvars doesn't cross processes" isn't fully fixed by W0 — it's worked around. Sub-agent CLIs (Claude Code) still don't inherit task_id from parent. Is that acceptable for W0, or does it need explicit documentation/handoff?

### 5. FastEmbed dependency (pyproject.toml)
- I added `fastembed` as a runtime dep (~50MB + onnxruntime). Original design implied sentence-transformers. FastEmbed is lighter, but locks us into its model list. Worth switching later?

### 6. Kill switch status
- v3 W0 kill switch criteria: "task_id 在新数据上填充率 + dev/prod 自动检测工作 + embedding 模型选定 / 100% / 工作 / 选定"
- All three met. Ready to enter W1?

## What's NOT in scope for this review

- W1-W4 design (already reviewed in v3)
- Cross-project recall (deferred to post-MVP per v3)
- The contextvars cross-process limitation (working as intended for W0; cross-process task attribution is via the DAG rebuilder joining on metadata.parent_session, not via task_id propagation)
