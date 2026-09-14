# M4 Implementation Review Brief — `vibe trace replay` CLI

You are reviewing the **M4 implementation** of v8.2 P1: a new `vibe trace replay` CLI subcommand that reads `.vibe/observability/spans.jsonl` and renders each trace as an indented task → llm → tool_call tree.

## Context

v8.2 P1 has now shipped M1-M3:
- M1: Span schema additions (`schema_version` + `project_id`)
- M2: `SpanWrappedProvider` wraps every `LLMProvider.call()` → llm-span
- M3: `SpanAggregator` gains trace_id-based skill attribution + `total_cost_usd`

M4 closes the loop with a human-facing debug tool: it shows what the agent actually did during a routing decision, including the LLM calls that were previously invisible.

## What shipped

**One file changed**: `src/vibesop/cli/commands/trace_cmd.py` (+170 lines)

New `vibe trace replay` subcommand alongside existing `list / show / clean` (those still operate on `.vibe/traces/*.json`, the older per-routing-trace JSON snapshots).

### CLI surface

```
vibe trace replay [--trace-id ID] [--span-file PATH] [--limit N] [--json]
```

Default: reads `.vibe/observability/spans.jsonl`, groups by trace_id, renders the most recent 10 traces as trees.

### Rendering

Each span line shows: kind icon (T/L/X/F/W), status, name, duration, `[tokens_in+tokens_out tok]`, cost, optionally `skill=`.

Tree depth inferred from `parent_span_id` chains.

Summary line per trace: span count, LLM/tool split, total tokens, total cost.

### Behaviors

- Missing span file → graceful panel with hint
- Empty span file → "No spans" message
- Orphan spans (empty trace_id) → skipped with notice
- `--trace-id` accepts prefix; no match → exit 1
- `--json` outputs `[{trace_id, spans: [...]}, ...]`

## Tests

`tests/cli/test_trace_replay.py` — 8 tests covering basic replay, missing/empty file, trace-id filter, no-match exit code, --limit cap, JSON structure, nested tree indentation.

All 8 pass. Full suite 4422 pass / 0 regressions.

## Self-adversarial pass

| # | Challenge | Finding |
|---|-----------|---------|
| C-1 | Empty trace_id merges orphans into bogus "" trace | **FIXED** — skip orphans, print notice |
| C-2 | Deep nesting stack overflow | Acceptable: real span depth <5; Python default recursion limit 1000 |
| C-3 | `_load_spans` reads whole file into memory | Acceptable for P1; production-size spans.jsonl is MB-scale; M5 microbench will quantify |
| C-4 | Short `--trace-id` prefix matches too broadly | Documented behavior, no fix needed |
| C-5 | `_decode_span_field` swallows JSONDecodeError → empty dict | Acceptable: replay tool optimizes for not-crashing over fidelity |
| C-6 | No streaming / incremental read | Acceptable: P1 scope |

## What I want from you

Independent verdict on the CLI implementation. Be terse. Find what I missed.

**Section A — Verdict**: score 1-5 on each:
1. Is the tree rendering correct given the data model?
2. Is the CLI surface ergonomic for the actual debug use case?
3. Does the orphan-skip behavior make sense, or should orphans be displayed separately?
4. Are the 8 tests adequate for what users will actually do with this?
5. Will this work on real production spans.jsonl after M2 wraps LLM calls (or will some field/format assumption break)?

**Section B — Top 2 concerns**: the two issues most likely to bite users.

**Section C — Missing flags/behaviors**: what's the most useful feature not implemented?

**Section D — One-sentence overall verdict**.

Do not summarize back. I wrote this. Find weaknesses.
