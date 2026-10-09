# B2 Grok post-commit gate

- Date: 2026-10-09
- Role: independent Grok read-only post-commit gate. This session did not author the commit.
- Verdict: **APPROVE**
- Batch status: this source commit is not batch close. Batch close still waits on Kimi `BATCH_CLOSE_APPROVE`.

No source, test, changelog, doc, patch, or receipt file was edited. No commit, push, Docker run, provider call, or subagent.

## Identity

[executed] Reconstructed repo `/private/tmp/vibesop-opt-20261009/snapshots/B2-grok-post`:

| Item | Value |
|---|---|
| HEAD | `7d1160f0c22375c85505e12c37b1dc3a6e0ce6da` |
| Parent | `d9d7804ffd1dfb92f6a82138e5a07f5304a11df0` |
| Tree | `cfc1341190c04d64a3fede7a9a4fc3691aed4bfe` |
| Shallow | false (`rev-list --count HEAD` = 1084) |
| Subject | `fix(routing): invalidate discovery caches after governance and content changes` |
| Author / committer | huchen, 2026-10-09T15:11:46+08:00 |
| `git diff HEAD^ HEAD` | 89405 bytes, 2034 lines, SHA256 `cc3a9539572b64c827d0033516f35f81e869a0aea358034ea4f44385333021df` |
| `git show --format=` | same byte count and SHA256 |
| `git archive --format=tar HEAD` | SHA256 `9f1a95776f46d80e1f822e045db52683d237bebad275192088a87a571bbd7d9e` |
| Index tree | `git write-tree` equals HEAD tree; staged diff empty |

[executed] That patch SHA256 and byte count match `B2-commit-receipt.json`, `B2-post-frozen.json`, `B2-frozen.json`, and `.omx/artifacts/diagnosis-B2.diff`. `git diff HEAD` on the pre snapshot `/tmp/vibesop-opt-20261009/snapshots/B2-glm-pre` is the same 89405 bytes and the same SHA256. `cmp` of that diagnosis diff against the commit diff succeeded.

[executed] `B2-glm-pre` HEAD is the parent `d9d7804f`. That repo does not contain commit object `7d1160f0`. Its tracked worktree for the 11 receipt paths matches the committed blobs. The post snapshot is the non-shallow tree at the commit. Archive extraction of HEAD does not contain the untracked diagnosis plan/report paths that remain in both working trees (`.omx/artifacts/diagnosis-B2.diff`, `docs/plans/2026-10-09-diagnosis-optimization.*`, `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/`). Those paths are outside the commit. Tracked status after this gate is still only those untracked paths.

[executed] Full patch read, all 2034 lines, nine files, +1580/−95:

- `CHANGELOG.md` (+4)
- `src/vibesop/core/routing/_layers.py` (+29/−2)
- `src/vibesop/core/routing/candidate_manager.py` (+327/−42)
- `src/vibesop/core/skills/config_manager.py` (+158/−21)
- `src/vibesop/core/skills/external_loader.py` (+4)
- `src/vibesop/core/skills/loader.py` (+90/−5)
- `tests/core/routing/test_skill_governance.py` (+409/−24)
- `tests/core/skills/test_loader.py` (+82/−1)
- `tests/unit/core/routing/test_candidate_manager.py` (+477)

Receipt `committed_paths` is exactly those nine. `tests/unit/core/routing/test_matcher_rewarm.py` and `tests/core/routing/test_demo_skills.py` are in the focused set and are byte-identical to the parent.

## Blob and source SHA256

[executed] For every receipt path, pre worktree SHA256 = post worktree SHA256 = receipt `source_sha256` = post-frozen `source_sha256` = SHA256 of `git cat-file blob HEAD:path`. Parent blob equals `B2-glm-pre` `HEAD:path`.

| Path | HEAD blob | Parent blob | Source SHA256 |
|---|---|---|---|
| `src/vibesop/core/routing/candidate_manager.py` | `d6951ab557396177d612ef476230fa4df3f475bd` | `919791f27c6bdd813752dbeadb8ab6080c727128` | `5281de662befd7146bfbe2dd656f18be5197124dae4f1ee5ac5387d449d5d14a` |
| `src/vibesop/core/skills/loader.py` | `4948c7b3064a34c5e0ac00711bedcf5ecfacf02d` | `50ae02984e33bea491ddcb081b6b9baa6cec85c5` | `cbb01d71e77162983bfeea57d59734c870299cae1c068cccde62ef3965e16da2` |
| `src/vibesop/core/skills/external_loader.py` | `356a3694a6cd46a886c837a07ae3a98af8eb6ca9` | `2d2de5a0a035d37be4e2da3c841e1afef5b117a3` | `a353c6b59c010b1d0b85f25dfdcd95931b977e4f947115cc9729c8f387bb12dc` |
| `src/vibesop/core/routing/_layers.py` | `690079dda0e3e4b72070e678b71419dc53b6297d` | `2ef2303a664ce6b8c5d0b2214296346249d6bdcb` | `62667b67944cd664aa66f601d7d26b793157088543f4f36929586d11ad52b341` |
| `src/vibesop/core/skills/config_manager.py` | `afb19a0e6158293c6d167b6e1041a5aa8bb947bf` | `84cd681f4c39f3eff35064e9d5d9819492def300` | `83505d3978c697be953931b69083ffbe67829c8538fe4e5bb03c3df4cacf5b5e` |
| `tests/unit/core/routing/test_candidate_manager.py` | `16f3f223856ed2d28dd65dc4a6fd72399414eaff` | `5dc5d43fe0a20f39253ecf5f114d15ecbdc094be` | `e3c818aed76dc4dd13eda194d230d4a131569d4d5509d7416aaf2401b09148a4` |
| `tests/core/skills/test_loader.py` | `a4c3538b018059c2b1329349448cc776a59cc6bc` | `319d6f3d5f17b6f71b0559215beaf702f121313d` | `0774eb009d8e0843228d410708e97beccad13824067f695483a3ffc255695f46` |
| `tests/core/routing/test_skill_governance.py` | `904131f64297fa14b12fa18986503e55f4b88b1e` | `5892a168df6da004429f1c0c918cb8efa78af370` | `fb47956dcbb3532a99e7e5d511e887114990fc7686e2faacf479b85b9dbb2229` |
| `tests/unit/core/routing/test_matcher_rewarm.py` | `d103d9123f38551b76186807dede43f9eebd0f9d` | same | `ea1715b47b3f8f8696a8027ccaf367cc64bba7c0bd28c35a47ef6d2c33d3a329` |
| `tests/core/routing/test_demo_skills.py` | `da22f966ecfae8acea956f44bb95ea0761294ba1` | same | `b9e6e2db327170c53349c941b00ca4f76364c7049ecd568e5b3e99644ee35400` |
| `CHANGELOG.md` | `7aeaa6ef50ce13870a6ab1d1560114b03e06720a` | `b1f089d62b3faeb162e75c3ff2307d1b573c37a9` | `8bb84cd16abbe41ce28f648b4fcaa0fe49dd817921b64520076d18787e3f17fe` |

[executed] `src/vibesop/core/config/manager.py` blob `8bb2bdedc1484c331d9f8a884d80d21001635b1a` is unchanged from the parent. `load_registry` still caches under `_registry` and returns that object on the second call.

## What this gate ran

Runner: `UV_NO_SYNC=1 uv run --no-sync --extra dev` in the post snapshot. [executed] Interpreter `/private/tmp/vibesop-opt-20261009/snapshots/B2-grok-post/.venv/bin/python3`, CPython 3.12.13. `vibesop.__file__` is `.../B2-grok-post/src/vibesop/__init__.py`. Pytest is that venv's pytest. A global pytest exists at `/Users/huchen/Projects/vibesop-py/.venv/bin/pytest` and was not invoked. System `python3` has no `vibesop` module.

| Check | Result |
|---|---|
| pytest, five focused files, `-p no:cacheprovider` | [executed] exit 0, **121 passed** in 4.74s |
| `ruff check --no-cache` on the 8 changed files | [executed] exit 0, all checks passed |
| `ruff format --check --no-cache` on those 8 | [executed] exit 0, 8 files already formatted |
| `basedpyright --level error` on the 5 source files | [executed] exit 0, 0 errors, 0 warnings, 0 notes |
| independent probe | [executed] exit 0, 13/13 PASS |
| `scripts/eval_routing.py --hermetic --check` | [executed] exit 0, **59 matched, new-fails 0, drift 0, known-fails 6** |

Raw files: `/tmp/vibesop-opt-20261009/probes-grok-b2-post/` (`pytest.txt`, `ruff-check.txt`, `ruff-format.txt`, `pyright.txt`, `probe-stdout.txt`, `hermetic.txt`, `post-head-diff.patch`, `blob-map.json`, `grok_b2_post_probe.py`).

The five pytest paths were `tests/unit/core/routing/test_candidate_manager.py`, `tests/core/skills/test_loader.py`, `tests/core/routing/test_skill_governance.py`, `tests/unit/core/routing/test_matcher_rewarm.py`, `tests/core/routing/test_demo_skills.py`.

## Producer probes

All 13 used the committed package. Governance, scope, lifecycle, owner hash, delete, same-mtime body, external pack, and explicit reload went through `SkillConfigManager.set_enabled` / `set_scope` / `set_lifecycle` / `update_skill_config` / `delete_skill_config` and `UnifiedRouter.route` / `reload_candidates`, or through `CandidateManager.get_cached_candidates` / `reload` on a strict loader. Work directory was `/tmp/vibesop-opt-20261009/probes-grok-b2-post/work`.

[executed]

- Armed 5s gate, then `set_enabled(False)`: next `route()` drops `gov-skill`. Disk `candidates_v2.json` is schema 5, hash equals the live fingerprint, skill absent. A new router serves an injected `disk-sentinel` and leaves the cache-file mtime unchanged. `set_enabled(True)` brings the skill back.
- `set_scope("project")` updates the hot candidate `scope` and the skill stays routable in its own project. `set_lifecycle("archived")` removes it from the hot pool and from `route()`.
- `update_skill_config` with this loader's `project_hash` keeps the skill. A foreign `evaluation_context.project_hash` removes it from the hot pool, a strict `SkillLoader.discover_all()`, and `route()`.
- `metadata.project_hash` with no `evaluation_context` has the same hide behavior, and `get_skill_config().evaluation_context["project_hash"]` is that foreign value.
- `delete_skill_config` restores the default routable skill.
- Same-mtime `SKILL.md` edit, production `time.monotonic`, interval armed: immediate `route()` still returns `Body ONE`. After `sleep(5.2)` it returns `Body TWO`, and `get_skill_loader().get_skill()` agrees. `reload_candidates()` while the interval is armed returns `Body THREE` and the disk entry stores that body under the recomputed hash. `_RELOAD_CHECK_INTERVAL` is `5.0`.
- Same-mtime `auto-config.yaml` `enabled: false` hides the skill on the next route. `discovery_skill_files()` equals `discovery_input_files(discovery_search_paths())` (26 files on that router). `project/skills` is one of those roots and a skill that lives only there is in the pool. `auto-config.yaml` and `registry.yaml` are outside the skill-YAML name set. Registry byte edits still change the fingerprint.
- `ExternalSkillLoader.clear_cache()` re-reads a preserved-mtime description (`Ext ONE` stays cached, then `Ext TWO` after clear). Through `UnifiedRouter`, the same external file moves from `Ext TWO` to `Ext THREE` only after the interval clock advances 5.1s; the +1s route still serves `Ext TWO`.
- Order on `reload()`: `invalidate_discovery_cache` runs while the parsed cache is full, then the cache and external cache are empty, then `discover_all` runs on an empty cache and reads `Order TWO`, then `_save_to_disk_cache` writes `Order TWO`. A warm external cache survives `clear_cache()` plus `discover_all(force_reload=True)` (`Ext old` kept). `invalidate_discovery_cache()` then loads `Ext new`.
- Unchanged config bytes: 25 `get_cached_candidates()` calls, `yaml.safe_load` count 0. A `usage_stats` write leaves the fingerprint and the pool body unchanged. The next check parses YAML once; the check after that adds no further parse.
- Missing config projects `b"absent"`. `skills` as a list projects `b"skills-not-map:list"`. Corrupt YAML projects a `raw\0` marker, a same-mtime rewrite moves that marker, and `get_skill_config` stays fail-open (`enabled is True`).
- Schema v3 and v4 disk entries with a matching `paths_hash` are rejected by `_load_from_disk_cache`.
- `reload()` bumps `index_cache_epoch` from 0 to 1. `try_index_layer` drops a dict stamped with the old epoch.
- `set_lifecycle("deprecated")`: skill remains in `get_cached_candidates()`, `route("!depr-skill")` does not select it, `filter_routable` drops it, and the deprecated-warning list is empty.
- `ConfigManager.load_registry`: second call is the same object and does not call `YAML.load` again; `force_reload=True` parses once more. Registry file was only read.

Labeled hash framing: `_hash_labeled` of path `ab` + payload `c` differs from path `a` + payload `bc`. [executed]

## Prior approvals and Docker logs

[inspected] `B2-kimi-glm-pre-report.md` verdict is **APPROVE**. [inspected] `B2-glm-cross-report.md` verdict is **APPROVE**. Both name the same patch SHA256 and 89405 bytes. This gate does not use those verdicts as its evidence.

[inspected] Cross-review session log `/tmp/vibesop-opt-20261009/logs/B2-glm-cross.jsonl`: Claude Code `2.1.153`, init `model` `GLM-5.3`, assistant messages `model` `GLM-5.3`, result `modelUsage` key `GLM-5.3` only (input 123931, output 41350), result subtype `success`. The one `claude-sonnet` occurrence is the source string `claude-sonnet-4-6` inside a read of `config_manager.py`. Identity receipts say client config plus `modelUsage`, and they do not claim a provider server attestation. This gate did not call a model provider. The cross reviewer is Claude Code with backend GLM-5.3.

[inspected] Docker, not re-run:

- `logs/B2-glm-target-container.log` and `.result.json`: image `vibesop-next-val:node24`, exit 1, 501.21s, patch SHA matches. Failure is `numpy==2.5.2` wheel extract / network timeout while installing dependencies. The log has no pytest session and no passed count. That first dependency failure stands.
- `logs/B2-glm-target-retry-container.log` and `.result.json`: image `vibesop-opt-depcache:20261009`, exit 0, 4.1s, same patch SHA, same five pytest paths. Log body: install `vibesop==8.5.0` from `file:///repo`, then **121 passed in 1.58s**.

## Findings

Factual unless marked inference. None of these block the commit.

1. **[P3, factual] Content freshness stays on a 5 second window.** Immediate route after a same-mtime body edit served the previous description. The route after a real 5.2 second wait served the new description. Governance (`enabled`, `scope`, `lifecycle`, owner hash) changed the next route while that window was armed. Changelog and `_RELOAD_CHECK_INTERVAL = 5.0` say this.

2. **[P3, factual mechanism; large-universe timing is not this gate's measurement]** The deep check hashes file bytes (`_compute_paths_hash` via `discovery_input_files`, registry bytes, and deep `auto-config.yaml` projection). On a 40-file temp tree: governance token 0.09 ms, mtime walk 3.12 ms, content hash 5.36 ms. On this repo's `core/skills` only (23 discovery files): mtime 1.73 ms, hash 2.98 ms. [inference] A router whose roots include the full builtin set and user skill homes will spend more than that; the GLM cross report's ~180 ms figure is their measurement of a larger universe, and this gate did not repeat that walk. Hot path cost stays the governance token. The 5 second gate is what keeps the byte hash off every route.

3. **[P3, factual] Disk hits still clear parsed caches and bump the index epoch before the lookup.** `_cached_reload_locked` always calls `_invalidate_discovery_caches()` and `_bump_index_cache_epoch()` before `_load_from_disk_cache`. The sentinel hit above still came from disk (mtime unchanged), so the extra clear did not turn that hit into a rescan. Extra work, stale data not reintroduced.

4. **[P3, factual, pre-existing shape]** `filter_routable` appends a deprecated warning only after `SkillLifecycleManager.is_routable`, and `is_routable` is ACTIVE-only. A deprecated skill stayed in the discovery pool, was not routed, and produced an empty warning list. Archived skills are removed earlier by the loader. The warning branch stays unreachable.

5. **[Info, factual] Registered legacy cache is unchanged.** `ConfigManager.load_registry` is the same parent blob. A second call reused the in-memory registry. `SkillManager.reload_skills` still calls `loader.clear_cache()`, and that plus `discover_all(force_reload=True)` kept a warm external description. Candidate reload calls `invalidate_discovery_cache()` first, which did drop that external cache. `_registry_files` still documents the `load_registry` cache as audit-only.

6. **[P2, inspected, not executed as a fault]** `discovery_input_files` catches `OSError` around `root.rglob(...)`, which returns a generator. An `OSError` raised while iterating that generator still propagates. The same shape exists for the deep `auto-config.yaml` / `registry.yaml` walks. This matches the pre-fix walk. It fails loudly. It does not serve a stale fingerprint.

7. **[Info, inspected]** `_parse_config_bytes` decodes UTF-8, then the preferred locale, without the old non-UTF-8 warning from `read_text_with_fallback`. Behavior of the governance marker is covered by the corrupt-YAML probe. The missing warning is observability.

## Limits

- This gate ran on macOS, CPython 3.12.13. Native Windows 3.12/3.13 and wheel CI are still pending. This report is not Windows proof. No GitHub API was called.
- Docker was not re-run. The 121 container pass is the retry log above. The earlier node24 log failed in dependency install before tests.
- GLM-5.3 is the Claude Code session's declared model and `modelUsage` key. No provider server attestation was added here.
- Hermetic 59 / 6 known-fails / 0 drift was re-run on this commit and matched the baseline at `tests/benchmark/routing_baseline.json`. The six known misses are the same fallback and keyword pairs already in that baseline (three `deep-diagnosis-optimization`, one `slash-evaluate`, `session-end`, `instinct`).
- An early probe draft mis-counted YAML parses by hashing before the spy, read `get_skill_loader()` before the first route, and inserted a bare object into the external cache. Those were harness errors. The retained `probe-stdout.txt` is the corrected 13/13 run.

## Verdict

**APPROVE.** Commit `7d1160f0c22375c85505e12c37b1dc3a6e0ce6da` is the approved 89405-byte patch. Hot and fresh consumers drop disabled, archived, and foreign-owner skills; same-mtime body edits refresh after the declared 5 second interval and on explicit reload; the saved fingerprint is written only after the parsed loader and external caches are cleared; unchanged config bytes do not re-parse; `usage_stats` does not move the pool. Schema v3/v4 entries are rejected. The legacy `load_registry` cache and the `clear_cache` external-cache contract stay as registered. Focused tests, ruff, error-level basedpyright, and the hermetic baseline are green on this tree. Windows CI remains outstanding, and this commit does not close the batch.
