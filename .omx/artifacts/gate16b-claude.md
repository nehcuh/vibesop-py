All verification complete. Here is the Gate 16b confirmation review.

---

# Gate 16b Review — M12 M0+M1 fix round

## gate16 BLOCK — flaky test: RESOLVED [executed]

`tests/core/observability/test_clustering.py` — `_angle_embedding` now derives the angle from `hashlib.sha1` (test_clustering.py:53), eliminating the PYTHONHASHSEED dependency structurally, not probabilistically. I ran the file in **5 consecutive fresh processes: 28/28 passed each time**, consistent with the orchestrator's 6-run report. With a deterministic hash there is no per-process variance left, so the ~17-20% failure mode cannot recur for these query pairs.

## Nit fixes: all four verified

1. **claude nit 1 (prefix over-match)** — `_matches_accepted` now gates the prefix fallback on `len(miss.query) >= SPAN_QUERY_MAX_CHARS` and only in the pend⊒span direction (tool_call_bridge.py:534-542). Cross-checked the producers really do truncate at 200: `query[:200]` at agent_runtime.py:457 and cli/main.py:760. Both new tests pass, including the exact over-match scenario from gate16 ("run tests" vs "run tests with coverage in ci" now decays to weak_positive, not a false strong_positive). [executed]
2. **claude nit 2 (write-once outcomes)** — `_derive_outcomes` docstring explicitly states outcomes are weak prior signals, never revised, and M2 must not treat rows as ground truth. [inspected]
3. **pi nit (purge domain)** — `clear_tool_sequences` deletes `tool_sequences.last` (tool_sequences.py:209); module docstring documents the observability-vs-capture purge split; `test_removes_last_capture_heartbeat` passes. [executed]
4. **pi nit 2 (CLI spans in outcome pool)** — `_is_miss` returns False for `rs.is_cli` (tool_call_bridge.py:469), same `is_cli` judgement as the join path; `test_cli_miss_spans_never_get_outcomes` passes. [executed]

## Cross-cutting wiring the diff depends on [inspected + executed]

- `handle_query_for_hook` already accepts `session_id` (agent_runtime.py:652); the route template heredoc imports `sys` and forwards the arg quoted — no Python-side change needed, and the hermetic stub test proves the payload session_id reaches argv[2].
- `_parse_entries` returns `(tool, datetime|None, session|None)` — matches the bridge's `ToolEvent`.
- `routing_pending.jsonl` path, `status="accepted"` vocabulary, and item `query` field all match `_load_accepted_queries`'s assumptions.
- Kimi `_sequences_enabled` is a faithful mirror of the claude-code adapter; the env-override disable path is proven by the passing test.
- Design doc m12-product-design.md:171-183 carries the M2-prerequisite note exactly as claimed (fastembed namespaced model name + `embed()` smoke + the four folded-in items).

## Test evidence [executed]

- Changed files: test_clustering (5×28), test_tool_call_bridge + test_tool_sequences (49), test_tool_seq_hook + test_hook_templates (28), test_kimi_cli + test_sequence_cmd (40) — all pass.
- Regression sweep `tests/adapters + tests/cli + tests/core/observability`: **1305 passed**, no regressions from the shared-template change or the bridge fan-out.

## New/remaining issues (nits — none block)

1. **Naive capture `ts` aborts a whole bridge batch** — `_parse_ts` (tool_sequences.py:260) doesn't normalize tz-naive values (the bridge's `_parse_dt` does). A tz-less `ts` (only from hand-written/foreign capture data; `record_tool_event` always writes aware ISO) raises TypeError in `_join_one` comparisons and aborts the entire `_run` — that batch's events then retry forever on manual re-runs since state is never saved. One-line fix (normalize or skip); low likelihood.
2. **`vibe sequence status` corrupt-cursor handling is partial** — sequence_cmd.py catches `JSONDecodeError` but a valid-JSON non-dict (`123` → AttributeError) or wrong-typed offset (`{"offset": "abc"}` → TypeError at `offset < 0`) produces a raw traceback. Core's `_read_cursor` (tool_sequences.py:217-224) already handles both; the CLI reimplemented the parse without those guards — reuse it.
3. **Concurrent `run_bridge` RMW race (watch item for M2)** — bridge state (`seen`) and outcome span_id dedup are read-modify-write without a cross-process lock; a `run_bridge` concurrent with an assembly fan-out can lose dedup keys → duplicate tool_call spans. Project history rates this pattern CRITICAL (W5.1 pool.yaml), but here assembly is the sole reader in practice, `run_bridge` is manual-only, and duplicates only double-count telemetry — fine for now, add the shared lock before `run_bridge` goes on any schedule.

Nits 1-3 all pre-date this fix round (present in the gate16 diff, not introduced by it); none are load-bearing for M0+M1's claims, and M2's "recompute, don't trust outcome rows" stance further contains them.

## VERDICT: PASS_WITH_NITS

- N1: tz-naive capture timestamps abort a full bridge batch (tool_sequences.py:260 vs bridge `_parse_dt`)
- N2: `vibe sequence status` cursor corruption handling incomplete vs core `_read_cursor` (sequence_cmd.py)
- N3: cross-process RMW race on bridge state/outcome dedup under concurrent `run_bridge` — add lock before any cron use
