# B8 Grok post-commit evidence gate

**Verdict: APPROVE**

Commit `beda9953c981336f6e2da1989307da0e94490c56` (parent `7d1160f0c22375c85505e12c37b1dc3a6e0ce6da`) matches the frozen, commit, and post receipts on diff bytes, diff SHA-256, and the four committed file hashes. Production triage, cache, unified router, and routing config are unchanged. Host focused tests, ruff, the controlled CLI, and an independent producer probe all passed. The live Deepseek result stays **6/7, exit 1**, with T4 `PRECONDITION_MISSING`. That live positive branch is **UNVERIFIED**. It does not block the authorized D15 amended contract. There is **no native Windows proof** for this commit.

This was a fresh read of the committed tree. No source, test, changelog, patch, receipt, Docker, API, provider, commit, or push was performed.

## Identity

[executed] Post snapshot `/tmp/vibesop-opt-20261009/snapshots/B8-grok-post`:

| Field | Value |
| --- | --- |
| HEAD | `beda9953c981336f6e2da1989307da0e94490c56` |
| Parent | `7d1160f0c22375c85505e12c37b1dc3a6e0ce6da` |
| Tree | `b9a24543c9c27d846115fb88372a7b5b08ebaaa1` |
| Author / committer | huchen `<curiousbull@outlook.com>` |
| Commit time | 2026-10-09T15:35:41+08:00 |
| Subject | `test(routing): validate last-good decay against captured cache rows` |
| Index | empty |
| Tracked worktree vs HEAD | clean |

`git diff HEAD^ HEAD`, `git show --format= HEAD`, `.omx/artifacts/diagnosis-B8.diff`, and the tracked worktree diff in the pre snapshot are the same bytes.

| Canonical diff | Value |
| --- | --- |
| Bytes | 61685 |
| SHA-256 | `009f0fc3d7caf952749a1d4937c13161bd741871c19af0f30f4dec39073ee157` |

[executed] `git archive --format=tar HEAD` SHA-256 is `c9d00a04a709247b6d8d36b564b66a95930257494365d3346f5cba2fd44495fd`, the post-receipt `archive_sha256`.

Committed file SHA-256 matches `B8-frozen.json`, `B8-commit-receipt.json`, and `B8-post-frozen.json`:

| Path | Parent blob | HEAD blob | SHA-256 |
| --- | --- | --- | --- |
| `CHANGELOG.md` | `7aeaa6ef50ce13870a6ab1d1560114b03e06720a` | `f7190491782c4354a0e55898b163abfcf10ef042` | `4e0d47d35fe8e09124697dd94b9dcfed1e0a9319b91546d2ced01887ffaa372c` |
| `scripts/e2e_llm_routing.py` | `a90eacca62548bfa6f8f4afe79821bc76a121896` | `110c0e0da28a6d1622c53738213ece2210094752` | `81b8d6962971e81f346bf9e7c5b73203a7404c285bb02cc83647128926b6624d` |
| `tests/core/routing/test_scenario_demotion.py` | `4497b3bbb072cec43500f8f4d3a2aa3b2a34cd82` | `97cc7467eb7df48d80c10fd480b33e779f21bfc0` | `829a6d4c01eb53be5d27b6e9fdae77ad434872b609def36e344855a33865ece7` |
| `tests/unit/core/routing/test_triage_service.py` | `902f303cdbae0ef236331c29bb040fa47a0eca0e` | `6687e255b1fa70973e1018a1299584110b1c3c89` | `d240bb965a1d654aa42d8b3d56cf9928a70187e75d80a2c38aaea2fc708dd181` |

[executed] The prompt names `/tmp/vibesop-opt-20261009/snapshots/B8-final-context-pre` as the archive whose HEAD is `beda9953`. That directory's `git rev-parse HEAD` is still the parent `7d1160f0`, and `beda9953` is not an object in that repository. Its four approved worktree files are byte-identical to the committed blobs, and its tracked diff is the canonical diff above. `B8-post-frozen.json` separates them: `review_snapshot` is the pre directory, `post_snapshot` is `B8-grok-post`, `working_tree_origin` is `git archive` of the committed HEAD. The commit object reviewed here is that post snapshot. Git status of `B8-grok-post` was unchanged by this gate.

The earlier approval patch `96f6c21b0c97f32c69a04c825c87b68f10c6f7ad417f51643d50030659b7112c` has the same three script/test SHA-256 values. Only `CHANGELOG.md` differs (`9bc7d35e…` then, `4e0d47d3…` now) because this commit sits on the B2 parent and adds two B8 bullets beside the existing B2 and B3 entries. `git diff HEAD^ HEAD -- CHANGELOG.md` is those two additions.

## Production invariants

[executed] `git diff --name-only HEAD^ HEAD -- src` is empty. Unchanged blobs include:

| File | Blob |
| --- | --- |
| `src/vibesop/core/routing/triage_service.py` | `5942de8fdd3b4fe33c8341fa71297f3180f5f39c` |
| `src/vibesop/core/routing/triage_cache.py` | `9a81ccafe8804c9ea2a3bfc6b936a5d7b401e173` |
| `src/vibesop/core/routing/unified.py` | `eb0f9794e8940877aee03f9d83cca58852c24f11` |
| `src/vibesop/core/skills/config_manager.py` | `afb19a0e6158293c6d167b6e1041a5aa8bb947bf` |

[executed] `LAST_GOOD_CONFIDENCE_DECAY` is `0.7`. `RoutingConfig().min_confidence` is `0.3`. The controlled gate `0.6` is a router setting in the harness, not the production default. Unified acceptance remains `match.confidence >= min_confidence`.

## Approvals read

[inspected] These files were read and left unmodified:

- `B8-kimi-final-context-report.md` — **APPROVE** on full diff `009f0fc3…`, parent `7d1160f0`. SHA-256 `05bd4f53528330ed8c1ff4608266182fa6de8f1df76759d7ba67caa567f264fc`.
- `B8-glm-final-context-report.md` — **APPROVE** on the same diff. SHA-256 `df8d7791d5e23075b9e04a186dd2a2091ab121fad49a69ec23bca6bb81c06ca0`.
- `B8-kimi-live-validation-decision.md` — **B8_VALIDATION_CONTRACT_APPROVE**. SHA-256 `083d6105fef03635375238757046d144a16f0272ab9dfac453461175455149fa`.

Post-run hashes of those files, the receipts, and the logs below match the hashes taken before any probe.

## Live and controlled evidence, left immutable

[inspected] `logs/B8-confidence2-live-container.log` (SHA-256 `ae39a4e7ccd9d3ad4d9adba0b242d88b4bcb77289c0e7257952038d68ab1f3ae`, 1397 bytes):

- T0, T1, T1b, T2, T3, T5 PASS
- T2 `cache_row=negative positive_persistent_hit=false` at captured key `7cf26d05a57f89dad55174dc5d20355090d642fe1eea23cb4a9f3e41c7ad329a`
- **T4 FAIL** `PRECONDITION_MISSING cache_row=negative` at that same key
- `E2E SUMMARY: 6/7 passed`
- `SCRIPT_EXIT 1`

Its result JSON records `mode=live`, `exit_code=1`, `script_sha256=81b8d696…` (this commit's script), and `patch_sha256=96f6c21b…` (the pre-reconciliation diff). This gate did not rerun it and does not rewrite it to 7/7.

[inspected] `logs/B8-confidence2-controlled-container.log` is a separate controlled run: `CONTROLLED SUMMARY: 7/7 passed marker=controlled` and `LIVE SUMMARY: not run`. It is not a live result. Its result JSON says `mode=controlled` and the same script SHA-256.

[inspected] `logs/B8-final-context-target-container.log` (SHA-256 `fa8274a0a54a3bd896513415f7bc9d99c5f894d24bb3fc43d5b3cd432639ca0c`) is the fresh Docker run for this exact patch: `118 passed in 2.49s`. The result JSON has `exit_code=0` and `patch_sha256=009f0fc3…`. Docker was not rerun here.

## This gate's execution

Host Python 3.12.13, repository `.venv`, `PYTHONDONTWRITEBYTECODE=1`, provider API keys unset. Raw stdout:

- `/tmp/vibesop-opt-20261009/probes-grok-b8-post/raw-01-pytest-focused.txt`
- `/tmp/vibesop-opt-20261009/probes-grok-b8-post/raw-02-ruff-check.txt`
- `/tmp/vibesop-opt-20261009/probes-grok-b8-post/raw-02-ruff-format.txt`
- `/tmp/vibesop-opt-20261009/probes-grok-b8-post/raw-03-controlled-cli.txt`
- `/tmp/vibesop-opt-20261009/probes-grok-b8-post/raw-04-independent-probe.txt`
- Probe: `/tmp/vibesop-opt-20261009/probes-grok-b8-post/independent_probe.py`

[executed] Focused pytest of `tests/core/routing/test_scenario_demotion.py` and `tests/unit/core/routing/test_triage_service.py`: **118 passed in 6.75s**, exit 0. Cache provider disabled; basetemp outside the repo.

[executed] `ruff check` and `ruff format --check` on the three changed Python files: all checks passed, 3 files already formatted.

[executed] `python scripts/e2e_llm_routing.py --controlled-lastgood`: exit 0.

```text
CONTROLLED SUMMARY: 7/7 passed marker=controlled
LIVE SUMMARY: not run; controlled mode is independent of live wiring
```

Every line is `marker=controlled` and `confidence_source=controlled_fixture`. This 7/7 is not live.

[executed] Independent probe, 115 checks, `PROBE_FAILURES 0`, exit 0. It imported `vibesop` from this snapshot and blocked `socket.create_connection` (0 attempts). For each controlled branch it used real `SkillRoute.to_dict()`, real `TriageCache.store()`, a real `TriageCache.candidates_hash` change (`fdea895f774bee75` to `66218926644e5b0e`, not `deadbeef`), a throwing transport (`calls=1`), and real `UnifiedRouter.route`. Scenario and index were stubbed only so the cascade reached the production `min_confidence` comparison.

| Branch | Observed |
| --- | --- |
| accept | stored 0.9 decays to 0.63, `last_good`, skill `builtin/review`, no scenario fallback |
| reject | stored 0.8 decays to 0.56, below 0.6; primary is scenario `builtin/commit` at 0.9, which is not the decay |
| equality | stored `0.6/0.7` decays to 0.6 and is accepted (`>=`) |
| negative | production `_store_negative` row has `skill_id=None`; stale hash does not resurrect it; scenario fallback |
| no-entry | captured key has no row; scenario fallback |
| same-skill-two-query | same skill at 0.8 and 0.9; captured key returns 0.8. A skill-id scan would see both. Judging the route with the other row fails the oracle |
| context-key | raw `继续`, result `继续 analyze architecture deterministic router`, and the `Conversation:` lookup string are three different strings. Captured row is 0.9; the raw-key decoy is 0.8; the result-query key is absent |

Oracle rejections on the real accept, equality, and context routes: primary confidence `0.01`, `True`, NaN, +inf, -inf, deleted confidence, deleted metadata, deleted `last_good_original_confidence`, and wrong skill all make `_decay_matches_row` return false. On the reject route, scenario primary confidence does not have to equal the decay: the real primary is 0.9 versus decay 0.56, and setting that primary confidence to 0.01 still passes the oracle.

[executed] Default T4, via the committed `_run_live_t4`, against a temp project that only received a copy of `.vibe/skill-routing.yaml`:

- Negative row at the observed lookup: **FAIL** `PRECONDITION_MISSING cache_row=negative captured_key=7cf26d05a57f89dad55174dc5d20355090d642fe1eea23cb4a9f3e41c7ad329a`. Cache bytes stayed 213. No `deadbeef`. No `127.0.0.1:9`. No `--t4-query` child.
- No row: **FAIL** `PRECONDITION_MISSING cache_row=missing` at that same key. Cache file stayed absent. No deadbeef and no blackhole.

That key is the live log's T4 key. This was a hermetic precondition check, not a live API call. The row was taken with `row_for_captured_key` / a single dict get. The probe did not scan cache rows or choose a row by skill id in the reason string.

## Live positive branch

**UNVERIFIED.** The live T4 positive path (positive captured row, then stale-hash degradation through the blackhole endpoint) was not observed. The preserved live outcome is 6/7, exit 1, T4 negative `PRECONDITION_MISSING`. Controlled 7/7 does not promote it. This matches amended D15 acceptance in `B8_VALIDATION_CONTRACT_APPROVE` and is not a merge block.

## Native Windows

**No native Windows proof yet.** No B8 final-context Windows log or Windows suite result was part of this evidence. Windows logs under this optimization directory belong to other batches. Nothing here claims Windows behavior.

## Scope kept

Not claimed: a new live 7/7, a rerun of Deepseek, a Docker rerun, provider-server attestation, or a Windows run. Historical live and controlled logs, Kimi and GLM reports, and the frozen/commit/post receipts were not edited. Repository git status after the probes matched the status taken before them.
