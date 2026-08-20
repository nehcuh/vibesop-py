# Gate 16 Review — M12 M0 + M1 implementation

You are reviewing the implementation of milestones M0 and M1 of the M12 design (repo: /Users/huchen/Projects/vibesop-py). The design (v3, thrice-reviewed): `.omx/artifacts/m12-product-design.md`. The full diff is appended. You may read any file but must NOT modify anything.

## What was implemented (three parallel coder paths)

**M0 (clustering extraction fix)** — `clustering.py` `_extract_query` now falls back to metadata (JSON string or dict; bad JSON silently skipped) when input_data lacks a query. Smoke on this repo's real spans.jsonl: 76 route spans → 97 extractable queries (was 0), 63 clusters (was 0). New tests: 10 cases in tests/core/observability/test_clustering.py.
- Also observed (NOT fixed, out of scope): fastembed default model name unsupported by installed fastembed → all embeddings None → soft-merge cosine merging never fires (second silent-degradation point); `_extract_step_names` only reads dict metadata; min_cluster_size=3 skips small clusters.

**M1a (hook channel)** — Root cause of gate15 BLOCK-2 found: globally-installed tool-seq hook bakes `project_root=$HOME`, so capture worked but wrote to `~/.vibe/tool_sequences.jsonl` (1.4MB exists there) instead of the project. Template now prefers `CLAUDE_PROJECT_DIR`; failures go to `.vibe/hook_errors.log` (64KB cap, 200-line roll) instead of `/dev/null`; success updates `.vibe/tool_sequences.last` (single-line epoch). Route hook template (shared: claude/kimi/opencode/cursor) now forwards `session_id` from the hook payload to `handle_query_for_hook`. kimi-cli adapter: PostToolUse capture IMPLEMENTED (spike confirmed Kimi supports it); pi spike says supported-but-unimplemented (`.omx/artifacts/m12-m1-hook-spike.md`). NOT done: redeploying live hooks to ~/.claude (awaits gate pass).

**M1b (assembly bridge + outcome signals)** — New `core/observability/tool_call_bridge.py`: joins tool events to route spans (session-first: latest route span with started_at ≤ event ts in same session; ±30min time-window fallback with ambiguity rejection; CLI spans excluded), emits tool_call spans (tool name only, no params), idempotent re-runs. `tool_sequences.py`: single-reader fanout (bridge hooks into `assemble_tool_sequences`, no second cursor). Outcome signals → `.vibe/observability/route_outcomes.jsonl` (accepted routing_pending match = strong_positive; same task_id re-ask = weak_negative; session progressed / span aged 24h = weak_positive). `vibe sequence status` command (capture age, sizes, cursor progress). New tests: 17 bridge + 4 status.

## Verification claims to check

- Full pytest was running at packet time (target: 0 failures; baseline was 5628).
- Each path reported its local suites green (385 observability, 210 adapters, 60 bridge/sequence).
- ruff clean on touched files (3 format warnings pre-existing on untouched files).

## Review focus

1. Correctness of the metadata fallback (M0): compat strategy sound? Any span shape that now mis-extracts? JSON-string parsing safe against adversarial metadata?
2. M1a: is the CLAUDE_PROJECT_DIR fix correct for both project-local and global installs? Does the route-hook session_id forwarding handle missing/malformed payloads (jq failure modes)? Does the kimi PostToolUse registration follow the adapter's own conventions? Hook scripts must always exit 0 and keep stdout clean — verify.
3. M1b: join strategy correctness (session-first + window fallback), idempotency, span model conformance (trace/parent wiring matches span_writer/models), single-reader fanout really single-reader (no second cursor), outcome-signal logic (any path that writes duplicate/contradictory outcomes?).
4. Cross-path interface consistency: `.vibe/tool_sequences.last` format (single-line epoch) — M1a writes it, M1b reads it; do the implementations match?
5. Scope discipline: anything changed beyond M0/M1? Anything the design said that was silently dropped (check the design's M0/M1 exit criteria — which are honestly not yet met and why)?
6. The fastembed silent-degradation observation (M0 path): real? Worth a design note for M2?

## Verdict format

End with exactly one of: `VERDICT: PASS`, `VERDICT: PASS_WITH_NITS` (list nits), `VERDICT: BLOCK` (list blocking issues with file:line + reasoning).
