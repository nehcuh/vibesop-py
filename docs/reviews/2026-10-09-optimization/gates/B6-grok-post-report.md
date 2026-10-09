# B6 Grok post-commit review

**Verdict: APPROVE**

Full patch SHA256: `f82e80c7d1556a771571ebf3552ed2394bf695c77ff96e1708144cfef0fa8fad`

Commit: `74f418628ba5bbf9729fb78bd22aa886b55e1132`
Parent: `3305bcc9aff72320db57e99e04f58c80cec6b62f`
Patch bytes: 55611
Subject: `fix(instinct): merge concurrent evidence without crossing action identities`

0 × P0, 0 × P1. D11 sums concurrent same-action counters. D13 keeps old action A feedback off new action B in both orders, and a second switch to B keeps B's own counters, confidence, and outcome history. The fresh three-file suite is 112/112, including `test_prune_auto_extracted.py`. The held-lock test and an independent probe both ran on this host: production `cross_process_lock` on `instincts.jsonl.lock`, `LOCK_HELD`, `CONTENDED` while the holder was still alive, then `RELEASE`, then `ACQUIRED` and disk writes. No skip.

This host exercised `fcntl.flock` on Darwin. Native Windows `msvcrt` contention is not claimed. It remains pending Windows CI. `learner.py` mentions `msvcrt` only in a comment; `file_lock.py` is not in this commit.

## Identity [executed]

Worktree: `/private/tmp/vibesop-opt-20261009/snapshots/B6-grok-post` (same tree as `/tmp/vibesop-opt-20261009/snapshots/B6-grok-post`).

`git rev-parse HEAD` = `74f418628ba5bbf9729fb78bd22aa886b55e1132`.
`git rev-parse HEAD^` = `3305bcc9aff72320db57e99e04f58c80cec6b62f`.
`git diff HEAD^ HEAD | wc -c` = 55611.
`git diff HEAD^ HEAD | shasum -a 256` = `f82e80c7d1556a771571ebf3552ed2394bf695c77ff96e1708144cfef0fa8fad`.
The patch is 1285 lines and was read in full. Tracked `git diff HEAD` is empty. The index is empty.

Commit blobs match the worktree (`git rev-parse HEAD:<path>` vs `git hash-object`):

| Path | Parent blob | HEAD blob | Worktree SHA256 |
|---|---|---|---|
| `src/vibesop/core/instinct/learner.py` | `a8a93b83502ee3185886b809e5b437cfef56f3b1` | `8ca4f1aa9838b8e72177f5cc650832ddef5d07db` | `324b8a3a9783cd2be5726c9939084d0e0783312dfdb1f3ab1368485e61a6d5ea` |
| `tests/core/test_instinct_learner.py` | `1d68382e919fb9ece940dc83b2d4b6176cfc08ea` | `ea1a383409220dab90a106d736cdbbf2891435eb` | `8bb124edbe9ca19ca2d5e5eb31ab888f17c7a58b25d9d69183996f5aa6f82b0f` |
| `tests/unit/core/routing/test_instinct_feedback_loop.py` | `35099cd9a11c21021fb27194732aa4c0b4c60369` | `6a554c5b2b3b802512a142bc314b8c905b3a7ee9` | `3c643363429aaea48c706d6fb7c914f657998b824409d5afc8689f2fe1098cb7` |
| `CHANGELOG.md` | `5a7d7865bc3063dc04d2ef4c6e594823b58bc48f` | `867aeb38585026adbedd62bfe471aa10ec96532b` | `3d4704b264b009165a600eca0b9e9863515183cfda2ff14f02648d5b04eb4ad9` |

Those four SHA256 values match `B6-frozen.json`, `B6-commit-receipt.json`, and `B6-post-frozen.json`. The post receipt records this commit, `verified_committed_blobs_match_approved_snapshot: true`, and `post_diff_sha256` equal to the patch above. Untracked snapshot files (`.omx/artifacts/diagnosis-B6.diff`, diagnosis docs/plans) are outside the commit. The artifact diff is byte-identical to `git diff HEAD^ HEAD` (same 55611 bytes and SHA256).

Added-line identity versus `patches/history/B6-approved-before-B4-ae98e682.diff`: every `+` line except `+++` headers hashes to `a4b613ca22b655146ab8ee272b342f91321adef97411cff778afc7ef44c52dd8` on both patches (1092 lines, 46096 bytes). The full-patch byte difference (55519 vs 55611) is CHANGELOG context from parent B4. The two B6 changelog entries are the only changelog additions. The adjacent B4 lines are context.

## Gates [inspected]

- `B6-kimi-final-after-B4-report.md`: APPROVE. Claims 112 passed and added-line equivalence to `ae98e682…`. The added-line SHA above was recomputed here and matches. Kimi's pytest log ends `112 passed in 1.59s`.
- `B6-glm-final-after-B4-report.md`: APPROVE from the GLM-5.3 session. Claims 112/112, 70/70 counterexamples, 11/11 held-lock checks. The saved logs agree: `B6-glm-final-after-B4-pytest.txt` (`112 passed in 0.90s` plus multiprocess class 4/4, held-lock test passed), `probes/B6-glm-final-after-B4-counterexamples.out.txt` (`TOTAL checks=70 failures=0`), `probes/B6-glm-final-after-B4-lock-ack.out.txt` (`TOTAL checks=11 failures=0`, `CONTENDED` with `holder.poll()=None` before RELEASE). Those runs are their evidence. This verdict uses the independent run below.
- `logs/B6-final-after-B4-target-container.log`: `112 passed in 2.29s`. Paired `B6-final-after-B4-target-container.log.result.json`: `exit_code` 0, `patch_sha256` `f82e80c7d1556a771571ebf3552ed2394bf695c77ff96e1708144cfef0fa8fad`, pytest args are the three files below. Docker was not re-run.

## Fresh 112 [executed]

Isolated `HOME=/tmp/vibesop-opt-20261009/probes-grok-b6-post/home` (0 files after the run). `PYTHONDONTWRITEBYTECODE=1`. Snapshot venv Python 3.12.13. Imports resolve to this snapshot's `src/vibesop/core/instinct/learner.py`. Command: `pytest -p no:cacheprovider -q` on

- `tests/core/test_instinct_learner.py` (85)
- `tests/unit/core/routing/test_instinct_feedback_loop.py` (11)
- `tests/unit/core/instinct/test_prune_auto_extracted.py` (16)

Result: **112 passed in 4.74s, exit 0**. No skip, no xfail. Raw: `probes-grok-b6-post/pytest-112.txt`.

`TestInstinctMultiprocessMerge` verbose, same environment: **4 passed in 1.29s**, including `test_held_lock_rejects_nonblocking_peer_then_learner_writes`. That test calls production `vibesop.utils.file_lock.cross_process_lock` on `instincts.jsonl.lock`, prints `LOCK_HELD` inside the hold, requires `CONTENDED`/`CouldNotLock` while `holder.poll()` is `None`, sends `RELEASE` only after that, then `ACQUIRED` and `record_outcome`/`learn` disk writes. It ran. It was not skipped.

Tracked git status after the run is still clean.

## D11 and D13 [executed]

Own probe: `probes-grok-b6-post/b6_grok_post_probe.py`. Output: `b6_grok_post_probe.out.txt`. **162 checks, 0 failures, PROBE_VERDICT PASS.** Storage was tempfile directories only. No `sleep`, no mock `flock`, no `msvcrt`. Subprocess joins are hang bounds. Children import this snapshot.

D11:

- Two loaded instances on one id: successes sum to 2, confidence equals `_wilson_confidence(2, 0)` (`0.6711859764448096`). A stale `save()` leaves the count at 2. A later failure delta lands once: 2 success / 1 failure, confidence `_wilson_confidence(2, 1)`.
- Cross-id: a peer's new row does not drop the other instance's success, and a later save does not reapply it.
- Two real processes, both `LOADED` before either `GO`: disk success is 2, failure 0, same Wilson value.

D13 outcome history (success count, failure count, `total_applications`, confidence, `is_reliable`) does not move from A onto B:

- Switch then old feedback, and old feedback then switch. Seeds 0 and 3. Success and failure. In-process and real processes. Disk stays action B, counts 0/0, confidence 0.5, `total_applications` 0, not reliable, confidence is not Wilson(3, 0).
- Both switch to B with no new B evidence: counts stay 0/0, confidence 0.5.
- Peer switches to B and records 2 successes. The second switcher, which still held A with 3 successes, keeps B at 2 and Wilson(2, 0). It does not inherit A's 3 and it does not wipe B. Real processes show the same 2.
- Same-counter trap: B has its own 3 successes and is reliable. A holder that still has action A records one success, and separately one failure. B stays 3/0 with the same confidence (`0.7192469597754911`) and stays reliable.
- Aligned case: B already has 2, the second switcher then records 1 on B. Disk becomes 3, Wilson(3, 0), not 0 and not 3+2 from A's baseline.
- One new success on the reset action stays at 1, is not reliable, confidence is Wilson(1, 0), `find_matching(..., min_confidence=0.6)` is empty, and `apply_instinct_boost` does not boost.

`created_at` stayed the row's original timestamp. `times_matched` is the documented neutral counter and is not outcome evidence.

Observation, not a blocker: on switch-then-feedback, discarded A feedback can advance B's `last_used` while counts stay 0/0 (seed 0: `None` becomes a timestamp; seed 3: the timestamp moves later). `_merge_disk_action_change` keeps the later local `last_used` on purpose. `last_used` is not read by `is_reliable` or `apply_instinct_boost`. Reliability and boost stay on the reset row. Registered here, not patched.

A back-to-back second outcome on the same holder, after that holder has already saved and adopted B, counts as B's evidence (3/1). That is adoption, not inheritance. The per-polarity checks above use a holder that still has action A.

## Held lock [executed]

Independent of the pytest test, the probe held production `cross_process_lock` on `storage.with_suffix(storage.suffix + ".lock")`, name `instincts.jsonl.lock`.

- `LOCK_HELD` printed inside the hold. `holder.poll()` is `None`.
- Contender `blocking=False` raises production `CouldNotLock` and prints `CONTENDED` while `holder.poll()` is still `None`. `RELEASE` is sent only after that observation.
- After release: holder exit 0, contender prints `ACQUIRED`, then production `record_outcome` and `learn` write the seeded row to success 1 / failure 0 / Wilson(1, 0) (`0.6032716457369465`) and a distinct beta row.

## Registered residuals [executed where probed, not fixed]

These were re-observed on this commit. No source, test, changelog, or receipt edit was made.

| ID | Still true on this tree | Disposition |
|---|---|---|
| F2 | A stale learner's first `learn()` after another process `clear()` writes nothing (`rows=[]`). The secret stays gone. A second `learn()` on the refreshed epoch persists. Parent `3305bcc9` already has the clear-epoch guard. Parent does not reset success/failure on action change. | Pre-existing clear-first. Register. |
| F3 | An `avoid builtin/systematic-debugging skill` row with 3 successes of its own is reliable, and `apply_instinct_boost` still boosts that skill (`boosted: True`, `boost_source: instinct`) because `sid.lower() in action` (`optimization_service.py`, not in this diff). | Pre-existing substring parse. Register. |
| F4 | An untouched stale save does not resurrect a pruned junk row. A row dirty only in `times_matched` does write `ok ok ok ok` back. | Bounded tradeoff. Register. |
| F5 | Disk A→B with 2 successes, memory A→C: the save keeps C at 0/0 confidence 0.5 and drops B's 2. | Last-writer, one action per id. Register. |
| F6 | Loaded `set_instinct` of absolute success 5, baseline 1, disk 2, saves as 6 (`2+(5-1)`), not 5. | Delta versus absolute. Register. |
| F7 | This session's first completed 112 and first multiprocess class 4/4 were green. The earlier GLM report's two first-run lost writes were not reproduced here. | Unresolved environment uncertainty. Not claimed fixed. Linux CI remains the authority. |
| F8 | `_confidence_matches_update` is still `confidence == _wilson_confidence(...)`. A stored confidence of `0.99` on counts 1/0 is kept. A later Wilson-produced update recomputes Wilson(2, 0). | Info. Register. |

## Limits

No Docker, API, auth, commit, push, or subagent. No edit to source, tests, changelog, patch, receipts, or provider config. No user-global write (`HOME` file count 0). No native Windows `msvcrt` dual-process claim. Full-suite pytest was not run. The container 112 is inspected artifact evidence; the 112 and lock/D11/D13 results above were executed on this Darwin tree.

**APPROVE** — commit `74f418628ba5bbf9729fb78bd22aa886b55e1132`, parent `3305bcc9aff72320db57e99e04f58c80cec6b62f`, full patch SHA256 `f82e80c7d1556a771571ebf3552ed2394bf695c77ff96e1708144cfef0fa8fad` (55611 bytes).
