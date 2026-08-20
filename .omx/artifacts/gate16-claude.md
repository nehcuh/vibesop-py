All checks complete. Here is the Gate 16 review.

---

# Gate 16 Review — M12 M0 + M1

## What I verified (executed, not just inspected)

- **Suites**: observability + hook/kimi/seq/bridge targeted set → 473 passed (1 flake, see blocker); `tests/adapters/ + tests/cli/ + tool_sequences + instinct_learner` → 984 passed; ruff clean on all 13 touched files; `git diff --stat` confirms scope is exactly the claimed files.
- **M0 on real data**: ran `_extract_query` over this repo's live `spans.jsonl`: 171 spans, 77 route spans → 76 extractable queries, **all via the new metadata fallback** (0 before). Claim substance confirmed.
- **fastembed observation**: reproduced — installed fastembed rejects `paraphrase-multilingual-MiniLM-L12-v2` ("not supported in TextEmbedding") → `_compute` returns None → soft-merge cosine **never fires**. The 63 smoke clusters are pure hard task_id grouping.

## Per-focus findings

**1. M0 metadata fallback — sound.** Compat strategy is correct: input_data preferred, dict-without-query now falls through (test-covered), and — importantly — a non-JSON metadata string is *not* treated as the query (metadata is a sidecar; asymmetric handling vs input_data is right). Adversarial metadata is safe: malformed JSON, non-dict JSON, and SpanWriter's `[TRUNCATED]`-truncated 16KB strings all fail `json.loads` → None; `str(q)` coercion matches pre-existing input_data behavior. `str()` on a dict-valued `query` produces repr noise but no crash — same as pre-M0.

**2. M1a — correct.**
- `CLAUDE_PROJECT_DIR` precedence fixes the global-install case (env var beats baked `$HOME`) and is a no-op for project-local installs (equal values). Behavior tests execute the *rendered* script and prove precedence, rc=127 logging, 64KB/200-line cap, and `stdout == b""` + `exit 0` on both success and failure paths.
- session_id forwarding handles all jq failure modes: `type == "object"` guard, `// empty` for null/absent, `2>/dev/null || true`, missing jq → `""` → `'' or None` → None → pre-M1 mint-UUID behavior. The hermetic execution tests (uv-tool stub plant) verify both present/absent payload paths end-to-end. Python side confirmed: `handle_query_for_hook(session_id=...)` exists and threads into `tracer.trace(session_id=...)` (agent_runtime.py:452-455), so the join key genuinely lands on route spans.
- Kimi adapter follows its own conventions: `[[hooks]]` with only event/command/timeout (per the schema comment at kimi_cli.py:175), `_sequences_enabled` byte-equivalent to claude's, equivalent Jinja env (`make_shell_safe_env` supplies `shellquote`), empty `project_root` is deliberate and documented. `handle_query_for_hook` skips a `cwd`-independence concern correctly since Kimi runs hooks in the session project dir.

**3. M1b bridge — correct.** Session-first join picks latest-started-preceding span (right semantics: tools follow routing); event-predates-all → window rescue; ±30min fallback with ambiguity refusal; CLI spans excluded from candidacy via both `platform=="vibe-cli"` and `source=="cli"` markers (both verified present in cli/main.py:761-763). Idempotency: state-file `(session,ts,tool)` dedup, outcome dedup by span_id against the outcomes file itself (state-loss safe), and the no-route-spans path still marks events seen (prevents infinite retry by manual re-runs) — that's careful. Span conformance: trace/parent wiring matches `models.Span`; metadata string round-trip matches SpanWriter's serialization; `get_pattern_sequences`'s `name.split(":",1)[-1]` consumes `tool:X` correctly — the E2E test proves the full capture→assemble→bridge→aggregator loop. Single-reader is real: only `assemble_tool_sequences` advances the cursor; `run_bridge` has no cursor of its own; bridge failure swallowed (test-proven both at the fan-out and direct-call level).

**4. Cross-path `.last` interface — matches.** Hook writes single-line `date +%s` on success only; `_read_last_capture` parses first line as float epoch with full exception guard (incl. OverflowError). 

**5. Scope discipline — clean.** Nothing beyond M0/M1. M0/M1 exit criteria honestly reported as not-yet-met (live hook redeploy + ≥20 bridged spans/≥3 sessions pending gate pass) — no false completion claims. One cosmetic extra: assert reformat at test_clustering.py:133 (ruff artifact, harmless). Minor phrasing nit: the packet's "76 route spans → 97 extractable queries" conflates route-span extraction (77→76 today) with all-span extraction (171→98).

**6. fastembed observation — real, verified, and M2-critical.** This isn't just "worth a design note": M2's miss-cluster admission is embedding Union-Find + calibrated cosine threshold — with the default model name dead, soft merge silently never fires and M2's core mechanism produces hard-groups-only. Recommend an M0.5/M2 prerequisite: fix the model id (likely `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) plus a smoke asserting `embed() is not None`, so calibration can't spin on another silent zero.

## Blocking issue

**BLOCK-1 — Flaky test introduced: `tests/core/observability/test_clustering.py:415-438`.** `test_cluster_queries_extracts_from_metadata` asserts `len(clusters) == 2` for two distinct task_ids whose embeddings come from `_angle_embedding` (test_clustering.py:39-47), which derives angles from Python's built-in `hash()` — randomized per process. Soft-merge fires iff cos(Δangle) ≥ 0.80 → for two ~uniform angles that's **≈20.5% of fresh processes** (analytic, 200k samples: 0.2046). Empirically confirmed: my first combined-suite run failed at line 436; a direct probe found a live seed where the two queries land at 240°/257° (cos 0.956 → merge → 1 cluster → fail). All pre-existing `_angle_embedding` uses assert `len == 1` on same-task_id spans (outcome-invariant), so this flake is introduced by this diff — and it re-commits the exact failure class this repo has already documented as a costly repeat offense (fake embeddings must be sha1-derived; last occurrence caused ~30% suite flake and took ~10 rounds to localize). CI does not pin PYTHONHASHSEED, so ~1 in 5 fresh runs fails. Fix is mechanical: deterministic embeddings — sha1-derived angle, or the explicit `_orthogonal` helper pattern already used at test_clustering.py:298, or a `_boundary_compute`-style fixed construction.

## Nits (non-blocking)

- `_matches_accepted` (tool_call_bridge.py:502-520): the bidirectional normalized-prefix fallback over-matches — a miss "run tests" prefixes-matches an accepted pending "run tests with coverage in ci" → false `strong_positive` on a different task. Gate the prefix branch on actual truncation (span query at its 200-char cap) rather than any prefix relation.
- Outcomes are write-once per span_id: a miss classified `weak_positive` at the 24h expiry can't be revised if the task is re-asked on day 2. Fine for weak signals; worth a comment so M2 doesn't treat these as ground truth.
- `.last` refresh means "record-tool exited 0", not "recorded" (malformed payloads and `sequences.enabled=false` also exit 0 — spike doc acknowledges). Keep the dual-signal check for the M1 exit verification.
- `_extract_step_names`/`min_cluster_size` observations: agree out of scope; fold both plus fastembed into the M2 design note.

The production code is solid — the single blocker is a test-reliability defect, not a logic defect, but it will fail CI intermittently from day one and violates the repo's own learned testing discipline.

VERDICT: BLOCK
