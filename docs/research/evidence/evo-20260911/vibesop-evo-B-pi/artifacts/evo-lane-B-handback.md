# Lane B handback — CI decision_source registry (B1, Wave 2 draft)

**Status: DRAFT — awaiting per-job human confirmation.** Nothing in this lane is
ratified. The registry ships with `proposed_by: grok` and
`pending_human_confirm: true` and must not be quoted as a maintainer ruling.

- Branch: `feat/evo-B` (based on `c4dbf187` = `main`)
- B1 implementation commit: `07805ae8` (this handback is the follow-up commit)
- Packet: `docs/specs/2026-09-11-evo-lane-B.md`
- Direction: `docs/specs/2026-09-11-evolution-direction-proposal.md` §方向 B (B1 先行)
- Scope actually touched: 3 new files (below). `.github/workflows/ci.yml` NOT modified
  (`git diff --stat` on tracked files is empty). No product code touched.
- Not pushed. No `git add -A`.

## 1. What was built

| file | role |
|---|---|
| `ci/decision-source.yaml` | the registry: one `decision_source` per CI job |
| `scripts/check_ci_decision_source.py` | guard: cross-checks the registry against the real workflow |
| `tests/unit/test_check_ci_decision_source.py` | 34 tests, fixture workflows + read-only use of the real `ci.yml` |

Guard contract (only these four rules fail):

1. **Coverage** — every job in `ci.yml` must be registered (missing → exit 1).
2. **Anti-drift** — every registry entry must name a job that still exists
   (leftover entry → exit 1).
3. **Domain** — `decision_source` must be present and one of
   `deterministic | human` (missing/empty → exit 1).
4. **No model gates** — any other value (e.g. `model`) on a job that still runs
   → exit 1. A job disabled with `if: false` is exempt (advisory only).

Exit codes: `0` ok, `1` contract violation, `2` fail-closed (workflow/registry
unreadable or unparseable).

`continue-on-error: true` is deliberately **not** an escape hatch: that job still
runs and humans still read it. **This is a judgement call that needs your ruling**
— see §3 item E.

## 2. Per-job confirmation list — 需要人点头的 job 清单

All eight are proposed `deterministic`. None has been confirmed by a human.
Cross-checked mechanically (ids and names match the real `ci.yml` exactly, zero
drift, zero name-mismatch advisories):

| # | job id | workflow `name` | proposed | evidence the verdict is machine-owned |
|---|---|---|---|---|
| 1 | `lint` | Lint | deterministic | `ruff check .` + `ruff format --check .` exit codes |
| 2 | `type-check` | Type Check | deterministic | basedpyright exit codes under `--level error` (0/1/3) |
| 3 | `test` | Test (Python ${{ matrix.python-version }}) | deterministic | pytest exit code + `--cov-fail-under=73` |
| 4 | `test-windows` | Test Windows (Python ${{ matrix.python-version }}) | deterministic | pytest exit code; `--reruns 2` absorbs OS flakes |
| 5 | `security` | Security Scan | deterministic | pip-audit + bandit exit codes |
| 6 | `benchmark` | Performance Benchmark | deterministic | pytest `-m benchmark` exit code |
| 7 | `routing-eval` | Routing Eval (report-only) | **deterministic (disputed — see A)** | `eval_routing.py` exit code (always 0) |
| 8 | `routing-benchmark` | Routing Benchmark (gate) | deterministic | `--hermetic --check` → 0 ok / 1 fail / 3 stale |

### A. `routing-eval` — the one job where I disagree with the packet

The packet's rationale for this job is "eval_routing hermetic". That is **not
true for this job**: only `routing-benchmark` runs `--hermetic --check`.
`routing-eval` runs the non-hermetic `--json` invocation, is
`continue-on-error: true` (comment in `ci.yml` says "PERMANENTLY report-only …
never to block merges. Do not 'graduate' it"), and its own step summary addresses
humans ("this job exists to surface the JSON metrics for humans").

So the honest reading may be `decision_source: human` — the decision this job
feeds is a person reading the step summary. I kept `deterministic` because the
lane instruction said "all listed CI jobs are proposed deterministic", and
recorded the disagreement in the registry's `rationale` + `notes` for this entry.
**Either value keeps the guard green; only the claim differs.** Please rule.

## 3. Other items needing your explicit ruling

- **B. Packet table drift.** The packet's table lists `security` with name
  `security`; the real `ci.yml` says `Security Scan` (job id is `security`).
  Names in the registry were extracted from the real file, not copied from the
  packet. Same for `benchmark` / `routing-*` display names.
- **C. Registry identity contract is the job id, not the name.** A recorded
  `name` that stops matching produces an advisory `note`, never a red build.
  If you want renames to be red, that is a one-line change — say so.
- **D. Unknown registry keys are advisory, not fatal.** `decision_source` is the
  only enforced field; annotations (`name`, `rationale`, `notes`, `evidence`,
  `confirmed_by`, `confirmed_at`) are free-form. Rationale: the upcoming
  confirm round will add fields, and a guard that rejects the confirmation is a
  guard nobody runs.
- **E. `if: false` is the only exemption** (packet's literal rule). Consequences
  to confirm: (i) `continue-on-error: true` jobs are NOT exempt; (ii) a
  `model`-sourced job must be fully disabled to be acceptable. If you want a
  middle rung ("model output allowed when the job cannot block"), say so.
- **F. This guard is not wired into CI.** Adding it to `ci.yml` is a change to
  `ci.yml`, which this lane is forbidden to touch. Until it is wired, B1 is a
  local/on-demand check — a mechanism that exists but does not run. Wiring is a
  separate, confirmable change.
- **G. Ratification mechanics.** Flipping `pending_human_confirm: false` (and
  adding `confirmed_by`) is the human act that turns this draft into a ruling.
  The file's header comment says exactly that; do not flip it in this lane.

## 4. Honest limits (unchanged from the proposal)

- This is a declaration check, not a proof. It cannot detect "a human pasted a
  model's conclusion into a PR comment".
- **B2 (static import ban** — a `deterministic` gate script may not import
  `anthropic`/`openai`) is deliberately **not implemented**. The packet says B2
  waits until B1 is accepted. Nothing in the registry's value column is verified
  by static analysis today.
- Advisory surfaces (name drift, unknown keys) do not affect the exit code.

## 5. Evidence

```
$ uv run python scripts/check_ci_decision_source.py ; echo exit=$?
check_ci_decision_source: 8 workflow job(s), 8 registry entr(y/ies) — all registered,
all decision sources deterministic | human.
exit=0

$ uv run pytest tests/unit/test_check_ci_decision_source.py -q
34 passed

$ <coverage of the guard>
scripts/check_ci_decision_source.py   131 stmts  44 branch  100.00%

$ uv run pytest -m "not benchmark and not slow" -q
7201 passed, 15 skipped, 17 deselected in 149.85s

$ uv run ruff check <new files> ; uv run ruff format --check <new files>
All checks passed! / 2 files already formatted

$ PYRIGHT_DISABLE_GITHUB_ACTIONS_OUTPUT=1 uv run basedpyright --level error scripts/check_ci_decision_source.py
0 errors, 0 warnings, 0 notes

$ git diff --stat          # tracked files
(empty — ci.yml and everything else untouched)
```

Red-light evidence (the packet's required negative case), all via fixture
workflows under `tmp_path` plus read-only copies of the real `ci.yml`:

- `test_model_decision_source_on_required_job_is_red` — registry says
  `model` for a live job → exit 1, code `model_decision_source_on_required_job`;
- `test_real_workflow_with_a_model_job_injected_is_red` — the **real** `ci.yml`
  content plus an injected model job → exit 1;
- `test_full_coverage_is_green` / `test_real_repo_registry_covers_real_ci_workflow`
  — 100% coverage → exit 0;
- `test_continue_on_error_is_not_an_exemption`,
  `test_only_literal_false_disables_a_job`,
  `test_unregistered_job_is_red`, `test_registry_entry_without_a_job_is_red`,
  `test_missing_workflow_fails_closed` (`exit 2`).

## 6. Environment note (worktree hazard, cost a step)

This lane runs in a linked worktree of `/Users/huchen/Projects/vibesop-py`, whose
`.git/info/exclude` (machine-local, invisible to collaborators) contains
`.omx/`. So `git add .omx/artifacts/evo-lane-B-handback.md` is refused on this
machine and the file needed `git add -f` — precisely the incident
`scripts/check_artifact_links.py` was written for. 357 `.omx/artifacts` files
are tracked, so the parent repo's exclude is a standing trap for every handback,
not a Lane B problem. Flagging it, not fixing it (outside this lane's scope).

## 7. What I did not do

- Did not edit `.github/workflows/ci.yml` or any product code.
- Did not implement B2 import scanning.
- Did not flip `pending_human_confirm`, and did not add `confirmed_by`.
- Did not wire the guard into CI (§3 F).
- Did not push.
