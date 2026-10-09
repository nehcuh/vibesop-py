# B4 Grok post-commit gate

- Date: 2026-10-09
- Role: independent Grok read-only post-commit gate. This session did not author the commit and did not resume the authoring session.
- Verdict: **APPROVE** `3305bcc9aff72320db57e99e04f58c80cec6b62f`
- Patch: **APPROVE** full SHA256 `1dd4a88029e4600e0e42f66bca0aff7abc2a17a7fe2b999bab7c999b4af77429` (70772 bytes, parent `beda9953c981336f6e2da1989307da0e94490c56`)

No source, test, changelog, doc, patch, receipt, Docker, API, auth, or global lock file was edited. No commit, push, or subagent.

## Identity

[executed] Reconstructed repo `/private/tmp/vibesop-opt-20261009/snapshots/B4-grok-post` (`/tmp/vibesop-opt-20261009/snapshots/B4-grok-post`):

| Item | Value |
|---|---|
| HEAD | `3305bcc9aff72320db57e99e04f58c80cec6b62f` |
| Parent | `beda9953c981336f6e2da1989307da0e94490c56` |
| Tree | `24b576c050d35bb15d7281794cb04ba7aeffa06b` |
| `git write-tree` | same tree; staged diff empty |
| Shallow | false (`rev-list --count HEAD` = 1086) |
| Subject | `fix(installer): publish isolated sandbox builds and preserve overlay policy` |
| Author / committer | huchen, 2026-10-09T16:25:59+08:00 |
| `git diff HEAD^ HEAD` | 70772 bytes, 1688 lines, SHA256 `1dd4a88029e4600e0e42f66bca0aff7abc2a17a7fe2b999bab7c999b4af77429` |
| `git show --format=` | same byte count and SHA256 |
| `git archive --format=tar HEAD` | SHA256 `8d5edd28e6805a298a841792d8f6fbfa2a75d856de34843495eb511220f2e4d1` |

[executed] That patch SHA256 and byte count match `B4-frozen.json`, `B4-commit-receipt.json`, `B4-post-frozen.json.post_diff_sha256`, and `.omx/artifacts/diagnosis-B4.diff`. The diagnosis diff was read in full (1688 lines, 7 file sections, +1335/−91). Independent `git diff HEAD^ HEAD` is byte-identical to that file.

[executed] `B4-post-frozen.json.post_snapshot` is `/tmp/vibesop-opt-20261009/snapshots/B4-grok-post`. That is this cwd. It is not the PRE `review_snapshot` `/tmp/vibesop-opt-20261009/snapshots/B4-final-context-pre`. `archive_sha256` recomputed from `git archive --format=tar HEAD` matches the post receipt.

Receipt `committed_paths` is exactly the 7 modified files. Frozen path `src/vibesop/builder/manifest.py` is unchanged (`apply_overlay` already delegates to `OverlayMerger`). Tracked worktree after this gate is still only the pre-existing untracked diagnosis paths (`.omx/artifacts/diagnosis-B4.diff`, `docs/plans/2026-10-09-diagnosis-optimization.*`, `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/`). Those paths are outside the commit.

## Blob and source SHA256

[executed] For every frozen path, post worktree SHA256 = receipt `source_sha256` = SHA256 of `git cat-file blob HEAD:path`. After tests and probes those hashes were unchanged.

| Path | Parent blob | HEAD blob | Source SHA256 | This delta |
|---|---|---|---|---|
| `src/vibesop/builder/overlay.py` | `6983e34c77b726a108366af90d9e514054f9c4f6` | `aeee12b01aedb008ff9cc0e907ea3df8d754e04c` | `f43fba20eaf8a2370f81d45f10ee7a0c1a16c2d33ae24a8f5f90a98fac90c71e` | changed |
| `src/vibesop/installer/pack_installer.py` | `4eee61cb22ab735fe45edf7087e331f029b1b967` | `18234fa2d51a4da6a6d7fdf56c7111d4926e2411` | `72551cbdac15a613a625afec880ca2a06b727a44326db87d9fc6e6ecf964639f` | changed |
| `tests/builder/test_overlay.py` | `4c4761a5a1036d6cae430375dbdbe8cf3565821f` | `f864fcb1e0a6c0d3e566157804279105a16f71e5` | `eda29c83efdaf6b913b47d24f0dd478bff268654f173cc9cc1009515433fb3b4` | changed |
| `tests/builder/test_manifest.py` | `9d1feac8b9af4f0315e07352651ec99ca5087a6c` | `0551a20eae6d5a0592bd4ce17e3326b310a1e772` | `1963cef24b37074941df00aa7b0882b3304a5fdfe4cae29a888d445e197c552c` | changed |
| `tests/installer/test_pack_install_order.py` | `00138724dc6af184a7fb1f2d635f8f24359fb629` | `ff8b67b3b78a8221192c98d24155ada6e76e21d8` | `d18e3c58b06f8e68dd82b739ce8c7b8302ac62e639f5fcdb759c69f3e1b43d9b` | changed |
| `tests/installer/test_pack_installer.py` | `815abdbe6e09039550e1e700da8dc45662ed6b23` | `025b7e4e970c2a88ad72f542db77d34e94fe7db5` | `41ffb6127e776f1bf6c471a620c35a31eb49e001182dfa2cbf5582cd45020fc8` | changed |
| `CHANGELOG.md` | `f7190491782c4354a0e55898b163abfcf10ef042` | `5a7d7865bc3063dc04d2ef4c6e594823b58bc48f` | `7dfa5715f181123358daf0bf530b13d0d00180c32ccbef41c793d3ba637165ee` | changed |
| `src/vibesop/builder/manifest.py` | `4bc88f1ab02a18addb381133486feae56404da61` | same | `7a4cdfd38104a07d9f1a95200e6486f412af8b90b371f757a30f2b4414be1ae8` | unchanged |

[executed] Historical approved patch `863d4e2e488ea24f493490558da46d6e901bdbf98d7ba3fd5796730d32c5670f` (71018 bytes, parent `d9d7804f…`): all seven files have identical `+`/`-` change-line sequences versus the new diff. Code/test source SHA256 values are identical, including pack725 and testd18. The 246-byte total delta is CHANGELOG hunk context/line-number shift after intervening B2/B8 commits. The B4 Changed/Fixed entries themselves are the same bytes.

## Inputs re-read this session

- `B4-kimi-final-context-report.md` **APPROVE** `1dd4a880…`
- `B4-glm-final-context-report.md` **APPROVE** `1dd4a880…` — Claude Code CLI, backend **GLM-5.3** (`base_url https://open.bigmodel.cn/api/anthropic`). Identity receipts `claude-glm-identity-config-receipt.json` / `claude-glm-identity-session-receipt.json`: `explicit_cli_model` / `explicit_model` = `GLM-5.3`, `global_settings_modified: false`. No Anthropic model identity.
- Exact-source fresh Docker `logs/B4-final-context-target-container.log` + `.result.json`: patch `1dd4a880…`, four focused files, **82 passed, 1 skipped in 1.86s**, exit 0. This lane did not rerun Docker.
- `B4-windows-source-real-docker-receipt.json` + `logs/B4-windows-source-real-docker.log`: **1 passed in 0.79s**, exit 0, real `BUILD.sh` opt-in `test_real_container_build_and_failure`. Log SHA256 `ac0988b070cfb8585ee6cce3a7e8654f43da14bf7e316bc0b9277c6ad43db855` recomputed and matches the receipt. Source pins pack725 / testd18, identical to HEAD. Receipt `patch_sha256` is historical `863d4e2e…` because that run predates the parent/CH rebase; the two pinned files are byte-identical on `1dd4a880…`.

## What this gate ran

Runner: snapshot `.venv` CPython 3.12, `vibesop.__file__` = `.../B4-grok-post/src/vibesop/__init__.py`. `HOME` for pytest was `/tmp/vibesop-opt-20261009/probes-grok-b4-post/pytest-home`. `VIBESOP_B4_DOCKER_E2E` unset.

| Check | Result |
|---|---|
| pytest, four focused files, `-q -rs -p no:cacheprovider` | [executed] exit 0, **82 passed, 1 skipped** in 8.74s |
| skip identity | [executed] `tests/installer/test_pack_install_order.py:894` — `VIBESOP_B4_DOCKER_E2E` opt-in real container e2e. Skip was not counted as a pass. |
| `ruff check --no-cache` on the 6 Python files | [executed] exit 0, All checks passed |
| `ruff format --check --no-cache` | [executed] exit 0, 6 files already formatted |
| independent probe | [executed] exit 0, **81/81 PASS**, `ALL_CHECKS_PASSED` |

Raw: `/tmp/vibesop-opt-20261009/probes-grok-b4-post/` (`pytest.txt`, `ruff-check.txt`, `ruff-format.txt`, `grok_b4_post_probe.py`, `grok_b4_post_producer.py`, `probe-stdout.txt`, `probe-results.json`, `reconcile.json`, `locks-before.json`, `locks-after.json`).

## Independent probe (real child exit)

[executed] `HOME` and `PackLockStore.LOCKS_DIR` redirected to this session's scoped temp **before** any `vibesop` import. User-global `~/.config/skills/.pack-locks` before and after: only historical `ui-ux-pro-max-skill.json` (317 bytes, SHA256 `69da52ebf9a9bed4765ecea8df9bf2752a9e6d2f9c9f4b72ec130a07fe1a44ab`, mtime Jul 24). Zero writes. Isolated locks wrote only `grok-b4-post-ok.json` and `grok-b4-post-copy.json`.

Only the network clone and the docker **launch** were substituted. Saved `subprocess.run` executed `[sys.executable, grok_b4_post_producer.py, *argv[1:]]`. Producer payload `grok-b4-post-artifact`. No fabricated `CompletedProcess`. Required-fail used real **exit 7**.

[executed] Overlay canonical nested policy / legacy roundtrip:

- `create_overlay` writes `policies.security` / `policies.routing`, not top-level keys.
- Merge keeps 0.9 / 1 / `scan_external_content=False` / `max_file_size=2048`. Partial overlay keeps unspecified `max_candidates=7`.
- Legacy top-level keys fail `validate_overlay` and still merge. Canonical `policies.*` wins over a conflicting top-level key (0.9 over 0.2).
- Illegal `confidence_threshold: 1.5` is rejected. `ManifestBuilder.apply_overlay` keeps 0.9 and unspecified 7.

[executed] Isolated sandbox / publication / failure:

- Production argv: `docker run --rm --read-only --network none`, exactly one `-v <isolated>:/work:rw`, no `docker.sock`. Mount source is not `/`, not redirected HOME, not the live pack tree. Sandbox directory gone after success.
- Success: `install_pack` True; artifact bytes `grok-b4-post-artifact`; user file `用户 笔记` preserved; lock only in isolated store; CLI tuple consumes as `success`.
- Required fail: producer writes partial then exit 7 → `(False, "Required build failed: … exit 7")`; no lock; failed central target removed; platform empty; CLI `failed`.
- Symlink artifact: `refusing symlink build artifact: generated/leak`; False; no `leak` persisted; no lock; CLI `failed`.
- Copy fallback: `Path.symlink_to` injected `OSError` → platform dest is a real directory, not a link; `COPY_SOURCE_MARKER` points at resolved central skill; `.vibe-manifest.json` `pack-copy`; `用户 笔记` and sibling `user-kept.txt` preserved; lock isolated; CLI `success`. Logged argv remains original production `docker run` with one isolated RW work mount.

[executed] Literal volume parser (fixed suffix `rsplit(":/work:rw")`, real child):

- `C:\Users\测试 用户\vibe pack:/work:rw` and `C:/Users/测试 用户/vibe pack:/work:rw` keep drive + CJK + space. Naive first-colon split is `C`.
- Drive roots `C:\`, `C:/`, `/` refuse with exit 99. Missing suffix exits 2.
- `_reject_unsafe_build_mount` / `_assert_container_command_safe` refuse `/`, HOME, live tree, `docker.sock`, host-root `:/work:rw`. Production isolated argv is accepted.

## Registered low debt (not blocking, not expanded)

Kimi/GLM F1–F3 remain on these bytes. This gate re-confirmed them and did not treat them as new findings.

- **F1 (Low)** `_index_pack_tree` still buffers whole file bytes (`path.read_bytes()`), no size cap.
- **F2 (Low)** production `_assert_container_command_safe` splits at the first `:/work:rw`; the fixture/producer parse the last. Production argv has one marker, so they agree. Pathological `/tmp/a:/work:rw/extra:/work:rw` diverges (`/tmp/a` vs `/tmp/a:/work:rw/extra`). This session's input fail-closed with `build mount is not a directory`.
- **F3 (Low)** BUILD-skip notices remain success strings (`BUILD skipped …`), not `PackBuildError`. Pre-B4 product decision.

Receipt `changelog_note` still says "pending B2 changes". B2 is already on parent. Stale receipt wording; CHANGELOG hunk itself is the isolated B4 pair. Receipts were not mutated.

## Windows boundary

This host is Darwin. **No native Windows proof.** Windows native CI is still pending. Docker Desktop on a Windows host with Linux containers is **unverified, not unsupported**. Docker build contract remains Linux containers. Fixture properties (Python `sys.executable` entry, fixed-suffix drive/CJK/space literals, production argv/safety/public-install/CLI) were re-probed here as literals and public paths, not as a Windows BUILD.

## Verdict

**APPROVE** `3305bcc9aff72320db57e99e04f58c80cec6b62f`  
**APPROVE** patch SHA256 `1dd4a88029e4600e0e42f66bca0aff7abc2a17a7fe2b999bab7c999b4af77429`

No P0/P1/P2. Confirmed Kimi/GLM findings are adopted on these bytes or remain explicit low F1/F2/F3 debt. No scope creep.
