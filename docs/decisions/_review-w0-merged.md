# W0 Implementation Review — Merged Findings (grok + pi)

> 2026-07-29 — independent reviews ran in parallel; bothreviewers saw the same brief
> Brief: `docs/decisions/_review-w0-implementation-brief.md`
> Verdict: **Ship W0 → W1 after punch-list below** (both reviewers)

## Independent convergence (both flagged) — must fix

| # | Issue | Severity | Action |
|---|---|---|---|
| 1 | `dev_detect.py` docstring inverts fail-safe cost rationale | P1 | Rewrite docstring: false-POSITIVE dev = silent prod data loss (HIGH cost); false-NEGATIVE dev = test pollution (medium). Default-to-prod remains correct, but justification must be right. |
| 2 | Embedding threshold drift: design says 0.85, benchmark says 0.80 | P1 | Update v3 design §W1 to default 0.80 (kill-switch tunable, not frozen). At 0.85 MiniLM recall=0.49 → W1 connectivity fails. |
| 3 | `fastembed` added as runtime dep but only used by benchmark script | P1 | Move to optional extra (`[project.optional-dependencies] semantic`) |
| 4 | Gold cluster contaminated (定位, multi-issue, bare EN errors mixed in) | P1 | Clean gold to permission-only; keep impure items as second "near-miss" set |
| 5 | CLI `vibe route` smoke not tested (only AgentRuntime e2e) | P1 | Add one CLI e2e or manual smoke: 2× `vibe route` → same task_id on spans.jsonl |

## Single-reviewer findings — also fix

| # | Issue | Source | Severity | Action |
|---|---|---|---|---|
| 6 | `-m pytest` argv check is loose: `"-m" in argv and "pytest" in argv` matches `python script.py -m pytest_flag` | grok | P2 | Tighten: require adjacency `argv[i]=="-m" and argv[i+1]=="pytest"` |
| 7 | Design addendum needed: capture W0 decisions (threshold, model, substitution, task_id scope) | pi | P1 | Append to `2026-07-29-task-memory-product-design.md` |

## Both approved

- Ship W0 → W1
- Don't reopen normalize for synonyms/trad-simp
- Embedding threshold + model are W1 kill-switch knobs, not frozen
- Highest risk to W1: **soft-cluster connectivity on loosely labeled gold family** — multi-cluster validation + one model/threshold retry as design allows

## Grades (pi's rubric)

| Area | Grade |
|---|---|
| W0.A task_id | A− |
| W0.B dev/prod | A− |
| W0.C embedding | B+ |
| W0.D wiring | A |
| Packaging | C+ |
| Kill switch | Pass with conditions |

## What went well (don't regress)

1. Pure-query task_id without project_path — correct v3 fix
2. Frozen fixture + "any normalize change must update fixture" culture
3. AgentRuntime + CLI both wired (better than design's single-line ask)
4. Dev routing with explicit path always wins
5. Benchmark report is unusually honest about deviations
6. Stale `_obs_tracer` cache diagnosed and fixed (real bug, not checkbox wiring)

## Punch-list execution plan

Order: P1 fixes → CLI smoke → design addendum → re-run full suite → commit → mark W0 done.
