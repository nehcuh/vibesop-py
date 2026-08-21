# Gate 25 review — e2e command-surface smoke script

You are an independent senior code reviewer. Review the attached diff (one new file: `scripts/e2e_command_smoke.py`, 331 lines) for the VibeSOP project (Python CLI, `vibe`).

## Context

The repo has an LLM-routing e2e (`scripts/e2e_llm_routing.py`, 7 scenarios, runs in an orbstack container against a built copy of the repo) but no systematic command-surface validation — ~45 top-level commands, including long-running/stateful ones like `vibe loop` (cron-tick model: create → tick executes via AgentRuntime.handle_query → pause/resume/delete; see src/vibesop/core/loop/executor.py). This new script closes that gap. It was run in the orbstack container (image vibesop-val-base:py3.12, DEEPSEEK_API_KEY in env): **50/50 passed**, and e2e_llm_routing still 7/7 in the same container run (smoke uses an isolated `/work/.smoke-project` cwd so the two don't pollute each other).

Coverage: Tier 1 real execution — loop full lifecycle (11 cases incl. a REAL tick execution through the routing pipeline with per-step timeouts, pause→tick-asserts-skip, resume, delete), observability commands against SpanWriter-seeded spans (scan-candidates / candidates / discover / sequence status / instinct status / route-stats / trace), session/feedback/deviation; Tier 2 read-only snapshots (20, incl. dashboard started on a free port → poll HTTP 200 → killpg cleanup); Tier 3 --help-only for network/interactive commands (market/install/sync-registry/quickstart/onboard/prompt-chain).

Findings the author reported (assess whether the script handles them honestly):
1. LoopStore is HOME-level (`~/.vibe/loops/`), not project-level — local runs enumerate the dev machine's real loops. Script works around via `tick --name` and targeted assertions; product-level backlog note.
2. `verify` exits 1 in an undeployed env — correct semantics, asserted as rc∈{0,1}.
3. bare `badges` exits 2 (typer group needs subcommand) — uses `badges list`.
4. `loop tick` is gated by kill-switch `loop.enabled` (default false) — the smoke config enables it explicitly.

## Review focus

1. **Assertion quality**: do the 50 cases assert meaningful output markers, or just exit codes? Any case that would pass even if the feature were broken (false-green)?
2. **Isolation**: is `/work/.smoke-project` isolation real (no writes to /work/.vibe, no HOME pollution inside container, no leftover dashboard/loop processes)? killpg usage correct?
3. **Flakiness**: timeout handling on the loop tick (LLM latency), dashboard port selection, cron-minute boundary on "* * * * *" (tick near a minute rollover), retry logic.
4. **Loop lifecycle coverage gaps**: pause→tick skip assertion sound? delete --force? reset path covered or consciously skipped?
5. **Honesty**: verify-rc∈{0,1} and the --help tier — do comments make the degraded level explicit at each site?
6. Consistency with e2e_llm_routing conventions (arg shape, summary format, exit codes).

## Output

Verdict: PASS / PASS_WITH_NITS / BLOCK, then numbered findings with severity (BLOCK/MAJOR/NIT), line refs, one-line residual-risk note. Be adversarial; do not rubber-stamp.
