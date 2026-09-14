# Formal multi-expert experiment — STATUS

Updated: 2026-09-13 (360 terminal; sensitivity 144 settled; editorial REPORT)

## Completed

- Same manifest `runs/20260913T023645Z`: **360/360 terminal** (149 passed, 211 failed, 0 error/interrupted/pending).
- First 12 retained; remaining 348 resumed with `--max-new 348`, concurrency 8.
- Freeze sources not modified. Docker digest unchanged; argv still tag.
- Full Chinese `REPORT.md`, `report/audit360.json`, matplotlib SVG+PNG in `report/figures/`.
- Confirmatory D−A (frozen analysis): −93.1pp, 95% CI [−100.0, −81.9], `support_worse` **on this envelope**. C/D almost never reached hidden eval (stage cap).

- Exploratory sensitivity 144 settled on `../multi-expert-sensitivity/runs/20260913T033401Z`: 136 completed + 8 controller-interrupted (not rerun). ITT D_soft−A −11.11pp, CI [−23.61, 0].
- Editorial Chinese `REPORT.md` covers both rounds; provenance in `report/provenance/`.

## Remaining

- Supervisor may copy directories to the main-repo `docs/experiments/` (authorized this delivery). No merge/push. No further model runs.

## Commands

Cohort complete. Re-audit:

```bash
PYTHONPATH=docs/experiments/multi-expert-formal uv run python docs/experiments/multi-expert-formal/report/audit360.py
PYTHONPATH=docs/experiments/multi-expert-formal uv run --with matplotlib --with numpy python docs/experiments/multi-expert-formal/report/generate_report.py
```

## Recent logs

`logs/formal-resume-348.log` (gitignored `*.log`; on disk)
`logs/docker-image-at-resume.txt`

## Errors

C 70/72 and D 72/72 `stage_budget_exhausted` (mostly independent-0). E 36 I_precheck, 11 ownership. A 5 incomplete_final_response. All retained.

## Next

Stop for supervisor. Do not change this cohort.
