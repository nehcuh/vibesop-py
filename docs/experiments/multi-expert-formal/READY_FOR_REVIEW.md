# READY_FOR_REVIEW — phase-1 supervisor gate

This is a Codex-internal direction review. **Do not start the 360 formal runs** until the supervisor accepts this freeze. Not a user-approval checkpoint.

Prepared by Grok in `.experiment/worktree` on branch `codex/multi-expert-e2e`. Historical `docs/experiments/multi-expert-calibration/runs/**` were not modified and are not formal samples.

## Verdict on preparation

Harness protocol gates and task pre-acceptance are green (`verify_experiment.py` compound 23/25 before freeze files; remaining reds were live calibration and this document). Informal calibration ran twice (15+15), all allocations retained. Candidate T/I/K are frozen in `freeze.json`. **Organizational ranking is not allowed from these 30 informal runs.**

## Evidence checklist

| Item | Evidence |
|---|---|
| 12 tasks, 4/4/4 categories, two specs | `tasks/catalog.py`, `independence.md` |
| Shared Q&A + metered `contract` = full spec | `tasks/qa_bank.py`; spec comparison measures retrieval/overhead as well as initial completeness |
| T4 depends_on = emission order, not sorted | `independence.md`, Q&A `t4-depends`, hidden case `mixed` |
| Real VWAP (volume-weighted, not mean of closes) | `match-vwap-window-v1` spec + hidden `volume_weight` |
| T6 cross-layer bind/lookup across app.py and adapter.py | `ping` is a small control; bind from one entry must resolve from the other |
| T7 persist across fresh containers | hidden `persist_across_containers` |
| Correct + mutant pre-acceptance, real CLI | `tasks/evaluate.py self_check` Docker |
| Identical tools | `harness/tools.py` SCHEMA; hash in `tools-schema.json` per run |
| Request logged before HTTP | `harness/engine.py`; offline `request_exists_on_api_error` |
| Monotonic call ids, no overwrite | `harness/recorder.py`; C/D/E multi-Loop offline |
| Raw usage sum = ledger | offline `C_usage_sum` / `E_usage_sum` |
| Per-member stage quotas | exchange-0/1/2 and worker-0/1 reserved; `stage_budget_exhausted` ≠ global |
| Truncated tool_calls get dummy results, not executed | offline truncation test |
| E DAG, unique ids, no cycles; overlap = failed run | `ownership_conflict`; integrator keeps planner history |
| A uses remaining T (no 6000 cap, no extra turn cap) | `resources.yaml` `per_call_cap: remaining_T`, `per_loop_max_turns: null` |
| Isolation | Docker `--network none`, no secrets, hidden tests not in workspace |
| Main comparison D−A, cluster by 12 tasks, +10pp, no LLM gate | `preregistration.md` |
| Calibration excluded from 360 | `cal-harness-*` ids disjoint from formal catalog |

## Frozen candidate task hashes

See `freeze.json` `formal_task_hashes`. Any catalog edit after this file invalidates the freeze.

## Frozen resources

| Quantity | Value | Why |
|---|---|---|
| T completion (incl. reasoning) | 24000 | max observed 8319 |
| I prompt (incl. cache hits) | 400000 | E integrator traces hit I_precheck at ~115k used / 200k cap |
| K tool calls | 120 | K=40 then K=80 still bound C/D; A max 14 and may use all 120 |
| hang | 600 s | anti-stuck only |
| per-call max_tokens | remaining T | equal usable budget |
| thinking | disabled | temperature 0 is meaningful |
| SDK retries | 0 | failures count |

C/D: independent 10% T each; exchange split of 10% T across three members; integrate 60% + unused transfer. E: plan 20%; workers split of 50%; integrate 30% + unused. Stage exhaustion is not reported as global exhaustion.

## Informal calibration (not 360)

| Batch | K cap | Result | Keep? |
|---|---|---|---|
| `runs/20260913T015759Z` | 40 | 7 passed / 8 failed (mostly K) | yes |
| `runs/20260913T020657Z` | 80 | 11 passed / 4 failed (K, stage, I_precheck) | yes |

Do not merge, cherry-pick, or treat as organization scores. Failures retained with call logs.

Observed response model: `deepseek-flash`. Reasoning tokens: 0. Thinking disabled in every request.

Cost (off-peak estimate, not an invoice): $0.0407 + $0.0603 ≈ **$0.101** for 30 informal runs. Source: DeepSeek Flash non-peak $0.15 / $0.003 / $0.6 per MTok.

## Formal 360 budget estimate (not a promise)

360 / 15 = 24× sample size; formal tasks are longer. Rough off-peak **$5–20** if usage resembles 2–3× the K=80 batch, highly sensitive to cache hits and E integrator traces. Re-estimate after the first 12 formal assignments if the supervisor starts them. Preparation/eval Docker time is separate from model sample cost.

## How a formal run actually executes

1. Fresh workspace from task `files` only (spec + visible.json + stubs). Hidden cases stay on the host.
2. Same tools for A–E: read/write, list, visible tests, Docker CLI, `ask_clarification`, deliver.
3. `call-NNN-request.json` created exclusively **before** HTTP (messages, schema hash, started_at). Response or error afterwards. Never overwrite.
4. All members’ tool events in `tools.jsonl`.
5. Candidate code runs only in `python:3.12-slim` (`--network none`, no API keys).
6. Hidden evaluate after final deliver. No feedback to the model.
7. Status `passed` only if hidden checks pass, deliver happened, and no ownership conflict.

## Known limitations (must not be forgotten at analysis time)

- **Scope:** controlled small-CLI tasks, not whole-repository engineering. Do not claim general multi-expert efficacy.
- **Model snapshot:** alias `deepseek-v4-flash` → V4.1-Flash / `deepseek-flash`. Weights are not pinned.
- **Temperature 0** still requires the three repeats.
- **K/I freeze uses headroom** from two informal batches; 80 still bound some committee loops. If 120 binds in formal, that is a result (do not raise after seeing D−A).
- **E integrator** appends full worker traces; that is why I was raised.
- **Brief vs full** is also a retrieval condition via `contract`.
- **LLM scoring is not the gate.**
- Historical 45 calibration runs remain a different harness; do not mix.

## Next command if the supervisor accepts the freeze

```bash
# still gated; requires this file AND --i-understand-formal
PYTHONPATH=docs/experiments/multi-expert-formal uv run python -m harness.runner --phase formal --i-understand-formal
```

Do not run that command in this headless turn.
