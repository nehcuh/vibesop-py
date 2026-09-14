# Supervisor ledger

2026-09-13: User delegated implementation and execution to Grok; Codex retains direction, gate review, interpretation and corrections.

Baseline: existing offline harness passes; valid formal runs 0/360. Prior 45 calibration runs preserved in experiment branch. Worktree: .experiment/worktree; branch codex/multi-expert-e2e. Phase-1 prompt and full headless log at grok-phase1.md/jsonl.

Review gates before formal allocation:
- 12 independently meaningful tasks (not 12 input permutations), two consistent spec views and a shared clarification source.
- Hidden acceptance not visible to participants; generated code only in isolated containers; task source or other runs cannot leak.
- Roles differ only where intended; independent reports not sequentially contaminated; E owns files and dependencies explicitly.
- Equal enforceable global resources and actual usage accounting. A has access to all its budget. Planning and coordination count.
- Functional tools and visible tests support iterative correction for all groups; histories preserved.
- Valid baseline/reference and targeted mutants; JSON delivery errors classified, not silently repaired by supervisor.
- Frozen prompts/tasks/evaluator before 360 assignments; all failures and deviations retained.
- D-A main comparison, cluster by 12 base tasks, threshold interpretation and uncertainty, secondary comparisons exploratory.

No organizational conclusion approved yet. Do not optimize participant success by selecting or excluding attempts.

## Formal 360 complete (2026-09-13)

Grok resumed `runs/20260913T023645Z` `--max-new 348`. Terminal 360/360. Freeze sources unchanged. Report: `docs/experiments/multi-expert-formal/REPORT.md`. Audit: `report/audit360.json` (360/360 usage match, no hidden-module leak).

Confirmatory D−A (frozen analysis.py): −93.1pp, 95% CI [−100.0, −81.9], `support_worse` **conditional on hard independent-analysis stage caps**. D 0/72 hidden-eval entry; C 2/72. Do not read as “experts are worse” in general. Soft-stage sensitivity not run in this cohort.


## Correction 1 (before any formal execution)

Interrupted owned Grok process via SIGINT, resumed same session 01a09859-bee8-7053-81f7-1e63cf63d4c2 with grok-correction1.md. Blocking findings: per-Loop call numbering overwrites logs; request saved only after successful API return; contradictory B planning exit; per-Loop turn cap changes total opportunity; shared internal stage pools can starve later members; E dependency/ownership validation and retained integration history incomplete. Also forwarded earlier task/QA parity notes. No participant outcome was used to decide these corrections.

Executor identified in its local session history: grok-4.6-build, high reasoning, fingerprint fp_08d0bc26c22b024e. This is the preparation agent, distinct from DeepSeek participant model.

## 2026-09-13T02:26:53.311549+00:00
Preparation verifier 25/25; resumed same Grok session for phase2. Authorized first12 only after strict full-code freeze, resumable full360 manifest, fixed concurrency8 and preregistered paired task bootstrap implementation. Final objective remains all360 + Chinese report.

## 2026-09-13T02:40:38.256017+00:00
First12 independent audit clean: immutable360, 25-source freeze, input/output/cache usage, calls and task hashes all match. Accepted continuation348 without changing formal code or selecting outcomes. Caveat: actual Docker argv uses tag; image ID same at launch/end checkpoint, report deviation accurately. Stage-cap failures dominate first C/D examples, must separate hard-stage termination from code quality. May require separate soft-stage sensitivity after full primary.

## 2026-09-13T03:10:26.973058+00:00
Primary360 completed, 4665calls independently reconciled; no auditissues. A67/B65/C2/D0/E15 out of72each. D72/72 internalstage termination => pre-recorded sensitivity trigger met. All160 artifacts reaching hidden eval pass;11E fail ownership protocol. Launching separate exploratory144 A vs D_soft with same task/spec/resources; only internal-stage cap termination becomes soft. No pooling/replacing primary. Report audit fields, false leak candidate, fonts and limitations sent for correction.

## 2026-09-13T03:35:10.212418+00:00
Exploratory144 started at runs/20260913T033401Z. A72/D_soft72, seed20260914, concurrency8, unchangedT/I/K. Same engine hash as independently tested five guard cases; new frozen pack42d2bb99..., original task/evaluator/analysis bytes retained. No pooling with primary.

## 2026-09-13T03:51:57.043601+00:00
Detected stalled records; ps confirmed no runner. Grok stderr proves headless600s background wait exit killed2 pending jobs at03:46:53Z. 123completed,8interrupted(A1/D_soft7),13notstarted. Snapshot saved before marking. Resuming samecohort13only, retain8asinterrupted0 per frozenrule; report infrastructure interference and outcome bounds. Reconstruct known usage from rawfiles as derived lowerbound, no fabricated unknown billing. Explicitly instructed Grok to await COMPLETE in active turn, not return into background timeout.

## 2026-09-13T03:57:25.203626+00:00
Old Grok resume remained silent without changes; terminated owned process23455(SIGINT,exit130), no participant runner active. Fresh Grok session01a098e8-57ab-7453-91e9-3c93e4159983 responded and took over exact same frozen recovery. No new experiment allocation.

## 2026-09-13T04:14:55.750079+00:00
Recovery13 completed84s; final144=130passed6failed8interrupted. Independent audit:2404requests2397responses7expectedunknown, no unexpected defects, manifest unchanged. D_soft61/A69; CI[-23.6111,0]pp, unknown interruption pointbounds[-12.5,-1.3889]pp. Final editorial review requires unified report, ceiling explanation, no claims of independent confirmation, no hypothesis-scenario confidence claims, meaningful case narrative/figures, provenance archive and main docs delivery; no further experiments.
