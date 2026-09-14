# W3 Implementation Review Brief

**Reviewer**: grok + pi
**Date**: 2026-07-29
**Phase**: task-memory-loop v3 → W3 Replay Mode
**Prior**: W2 shipped at commit a7f57dc (vibe recall CLI + 33 tests, grok+pi pass)

## Scope (7 files, ~1100 LOC)

| File | Purpose | LOC |
|------|---------|-----|
| `src/vibesop/core/observability/recall.py` | Extended RecallResult (trace_id, skill_id, gold_success_count) + learner param | ~370 (was ~270) |
| `src/vibesop/core/observability/replay.py` | NEW: `ReplayDecision`, `should_replay()`, `emit_replay_span()` | ~190 |
| `src/vibesop/cli/main.py` | `--no-replay` flag + `_maybe_prompt_replay()` helper + route integration | +60 |
| `tests/core/observability/test_recall.py` | +10 tests for W3.1 (trace_id/skill_id) + W3.2 (learner gold fusion) | +200 |
| `tests/core/observability/test_replay.py` | NEW: 14 tests for should_replay + emit_replay_span | ~290 |
| `tests/cli/test_route_replay_cli.py` | NEW: 4 CLI smoke tests (auto-prompt / suppress flags) | ~210 |
| `tests/core/observability/test_replay_acceptance_smoke.py` | NEW: 10 fixture-based kill-switch tests | ~260 |
| `tests/fixtures/replay_gold_spans.jsonl` | NEW: 10 spans (7 cmspark gold + 2 lidsleep candidate + 1 distract) | 10 lines |

## Contract to verify

### 1. RecallResult extension (W3.1+W3.2)

Three new optional fields on `RecallResult`:
- `trace_id: str | None` — most recent trace_id for this task_id
- `skill_id: str | None` — mode of skill_id across spans
- `gold_success_count: int` — from InstinctLearner.success_count

New `recall_similar(learner=None, min_gold_span_count=5)` parameter:
- When `learner=None`: `is_gold=False`, `gold_success_count=0` (preserves W2 D5 retrieval purity)
- When `learner=InstinctLearner()`: looks up instinct for representative_query; if `success_count>=1 AND span_count>=5` → `is_gold=True`

### 2. `should_replay()` + `ReplayDecision` (W3.3)

```python
should_replay(query, spans, cache=None, learner=None, threshold=0.70, days=30)
  → ReplayDecision(should_prompt, top_match, reason)
```

Decision matrix:
- `learner=None` → `(False, None, "no_learner")`
- empty spans or no match → `(False, None, "no_recall")`
- top match `is_gold=True` → `(True, top_match, "gold_match")`
- top match not gold → `(False, top_match, "not_gold")`

### 3. `emit_replay_span()` (W3.4)

```python
emit_replay_span(tracer, top_match, extra_metadata=None) -> trace_id | None
```

Emits a `workflow_node` span (not `task` — avoids creating sibling top-level trace) with:
- `name = replay:<old_task_id>`
- `metadata.replay_of = prior trace_id`
- `metadata.old_task_id`, `metadata.old_query`, `metadata.skill_id`, `metadata.similarity`, `metadata.gold_success_count`

Failures are caught + logged (returns None) — replay is UX affordance, not critical path.

### 4. `vibe route` integration (W3.5)

Auto-prompt flow inside the existing `with _cli_tracer.trace(...)` block:

```python
if not no_replay and not json_output and not minimal:
    try:
        _maybe_prompt_replay(tracer=_cli_tracer, query=decision.query, console=console)
    except Exception as exc:
        logger.warning("replay prompt skipped due to: %s", exc)
# ... normal routing continues ...
```

Inside `_maybe_prompt_replay`:
1. `SpanWriter().query_recent(limit=500)` → historical spans
2. `InstinctLearner()` → fresh learner (file-backed)
3. `should_replay(query, spans, learner=learner)` → decision
4. If gold match: Rich panel showing trace_id + skill_id + step_sequence preview, then `typer.confirm("Replay?", default=True)`
5. On Y: `emit_replay_span()` + print step_sequence numbered list
6. On n: silent skip
7. Routing continues either way

Suppress flags:
- `--no-replay` (explicit opt-out)
- `--json` (programmatic consumer)
- `--minimal` (sub-agent consumption)

## Design decisions to scrutinize

### D1: Why auto-prompt default (not `--replay` flag)

V3 design §3 W3 line 112 says "`vibe route --replay`". Merged review P0-3 says "默认提示" (auto-prompt). I went with auto-prompt because:
- Pi's P0-3 argument: opt-in flag adds cognitive load (user must remember to add it)
- Kill criterion "follow rate" only measures signal when the prompt fires; opt-in kills signal
- Users who don't want prompts can use `--no-replay`

**Push-back welcome**: Is `--no-replay` discoverable enough? Should we add a config setting (e.g. `vibe config set replay.enabled false`)?

### D2: Why no hint injection into routing context

Pi's P0-3 explicitly rejected auto-injected hints. The current implementation emits a `replay` span for **provenance** (new trace linked to old) and **displays** the prior step_sequence, but does NOT inject step_sequence into the routing decision or skill context. The external AI agent (Claude Code) receives the same routing output as a normal `vibe route` call.

**Trade-off**: This means replay's "value" is purely (a) trust signal (gold match) + (b) transparency (visible prior trace). It does NOT make the agent itself faster or smarter. Is this the right scope, or should W3 also inject a "prior context" payload?

### D3: Why `learner` is optional on `recall_similar`

Recall is a retrieval primitive (W2 D5 decision). Gold status is a separate concern. By keeping `learner` optional:
- `vibe recall` (W2 CLI) continues to work without InstinctLearner
- `should_replay` (W3) passes a learner to fuse gold status at the decision layer
- Future callers (W4 skill promote) can use either path

### D4: Why `workflow_node` span kind (not new `replay` kind)

Existing SpanKind = `Literal["task", "llm", "tool_call", "file_edit", "workflow_node"]`. Adding "replay" would require schema migration + downstream aggregator changes. Using `workflow_node` with `name="replay:<task_id>"` + `metadata.replay_of=<trace_id>`:
- No schema migration
- Aggregator/dashboard can filter by `name.startswith("replay:")` if needed
- Provenance is captured in metadata, not kind

### D5: Why per-task gold (via `get_instinct_for_query`) not per-cluster (via `assess_gold_status`)

Recall returns individual `task_id`s, not `Cluster`s. To use cluster-level gold, we'd need to:
1. Recall top-k task_ids
2. Re-cluster all spans
3. Find which cluster each task_id belongs to
4. Check cluster.is_gold

This is O(N) re-clustering per route. Instead, we use per-task gold:
- `instinct = learner.get_instinct_for_query(representative_query)` — O(1) dict lookup
- `is_gold = instinct.success_count >= 1 AND span_count >= 5`

The 5-span gate mirrors W1's cluster_size gate (assess_gold_status uses min_cluster_size=5). Per-task span_count is the analog.

**Trade-off**: A cluster with 3 task_ids (each 2 spans = 6 total) would be `is_gold=True` under W1 but `is_gold=False` under W3 (no single task_id reaches 5 spans). Is this the right call?

## Review focus questions

1. **Correctness**: Does `_maybe_prompt_replay` correctly swallow all failure modes without breaking routing? (try/except wraps the whole call site)
2. **Concurrency**: `InstinctLearner()` is constructed fresh each route call. The constructor reads `.vibe/instincts.jsonl` from disk. Is this acceptable overhead, or should we cache the singleton?
3. **UX**: The Y/n prompt uses `typer.confirm("Replay?", default=True)`. Is Y the right default? (User pressed enter = replay)
4. **Test coverage**: Acceptance smoke uses mocked keyword embeddings + fake learner. Are there code paths only exercised by real InstinctLearner that we're missing?
5. **API stability**: Is `ReplayDecision` field set right for W4 consumers? (W4 skill promote will likely use cluster-level gold, not ReplayDecision directly)

## How to run

```bash
# Unit + helper tests
uv run pytest tests/core/observability/test_replay.py tests/core/observability/test_recall.py -v

# CLI integration
uv run pytest tests/cli/test_route_replay_cli.py -v

# Acceptance smoke
uv run pytest tests/core/observability/test_replay_acceptance_smoke.py -v

# Manual smoke (requires real spans + instincts)
uv run vibe route "cmspark screenshot permission popup"
# Expect: if gold match, prompt appears
```

## Out of scope (defer)

- Hint injection mode (config fallback per design line 114) — config schema not yet defined
- Real `rebuild_dag` integration in prompt preview — `step_sequence` from recall is enough for v1
- Cross-project replay — cut in v3
- Per-step frequency count — W4 (Skill Promote) territory
- Tool-call replay — blocked by privacy rule on `tool_input`
